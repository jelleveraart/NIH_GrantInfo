import csv
import sys
import time
import requests

API_URL = "https://api.reporter.nih.gov/v2/projects/search"


def fetch_grant_history(core_project_num, page_size=100, pause=1.0, max_pages=50):
    """
    Fetch all fiscal-year records for a given NIH grant.
    Uses the 'project_nums' criterion, guards against runaway loops,
    and filters client-side to keep only exact core-number matches.
    """
    all_results = []
    offset = 0
    page = 0

    while True:
        page += 1
        if page > max_pages:
            print(f"  Reached max_pages ({max_pages}); stopping to avoid runaway loop.")
            break

        payload = {
            "criteria": {"project_nums": [core_project_num]},
            "include_fields": [
                "ApplId",
                "ProjectNum",
                "CoreProjectNum",
                "FiscalYear",
                "AwardAmount",         # total cost
                "DirectCostAmt",       # direct costs
                "IndirectCostAmt",     # indirect costs
                "ProjectTitle",
                "Organization",
                "ContactPiName",
                "AwardNoticeDate",
                "ProjectStartDate",
                "ProjectEndDate",
                "AgencyIcAdmin",       # administering IC (funding agency)
            ],
            "offset": offset,
            "limit": page_size,
            "sort_field": "fiscal_year",
            "sort_order": "asc",
        }

        print(f"  Requesting page {page} (offset={offset})...", flush=True)
        try:
            resp = requests.post(API_URL, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            print("  Request timed out. The API may be slow or unreachable.")
            break
        except requests.exceptions.RequestException as e:
            print(f"  Request failed: {e}")
            break

        data = resp.json()
        results = data.get("results", [])
        total = data.get("meta", {}).get("total", 0)

        print(f"    -> got {len(results)} records (reported total: {total})", flush=True)

        # SAFETY GUARD: a single grant's history is small.
        if total > 1000:
            print(
                f"  ⚠️  ERROR: Query matched {total:,} records — far too many "
                f"for a single grant. Skipping '{core_project_num}'."
            )
            return []

        all_results.extend(results)
        offset += page_size

        if not results or offset >= total:
            break

        time.sleep(pause)

    # CLIENT-SIDE FILTER: keep only exact core-number matches.
    filtered = [
        r for r in all_results
        if (r.get("core_project_num") or "").upper() == core_project_num.upper()
    ]
    print(
        f"  Done. Collected {len(all_results)} raw record(s); "
        f"{len(filtered)} match core '{core_project_num}' exactly."
    )
    return filtered


def derive_funding_agency(record):
    """Build a short funding-agency label like 'NIH/NIA'."""
    core = record.get("core_project_num") or ""
    ic_abbrev = ""
    if len(core) >= 5:
        ic_abbrev = core[3:5].upper()

    admin = record.get("agency_ic_admin") or {}
    admin_abbrev = admin.get("abbreviation") if isinstance(admin, dict) else None

    abbrev = admin_abbrev or ic_abbrev
    if abbrev:
        return f"NIH/{abbrev}"
    return "NIH"


def to_year_month(date_str):
    """Convert an ISO-ish date string into 'YYYY/MM'."""
    if not date_str:
        return None
    part = str(date_str)[:7]  # 'YYYY-MM'
    if len(part) == 7 and part[4] == "-":
        return part.replace("-", "/")
    return date_str


def fmt_money(val):
    """Format a number as '$1,023,343'."""
    if val is None:
        return "$0"
    return f"${val:,.0f}"


def summarize_grant(core_project_num, records):
    """Collapse fiscal-year records into a single summary dict."""
    if not records:
        return None

    records = sorted(records, key=lambda x: (x.get("fiscal_year") or 0))
    latest = records[-1]

    directs = [r.get("direct_cost_amt") for r in records if r.get("direct_cost_amt") is not None]
    indirects = [r.get("indirect_cost_amt") for r in records if r.get("indirect_cost_amt") is not None]
    totals = [r.get("award_amount") for r in records if r.get("award_amount") is not None]

    def avg(vals):
        return round(sum(vals) / len(vals)) if vals else 0

    def total(vals):
        return sum(vals) if vals else 0

    start_dates = [r.get("project_start_date") for r in records if r.get("project_start_date")]
    end_dates = [r.get("project_end_date") for r in records if r.get("project_end_date")]
    project_start = min(start_dates) if start_dates else None
    project_end = max(end_dates) if end_dates else None

    return {
        "funding_agency": derive_funding_agency(latest),
        "title": latest.get("project_title"),
        "project_pi": latest.get("contact_pi_name"),
        "application_id": core_project_num,
        "project_start_date": to_year_month(project_start),
        "project_end_date": to_year_month(project_end),
        "annual_direct_costs": avg(directs),
        "annual_indirect_costs": avg(indirects),
        "annual_total_costs": avg(totals),
        "total_direct_costs": total(directs),
        "total_indirect_costs": total(indirects),
        "total_project_costs": total(totals),
    }


FIELDNAMES = [
    "funding_agency",
    "title",
    "project_pi",
    "application_id",
    "project_start_date",
    "project_end_date",
    "annual_direct_costs",
    "annual_indirect_costs",
    "annual_total_costs",
    "total_direct_costs",
    "total_indirect_costs",
    "total_project_costs",
]

MONEY_FIELDS = {
    "annual_direct_costs", "annual_indirect_costs", "annual_total_costs",
    "total_direct_costs", "total_indirect_costs", "total_project_costs",
}


def write_summary_csv(summaries, filename):
    """Write one row per grant to a single CSV."""
    if not summaries:
        print("No summaries to write.")
        return

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for summary in summaries:
            row = dict(summary)
            for key in MONEY_FIELDS:
                row[key] = fmt_money(row.get(key))
            writer.writerow(row)

    print(f"\nWrote {len(summaries)} grant(s) to {filename}")


def print_summary_table(summaries):
    """Print all grants as a readable table in the terminal."""
    if not summaries:
        return

    print("\n=== Grant Summary Table ===")
    for i, summary in enumerate(summaries, 1):
        print(f"\n[{i}] {summary['application_id']}")
        labels = {
            "funding_agency": "Funding Agency",
            "title": "Title",
            "project_pi": "Project PI",
            "application_id": "Application ID",
            "project_start_date": "Project Start Date",
            "project_end_date": "Project End Date",
            "annual_direct_costs": "Annual Direct Costs (avg)",
            "annual_indirect_costs": "Annual Indirect Costs (avg)",
            "annual_total_costs": "Annual Total Costs (avg)",
            "total_direct_costs": "Total Direct Costs (sum)",
            "total_indirect_costs": "Total Indirect Costs (sum)",
            "total_project_costs": "Total Project Costs (sum)",
        }
        for key, label in labels.items():
            val = summary.get(key)
            if key in MONEY_FIELDS:
                print(f"    {label:<32} {fmt_money(val):>15}")
            else:
                print(f"    {label:<32} {val}")


def parse_grant_ids(args):
    """
    Accept grant IDs as separate arguments and/or comma-separated.
    e.g. 'R21AG087904,R01EB027075 R01CA245671' -> list of 3 IDs.
    """
    ids = []
    for arg in args:
        for piece in arg.split(","):
            piece = piece.strip()
            if piece:
                ids.append(piece)
    return ids


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 nih_grant_history.py <GRANT_ID>[,<GRANT_ID>,...]")
        print("Example: python3 nih_grant_history.py R21AG087904,R01EB027075,R01CA245671")
        sys.exit(1)

    grant_ids = parse_grant_ids(sys.argv[1:])
    print(f"Processing {len(grant_ids)} grant(s): {', '.join(grant_ids)}\n")

    summaries = []
    for grant_id in grant_ids:
        print(f"--- {grant_id} ---")
        raw = fetch_grant_history(grant_id)
        if not raw:
            print(f"  No records found for '{grant_id}'. Skipping.\n")
            continue
        summary = summarize_grant(grant_id, raw)
        if summary:
            summaries.append(summary)
        print()

    if not summaries:
        print("No results for any of the provided grant IDs.")
        return

    write_summary_csv(summaries, "grant_summaries.csv")
    print_summary_table(summaries)


if __name__ == "__main__":
    main()
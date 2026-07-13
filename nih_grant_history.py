import csv
import sys
import time
import datetime
import requests

API_URL = "https://api.reporter.nih.gov/v2/projects/search"


def safe_log(msg):
    """Print a message, but never crash if stdout is unavailable
    (e.g., when launched from a double-clickable .command file)."""
    try:
        print(msg, flush=True)
    except (OSError, IOError):
        pass


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
            safe_log(f"  Reached max_pages ({max_pages}); stopping to avoid runaway loop.")
            break

        payload = {
            "criteria": {"project_nums": [core_project_num]},
            "include_fields": [
                "ApplId",
                "ProjectNum",
                "CoreProjectNum",
                "SubprojectId",
                "FiscalYear",
                "AwardAmount",
                "DirectCostAmt",
                "IndirectCostAmt",
                "ProjectTitle",
                "Organization",
                "ContactPiName",
                "AwardNoticeDate",
                "ProjectStartDate",
                "ProjectEndDate",
                "AgencyIcAdmin",
            ],
            "offset": offset,
            "limit": page_size,
            "sort_field": "fiscal_year",
            "sort_order": "asc",
        }

        safe_log(f"  Requesting page {page} (offset={offset})...")
        try:
            resp = requests.post(API_URL, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            safe_log("  Request timed out. The API may be slow or unreachable.")
            break
        except requests.exceptions.RequestException as e:
            safe_log(f"  Request failed: {e}")
            break

        data = resp.json()
        results = data.get("results", [])
        total = data.get("meta", {}).get("total", 0)

        safe_log(f"    -> got {len(results)} records (reported total: {total})")

        # SAFETY GUARD: a single grant's history is small.
        if total > 1000:
            safe_log(
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
    safe_log(
        f"  Done. Collected {len(all_results)} raw record(s); "
        f"{len(filtered)} match core '{core_project_num}' exactly."
    )
    return filtered


def fetch_grants_by_pi(pi_name, page_size=100, pause=1.0, max_pages=50):
    """
    Find all grants associated with a Principal Investigator name.
    Returns a list of unique core project numbers.

    Accepts names as 'Last, First' or 'First Last'. Uses last_name /
    first_name matching, which is more reliable than 'any_name'.
    """
    pi_name = pi_name.strip()
    last_name = ""
    first_name = ""
    if "," in pi_name:
        parts = pi_name.split(",", 1)
        last_name = parts[0].strip()
        first_name = parts[1].strip()
    else:
        parts = pi_name.split()
        if len(parts) >= 2:
            first_name = parts[0].strip()
            last_name = parts[-1].strip()
        else:
            last_name = pi_name  # single token: treat as last name

    pi_criterion = {}
    if last_name:
        pi_criterion["last_name"] = last_name
    if first_name:
        pi_criterion["first_name"] = first_name

    safe_log(f"  PI search: last_name='{last_name}', first_name='{first_name}'")

    core_nums = []
    seen = set()
    offset = 0
    page = 0

    while True:
        page += 1
        if page > max_pages:
            safe_log(f"  Reached max_pages ({max_pages}); stopping PI search.")
            break

        payload = {
            "criteria": {"pi_names": [pi_criterion]},
            "include_fields": [
                "CoreProjectNum",
                "ContactPiName",
                "ProjectTitle",
                "FiscalYear",
            ],
            "offset": offset,
            "limit": page_size,
            "sort_field": "fiscal_year",
            "sort_order": "desc",
        }

        safe_log(f"  PI search page {page} (offset={offset}) for '{pi_name}'...")
        try:
            resp = requests.post(API_URL, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            safe_log("  Request timed out. The API may be slow or unreachable.")
            break
        except requests.exceptions.RequestException as e:
            safe_log(f"  Request failed: {e}")
            break

        data = resp.json()
        results = data.get("results", [])
        total = data.get("meta", {}).get("total", 0)

        safe_log(f"    -> got {len(results)} records (reported total: {total})")

        if total > 2000:
            safe_log(
                f"  ⚠️  WARNING: '{pi_name}' matched {total:,} records — "
                f"the name may be too common. Consider adding first name."
            )

        for r in results:
            core = r.get("core_project_num")
            if core and core not in seen:
                seen.add(core)
                core_nums.append(core)

        offset += page_size
        if not results or offset >= total or offset >= (max_pages * page_size):
            break

        time.sleep(pause)

    safe_log(f"  Found {len(core_nums)} unique grant(s) for PI '{pi_name}'.")
    return core_nums


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


def year_from_date(date_str):
    """Extract a 4-digit year (int) from a date string, or None."""
    if not date_str:
        return None
    s = str(date_str)[:4]
    if s.isdigit():
        return int(s)
    return None


def fmt_money(val):
    """Format a number as '$1,023,343'."""
    if val is None:
        return "$0"
    return f"${val:,.0f}"


def summarize_grant(core_project_num, records, annual_method="average",
                    project_future=False):
    """Collapse fiscal-year records into a single summary dict.

    For multi-component awards (e.g., P41, P01, U54), RePORTER returns
    both a parent/overall record AND individual subproject records for
    each fiscal year. Summing all of them double-counts the money, so
    we keep only the parent records (subproject_id is empty).

    annual_method controls how "annual" costs are computed:
      - "average": mean across all active years (default)
      - "latest":  most recent fiscal year only

    project_future controls the TOTAL columns:
      - False: totals = actual sum of awarded years (default)
      - True:  for active grants, totals = actual to date PLUS an
               extrapolation of remaining years, using the most recent
               year's costs for each remaining year.
    """
    if not records:
        return None

    def is_subproject(r):
        sid = r.get("subproject_id")
        return sid not in (None, "", "0")

    parent_records = [r for r in records if not is_subproject(r)]
    subproject_records = [r for r in records if is_subproject(r)]

    if subproject_records:
        safe_log(
            f"  Note: '{core_project_num}' is a multi-component award. "
            f"Using {len(parent_records)} parent record(s); "
            f"excluding {len(subproject_records)} subproject record(s) "
            f"to avoid double-counting."
        )

    working = parent_records if parent_records else records
    working = sorted(working, key=lambda x: (x.get("fiscal_year") or 0))
    latest = working[-1]

    directs = [r.get("direct_cost_amt") for r in working if r.get("direct_cost_amt") is not None]
    indirects = [r.get("indirect_cost_amt") for r in working if r.get("indirect_cost_amt") is not None]
    totals = [r.get("award_amount") for r in working if r.get("award_amount") is not None]

    def total(vals):
        return sum(vals) if vals else 0

    # Annual metric depends on the chosen method.
    if annual_method == "latest":
        annual_direct = latest.get("direct_cost_amt") or 0
        annual_indirect = latest.get("indirect_cost_amt") or 0
        annual_total = latest.get("award_amount") or 0
    else:  # "average" (default)
        def avg(vals):
            return round(sum(vals) / len(vals)) if vals else 0
        annual_direct = avg(directs)
        annual_indirect = avg(indirects)
        annual_total = avg(totals)

    start_dates = [r.get("project_start_date") for r in working if r.get("project_start_date")]
    end_dates = [r.get("project_end_date") for r in working if r.get("project_end_date")]
    project_start = min(start_dates) if start_dates else None
    project_end = max(end_dates) if end_dates else None

    # --- Determine active status and remaining years ---
    latest_fy = latest.get("fiscal_year")
    end_year = year_from_date(project_end)
    current_year = datetime.date.today().year

    is_active = False
    projected_years = 0
    if end_year and latest_fy:
        # Active if the project end year is beyond the latest awarded FY
        # AND the project has not already ended relative to today.
        if end_year > latest_fy and end_year >= current_year:
            is_active = True
            projected_years = end_year - latest_fy

    # --- Actual (awarded) totals ---
    actual_direct = total(directs)
    actual_indirect = total(indirects)
    actual_total = total(totals)

    # --- Projected totals (most-recent-year extrapolation) ---
    per_year_direct = latest.get("direct_cost_amt") or 0
    per_year_indirect = latest.get("indirect_cost_amt") or 0
    per_year_total = latest.get("award_amount") or 0

    projected_direct = actual_direct + per_year_direct * projected_years
    projected_indirect = actual_indirect + per_year_indirect * projected_years
    projected_total = actual_total + per_year_total * projected_years

    # --- Choose which totals to DISPLAY based on the toggle ---
    if project_future:
        disp_direct = projected_direct
        disp_indirect = projected_indirect
        disp_total = projected_total
        total_basis = "projected" if projected_years > 0 else "actual"
    else:
        disp_direct = actual_direct
        disp_indirect = actual_indirect
        disp_total = actual_total
        total_basis = "actual"

    return {
        "funding_agency": derive_funding_agency(latest),
        "title": latest.get("project_title"),
        "project_pi": latest.get("contact_pi_name"),
        "application_id": core_project_num,
        "project_start_date": to_year_month(project_start),
        "project_end_date": to_year_month(project_end),
        "is_active": "Yes" if is_active else "No",
        "annual_method": annual_method,
        "total_basis": total_basis,
        "projected_years": projected_years,
        "annual_direct_costs": annual_direct,
        "annual_indirect_costs": annual_indirect,
        "annual_total_costs": annual_total,
        "total_direct_costs": disp_direct,
        "total_indirect_costs": disp_indirect,
        "total_project_costs": disp_total,
    }


FIELDNAMES = [
    "funding_agency",
    "title",
    "project_pi",
    "application_id",
    "project_start_date",
    "project_end_date",
    "is_active",
    "annual_method",
    "total_basis",
    "projected_years",
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
        safe_log("No summaries to write.")
        return

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for summary in summaries:
            row = dict(summary)
            for key in MONEY_FIELDS:
                row[key] = fmt_money(row.get(key))
            writer.writerow(row)

    safe_log(f"\nWrote {len(summaries)} grant(s) to {filename}")


def print_summary_table(summaries):
    """Print all grants as a readable table in the terminal."""
    if not summaries:
        return

    safe_log("\n=== Grant Summary Table ===")
    for i, summary in enumerate(summaries, 1):
        safe_log(f"\n[{i}] {summary['application_id']}")
        labels = {
            "funding_agency": "Funding Agency",
            "title": "Title",
            "project_pi": "Project PI",
            "application_id": "Application ID",
            "project_start_date": "Project Start Date",
            "project_end_date": "Project End Date",
            "is_active": "Active",
            "annual_method": "Annual Method",
            "total_basis": "Total Basis",
            "projected_years": "Projected Years",
            "annual_direct_costs": "Annual Direct Costs",
            "annual_indirect_costs": "Annual Indirect Costs",
            "annual_total_costs": "Annual Total Costs",
            "total_direct_costs": "Total Direct Costs",
            "total_indirect_costs": "Total Indirect Costs",
            "total_project_costs": "Total Project Costs",
        }
        for key, label in labels.items():
            val = summary.get(key)
            if key in MONEY_FIELDS:
                safe_log(f"    {label:<32} {fmt_money(val):>15}")
            else:
                safe_log(f"    {label:<32} {val}")


def summarize_grants(grant_ids, annual_method="average", project_future=False):
    """
    Given a list of grant IDs (core project numbers), fetch and summarize
    each one. Returns (summaries, errors).
    """
    summaries = []
    errors = []
    for gid in grant_ids:
        safe_log(f"--- {gid} ---")
        raw = fetch_grant_history(gid)
        if not raw:
            errors.append(f"No records found for '{gid}'.")
            continue
        summary = summarize_grant(gid, raw, annual_method=annual_method,
                                  project_future=project_future)
        if summary:
            summaries.append(summary)
        safe_log("")
    return summaries, errors


def parse_grant_ids(args):
    """Accept grant IDs as separate arguments and/or comma-separated."""
    ids = []
    for arg in args:
        for piece in arg.split(","):
            piece = piece.strip()
            if piece:
                ids.append(piece)
    return ids


def main():
    args = sys.argv[1:]

    # Optional: --annual average|latest  (default: average)
    annual_method = "average"
    if "--annual" in args:
        idx = args.index("--annual")
        try:
            annual_method = args[idx + 1].lower()
            if annual_method not in ("average", "latest"):
                safe_log("Invalid --annual value. Use 'average' or 'latest'. Defaulting to 'average'.")
                annual_method = "average"
            del args[idx:idx + 2]
        except IndexError:
            safe_log("--annual requires a value. Defaulting to 'average'.")
            annual_method = "average"
            del args[idx:]

    # Optional: --project  -> extrapolate remaining years for active grants
    project_future = False
    if "--project" in args:
        project_future = True
        args.remove("--project")

    # Optional: --pi "Last, First"  -> search by investigator
    pi_mode = False
    pi_name = None
    if "--pi" in args:
        idx = args.index("--pi")
        try:
            pi_name = args[idx + 1]
            pi_mode = True
            del args[idx:idx + 2]
        except IndexError:
            safe_log("--pi requires a name, e.g., --pi \"Fieremans, Els\".")
            sys.exit(1)

    # Determine the list of grant IDs to summarize.
    if pi_mode:
        safe_log(f"Searching grants for PI '{pi_name}' "
                 f"[annual={annual_method}, project={project_future}]...\n")
        grant_ids = fetch_grants_by_pi(pi_name)
        if not grant_ids:
            safe_log(f"No grants found for PI '{pi_name}'.")
            return
        safe_log(f"\nSummarizing {len(grant_ids)} grant(s) found for '{pi_name}'.\n")
    else:
        if not args:
            safe_log("Usage:")
            safe_log("  By grant ID:")
            safe_log("    python3 nih_grant_history.py <GRANT_ID>[,<GRANT_ID>,...] "
                     "[--annual average|latest] [--project]")
            safe_log("  By investigator:")
            safe_log("    python3 nih_grant_history.py --pi \"Last, First\" "
                     "[--annual average|latest] [--project]")
            sys.exit(1)
        grant_ids = parse_grant_ids(args)
        safe_log(f"Processing {len(grant_ids)} grant(s) "
                 f"[annual={annual_method}, project={project_future}]: "
                 f"{', '.join(grant_ids)}\n")

    summaries, errors = summarize_grants(
        grant_ids, annual_method=annual_method, project_future=project_future
    )

    for err in errors:
        safe_log(f"  {err}")

    if not summaries:
        safe_log("No results to report.")
        return

    write_summary_csv(summaries, "grant_summaries.csv")
    print_summary_table(summaries)


if __name__ == "__main__":
    main()
"""
Diagnostic script to inspect budget periods for a single NIH grant.
Helps identify why funded_years may exceed intended_years (e.g., overlapping
or duplicate budget periods in multi-component awards like P41 centers).

Usage:
    python3 test_budget.py P41EB017183
"""

import sys
import requests

API_URL = "https://api.reporter.nih.gov/v2/projects/search"


def year_from_date(date_str):
    if not date_str:
        return None
    s = str(date_str)[:4]
    return int(s) if s.isdigit() else None


def month_from_date(date_str, default=1):
    if not date_str:
        return default
    s = str(date_str)[5:7]
    return int(s) if s.isdigit() else default


def months_between(start_date, end_date):
    sy = year_from_date(start_date)
    ey = year_from_date(end_date)
    if sy is None or ey is None:
        return None
    sm = month_from_date(start_date, default=1)
    em = month_from_date(end_date, default=1)
    return (ey - sy) * 12 + (em - sm)


def date_to_month_index(date_str):
    y = year_from_date(date_str)
    if y is None:
        return None
    m = month_from_date(date_str, default=1)
    return y * 12 + m


def fetch_all(core_project_num, page_size=100, max_pages=50):
    """Fetch every record (including subprojects) for inspection."""
    all_results = []
    offset = 0
    page = 0
    while True:
        page += 1
        if page > max_pages:
            break
        payload = {
            "criteria": {"project_nums": [core_project_num]},
            "include_fields": [
                "ApplId", "ProjectNum", "CoreProjectNum", "SubprojectId",
                "FiscalYear", "AwardAmount", "DirectCostAmt", "IndirectCostAmt",
                "ProjectStartDate", "ProjectEndDate",
                "BudgetStart", "BudgetEnd",
            ],
            "offset": offset,
            "limit": page_size,
            "sort_field": "fiscal_year",
            "sort_order": "asc",
        }
        resp = requests.post(API_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        total = data.get("meta", {}).get("total", 0)
        all_results.extend(results)
        offset += page_size
        if not results or offset >= total:
            break

    # Keep only exact core-number matches (as the main tool does)
    filtered = [
        r for r in all_results
        if (r.get("core_project_num") or "").upper() == core_project_num.upper()
    ]
    return filtered


def is_subproject(r):
    sid = r.get("subproject_id")
    return sid not in (None, "", "0")


def merged_funded_months(records):
    """Union of budget-period coverage in months, merging overlaps."""
    intervals = []
    for r in records:
        s = date_to_month_index(r.get("budget_start"))
        e = date_to_month_index(r.get("budget_end"))
        if s is None or e is None or e < s:
            continue
        intervals.append((s, e))
    if not intervals:
        return None
    intervals.sort()
    merged = [list(intervals[0])]
    for s, e in intervals[1:]:
        last = merged[-1]
        if s <= last[1] + 1:
            last[1] = max(last[1], e)
        else:
            merged.append([s, e])
    return sum((e - s) for s, e in merged)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_budget.py <GRANT_ID>")
        print("Example: python3 test_budget.py P41EB017183")
        sys.exit(1)

    grant = sys.argv[1].strip()
    print(f"Fetching all records for {grant}...\n")
    records = fetch_all(grant)
    print(f"Total records retrieved (incl. subprojects): {len(records)}\n")

    # Split into parent vs. subproject
    parents = [r for r in records if not is_subproject(r)]
    subs = [r for r in records if is_subproject(r)]
    print(f"Parent (overall) records:  {len(parents)}")
    print(f"Subproject records:        {len(subs)}\n")

    # We analyze the PARENT records (what the main tool uses)
    working = sorted(parents if parents else records,
                     key=lambda x: (x.get("fiscal_year") or 0))

    print("=" * 110)
    print("PARENT RECORDS — budget periods and per-record year coverage")
    print("=" * 110)
    header = (f"{'FY':<6}{'ProjectNum':<22}{'Subproj':<9}"
              f"{'BudgetStart':<13}{'BudgetEnd':<13}"
              f"{'Months':<8}{'Years':<7}{'Award':>15}")
    print(header)
    print("-" * 110)

    total_per_record_years = 0
    for r in working:
        bs = r.get("budget_start")
        be = r.get("budget_end")
        bm = months_between(bs, be)
        yrs = max(1, round(bm / 12)) if (bm and bm > 0) else 1
        total_per_record_years += yrs
        award = r.get("award_amount")
        award_str = f"${award:,.0f}" if award is not None else "N/A"
        print(f"{str(r.get('fiscal_year')):<6}"
              f"{str(r.get('project_num')):<22}"
              f"{str(r.get('subproject_id')):<9}"
              f"{str(bs)[:10]:<13}"
              f"{str(be)[:10]:<13}"
              f"{str(bm):<8}"
              f"{yrs:<7}"
              f"{award_str:>15}")

    print("-" * 110)

    # Project period span
    starts = [r.get("project_start_date") for r in working if r.get("project_start_date")]
    ends = [r.get("project_end_date") for r in working if r.get("project_end_date")]
    proj_start = min(starts) if starts else None
    proj_end = max(ends) if ends else None
    span_months = months_between(proj_start, proj_end)
    intended_years = max(1, round(span_months / 12)) if (span_months and span_months > 0) else None

    # The two funded-years calculations for comparison
    merged_months = merged_funded_months(working)
    merged_years = max(1, round(merged_months / 12)) if (merged_months and merged_months > 0) else None

    print("\n=== SUMMARY ===")
    print(f"Project period:            {str(proj_start)[:10]} -> {str(proj_end)[:10]} "
          f"({span_months} months, ~{intended_years} years)")
    print(f"Parent records:            {len(working)}")
    print(f"funded_years (OLD method): sum of per-record years = {total_per_record_years}   "
          f"<-- this is the buggy value")
    print(f"funded_years (NEW method): merged budget coverage = {merged_years}   "
          f"({merged_months} distinct months)")
    print(f"intended_years:            {intended_years}")

    # Highlight overlaps
    print("\n=== OVERLAP CHECK ===")
    intervals = []
    for r in working:
        s = date_to_month_index(r.get("budget_start"))
        e = date_to_month_index(r.get("budget_end"))
        if s is not None and e is not None and e >= s:
            intervals.append((s, e, r.get("fiscal_year"), r.get("project_num")))
    intervals.sort()
    overlaps_found = False
    for i in range(1, len(intervals)):
        prev = intervals[i - 1]
        cur = intervals[i]
        if cur[0] <= prev[1]:  # overlap
            overlaps_found = True
            print(f"  OVERLAP: FY{prev[2]} ({prev[3]}) ends month {prev[1]} "
                  f"but FY{cur[2]} ({cur[3]}) starts month {cur[0]}")
    if not overlaps_found:
        print("  No overlapping budget periods detected among parent records.")

    # Also show subprojects in case any leaked through
    if subs:
        print("\n=== SUBPROJECT RECORDS (excluded from calculations) ===")
        for r in subs[:20]:
            print(f"  FY{r.get('fiscal_year')} | subproj={r.get('subproject_id')} | "
                  f"{r.get('project_num')} | "
                  f"budget {str(r.get('budget_start'))[:10]} -> "
                  f"{str(r.get('budget_end'))[:10]}")
        if len(subs) > 20:
            print(f"  ... and {len(subs) - 20} more subproject records")


if __name__ == "__main__":
    main()
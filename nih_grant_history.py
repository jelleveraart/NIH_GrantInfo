import csv
import sys
import time
import datetime
import re
import requests

API_URL = "https://api.reporter.nih.gov/v2/projects/search"


def safe_log(msg):
    """Print a message, but never crash if stdout is unavailable."""
    try:
        print(msg, flush=True)
    except (OSError, IOError):
        pass


# ---------------------------------------------------------------------------
# API fetching
# ---------------------------------------------------------------------------

def fetch_grant_history(core_project_num, page_size=100, pause=1.0, max_pages=50):
    """Fetch all fiscal-year records (including subprojects) for a grant."""
    all_results = []
    offset = 0
    page = 0

    while True:
        page += 1
        if page > max_pages:
            safe_log(f"  Reached max_pages ({max_pages}); stopping.")
            break

        payload = {
            "criteria": {"project_nums": [core_project_num]},
            "include_fields": [
                "ApplId", "ProjectNum", "CoreProjectNum", "SubprojectId",
                "FiscalYear", "AwardAmount", "DirectCostAmt", "IndirectCostAmt",
                "ProjectTitle", "Organization", "ContactPiName",
                "PrincipalInvestigators", "AwardNoticeDate",
                "ProjectStartDate", "ProjectEndDate",
                "BudgetStart", "BudgetEnd", "AgencyIcAdmin",
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
            safe_log("  Request timed out.")
            break
        except requests.exceptions.RequestException as e:
            safe_log(f"  Request failed: {e}")
            break

        data = resp.json()
        results = data.get("results", [])
        total = data.get("meta", {}).get("total", 0)
        safe_log(f"    -> got {len(results)} records (reported total: {total})")

        if total > 1000:
            safe_log(f"  ⚠️  ERROR: {total:,} records — too many. Skipping.")
            return []

        all_results.extend(results)
        offset += page_size
        if not results or offset >= total:
            break
        time.sleep(pause)

    filtered = [
        r for r in all_results
        if (r.get("core_project_num") or "").upper() == core_project_num.upper()
    ]
    safe_log(f"  Done. {len(filtered)} record(s) match core '{core_project_num}'.")
    return filtered


def parse_pi_name(pi_name):
    pi_name = pi_name.strip()
    if "," in pi_name:
        last, first = pi_name.split(",", 1)
        return last.strip(), first.strip()
    parts = pi_name.split()
    if len(parts) >= 2:
        return parts[-1].strip(), parts[0].strip()
    return pi_name, ""


def pi_exact_match(record, target_last, target_first):
    tl = target_last.strip().lower()
    tf = target_first.strip().lower()
    pis = record.get("principal_investigators")
    if not isinstance(pis, list):
        return False
    for pi in pis:
        if isinstance(pi, dict):
            ln = (pi.get("last_name") or "").strip().lower()
            fn = (pi.get("first_name") or "").strip().lower()
            if ln == tl and fn == tf:
                return True
    return False


def pi_role_on_record(record, target_last, target_first):
    tl = target_last.strip().lower()
    tf = target_first.strip().lower()
    pis = record.get("principal_investigators")
    if isinstance(pis, list):
        for pi in pis:
            if isinstance(pi, dict):
                ln = (pi.get("last_name") or "").strip().lower()
                fn = (pi.get("first_name") or "").strip().lower()
                if ln == tl and fn == tf:
                    return "Contact PI" if pi.get("is_contact_pi") else "MPI"
    return ""


def fetch_pi_matched_records(pi_name, page_size=100, pause=1.0, max_pages=50):
    target_last, target_first = parse_pi_name(pi_name)
    safe_log(f"  PI search: last='{target_last}', first='{target_first}'")

    matched = []
    offset = 0
    page = 0

    while True:
        page += 1
        if page > max_pages:
            safe_log(f"  Reached max_pages ({max_pages}); stopping PI search.")
            break

        pi_criterion = {}
        if target_last:
            pi_criterion["last_name"] = target_last
        if target_first:
            pi_criterion["first_name"] = target_first

        payload = {
            "criteria": {"pi_names": [pi_criterion]},
            "include_fields": [
                "CoreProjectNum", "ProjectNum", "SubprojectId",
                "ContactPiName", "PrincipalInvestigators",
                "ProjectTitle", "FiscalYear",
            ],
            "offset": offset,
            "limit": page_size,
            "sort_field": "fiscal_year",
            "sort_order": "desc",
        }

        safe_log(f"  PI search page {page} (offset={offset})...")
        try:
            resp = requests.post(API_URL, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            safe_log("  Request timed out.")
            break
        except requests.exceptions.RequestException as e:
            safe_log(f"  Request failed: {e}")
            break

        data = resp.json()
        results = data.get("results", [])
        total = data.get("meta", {}).get("total", 0)
        safe_log(f"    -> got {len(results)} (reported total: {total})")

        for r in results:
            if pi_exact_match(r, target_last, target_first):
                matched.append(r)

        offset += page_size
        if not results or offset >= total or offset >= (max_pages * page_size):
            break
        time.sleep(pause)

    safe_log(f"  {len(matched)} record(s) match '{pi_name}' exactly.")
    return matched, target_last, target_first


# ---------------------------------------------------------------------------
# Helpers: agency, dates, money, titles
# ---------------------------------------------------------------------------

def derive_funding_agency(record):
    core = record.get("core_project_num") or ""
    ic_abbrev = core[3:5].upper() if len(core) >= 5 else ""
    admin = record.get("agency_ic_admin") or {}
    admin_abbrev = admin.get("abbreviation") if isinstance(admin, dict) else None
    abbrev = admin_abbrev or ic_abbrev
    return f"NIH/{abbrev}" if abbrev else "NIH"


def derive_award_type(core_project_num):
    core = (core_project_num or "").upper()
    m = re.match(r"^([A-Z]{1,2}\d{2})", core)
    return m.group(1) if m else ""


def normalize_title(title):
    """Normalize a title for consolidation matching:
    lowercase, replace punctuation with spaces, collapse whitespace."""
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_supplement(record):
    proj = (record.get("project_num") or "").upper()
    if "-" in proj:
        suffix = proj.rsplit("-", 1)[-1]
        return bool(re.search(r"S\d", suffix))
    return False


def is_subproject_record(r):
    sid = r.get("subproject_id")
    return sid not in (None, "", "0")


def to_year_month(date_str):
    if not date_str:
        return None
    part = str(date_str)[:7]
    if len(part) == 7 and part[4] == "-":
        return part.replace("-", "/")
    return date_str


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


def merged_funded_months(records):
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


def years_covered_by_record(record):
    bm = months_between(record.get("budget_start"), record.get("budget_end"))
    if bm is None or bm <= 0:
        return 1
    return max(1, round(bm / 12))


def record_direct(record):
    d = record.get("direct_cost_amt")
    return d if d is not None else 0


def record_indirect(record):
    i = record.get("indirect_cost_amt")
    return i if i is not None else 0


def record_total_cost(record):
    """Reliable total: prefer direct+indirect; fall back to award_amount."""
    d = record.get("direct_cost_amt")
    i = record.get("indirect_cost_amt")
    a = record.get("award_amount")
    if d is not None and i is not None:
        di = d + i
        mismatch = a is not None and abs(di - a) >= 1
        return di, mismatch
    if a is not None:
        return a, False
    return (d or 0) + (i or 0), False


def fmt_money(val):
    if val is None:
        return "$0"
    return f"${val:,.0f}"


# ---------------------------------------------------------------------------
# Core cost/year aggregation (shared)
# ---------------------------------------------------------------------------

def _aggregate_cost_years(cost_records, project_end, annual_method):
    cost_records = sorted(cost_records, key=lambda x: (x.get("fiscal_year") or 0))
    latest = cost_records[-1]

    annualized_directs, annualized_indirects, annualized_totals = [], [], []
    any_multi_year = False
    any_mismatch = False

    for r in cost_records:
        yrs = years_covered_by_record(r)
        if yrs > 1:
            any_multi_year = True
        d = record_direct(r)
        i = record_indirect(r)
        t, mism = record_total_cost(r)
        if mism:
            any_mismatch = True
        annualized_directs.append(d / yrs)
        annualized_indirects.append(i / yrs)
        annualized_totals.append(t / yrs)

    funding_model = "multi_year" if any_multi_year else "staggered"

    merged_months = merged_funded_months(cost_records)
    funded_years = (max(1, round(merged_months / 12))
                    if merged_months and merged_months > 0 else len(cost_records))

    if annual_method == "latest":
        lyrs = years_covered_by_record(latest)
        lt, _ = record_total_cost(latest)
        annual_direct = round(record_direct(latest) / lyrs)
        annual_indirect = round(record_indirect(latest) / lyrs)
        annual_total = round(lt / lyrs)
    else:
        def avg(vals):
            return round(sum(vals) / len(vals)) if vals else 0
        annual_direct = avg(annualized_directs)
        annual_indirect = avg(annualized_indirects)
        annual_total = avg(annualized_totals)

    budget_starts = [r.get("budget_start") for r in cost_records if r.get("budget_start")]
    budget_ends = [r.get("budget_end") for r in cost_records if r.get("budget_end")]
    earliest_budget_start = min(budget_starts) if budget_starts else None
    latest_budget_end = max(budget_ends) if budget_ends else None

    eff_span_months = months_between(earliest_budget_start, project_end)
    intended_years = (max(1, round(eff_span_months / 12))
                      if eff_span_months and eff_span_months > 0 else funded_years)

    if intended_years and funded_years > intended_years:
        funded_years = intended_years

    end_year = year_from_date(project_end)
    end_month = month_from_date(project_end, default=12)
    today = datetime.date.today()
    is_active = bool(end_year and (
        (end_year > today.year) or (end_year == today.year and end_month >= today.month)
    ))

    projected_years = 0
    if is_active and latest_budget_end and project_end:
        fwd = months_between(latest_budget_end, project_end)
        if fwd and fwd > 0:
            projected_years = max(0, round(fwd / 12))

    lyrs = years_covered_by_record(latest)
    lt, _ = record_total_cost(latest)
    per_year_direct = round(record_direct(latest) / lyrs)
    per_year_indirect = round(record_indirect(latest) / lyrs)
    per_year_total = round(lt / lyrs)

    return {
        "funding_model": funding_model,
        "funded_years": funded_years,
        "intended_years": intended_years,
        "is_active": is_active,
        "projected_years": projected_years,
        "annual_direct": annual_direct,
        "annual_indirect": annual_indirect,
        "annual_total": annual_total,
        "per_year_direct": per_year_direct,
        "per_year_indirect": per_year_indirect,
        "per_year_total": per_year_total,
        "any_mismatch": any_mismatch,
        "latest": latest,
    }


def _build_summary_row(core_project_num, all_unit_records, cost_records,
                       project_start, project_end, title, contact_pi,
                       record_type, role, annual_method, project_future):
    agg = _aggregate_cost_years(cost_records, project_end, annual_method)

    actual_direct = sum(record_direct(r) for r in all_unit_records)
    actual_indirect = sum(record_indirect(r) for r in all_unit_records)
    any_mismatch = agg["any_mismatch"]
    actual_total = 0
    for r in all_unit_records:
        t, mism = record_total_cost(r)
        if mism:
            any_mismatch = True
        actual_total += t

    py = agg["projected_years"]
    projected_direct = actual_direct + agg["per_year_direct"] * py
    projected_indirect = actual_indirect + agg["per_year_indirect"] * py
    projected_total = actual_total + agg["per_year_total"] * py

    if project_future:
        disp_direct, disp_indirect, disp_total = projected_direct, projected_indirect, projected_total
        total_basis = "projected" if py > 0 else "actual"
    else:
        disp_direct, disp_indirect, disp_total = actual_direct, actual_indirect, actual_total
        total_basis = "actual"

    total_source = "direct+indirect" if any_mismatch else "standard"
    if any_mismatch:
        safe_log(
            f"  Note: '{core_project_num}' ({record_type}) had record(s) where "
            f"award_amount != direct+indirect; totals derived from direct+indirect."
        )

    return {
        "funding_agency": derive_funding_agency(agg["latest"]),
        "title": title,
        "contact_pi": contact_pi,
        "application_id": core_project_num,
        "record_type": record_type,
        "role": role,
        "project_start_date": to_year_month(project_start),
        "project_end_date": to_year_month(project_end),
        "is_active": "Yes" if agg["is_active"] else "No",
        "funding_model": agg["funding_model"],
        "funded_years": agg["funded_years"],
        "intended_years": agg["intended_years"],
        "annual_method": annual_method,
        "total_basis": total_basis,
        "total_source": total_source,
        "projected_years": py,
        "annual_direct_costs": agg["annual_direct"],
        "annual_indirect_costs": agg["annual_indirect"],
        "annual_total_costs": agg["annual_total"],
        "total_direct_costs": disp_direct,
        "total_indirect_costs": disp_indirect,
        "total_project_costs": disp_total,
    }


# ---------------------------------------------------------------------------
# Summarizers
# ---------------------------------------------------------------------------

def summarize_grant(core_project_num, records, annual_method="average",
                    project_future=False, role=""):
    """Summarize the PARENT (overall) grant. Excludes subprojects."""
    if not records:
        return None

    parent_records = [r for r in records if not is_subproject_record(r)]
    working = parent_records if parent_records else records
    working = sorted(working, key=lambda x: (x.get("fiscal_year") or 0))

    regular = [r for r in working if not is_supplement(r)]
    cost_records = regular if regular else working

    starts = [r.get("project_start_date") for r in working if r.get("project_start_date")]
    ends = [r.get("project_end_date") for r in working if r.get("project_end_date")]
    project_start = min(starts) if starts else None
    project_end = max(ends) if ends else None
    if not project_end:
        be = [r.get("budget_end") for r in working if r.get("budget_end")]
        project_end = max(be) if be else None

    latest = cost_records[-1]
    return _build_summary_row(
        core_project_num, working, cost_records,
        project_start, project_end,
        latest.get("project_title"), latest.get("contact_pi_name"),
        "Parent", role, annual_method, project_future,
    )


def summarize_subproject_records(core_project_num, sub_records,
                                 annual_method="average", project_future=False,
                                 role="", parent_project_end=None):
    """Summarize a consolidated set of SUBPROJECT records (already grouped
    by normalized title). Uses the most-recent title for display."""
    if not sub_records:
        return None
    sub_records = sorted(sub_records, key=lambda x: (x.get("fiscal_year") or 0))

    regular = [r for r in sub_records if not is_supplement(r)]
    cost_records = regular if regular else sub_records

    own_ends = [r.get("project_end_date") for r in sub_records if r.get("project_end_date")]
    if own_ends:
        project_end = max(own_ends)
    elif parent_project_end:
        project_end = parent_project_end
    else:
        be = [r.get("budget_end") for r in sub_records if r.get("budget_end")]
        project_end = max(be) if be else None

    own_starts = [r.get("project_start_date") for r in sub_records if r.get("project_start_date")]
    project_start = min(own_starts) if own_starts else None

    latest = cost_records[-1]  # most-recent record -> its title is the display title
    return _build_summary_row(
        core_project_num, sub_records, cost_records,
        project_start, project_end,
        latest.get("project_title"), latest.get("contact_pi_name"),
        "Sub", role, annual_method, project_future,
    )


# ---------------------------------------------------------------------------
# High-level orchestration
# ---------------------------------------------------------------------------

def _parent_project_end(records):
    ends = [r.get("project_end_date") for r in records
            if not is_subproject_record(r) and r.get("project_end_date")]
    return max(ends) if ends else None


def summarize_by_grant_ids(grant_ids, annual_method="average",
                           project_future=False, include_subprojects=False):
    summaries, errors = [], []
    for gid in grant_ids:
        safe_log(f"--- {gid} ---")
        raw = fetch_grant_history(gid)
        if not raw:
            errors.append(f"No records found for '{gid}'.")
            continue

        parent = summarize_grant(gid, raw, annual_method=annual_method,
                                 project_future=project_future, role="")
        if parent:
            summaries.append(parent)

        if include_subprojects:
            parent_end = _parent_project_end(raw)
            # Group all subproject records by (normalized title).
            groups = {}
            for r in raw:
                if is_subproject_record(r):
                    key = normalize_title(r.get("project_title"))
                    groups.setdefault(key, []).append(r)
            for key, recs in groups.items():
                sub = summarize_subproject_records(
                    gid, recs, annual_method=annual_method,
                    project_future=project_future, role="",
                    parent_project_end=parent_end,
                )
                if sub:
                    summaries.append(sub)
        safe_log("")
    return summaries, errors


def summarize_by_pi(pi_name, annual_method="average", project_future=False):
    matched, tlast, tfirst = fetch_pi_matched_records(pi_name)
    if not matched:
        return [], [f"No grants found for PI '{pi_name}'."]

    # Parent units: core -> best role
    parent_units = {}
    # Subproject groups: (core, normalized_title) -> {records, best role}
    sub_groups = {}

    for r in matched:
        core = r.get("core_project_num")
        if not core:
            continue
        role = pi_role_on_record(r, tlast, tfirst)
        if is_subproject_record(r):
            key = (core, normalize_title(r.get("project_title")))
            if key not in sub_groups:
                sub_groups[key] = {"records": [], "role": role}
            sub_groups[key]["records"].append(r)
            if role == "Contact PI":
                sub_groups[key]["role"] = "Contact PI"
        else:
            if core not in parent_units or role == "Contact PI":
                parent_units[core] = role

    summaries, errors = [], []
    history_cache = {}

    def get_history(core):
        if core not in history_cache:
            safe_log(f"--- fetching history for {core} ---")
            history_cache[core] = fetch_grant_history(core)
        return history_cache[core]

    # Parent units
    for core, role in parent_units.items():
        raw = get_history(core)
        if not raw:
            errors.append(f"No records found for '{core}'.")
            continue
        s = summarize_grant(core, raw, annual_method=annual_method,
                            project_future=project_future, role=role)
        if s:
            summaries.append(s)

    # Subproject groups (consolidated by normalized title).
    # Option (a): summarize ONLY the records the PI matched (precise),
    # but enrich each matched record with full cost/date fields from history
    # (the PI-search records lack cost/budget fields).
    for (core, norm_title), info in sub_groups.items():
        raw = get_history(core)
        if not raw:
            errors.append(f"No records found for '{core}'.")
            continue
        parent_end = _parent_project_end(raw)

        # Identify the (subproject_id, fiscal_year) pairs the PI matched,
        # then pull the full-history records for exactly those pairs.
        matched_keys = {
            (str(r.get("subproject_id")), r.get("fiscal_year"))
            for r in info["records"]
        }
        full_records = [
            r for r in raw
            if is_subproject_record(r)
            and (str(r.get("subproject_id")), r.get("fiscal_year")) in matched_keys
        ]
        if not full_records:
            # Fallback: match by subproject_id alone if FY pairing missed.
            matched_sids = {str(r.get("subproject_id")) for r in info["records"]}
            full_records = [
                r for r in raw
                if is_subproject_record(r)
                and str(r.get("subproject_id")) in matched_sids
            ]

        s = summarize_subproject_records(
            core, full_records, annual_method=annual_method,
            project_future=project_future, role=info["role"],
            parent_project_end=parent_end,
        )
        if s:
            summaries.append(s)

    return summaries, errors


# ---------------------------------------------------------------------------
# Output columns and writers
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "funding_agency", "title", "contact_pi", "application_id",
    "record_type", "role",
    "project_start_date", "project_end_date", "is_active",
    "funding_model", "funded_years", "intended_years",
    "annual_method", "total_basis", "total_source", "projected_years",
    "annual_direct_costs", "annual_indirect_costs", "annual_total_costs",
    "total_direct_costs", "total_indirect_costs", "total_project_costs",
]

MONEY_FIELDS = {
    "annual_direct_costs", "annual_indirect_costs", "annual_total_costs",
    "total_direct_costs", "total_indirect_costs", "total_project_costs",
}


NYU_CV_FIELDNAMES = [
    "Funding Agency", "Role", "Effort %", "Project Title", "Award Type",
    "Grant #", "Project ID", "Project Start Date", "Project End Date",
    "Annual Project Direct Costs", "Annual Project Indirect Costs",
    "Annual Project Total Costs", "Total Project Direct Costs",
    "Total Project Indirect Costs", "Total Project Costs",
]


def summary_to_nyu_cv_row(summary):
    grant_num = summary.get("application_id", "")
    return {
        "Funding Agency": summary.get("funding_agency", ""),
        "Role": "",
        "Effort %": "",
        "Project Title": summary.get("title", ""),
        "Award Type": derive_award_type(grant_num),
        "Grant #": grant_num,
        "Project ID": "",
        "Project Start Date": summary.get("project_start_date", ""),
        "Project End Date": summary.get("project_end_date", ""),
        "Annual Project Direct Costs": fmt_money(summary.get("annual_direct_costs")),
        "Annual Project Indirect Costs": fmt_money(summary.get("annual_indirect_costs")),
        "Annual Project Total Costs": fmt_money(summary.get("annual_total_costs")),
        "Total Project Direct Costs": fmt_money(summary.get("total_direct_costs")),
        "Total Project Indirect Costs": fmt_money(summary.get("total_indirect_costs")),
        "Total Project Costs": fmt_money(summary.get("total_project_costs")),
    }


def write_nyu_cv_csv(summaries, filename):
    if not summaries:
        safe_log("No summaries to write.")
        return
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=NYU_CV_FIELDNAMES)
        writer.writeheader()
        for s in summaries:
            writer.writerow(summary_to_nyu_cv_row(s))
    safe_log(f"\nWrote NYU CV table ({len(summaries)} row(s)) to {filename}")


def write_summary_csv(summaries, filename):
    if not summaries:
        safe_log("No summaries to write.")
        return
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for s in summaries:
            row = dict(s)
            for key in MONEY_FIELDS:
                row[key] = fmt_money(row.get(key))
            writer.writerow(row)
    safe_log(f"\nWrote {len(summaries)} row(s) to {filename}")


def print_summary_table(summaries):
    if not summaries:
        return
    safe_log("\n=== Grant Summary Table ===")
    labels = {
        "funding_agency": "Funding Agency", "title": "Title",
        "contact_pi": "Contact PI", "application_id": "Application ID",
        "record_type": "Record Type", "role": "Role",
        "project_start_date": "Project Start Date",
        "project_end_date": "Project End Date", "is_active": "Active",
        "funding_model": "Funding Model", "funded_years": "Funded Years",
        "intended_years": "Intended Years", "annual_method": "Annual Method",
        "total_basis": "Total Basis", "total_source": "Total Source",
        "projected_years": "Projected Years",
        "annual_direct_costs": "Annual Direct Costs",
        "annual_indirect_costs": "Annual Indirect Costs",
        "annual_total_costs": "Annual Total Costs",
        "total_direct_costs": "Total Direct Costs",
        "total_indirect_costs": "Total Indirect Costs",
        "total_project_costs": "Total Project Costs",
    }
    for i, s in enumerate(summaries, 1):
        safe_log(f"\n[{i}] {s['application_id']} ({s.get('record_type')})")
        for key, label in labels.items():
            val = s.get(key)
            if key in MONEY_FIELDS:
                safe_log(f"    {label:<24} {fmt_money(val):>15}")
            else:
                safe_log(f"    {label:<24} {val}")


def parse_grant_ids(args):
    ids = []
    for arg in args:
        for piece in arg.split(","):
            piece = piece.strip()
            if piece:
                ids.append(piece)
    return ids


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    annual_method = "average"
    if "--annual" in args:
        idx = args.index("--annual")
        try:
            annual_method = args[idx + 1].lower()
            if annual_method not in ("average", "latest"):
                annual_method = "average"
            del args[idx:idx + 2]
        except IndexError:
            annual_method = "average"
            del args[idx:]

    project_future = False
    if "--project" in args:
        project_future = True
        args.remove("--project")

    include_subprojects = False
    if "--subprojects" in args:
        include_subprojects = True
        args.remove("--subprojects")

    write_nyu = False
    if "--nyu" in args:
        write_nyu = True
        args.remove("--nyu")

    pi_mode = False
    pi_name = None
    if "--pi" in args:
        idx = args.index("--pi")
        try:
            pi_name = args[idx + 1]
            pi_mode = True
            del args[idx:idx + 2]
        except IndexError:
            safe_log("--pi requires a name, e.g., --pi \"Feng, Li\".")
            sys.exit(1)

    if pi_mode:
        safe_log(f"Searching grants for PI '{pi_name}' "
                 f"[annual={annual_method}, project={project_future}]...\n")
        summaries, errors = summarize_by_pi(
            pi_name, annual_method=annual_method, project_future=project_future
        )
    else:
        if not args:
            safe_log("Usage:")
            safe_log("  By grant ID:")
            safe_log("    python3 nih_grant_history.py <GRANT_ID>[,...] "
                     "[--annual average|latest] [--project] [--subprojects] [--nyu]")
            safe_log("  By investigator:")
            safe_log("    python3 nih_grant_history.py --pi \"Last, First\" "
                     "[--annual average|latest] [--project] [--nyu]")
            sys.exit(1)
        grant_ids = parse_grant_ids(args)
        safe_log(f"Processing {len(grant_ids)} grant(s) "
                 f"[annual={annual_method}, project={project_future}, "
                 f"subprojects={include_subprojects}]: {', '.join(grant_ids)}\n")
        summaries, errors = summarize_by_grant_ids(
            grant_ids, annual_method=annual_method,
            project_future=project_future,
            include_subprojects=include_subprojects,
        )

    for err in errors:
        safe_log(f"  {err}")

    if not summaries:
        safe_log("No results to report.")
        return

    write_summary_csv(summaries, "grant_summaries.csv")
    if write_nyu:
        write_nyu_cv_csv(summaries, "NYU_CV_table.csv")
    print_summary_table(summaries)


if __name__ == "__main__":
    main()
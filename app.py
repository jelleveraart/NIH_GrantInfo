import csv
import io
import json

from flask import Flask, render_template, request, Response, jsonify

from nih_grant_history import (
    summarize_by_pi,
    summarize_by_grant_ids,
    parse_grant_ids,
    fmt_money,
    FIELDNAMES,
    MONEY_FIELDS,
    NYU_CV_FIELDNAMES,
    summary_to_nyu_cv_row,
)

app = Flask(__name__)


def normalize_annual_method(value):
    value = (value or "average").lower()
    return value if value in ("average", "latest") else "average"


def parse_bool(value):
    return str(value).lower() in ("1", "true", "yes", "on")


def run_search(search_mode, raw_input, annual_method, project_future,
               include_subprojects):
    """Dispatch to PI or grant-ID search. Returns (summaries, errors)."""
    if search_mode == "pi":
        pi_name = raw_input.strip()
        if not pi_name:
            return [], ["Please enter an investigator name."]
        return summarize_by_pi(
            pi_name, annual_method=annual_method, project_future=project_future
        )
    else:
        grant_ids = parse_grant_ids([raw_input])
        if not grant_ids:
            return [], ["No valid grant IDs found."]
        return summarize_by_grant_ids(
            grant_ids, annual_method=annual_method,
            project_future=project_future,
            include_subprojects=include_subprojects,
        )


def format_row_for_csv(row):
    """Ensure money fields are formatted as strings for CSV output.
    Rows arriving from the browser may already be formatted; this is
    idempotent because fmt_money on a string would fail, so we guard."""
    out = dict(row)
    for key in MONEY_FIELDS:
        val = out.get(key)
        if isinstance(val, (int, float)):
            out[key] = fmt_money(val)
        elif val is None:
            out[key] = "$0"
        # if it's already a formatted string (e.g. "$1,234"), leave as-is
    return out


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    raw_input = request.form.get("query", "").strip()
    search_mode = request.form.get("search_mode", "grant_id")
    annual_method = normalize_annual_method(request.form.get("annual_method"))
    project_future = parse_bool(request.form.get("project_future"))
    include_subprojects = parse_bool(request.form.get("include_subprojects"))

    if not raw_input:
        return jsonify({"error": "Please enter a search term."}), 400

    summaries, errors = run_search(
        search_mode, raw_input, annual_method, project_future,
        include_subprojects,
    )

    if not summaries and errors:
        return jsonify({"error": errors[0]}), 400

    # Full row data (all fields) is sent to the browser so it can hold the
    # complete records for selective export. Money fields are formatted for
    # display; the browser keeps these full objects and returns the selected
    # subset on download.
    # Hidden from the web table (but kept in CSV downloads):
    hidden_in_table = {
        "total_source", "role", "funding_model", "annual_method", "total_basis",
    }
    display_columns = [c for c in FIELDNAMES if c not in hidden_in_table]
    rows = []
    for s in summaries:
        row = dict(s)
        for key in MONEY_FIELDS:
            row[key] = fmt_money(row.get(key))
        rows.append(row)

    return jsonify({
        "columns": display_columns,
        "rows": rows,
        "errors": errors,
    })


@app.route("/download", methods=["POST"])
def download():
    """Standard CSV built from the SELECTED rows sent by the browser."""
    try:
        payload = request.get_json(force=True)
        rows = payload.get("rows", [])
    except Exception:
        rows = []

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(format_row_for_csv(row))

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=grant_summaries.csv"},
    )


@app.route("/download_nyu", methods=["POST"])
def download_nyu():
    """NYU CV table built from the SELECTED rows sent by the browser."""
    try:
        payload = request.get_json(force=True)
        rows = payload.get("rows", [])
    except Exception:
        rows = []

    # The NYU mapping expects numeric money values. Rows from the browser
    # have money formatted as strings (e.g. "$1,234"); convert back to numbers
    # so summary_to_nyu_cv_row can re-format consistently.
    def to_number(val):
        if isinstance(val, (int, float)):
            return val
        if isinstance(val, str):
            cleaned = val.replace("$", "").replace(",", "").strip()
            try:
                return float(cleaned) if cleaned else 0
            except ValueError:
                return 0
        return 0

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=NYU_CV_FIELDNAMES)
    writer.writeheader()
    for row in rows:
        numeric_row = dict(row)
        for key in MONEY_FIELDS:
            numeric_row[key] = to_number(row.get(key))
        writer.writerow(summary_to_nyu_cv_row(numeric_row))

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=NYU_CV_table.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
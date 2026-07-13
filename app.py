import csv
import io

from flask import Flask, render_template, request, Response, jsonify

# Reuse the existing logic from the CLI script
from nih_grant_history import (
    fetch_grant_history,
    fetch_grants_by_pi,
    summarize_grant,
    summarize_grants,
    parse_grant_ids,
    fmt_money,
    FIELDNAMES,
    MONEY_FIELDS,
)

app = Flask(__name__)


def normalize_annual_method(value):
    """Validate the annual_method form value; default to 'average'."""
    value = (value or "average").lower()
    return value if value in ("average", "latest") else "average"


def parse_bool(value):
    """Interpret a form value as a boolean."""
    return str(value).lower() in ("1", "true", "yes", "on")


def resolve_grant_ids(search_mode, raw_input):
    """
    Return (grant_ids, errors) based on the search mode.
    - 'pi': treat raw_input as an investigator name
    - otherwise: treat raw_input as one or more grant IDs
    """
    errors = []
    if search_mode == "pi":
        pi_name = raw_input.strip()
        if not pi_name:
            return [], ["Please enter an investigator name."]
        grant_ids = fetch_grants_by_pi(pi_name)
        if not grant_ids:
            errors.append(f"No grants found for PI '{pi_name}'.")
        return grant_ids, errors
    else:
        grant_ids = parse_grant_ids([raw_input])
        if not grant_ids:
            errors.append("No valid grant IDs found.")
        return grant_ids, errors


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    """Handle the form submission, return JSON with results."""
    raw_input = request.form.get("query", "").strip()
    search_mode = request.form.get("search_mode", "grant_id")
    annual_method = normalize_annual_method(request.form.get("annual_method"))
    project_future = parse_bool(request.form.get("project_future"))

    if not raw_input:
        return jsonify({"error": "Please enter a search term."}), 400

    grant_ids, resolve_errors = resolve_grant_ids(search_mode, raw_input)
    if not grant_ids:
        return jsonify({
            "error": resolve_errors[0] if resolve_errors else "Nothing to search."
        }), 400

    summaries, errors = summarize_grants(
        grant_ids, annual_method=annual_method, project_future=project_future
    )
    errors = resolve_errors + errors

    rows = []
    for s in summaries:
        row = dict(s)
        for key in MONEY_FIELDS:
            row[key] = fmt_money(row.get(key))
        rows.append(row)

    return jsonify({
        "columns": FIELDNAMES,
        "rows": rows,
        "errors": errors,
    })


@app.route("/download", methods=["POST"])
def download():
    """Regenerate results and return them as a downloadable CSV."""
    raw_input = request.form.get("query", "").strip()
    search_mode = request.form.get("search_mode", "grant_id")
    annual_method = normalize_annual_method(request.form.get("annual_method"))
    project_future = parse_bool(request.form.get("project_future"))

    grant_ids, _ = resolve_grant_ids(search_mode, raw_input)
    summaries, _ = summarize_grants(
        grant_ids, annual_method=annual_method, project_future=project_future
    )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDNAMES)
    writer.writeheader()
    for s in summaries:
        row = dict(s)
        for key in MONEY_FIELDS:
            row[key] = fmt_money(row.get(key))
        writer.writerow(row)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=grant_summaries.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
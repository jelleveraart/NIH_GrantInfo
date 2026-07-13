import csv
import io

from flask import Flask, render_template, request, Response, jsonify

# Reuse the existing logic from your CLI script
from nih_grant_history import (
    fetch_grant_history,
    summarize_grant,
    parse_grant_ids,
    fmt_money,
    FIELDNAMES,
    MONEY_FIELDS,
)

app = Flask(__name__)


def process_grants(grant_ids, annual_method="average"):
    """Fetch and summarize a list of grant IDs.
    Returns (summaries, errors)."""
    summaries = []
    errors = []
    for grant_id in grant_ids:
        try:
            raw = fetch_grant_history(grant_id)
            if not raw:
                errors.append(f"No records found for '{grant_id}'.")
                continue
            summary = summarize_grant(grant_id, raw, annual_method=annual_method)
            if summary:
                summaries.append(summary)
        except Exception as e:
            errors.append(f"Error processing '{grant_id}': {e}")
    return summaries, errors


def normalize_annual_method(value):
    """Validate the annual_method form value; default to 'average'."""
    value = (value or "average").lower()
    return value if value in ("average", "latest") else "average"


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    """Handle the form submission, return JSON with results."""
    raw_input = request.form.get("grant_ids", "").strip()
    annual_method = normalize_annual_method(request.form.get("annual_method"))

    if not raw_input:
        return jsonify({"error": "Please enter at least one grant ID."}), 400

    grant_ids = parse_grant_ids([raw_input])
    if not grant_ids:
        return jsonify({"error": "No valid grant IDs found."}), 400

    summaries, errors = process_grants(grant_ids, annual_method=annual_method)

    # Build display rows with formatted money
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
    raw_input = request.form.get("grant_ids", "").strip()
    annual_method = normalize_annual_method(request.form.get("annual_method"))

    grant_ids = parse_grant_ids([raw_input])
    summaries, _ = process_grants(grant_ids, annual_method=annual_method)

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
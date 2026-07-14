# NIH Grant Info

A tool to extract funding information for NIH grants from the
[NIH RePORTER API](https://api.reporter.nih.gov/). For each grant, it retrieves
the full fiscal-year award history and produces a clean summary of direct,
indirect, and total costs. Available as both a **command-line tool** and a
**browser-based web application**.

## Features

- Search by **grant ID** or by **investigator**
- Query one or multiple grants in a single run
- Retrieves the complete funding history for each grant via the official NIH RePORTER API
- Computes both **annual** and **lifetime (total)** direct, indirect, and total costs
- **Choose how the annual metric is computed:** average across all active years, or the most recent year only
- **Project total costs for active grants** by extrapolating remaining years
- Correctly handles **multi-component awards** (e.g., P41, P01, U54) by excluding subprojects to avoid double-counting
- Export results as a **standard CSV** or a formatted **NYU CV table**
- Web interface with a results table and download options
- Built-in safety guards against runaway API queries

## Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/)
- [`flask`](https://pypi.org/project/flask/) (for the web app)

## Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/jelleveraart/NIH_GrantInfo.git
cd NIH_GrantInfo
pip install -r requirements.txt
```

> Tip: Consider using a virtual environment:
> ```bash
> python3 -m venv venv
> source venv/bin/activate      # macOS/Linux
> pip install -r requirements.txt
> ```

## Command-Line Usage

### Search by grant ID

Run the script with one or more grant IDs. IDs can be comma-separated,
space-separated, or a mix:

```bash
# Single grant
python3 nih_grant_history.py R21AG087904

# Multiple grants
python3 nih_grant_history.py R21AG087904,R01EB027075,R01CA245671
```

### Search by investigator

Use the `--pi` flag to find all grants for a Principal Investigator (name in
`Last, First` format):

```bash
python3 nih_grant_history.py --pi "Doe, John"
```

### Options

```bash
# Annual metric: average across all active years (default) or latest year only
python3 nih_grant_history.py R21AG087904 --annual average
python3 nih_grant_history.py R21AG087904 --annual latest

# Project total costs for active grants (extrapolate remaining years)
python3 nih_grant_history.py R01EB027075 --project

# Also write the NYU CV table (NYU_CV_table.csv)
python3 nih_grant_history.py R21AG087904 --nyu

# Options can be combined
python3 nih_grant_history.py --pi "Fieremans, Els" --annual latest --project --nyu
```

By default the CLI writes `grant_summaries.csv`. Adding `--nyu` also writes
`NYU_CV_table.csv`.

### Grant ID format

Use the **core project number** — the activity code, institute code, and serial number:

- ✅ Correct: `R21AG087904`
- ❌ Incorrect: `5R21AG087904-01` (full project number with prefix/suffix)

## Web Application

A simple browser-based interface is also available.

```bash
pip install -r requirements.txt
python3 app.py
```

Then open http://127.0.0.1:5000 in your browser:

1. Use the **"Search by"** toggle to choose **Grant ID** or **Investigator**.
   - For grant ID: enter one or more core project numbers.
   - For investigator: enter the name in `Last, First` format (e.g., `Fieremans, Els`).
2. Choose the **annual metric** (average across years, or most recent year only).
3. Optionally check **"Project total costs for active grants"** to extrapolate
   remaining years for grants that have not yet ended.
4. Click **Search** to view results in a table.
5. Export the results:
   - **Download CSV** — standard summary format.
   - **Download NYU CV Table** — formatted for an NYU CV (see below).

### One-Click Launcher (macOS)

For users who prefer not to use the terminal, a double-clickable launcher is included.

1. Make the launcher executable (one-time setup):
   ```bash
   chmod +x Launch_NIH_GrantInfo.command
   ```
2. Double-click `Launch_NIH_GrantInfo.command`.
3. The app starts and your browser opens automatically to
   http://127.0.0.1:5000.

To stop the app, press `Ctrl+C` in the Terminal window or close the window.

## Output

### Standard CSV

One row per grant with the following columns:

| Column | Description |
|---|---|
| `funding_agency` | Administering agency (e.g., `NIH/NIA`) |
| `title` | Project title |
| `project_pi` | Contact Principal Investigator |
| `application_id` | Grant ID (e.g., `R21AG087904`) |
| `project_start_date` | Earliest project start (`YYYY/MM`) |
| `project_end_date` | Latest project end (`YYYY/MM`) |
| `is_active` | Whether the grant is still active (`Yes`/`No`) |
| `annual_method` | How annual costs were computed (`average` or `latest`) |
| `total_basis` | Whether totals are `actual` or `projected` |
| `projected_years` | Number of remaining years extrapolated (if projected) |
| `annual_direct_costs` | Annual direct costs |
| `annual_indirect_costs` | Annual indirect costs |
| `annual_total_costs` | Annual total costs |
| `total_direct_costs` | Total direct costs |
| `total_indirect_costs` | Total indirect costs |
| `total_project_costs` | Total project costs |

Cost values are formatted as `$1,023,343`.

### NYU CV Table

The **Download NYU CV Table** button (web) or `--nyu` flag (CLI) produces a CSV
with columns formatted for an NYU CV:

| Column | Notes |
|---|---|
| Funding Agency | e.g., `NIH/NIA` |
| Role | Left blank (fill in manually if not PI) |
| Effort % | Left blank (fill in manually) |
| Project Title | |
| Award Type | Activity code, e.g., `R21`, `R01`, `P41` |
| Grant # | e.g., `R21AG087904` |
| Project ID | Left blank |
| Project Start Date | `YYYY/MM` |
| Project End Date | `YYYY/MM` |
| Annual Project Direct Costs | |
| Annual Project Indirect Costs | |
| Annual Project Total Costs | |
| Total Project Direct Costs | |
| Total Project Indirect Costs | |
| Total Project Costs | |

## How It Works

The tool queries the NIH RePORTER `/v2/projects/search` endpoint. When searching
by grant ID, it uses the `project_nums` criterion; when searching by investigator,
it uses the `pi_names` criterion (matching on last and first name). It pages
through all fiscal-year records, filters client-side to exact matches, and
aggregates the cost data.

For **multi-component awards** (P41, P01, U54, etc.), RePORTER returns both a
parent/overall record and individual subproject records per fiscal year. The
tool keeps only the parent records to avoid double-counting costs.

### Projected totals

When projection is enabled, the tool estimates the total cost of an active grant:

1. It computes the intended project duration (in whole years) from the project
   start and end dates.
2. It counts the fiscal-year records already awarded.
3. Remaining years = intended duration − awarded records (only if the grant is
   genuinely still active, based on the end date).
4. Each remaining year is estimated using the **most recent year's** costs.

The `total_basis` and `projected_years` columns make it transparent whether a
figure is actual or projected.

## Notes & Caveats

- Costs are averaged/summed only over fiscal years with reported values, so
  years with missing cost data do not skew the results toward zero.
- Older grants may lack a direct/indirect breakdown in the RePORTER data.
- Investigator search matches on last and first name. Common names may return
  grants from multiple people sharing the same name.
- Projected totals are estimates. No-cost extensions (which extend the end date
  without new funding) may lead to over-projection in rare cases.
- The tool respects the API with a ~1 request/second pace and includes a
  safety guard that aborts if a query unexpectedly matches too many records.

## Troubleshooting

**`ModuleNotFoundError: No module named 'flask'`**
Flask isn't installed in the active Python environment. Run
`python3 -m pip install -r requirements.txt`. On machines with Anaconda, ensure
`pip` and `python3` point to the same environment (using `python3 -m pip`
guarantees this).

**`[Errno 5] Input/output error`**
This can occur when the app is launched from the one-click `.command` file.
The code wraps all console output in a safe logging helper (`safe_log`) that
prevents this from crashing the app, so running the latest version resolves it.

**`127.0.0.1 refused to connect` / `ERR_CONNECTION_REFUSED`**
The Flask server may still be starting, or it crashed on launch. Check the
Terminal window for errors, or run `python3 app.py` manually to see the output.
Refreshing the browser after a few seconds often resolves a timing issue.

**No grants found for an investigator**
Enter the name in `Last, First` format (e.g., `Fieremans, Els`). The search
matches on last and first name.

## Data Source

Funding data is retrieved from the publicly available
[NIH RePORTER API](https://api.reporter.nih.gov/). Please review NIH RePORTER's
terms of use for appropriate usage.

## License

MIT License — see [LICENSE](LICENSE) for details.
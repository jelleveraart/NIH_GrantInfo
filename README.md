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
- Correctly handles **multi-component awards** (e.g., P41, P01, U54) by excluding subprojects to avoid double-counting
- Outputs a tidy CSV with one row per grant
- Web interface with a results table and CSV download
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

Use the `--pi` flag to find all grants for a Principal Investigator:

```bash
# Investigator name in "Last, First" format
python3 nih_grant_history.py --pi "Fieremans, Els"

# Combine with the annual metric option
python3 nih_grant_history.py --pi "Fieremans, Els" --annual latest
```

### Annual metric option

Use the `--annual` flag to control how annual costs are computed:

```bash
# Average across all active years (default)
python3 nih_grant_history.py R21AG087904 --annual average

# Most recent year only
python3 nih_grant_history.py R21AG087904 --annual latest
```

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
2. Choose the **annual metric** using the radio buttons:
   - *Average across all active years*
   - *Most recent year only*
3. Click **Search** to view results in a table.
4. Click **Download CSV** to export them.

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

One row per grant with the following columns:

| Column | Description |
|---|---|
| `funding_agency` | Administering agency (e.g., `NIH/NIA`) |
| `title` | Project title |
| `project_pi` | Contact Principal Investigator |
| `application_id` | Grant ID (e.g., `R21AG087904`) |
| `project_start_date` | Earliest project start (`YYYY/MM`) |
| `project_end_date` | Latest project end (`YYYY/MM`) |
| `annual_method` | How annual costs were computed (`average` or `latest`) |
| `annual_direct_costs` | Annual direct costs |
| `annual_indirect_costs` | Annual indirect costs |
| `annual_total_costs` | Annual total costs |
| `total_direct_costs` | Sum of direct costs across all years |
| `total_indirect_costs` | Sum of indirect costs across all years |
| `total_project_costs` | Sum of total costs across all years |

Cost values are formatted as `$1,023,343`.

## How It Works

The tool queries the NIH RePORTER `/v2/projects/search` endpoint. When searching
by grant ID, it uses the `project_nums` criterion; when searching by investigator,
it uses the `pi_names` criterion (matching on last and first name). It pages
through all fiscal-year records, filters client-side to exact matches, and
aggregates the cost data.

For **multi-component awards** (P41, P01, U54, etc.), RePORTER returns both a
parent/overall record and individual subproject records per fiscal year. The
tool keeps only the parent records to avoid double-counting costs.

## Notes & Caveats

- Costs are averaged/summed only over fiscal years with reported values, so
  years with missing cost data do not skew the results toward zero.
- Older grants may lack a direct/indirect breakdown in the RePORTER data.
- Investigator search matches on last and first name. Common names may return
  grants from multiple people sharing the same name.
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
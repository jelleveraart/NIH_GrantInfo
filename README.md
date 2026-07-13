# NIH Grant Info

A command-line tool to extract funding information for NIH grants from the
[NIH RePORTER API](https://api.reporter.nih.gov/). For each grant, it retrieves
the full fiscal-year award history and produces a clean summary of direct,
indirect, and total costs.

## Features

- Query one or multiple grants by project ID in a single run
- Retrieves the complete funding history for each grant via the official NIH RePORTER API
- Computes both **annual averages** and **lifetime sums** of direct, indirect, and total costs
- Outputs a tidy CSV (`grant_summaries.csv`) with one row per grant
- Prints a readable summary table to the terminal
- Built-in safety guards against runaway API queries

## Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/)

## Installation

Clone the repository and install the dependency:

```bash
git clone https://github.com/jelleveraart/NIH_GrantInfo.git
cd NIH_GrantInfo
pip install requests
```

> Tip: Consider using a virtual environment:
> ```bash
> python3 -m venv venv
> source venv/bin/activate      # macOS/Linux
> pip install requests
> ```

## Usage

Run the script with one or more grant IDs. IDs can be comma-separated,
space-separated, or a mix:

```bash
# Single grant
python3 nih_grant_history.py R21AG087904

# Multiple grants (comma-separated)
python3 nih_grant_history.py R21AG087904,R01EB027075,R01CA245671

# Multiple grants (space-separated)
python3 nih_grant_history.py R21AG087904 R01EB027075 R01CA245671
```

### Grant ID format

Use the **core project number** — the activity code, institute code, and serial number:

- ✅ Correct: `R21AG087904`
- ❌ Incorrect: `5R21AG087904-01` (full project number with prefix/suffix)

## Output

### CSV file: `grant_summaries.csv`

One row per grant with the following columns:

| Column | Description |
|---|---|
| `funding_agency` | Administering agency (e.g., `NIH/NIA`) |
| `title` | Project title |
| `project_pi` | Contact Principal Investigator |
| `application_id` | Grant ID (e.g., `R21AG087904`) |
| `project_start_date` | Earliest project start (`YYYY/MM`) |
| `project_end_date` | Latest project end (`YYYY/MM`) |
| `annual_direct_costs` | Average direct costs across all years |
| `annual_indirect_costs` | Average indirect costs across all years |
| `annual_total_costs` | Average total costs across all years |
| `total_direct_costs` | Sum of direct costs across all years |
| `total_indirect_costs` | Sum of indirect costs across all years |
| `total_project_costs` | Sum of total costs across all years |

Cost values are formatted as `$1,023,343`.


## How It Works

The tool queries the NIH RePORTER `/v2/projects/search` endpoint using the
`project_nums` criterion, pages through all fiscal-year records for each grant,
filters client-side to exact core-number matches, and aggregates the cost data.

## Notes & Caveats

- Costs are averaged/summed only over fiscal years with reported values, so
  years with missing cost data do not skew the results toward zero.
- Older grants may lack a direct/indirect breakdown in the RePORTER data.
- The tool respects the API with a ~1 request/second pace and includes a
  safety guard that aborts if a query unexpectedly matches too many records.

## Data Source

Funding data is retrieved from the publicly available
[NIH RePORTER API](https://api.reporter.nih.gov/). Please review NIH RePORTER's
terms of use for appropriate usage.

## License

MIT License — see [LICENSE](LICENSE) for details.
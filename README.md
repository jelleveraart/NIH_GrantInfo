# NIH Grant Info

A tool to extract funding information for NIH grants from the
[NIH RePORTER API](https://api.reporter.nih.gov/). For each grant, it retrieves
the full fiscal-year award history and produces a clean summary of direct,
indirect, and total costs. Available as both a **command-line tool** and a
**browser-based web application**.

## Features

- Query one or multiple grants by project ID in a single run
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

Run the script with one or more grant IDs. IDs can be comma-separated,
space-separated, or a mix:

```bash
# Single grant
python3 nih_grant_history.py R21AG087904

# Multiple grants
python3 nih_grant_history.py R21AG087904,R01EB027075,R01CA245671
```

### Annual metric option

Use the `--annual` flag to control how annual costs are computed:

```bash
# Average across all active years (default)
python3 nih_grant_history.py R21AG087904 --annual average

# Most recent year only
python3 nih_grant_history.py R21AG087904 --annual latest
```
MIT License — see [LICENSE](LICENSE) for details.
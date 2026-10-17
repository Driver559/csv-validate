# csv-validate

A small, dependency-light command-line tool that checks a CSV file against simple rules and writes an error report with the line, column and reason of every problem. Runs headless, so it works in CI. Exit code is 1 when errors are found.

Checks: required values, unique values, regex patterns, allowed values, date formats, numbers with min/max, length limits, line breaks, control characters, leading/trailing spaces, duplicate rows, UTF-8 byte order mark, invalid encoding.

## Install

```
pip install -r requirements.txt
```

## Use

```
python csv_validate.py sample_customers.csv --rules rules.example.yaml --report report.md
```

The report can be Markdown (`.md`) or CSV (`.csv`). Exit codes: `0` no errors, `1` errors found, `2` usage or file problem.

### Rules file

```yaml
no_duplicate_rows: true
columns:
  id:    {required: true, unique: true, regex: '\d+'}
  email: {required: true, regex: '[^@\s]+@[^@\s]+\.[A-Za-z]{2,}'}
  signup_date: {date_format: '%Y-%m-%d'}
  amount: {type: float, min: 0}
  country: {allowed: [PL, UA, DE]}
```

### In CI (GitHub Actions)

```yaml
- run: pip install -r requirements.txt
- run: python csv_validate.py data/*.csv --rules rules.yaml --report validation.md
```

## Need more?

I also publish a paid toolkit that adds a cleaning tool (trim, normalize dates and numbers, remove duplicates, with a change log), a file merger for CSV/Excel, a near-duplicate finder, tests and documentation: https://driveagent.gumroad.com

## License

MIT

#!/usr/bin/env python3
"""Validate CSV files against simple rules and write an error report.

Usage:
    python csv_validate.py data.csv --rules rules.yaml --report report.md
    python csv_validate.py a.csv b.csv --rules rules.yaml --report errors.csv

Exit code: 0 = no errors, 1 = errors found, 2 = usage or file problem.
Runs headless (no GUI), so it can be called from CI.
"""
import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def load_rules(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_table(path, encoding="utf-8-sig", sep=","):
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding=encoding, sep=sep)


def check_value(col, value, rule):
    """Return a list of (rule_name, message) problems for one cell."""
    problems = []
    v = value
    empty = v.strip() == ""
    if rule.get("required") and empty:
        problems.append(("required", "value is missing"))
        return problems
    if empty:
        return problems
    if "\n" in v or "\r" in v:
        problems.append(("line_break", "contains a line break"))
    if CONTROL_CHARS.search(v):
        problems.append(("control_chars", "contains control characters"))
    if rule.get("no_edge_spaces", True) and v != v.strip():
        problems.append(("edge_spaces", "has leading or trailing spaces"))
    if "max_length" in rule and len(v) > rule["max_length"]:
        problems.append(("max_length", f"longer than {rule['max_length']} characters"))
    if "min_length" in rule and len(v) < rule["min_length"]:
        problems.append(("min_length", f"shorter than {rule['min_length']} characters"))
    if "regex" in rule and not re.fullmatch(rule["regex"], v.strip()):
        problems.append(("regex", f"does not match pattern {rule['regex']}"))
    if "allowed" in rule and v.strip() not in [str(a) for a in rule["allowed"]]:
        problems.append(("allowed", "not one of the allowed values"))
    if "date_format" in rule:
        try:
            datetime.strptime(v.strip(), rule["date_format"])
        except ValueError:
            problems.append(("date_format", f"not a valid date in format {rule['date_format']}"))
    if rule.get("type") in ("int", "float", "number"):
        try:
            num = int(v) if rule["type"] == "int" else float(v)
            if "min" in rule and num < rule["min"]:
                problems.append(("min", f"below minimum {rule['min']}"))
            if "max" in rule and num > rule["max"]:
                problems.append(("max", f"above maximum {rule['max']}"))
        except ValueError:
            problems.append(("type", f"not a valid {rule['type']}"))
    return problems


def validate_file(path, rules, encoding="utf-8-sig", sep=","):
    """Return a list of error dicts for one file."""
    errors = []
    name = Path(path).name

    def add(row, column, rule, value, message):
        errors.append({"file": name, "row": row, "column": column, "rule": rule, "value": value, "message": message})

    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        add("", "", "bom", "", "file starts with a UTF-8 byte order mark (BOM)")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        add("", "", "encoding", "", f"file is not valid UTF-8: {e.reason}")
        encoding = "latin-1"
    try:
        df = read_table(path, encoding=encoding, sep=sep)
    except Exception as e:  # noqa: BLE001 - report any parse failure
        add("", "", "parse", "", f"could not read the file: {e}")
        return errors

    columns = rules.get("columns", {})
    for col in columns:
        if col not in df.columns:
            add("", col, "missing_column", "", "column not found in file")
    unique_seen = {}
    for idx, row in df.iterrows():
        line = idx + 2  # header is line 1
        for col, rule in columns.items():
            if col not in df.columns:
                continue
            value = row[col]
            for rname, msg in check_value(col, value, rule):
                add(line, col, rname, value, msg)
            if rule.get("unique") and value.strip() != "":
                key = (col, value.strip())
                if key in unique_seen:
                    add(line, col, "unique", value, f"duplicate of line {unique_seen[key]}")
                else:
                    unique_seen[key] = line
    if rules.get("no_duplicate_rows", False):
        dups = df[df.duplicated(keep="first")]
        for idx in dups.index:
            add(idx + 2, "", "duplicate_row", "", "identical to an earlier row")
    return errors


def write_report(errors, path, files):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        cols = ["file", "row", "column", "rule", "value", "message"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(errors)
        return
    by_rule = {}
    for e in errors:
        by_rule[e["rule"]] = by_rule.get(e["rule"], 0) + 1
    lines = ["# CSV validation report", "", f"Files checked: {', '.join(Path(f).name for f in files)}",
             f"Errors found: {len(errors)}", ""]
    if by_rule:
        lines += ["## Summary by rule", "", "| Rule | Count |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(by_rule.items(), key=lambda kv: -kv[1])]
        lines += ["", "## All errors", "", "| File | Line | Column | Rule | Value | Message |", "|---|---|---|---|---|---|"]
        for e in errors:
            val = str(e["value"]).replace("|", "\\|").replace("\n", " ")[:40]
            lines.append(f"| {e['file']} | {e['row']} | {e['column']} | {e['rule']} | {val} | {e['message']} |")
    else:
        lines.append("No errors found.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="CSV file(s) to check")
    ap.add_argument("--rules", required=True, help="YAML rules file")
    ap.add_argument("--report", default="validation_report.md", help="report path (.md or .csv)")
    ap.add_argument("--sep", default=",", help="column separator (default ,)")
    args = ap.parse_args(argv)
    try:
        rules = load_rules(args.rules)
    except Exception as e:  # noqa: BLE001
        print(f"Could not read rules file: {e}", file=sys.stderr)
        return 2
    errors = []
    for f in args.files:
        if not Path(f).exists():
            print(f"File not found: {f}", file=sys.stderr)
            return 2
        errors += validate_file(f, rules, sep=args.sep)
    write_report(errors, args.report, args.files)
    print(f"{len(errors)} error(s) found. Report: {args.report}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

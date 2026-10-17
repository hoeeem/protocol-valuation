#!/usr/bin/env python3
"""Daily chart file from a CSV download or a listed text copy, checked against the all-time total. protocol-valuation 6.6.0

For when the raw API response can't be saved directly (a saved api.llama.fi page needs no conversion). Two inputs:
  - a CSV downloaded from the protocol's DefiLlama page (a DefiLlama Pro feature: fees chart set to daily, the ".csv"
    button), with a header row: a date or timestamp column and one column per series. Pick one with --column.
  - a listing typed out by a fetch tool that summarises pages: ask it for api.llama.fi/summary/fees/<slug>?dataType=<type>
    with "first line: totalAllTime; then EVERY entry of totalDataChart, one per line, as timestamp,value exactly as they
    appear", and save the lines to a text file (a header line, blank lines, and spaces or tabs instead of commas are fine).
DefiLlama's summary totals are not a substitute: total7d and total30d can cover 6-7 and 29-30 days and include a part day.

The check: the rows must sum to the all-time total (--total-all-time, to within $1 or --tolerance), so a dropped,
duplicated or mistyped row is caught; date gaps are reported (a dropped zero row shows up as one). For a typed-out
listing use the exact totalAllTime. For a CSV, the page's rounded "Cumulative ..." card works with a tolerance (e.g.
$22.58m -> --total-all-time 22580000 --tolerance 5000), or pass --no-total-check for a file downloaded straight from
the source. Rows must be daily: weekly or monthly rows are refused (set the chart to daily before downloading).
The output is {"totalDataChart": [[ts, usd], ...]}, ready for engine.py windows and revenue_stack.py.

Usage: python3 chart_from_text.py <file> (--total-all-time <usd> [--tolerance usd] | --no-total-check)
                                  [--column "<series name>"] [--out chart.json]
"""
import csv, re, sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as cm   # shared input validation and CLI error handling

TIME_WORDS = ("date", "time", "timestamp", "day")

def _num(cell):
    """A number from a cell: '$1,234.5', '1_234', ' 12 ' -> float; empty -> None; text -> ValueError."""
    s = cell.strip().replace("$", "").replace(",", "").replace("_", "").replace(" ", "")
    if s == "" or s.lower() in ("null", "none", "nan", "-"): return None
    return float(s)

def _ts(cell):
    """Unix seconds (or ms) or an ISO date/datetime -> unix seconds; ValueError otherwise."""
    s = cell.strip()
    try:
        return float(s)
    except ValueError:
        pass
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        dt = datetime.fromisoformat(s[:19].replace("Z", "").replace(" ", "T") if len(s) > 10 else s[:10])
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    raise ValueError(f"not a timestamp or YYYY-MM-DD date: {cell!r}")

def _cells(line):
    if "," in line: return [c.strip() for c in next(csv.reader([line]))]
    if "\t" in line: return [c.strip() for c in line.split("\t")]
    return [c for c in re.split(r"[\s;]+", line) if c]

def _parsable(cell):
    for f in (_num, _ts):
        try:
            f(cell); return True
        except ValueError:
            pass
    return False

def _is_row(cells):
    return len(cells) >= 2 and all(_parsable(c) for c in cells)

def parse_table(text, path="input", column=None):
    """([[ts, value], ...], series name) from a CSV with a header row, or from listed timestamp,value lines.
    Lines before the first data row are preamble; the last of them with as many cells as the data is the header."""
    parsed = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip().strip("[]()")
        if s: parsed.append((i, _cells(s)))
    first = next((k for k, (_, c) in enumerate(parsed) if _is_row(c)), None)
    if first is None: raise cm.InputError(f"{path}: no data rows found (expected a date or timestamp, then values)")
    rows = parsed[first:]
    for i, c in rows:
        if not _is_row(c): raise cm.InputError(f"{path}: line {i} is not a data row: {','.join(c)!r} (remove notes after the data)")
    width = max(len(c) for _, c in rows)
    header = next((c for _, c in reversed(parsed[:first]) if len(c) == width), None)
    names = header or [f"column {k + 1}" for k in range(width)]
    def looks_like_time(k):
        try: return all(_ts(c[k]) >= 1e9 for _, c in rows if k < len(c) and c[k] != "")
        except ValueError: return False
    tcol = next((k for k, n in enumerate(names) if header and n.strip().lower().startswith(TIME_WORDS)), None)
    if tcol is None: tcol = next((k for k in range(width) if looks_like_time(k)), 0)
    vcols = [k for k in range(width) if k != tcol]
    if column is not None:
        want = column.strip().lower()
        hit = [k for k in vcols if names[k].strip().lower() == want] or [k for k in vcols if want in names[k].strip().lower()]
        if len(hit) != 1:
            raise cm.InputError(f"{path}: column {column!r} {'not found' if not hit else 'is ambiguous'}; columns: "
                                + ", ".join(names[k] for k in vcols))
        vcol = hit[0]
    elif len(vcols) == 1: vcol = vcols[0]
    else:
        raise cm.InputError(f"{path}: several value columns; pick one with --column. Columns: " + ", ".join(names[k] for k in vcols))
    out = []
    for i, cells in rows:
        if vcol >= len(cells): continue
        try: t, v = _ts(cells[tcol]), _num(cells[vcol])
        except ValueError as e: raise cm.InputError(f"{path}: line {i}: {e}")
        if v is not None: out.append([t, v])
    if not out: raise cm.InputError(f"{path}: column {names[vcol]!r} has no values")
    return out, names[vcol]

def parse_lines(text, path="input"):
    """Listed timestamp,value lines (the 6.4 interface)."""
    return parse_table(text, path)[0]

def build(rows, total_all_time, path="input", tolerance=1.0):
    """Chart file from parsed rows. total_all_time None = no total check (a file downloaded from the source)."""
    pts, notes = cm.series(rows, path)
    s = sum(v for _, v in pts)
    if total_all_time is not None and abs(s - total_all_time) > tolerance:
        raise cm.InputError(f"{path}: the rows sum to {s:,.0f} but the all-time total is {total_all_time:,.0f} "
                            f"({s - total_all_time:+,.0f}): a row was dropped, duplicated or mistyped; list or download the chart again")
    days = [t // 86400 for t, _ in pts]
    steps = sorted(b - a for a, b in zip(days, days[1:]))
    if steps and steps[len(steps) // 2] > 1:
        raise cm.InputError(f"{path}: rows are {steps[len(steps) // 2]} days apart: this looks like weekly or monthly data. "
                            "Set the chart to daily before downloading")
    gaps = [(cm.iso_day(a), cm.iso_day(b)) for a, b in zip(days, days[1:]) if b - a != 1]
    return {"totalDataChart": [[t, v] for t, v in pts],
            "check": {"rows": len(pts), "first_day": cm.iso_day(days[0]), "last_day": cm.iso_day(days[-1]), "sum": s,
                      "total_all_time": total_all_time, "verified": total_all_time is not None, "date_gaps": gaps, "notes": notes}}

def main(argv):
    if len(argv) < 2 or argv[1].startswith("--"): raise cm.InputError("missing file argument (a CSV download or a listed chart)")
    p = argv[1]
    if not os.path.exists(p): raise cm.InputError(f"file not found: {p}")
    with open(p, encoding="utf-8-sig") as fh: text = fh.read()
    nocheck = "--no-total-check" in argv
    tat = cm.arg(argv, "--total-all-time", required=not nocheck)
    if tat is not None:
        try: tat = float(tat.replace(",", "").replace("_", "").replace("$", ""))
        except ValueError: raise cm.InputError(f"--total-all-time must be a number, got {tat!r}")
        cm.num(tat, "--total-all-time")
    tol = cm.arg(argv, "--tolerance")
    try: tol = 1.0 if tol is None else float(tol)
    except ValueError: raise cm.InputError(f"--tolerance must be a number, got {tol!r}")
    cm.num(tol, "--tolerance", lo=0)
    rows, name = parse_table(text, p, cm.arg(argv, "--column"))
    out = build(rows, tat, p, tol)
    op = cm.arg(argv, "--out")
    if op: cm.write_json(op, out)
    c = out["check"]
    print(f"OK: {name}: {c['rows']} daily rows {c['first_day']}..{c['last_day']}, sum {c['sum']:,.0f}"
          + (" = the all-time total" if c["verified"] else " (UNVERIFIED: no total check)")
          + (f"; date gaps {c['date_gaps']}" if c["date_gaps"] else "; no date gaps")
          + (f"; {'; '.join(c['notes'])}" if c["notes"] else "") + (f" -> {op}" if op else ""))
    return out

if __name__ == "__main__":
    cm.cli(main, sys.argv)

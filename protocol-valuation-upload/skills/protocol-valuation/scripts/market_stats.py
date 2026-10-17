#!/usr/bin/env python3
"""Market facts for the defaults step (D2, D3) from a daily category series. protocol-valuation 6.6.0

Input: a JSON file holding [[unix_ts, usd], ...] for the protocol's on-chain category (daily revenue summed across every
protocol in the category: `scripts/category_stats.py` builds it from a DefiLlama overview response). A dict with a
"totalDataChart" or "series" key is also accepted.

Rules (identical to defaults.py, so there is one rule for each number):
  - complete UTC days only (the day containing --as-of, default now, is dropped); missing days count as 0, except the
    latest 1-2 days when the source hasn't published them yet: the series then ends on its last row (data_note)
  - trailing_cagr  CAGR of the trailing-365d sum over the longest of 5/4/3/2 years the series supports (else 0)
  - yoy            latest 365d sum vs the 365d before it (None if under 730 days); negative = shrinking market
  - record_365d    maximum rolling 365-day sum ($m); ttm_365d = latest ($m)
  - level_2y_ago_365d  the 365-day sum ending two years before the last complete day ($m; None under 1,095 days)
  - benchmark_yoy  with --benchmark all_defi.json (all-DeFi daily revenue, from category_stats.py --benchmark-out):
                   the same latest-year change for DeFi as a whole, so the defaults step can tell a cycle from a
                   category-specific collapse
  - the cycle factor is NOT output here: defaults.py computes it as min(1, 0.6522 x record / TTM)

Output (JSON): paste as facts.market, it already carries "basis": "category_series".
Usage: python3 market_stats.py category_series.json [--benchmark all_defi.json] [--as-of ISO]
"""
import json, sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as cm   # shared input validation and CLI error handling

def _last_complete_day(as_of):
    if as_of is None: ts = datetime.now(timezone.utc).timestamp()
    else:
        dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        ts = dt.timestamp()
    return int(ts // 86400) - 1

def stats(chart, as_of=None):
    pts, notes = cm.series(chart, "category series")
    by_day = {}
    for t, v in pts: by_day[int(t) // 86400] = by_day.get(int(t) // 86400, 0.0) + v
    last, _, pub_flag = cm.published_end(by_day, _last_complete_day(as_of))   # the latest 1-2 days may not be published yet
    days = [d for d in by_day if last is not None and d <= last]
    if not days:
        return {"basis": "none", "days": 0, "note": "no complete days of category data"}
    first = min(days); n = last - first + 1
    vals = [by_day.get(d, 0.0) for d in range(first, last + 1)]
    if n < 365:
        return {"basis": "none", "days": n, "note": "under 365 days of category history: use basis none (trailing 0, cycle 1)"}
    roll = [sum(vals[:365])]
    for i in range(365, n): roll.append(roll[-1] + vals[i] - vals[i - 365])
    ttm, record = roll[-1], max(roll)
    cagr, yrs_used = 0.0, None
    for yrs in (5, 4, 3, 2):
        back = 365 * yrs
        if len(roll) > back and roll[-1 - back] > 0:
            cagr = (ttm / roll[-1 - back]) ** (1 / yrs) - 1; yrs_used = yrs; break
    yoy = (ttm / roll[-1 - 365] - 1) if len(roll) > 365 and roll[-1 - 365] > 0 else None
    lvl2 = roll[-1 - 730] if len(roll) > 730 else None
    iso = lambda d: datetime.fromtimestamp(d * 86400, timezone.utc).date().isoformat()
    return {"basis": "category_series", "days": n, "first_day": iso(first), "last_complete_day": iso(last),
            "trailing_cagr": round(cagr, 6), "cagr_years": yrs_used, "yoy": None if yoy is None else round(yoy, 6),
            "record_365d": round(record / 1e6, 3), "ttm_365d": round(ttm / 1e6, 3),
            "level_2y_ago_365d": None if lvl2 is None else round(lvl2 / 1e6, 3),
            "drawdown_from_record": round(ttm / record - 1, 6) if record > 0 else None,
            "missing_days": sum(1 for d in range(first, last + 1) if d not in by_day),
            **({"data_note": pub_flag} if pub_flag else {}),
            **({"warning": "more than 10% of days missing (counted as 0): check the series before using it"}
               if sum(1 for d in range(first, last + 1) if d not in by_day) > 0.1 * n else {})}

def main(argv):
    d = cm.load_json(argv[1] if len(argv) > 1 else None)
    chart = (d.get("totalDataChart") or d.get("series")) if isinstance(d, dict) else d
    if chart is None: raise cm.InputError(f"{argv[1]}: expected a list of [unix_ts, usd] pairs or a dict with totalDataChart/series")
    as_of = cm.arg(argv, "--as-of")
    if as_of is not None: cm.iso_ts(as_of, "--as-of")
    out = stats(chart, as_of)
    bpath = cm.arg(argv, "--benchmark")
    if bpath and out.get("basis") == "category_series":
        b = cm.load_json(bpath)
        bchart = (b.get("totalDataChart") or b.get("series")) if isinstance(b, dict) else b
        bs = stats(bchart, as_of)
        out["benchmark_yoy"] = bs.get("yoy")
        if bs.get("yoy") is None: out["benchmark_note"] = "benchmark series too short for a latest-year change"
    print(json.dumps(out, indent=1))

if __name__ == "__main__":
    cm.cli(main, sys.argv)

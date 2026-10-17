#!/usr/bin/env python3
"""Supply schedule: turn a documented allocation table into the supply inputs the method needs (D14, D15).

Input JSON (tokens in millions, dates YYYY-MM-DD; see reference/DOCS-RESEARCH.md section 5):
{
 "as_of": "2026-10-14", "horizon": 7, "max_supply": 1000,
 "burned": 44.7,                         # permanently removed (or give "total_supply" and burned = max - total)
 "tracker_circulating": 222.4,           # optional: CoinGecko/tracker figure, for reconciliation only
 "buckets": [
  {"name": "Genesis distribution", "tokens": 310, "type": "vesting", "start": "2024-11-29", "tge_pct": 1.0, "source": "..."},
  {"name": "Core contributors", "tokens": 238, "type": "vesting", "start": "2024-11-29", "cliff_months": 12,
   "cliff_pct": 0.0, "linear_months": 24, "source": "..."},
  {"name": "Foundation budget", "tokens": 60, "type": "discretionary"},
  {"name": "Future emissions", "tokens": 388.88, "type": "emission", "distributed": 0},
  {"name": "Buyback fund (held, not burned)", "tokens": 12, "type": "retired"}
 ]
}
Bucket types:
  vesting        tge_pct at start; cliff_pct at start + cliff_months; the remainder linearly over linear_months after the
                 cliff (all at the cliff if linear_months = 0). Vested-but-unclaimed counts as outstanding (D15).
  unlocked       fully outstanding (same as vesting with tge_pct 1).
  emission       authorised but not yet issued: tokens - distributed goes to the unissued pool (enters via D14);
                 distributed is already outstanding.
  discretionary  treasury/foundation inventory with no schedule. Default "treat_as": "unissued" (spendable, enters via
                 D14 like emissions); set "treat_as": "outstanding" if the docs say it is already in circulation.
  retired        held by a buyback fund and not resaleable: excluded from S0 (subtract). Use "burned" for true burns.
Output: S0 (outstanding today), vest[1..N] (new vesting in each projected year), unissued, a bucket breakdown and a
reconciliation against the tracker's circulating figure (> 10% apart is flagged).
Usage: python3 supply_schedule.py schedule.json [--md supply.md] [--json supply_out.json]
"""
import json, sys, os
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as cm   # shared input validation and CLI error handling

def months(d0, d1):
    """Calendar months from d0 to d1 (fractional by day within the month), so a 12-month cliff lands on its anniversary."""
    import calendar
    a, b = date.fromisoformat(d0), date.fromisoformat(d1)
    whole = (b.year - a.year) * 12 + (b.month - a.month)
    day_a = min(a.day, calendar.monthrange(b.year, b.month)[1])
    return whole + (b.day - day_a) / calendar.monthrange(b.year, b.month)[1]

def add_years(d, y):
    d = date.fromisoformat(d)
    try: return d.replace(year=d.year + y).isoformat()
    except ValueError: return d.replace(year=d.year + y, day=28).isoformat()

def vested_frac(b, on):
    """Fraction of a vesting bucket vested by date `on`."""
    if b["type"] == "unlocked": return 1.0
    m = months(b["start"], on)
    if m < 0: return 0.0
    tge, cl, cm, lm = b.get("tge_pct", 0.0), b.get("cliff_pct", 0.0), b.get("cliff_months", 0.0), b.get("linear_months", 0.0)
    if tge + cl > 1 + 1e-9: raise ValueError(f"STOP: bucket {b['name']!r}: tge_pct + cliff_pct > 1")
    f = tge
    if m >= cm:
        f += cl
        rest = 1 - tge - cl
        f += rest if lm <= 0 else rest * min(1.0, (m - cm) / lm)
    return min(1.0, f)

def build(sch):
    as_of, N = sch["as_of"][:10], sch.get("horizon", 7)
    mx = sch.get("max_supply")
    burned = sch.get("burned")
    if burned is None and mx is not None and sch.get("total_supply") is not None: burned = mx - sch["total_supply"]
    burned = burned or 0.0
    rows, flags = [], []
    S0 = -burned; unissued = 0.0; vest = [0.0] * N; alloc = 0.0
    cm.iso_date(sch.get("as_of"), "as_of")
    if not sch.get("buckets"): raise cm.InputError("buckets must list at least one allocation bucket")
    for b in sch["buckets"]:
        t = b.get("type"); tok = cm.num(b.get("tokens"), f"bucket {b.get('name')!r} tokens", lo=0); alloc += tok
        if "start" in b: cm.iso_date(b["start"], f"bucket {b.get('name')!r} start")
        for k in ("tge_pct", "cliff_pct"):
            if k in b: cm.num(b[k], f"bucket {b.get('name')!r} {k}", lo=0, hi=1)
        for k in ("cliff_months", "linear_months", "distributed"):
            if k in b: cm.num(b[k], f"bucket {b.get('name')!r} {k}", lo=0)
        r = {"name": b["name"], "type": t, "tokens": tok, "outstanding_now": 0.0, "to_unissued": 0.0, "vest_by_year": [0.0] * N,
             "source": b.get("source", "")}
        if t in ("vesting", "unlocked"):
            if t == "vesting" and "start" not in b: raise ValueError(f"STOP: vesting bucket {b['name']!r} has no start date")
            now = tok * vested_frac(b, as_of); r["outstanding_now"] = now; S0 += now
            prev = now
            for y in range(1, N + 1):
                cum = tok * vested_frac(b, add_years(as_of, y))
                r["vest_by_year"][y - 1] = cum - prev; vest[y - 1] += cum - prev; prev = cum
            if t == "vesting" and b.get("schedule_uncertain"): flags.append(f"{b['name']}: schedule marked uncertain in the docs ({b.get('note', 'see source')})")
        elif t == "emission":
            dist = float(b.get("distributed", 0.0)); r["outstanding_now"] = dist; r["to_unissued"] = tok - dist
            S0 += dist; unissued += tok - dist
            if "distributed" not in b: flags.append(f"{b['name']}: amount already distributed not stated; assumed 0 (unissued may be overstated)")
        elif t == "discretionary":
            if b.get("treat_as", "unissued") == "outstanding": r["outstanding_now"] = tok; S0 += tok
            else: r["to_unissued"] = tok; unissued += tok
            flags.append(f"{b['name']}: no release schedule; treated as {b.get('treat_as', 'unissued')}")
        elif t == "retired":
            r["outstanding_now"] = -tok; S0 -= tok
        else:
            raise ValueError(f"STOP: bucket {b['name']!r} has unknown type {t!r} (vesting | unlocked | emission | discretionary | retired)")
        rows.append(r)
    if mx is not None and abs(alloc - mx) > 0.01 * mx:
        flags.append(f"allocation buckets sum to {alloc:,.1f}m vs max supply {mx:,.1f}m ({alloc / mx - 1:+.1%}): a bucket is missing or double-counted")
    rec = None
    tc = sch.get("tracker_circulating")
    if tc:
        rec = {"schedule_S0": S0, "tracker_circulating": tc, "diff_pct": S0 / tc - 1}
        if abs(S0 / tc - 1) > 0.10:
            flags.append(f"schedule S0 {S0:,.1f}m vs tracker circulating {tc:,.1f}m ({S0 / tc - 1:+.0%}): trackers often exclude "
                         "vested-unclaimed, staked or foundation-held tokens. Use the schedule (D15) and run the tracker figure as a bracket")
    remaining_vesting = sum(r["tokens"] - r["outstanding_now"] - sum(r["vest_by_year"]) for r in rows if r["type"] == "vesting")
    if remaining_vesting > 1e-6: flags.append(f"{remaining_vesting:,.1f}m still vesting after year {N} (not in the explicit period)")
    return {"as_of": as_of, "S0": round(S0, 3), "vest": [round(v, 3) for v in vest], "unissued": round(unissued, 3),
            "burned": burned, "allocated": alloc, "buckets": rows, "reconciliation": rec, "flags": flags}

def to_md(o):
    N = len(o["vest"])
    L = [f"# Supply schedule as of {o['as_of']}", "",
         f"**S0 (outstanding today, incl. vested-unclaimed) {o['S0']:,.1f}m** · vesting over next {N}y {sum(o['vest']):,.1f}m · "
         f"unissued pool {o['unissued']:,.1f}m · burned {o['burned']:,.1f}m", "",
         "| Bucket | Type | Tokens (m) | Outstanding now | To unissued | " + " | ".join(f"Y{y}" for y in range(1, N + 1)) + " | Source |",
         "|---|---|---|---|---|" + "---|" * N + "---|"]
    for r in o["buckets"]:
        L.append(f"| {r['name']} | {r['type']} | {r['tokens']:,.1f} | {r['outstanding_now']:,.1f} | {r['to_unissued']:,.1f} | "
                 + " | ".join(f"{v:,.1f}" for v in r["vest_by_year"]) + f" | {r['source']} |")
    L.append(f"| **Total** | | {o['allocated']:,.1f} | {o['S0'] + o['burned']:,.1f} (− burned {o['burned']:,.1f}) | {o['unissued']:,.1f} | "
             + " | ".join(f"{v:,.1f}" for v in o["vest"]) + " | |")
    if o["reconciliation"]:
        r = o["reconciliation"]
        L += ["", f"Reconciliation: schedule S0 {r['schedule_S0']:,.1f}m vs tracker circulating {r['tracker_circulating']:,.1f}m ({r['diff_pct']:+.0%})"]
    if o["flags"]: L += ["", "**Flags:**"] + [f"- {f}" for f in o["flags"]]
    L += ["", "Paste into facts.json → supply: `S0`, `vest`, `unissued` (and set `fallback_circulating: false`)."]
    return "\n".join(L)

def main(argv):
    o = build(cm.load_json(argv[1] if len(argv) > 1 else None))
    md = to_md(o)
    md_path, json_path = cm.arg(argv, "--md"), cm.arg(argv, "--json")
    if md_path: cm.write_text(md_path, md + "\n")
    if json_path: cm.write_json(json_path, o, indent=1)
    print(md)

if __name__ == "__main__":
    cm.cli(main, sys.argv)

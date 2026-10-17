#!/usr/bin/env python3
"""Revenue stack: fees -> protocol revenue -> holder revenue, reconciled on one window, with the right valuation input.
protocol-valuation 6.6.0

Why: "revenue" means three different numbers, and using the wrong one changes the answer several times over.
  fees             what users pay                               DefiLlama dataType=dailyFees
  protocol revenue what the protocol keeps (treasury + holders) DefiLlama dataType=dailyRevenue
  holder revenue   what actually reaches token holders          DefiLlama dataType=dailyHoldersRevenue
Always fetch all three for the PARENT slug: api.llama.fi/summary/fees/<slug>?dataType=<type>

Each input file may be:
  - the raw summary response (with totalDataChart), or a chart built by scripts/chart_from_text.py. All three series are
    measured on ONE calendar window ending on the same day (the latest day all three have published), so the waterfall and
    the holder share compare like with like. The window: TTM if every series with revenue has a year of data, else 90 days,
    else the youngest series' history (at least 30 days). Run-rates over the last 30, 14 and 7 days end on the same day.
  - a totals file when your tools only show summaries, or figures read from screenshots of the DefiLlama page:
    {"total1y": 89486657, "total30d": 5062205, "total7d": 1201300, "totalAllTime": 412000000, "history_days": 2141}
    (dollars; give what you have). The level is TTM (total1y) from 365 days of history; under a year, the cumulative
    total over the days since the first revenue day (totalAllTime, history_days), else 30d annualised. Flagged "from
    totals": DefiLlama's 7d and 30d totals can cover 6-7 and 29-30 days and include a part day, so for histories under a
    year prefer the daily chart.
Optional:
  --expenses X      $m/yr of operating costs the DAO pays out of revenue (service providers, grants); from the forum/budget
  --incentives X    $m/yr of incentives paid OUT OF REVENUE (cash or treasury assets). Incentives paid in newly emitted
                    tokens are dilution and belong in the supply schedule, never here as well
  --take-rate r     share of the base a fee switch would send to holders, from the proposal or docs (0-1)
  --holder-share s  documented share of protocol revenue that goes to holders (0-1), for the revenue check; default: the
                    share measured on the common window
  --as-of ISO       complete days before this moment (default now)
Output: the waterfall, run-rates, checks, a classification, the input to use (holder earnings, or a fee-switch option
block) and a revenue_check block for facts.earnings: under a year of history the defaults step caps E0 at what current
protocol revenue supports, because buybacks can run weeks behind revenue.
Usage: python3 revenue_stack.py --fees fees.json --revenue revenue.json --holders holders.json [options] [--json out.json]
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as cm      # shared input validation, daily-series rules and CLI error handling
import engine            # as_of parsing and the windows rules

ROUTED_MIN = 0.80        # holder revenue >= 80% of protocol revenue: revenue already reaches holders
KEPT_MIN = 0.05          # protocol revenue < 5% of fees: the protocol keeps (almost) nothing; fees go to LPs/suppliers
TOL = 1.02               # 2% tolerance for rounding/coverage when checking fees >= revenue >= holder revenue
BRACKETS = (1.0, 0.8, 0.6)   # share of the fee base assumed to survive a switch that charges users/LPs
DRIFT = 0.30             # 30d run-rate more than 30% from the window level -> flagged, show both
SHARP_FALL = 0.50        # 7d run-rate below 50% of the window level -> SHARP FALL
LAG = 1.5                # holders' 7d run-rate above 1.5x what the same week's revenue supports -> holder flow lags revenue
NAMES = {"fees": "fees", "revenue": "protocol revenue", "holders": "holder revenue"}

def parse(d, as_of, path="input"):
    """One input file -> a measured series: {"kind": "chart", ...} or {"kind": "totals", ...}."""
    if isinstance(d, dict) and d.get("totalDataChart") is not None:
        pts, notes = cm.series(d["totalDataChart"], path)
        by = {}
        for t, x in pts: by[t // 86400] = by.get(t // 86400, 0.0) + x
        return {"kind": "chart", "by_day": by, "clock_last": int(engine._as_of_ts(as_of) // 86400) - 1, "notes": notes,
                "path": path, "from_totals": False}
    if isinstance(d, dict) and ("total1y" in d or "total30d" in d):
        h = cm.num(d.get("history_days", 365), f"{path}: history_days", lo=0)
        t1 = cm.num(d.get("total1y"), f"{path}: total1y", allow_none=True)
        t30 = cm.num(d.get("total30d"), f"{path}: total30d", allow_none=True)
        t7 = cm.num(d.get("total7d"), f"{path}: total7d", allow_none=True)
        tat = cm.num(d.get("totalAllTime"), f"{path}: totalAllTime", allow_none=True)
        if h >= 365 and t1 is not None: v, how = t1 / 1e6, "TTM from DefiLlama total1y"
        elif tat is not None and 30 <= h < 365: v, how = tat * 365 / h / 1e6, f"cumulative over {int(h)}d annualised, since launch"
        elif t30 is not None and h >= 30: v, how = t30 * 365 / 30 / 1e6, "DefiLlama total30d annualised, short history"
        else: v, how = None, "insufficient totals"
        return {"kind": "totals", "ttm": v, "level": v, "how": how, "history_days": int(h), "from_totals": True,
                "rr": {"30d": None if t30 is None else t30 * 365 / 30 / 1e6, "14d": None,
                       "7d": None if t7 is None else t7 * 365 / 7 / 1e6},
                "notes": ["from summary totals, not the daily chart"], "path": path}
    raise cm.InputError(f"{path}: expected a DefiLlama summary response (with totalDataChart) or a totals file "
                        "{\"total1y\": ..., \"total30d\": ..., \"history_days\": ...}")

def level(path, as_of):
    return parse(cm.load_json(path), as_of, path)

level_from = parse     # earlier name, kept for callers of 6.3

def _ann(by, end, n):
    return sum(by.get(d, 0.0) for d in range(end - n + 1, end + 1)) / n * 365 / 1e6

def _own_level(x):
    """A chart measured on its own (mixed inputs only): TTM, 90d or since its first non-zero day."""
    end, _, _ = cm.published_end(x["by_day"], x["clock_last"])
    if end is None: return None, "no complete days", {}
    nz = [d for d, v in x["by_day"].items() if v != 0 and d <= end]
    h = (end - min(nz) + 1) if nz else 0
    n = 365 if h >= 365 else 90 if h >= 90 else h if h >= 30 else None
    if n is None: return None, f"only {h} days", {}
    rr = {f"{w}d": (_ann(x["by_day"], end, w) if h >= w else None) for w in (30, 14, 7)}
    return _ann(x["by_day"], end, n), ("TTM" if n == 365 else f"{n}d annualised"), rr

def common_window(S, flags):
    """All three charts on one window ending on the latest day all three have published."""
    ends = []
    for k, x in S.items():
        end_k, _, fl = cm.published_end(x["by_day"], x["clock_last"])
        if fl: flags.append(f"{NAMES[k]}: {fl}")
        if end_k is not None: ends.append(end_k)
    if len(ends) < 3: return None, "a series has no complete days of data"
    end = min(ends)
    if max(ends) > end: flags.append(f"series end on different days: all three measured to {cm.iso_day(end)}, the earliest")
    hist = {}
    for k, x in S.items():
        nz = [d for d, v in x["by_day"].items() if v != 0 and d <= end]
        hist[k] = (end - min(nz) + 1) if nz else 0
    if hist["fees"] == 0: return None, "no fees recorded"
    active = {k: h for k, h in hist.items() if h > 0}
    young = min(active, key=active.get); hmin = active[young]
    if hmin >= 365: n, label = 365, "TTM"
    elif hmin >= 90: n, label = 90, "90d annualised"
    elif hmin >= 30: n, label = hmin, f"{hmin}d annualised, since {NAMES[young]} began"
    elif max(active.values()) >= 30:
        n, label = 30, "30d annualised"
        flags.append(f"{NAMES[young]} has only {hmin} days of data: all three measured over the last 30 days")
    else: return None, f"under 30 days of data ({max(active.values())} days)"
    lv = {k: _ann(x["by_day"], end, n) for k, x in S.items()}
    rr = {k: {f"{w}d": (_ann(x["by_day"], end, w) if (hist[k] >= w or hist[k] == 0) else None) for w in (30, 14, 7)}
          for k, x in S.items()}
    return {"end": end, "n": n, "label": label, "level": lv, "rr": rr, "history_days": hist}, None

def build(fees, revenue, holders, expenses=0.0, incentives=0.0, take_rate=None, holder_share=None):
    S = {"fees": fees, "revenue": revenue, "holders": holders}
    flags, levels_how = [], {}
    end = None
    if all(x["kind"] == "chart" for x in S.values()):
        meas, why = common_window(S, flags)
        if meas is None:
            return {"case": "incomplete", "flags": flags + [f"no common window: {why}"], "levels": {}}
        F, R, H = (meas["level"][k] for k in ("fees", "revenue", "holders"))
        label, rr, end = meas["label"], meas["rr"], meas["end"]
        levels_how = {k: label for k in S}
        hist = meas["history_days"]
    else:
        if any(x["kind"] == "chart" for x in S.values()):
            flags.append("mixed inputs (some daily charts, some totals): each series measured on its own window, so the waterfall "
                         "mixes windows; use daily charts for all three where you can")
        lv, rr, hist = {}, {}, {}
        for k, x in S.items():
            if x["kind"] == "totals":
                lv[k], levels_how[k], rr[k], hist[k] = x["level"], x["how"], x["rr"], x["history_days"]
                flags.append(f"{NAMES[k]}: from summary totals; windows not recomputed from daily data")
            else:
                lv[k], levels_how[k], rr[k] = _own_level(x)
                hist[k] = None
        for k in S:
            if lv[k] is None: flags.append(f"{NAMES[k]}: no usable annual level ({levels_how[k]}); check the series or the docs")
        if None in lv.values():
            return {"case": "incomplete", "flags": flags, "levels": {k: {"level": lv[k], "how": levels_how[k]} for k in S}}
        F, R, H = lv["fees"], lv["revenue"], lv["holders"]
        label = levels_how["revenue"]
    if R > F * TOL: flags.append(f"protocol revenue (${R:,.1f}m) exceeds fees (${F:,.1f}m): different coverage; check the methodology")
    if H > R * TOL: flags.append(f"holder revenue (${H:,.1f}m) exceeds protocol revenue (${R:,.1f}m): the excess is funded from outside "
                                 "revenue (treasury reserves, or buybacks catching up) and isn't recurring business earnings, so the "
                                 "revenue check caps the holder share at 100%; check the methodology")
    if expenses + incentives > R: flags.append("expenses + incentives exceed protocol revenue: nothing distributable on these numbers")
    base_net = max(0.0, R - expenses - incentives)
    rr_h30 = rr["holders"].get("30d")
    paused = bool(H > 0 and rr_h30 is not None and rr_h30 < 0.10 * H)
    if paused: flags.append(f"holder revenue has stopped (30d run-rate ${rr_h30:,.1f}m vs ${H:,.1f}m over the {label}) while the protocol still earns")
    r30, r7 = rr["revenue"].get("30d"), rr["revenue"].get("7d")
    if r30 is not None and R > 0 and abs(r30 / R - 1) > DRIFT:
        flags.append(f"protocol revenue 30d run-rate (${r30:,.1f}m) is {r30 / R - 1:+.0%} vs the {label} level (${R:,.1f}m): show both in the report")
    if r7 is not None and R > 0 and r7 < SHARP_FALL * R:
        flags.append(f"SHARP FALL: protocol revenue over the last 7 days runs at ${r7:,.1f}m a year, {r7 / R - 1:+.0%} vs the {label} level")
    share_meas = (H / R) if R > 0 else None
    h7 = rr["holders"].get("7d")
    if h7 is not None and r7 and share_meas and h7 > LAG * r7 * share_meas:
        flags.append(f"HOLDER FLOW LAGS REVENUE: holder revenue over the last 7 days (${h7:,.1f}m a year) is {h7 / (r7 * share_meas):.1f}x what "
                     f"the same week's protocol revenue supports at the measured holder share ({share_meas:.0%}). Buybacks may be catching "
                     "up on earlier revenue, so the holder series overstates the current rate")
    out = {"window": label, "window_end": cm.iso_day(end) if end is not None else None,
           "levels": {k: {"level": v, "how": levels_how[k]} for k, v in (("fees", F), ("revenue", R), ("holders", H))},
           "history_days": hist, "run_rates_musd": rr,
           "waterfall_musd": {"fees": F, "supply_side": F - R, "protocol_revenue": R, "to_holders": H, "retained": R - H,
                              "expenses": expenses, "incentives_from_revenue": incentives, "distributable": base_net},
           "ratios": {"revenue_of_fees": R / F if F else None, "holders_of_revenue": share_meas}, "flags": flags}
    tr_note = "from the proposal or docs" if take_rate is not None else "FILL IN from the proposal or docs (the engine refuses a missing rate)"
    def option_block(base, lbl, rate):
        return {"type": "fee_switch", "fees_ttm": round(base, 3), "base_label": lbl, "take_rate": rate,
                "routing_on": "documented_not_immutable", "condition": None}
    if R > 0 and H >= ROUTED_MIN * R and not paused:
        out["case"] = "routed"
        out["use"] = ("Revenue already reaches holders: value it on the standard path. Feed the holder-revenue chart to "
                      "engine.py windows and put the output in facts.earnings.windows.")
        if R - H > 0.05 * R:
            out["use"] += f" ${R - H:,.1f}m a year stays in the treasury: note it as possible extra value; it is not in E0."
    elif R >= KEPT_MIN * F and R > 0:
        out["case"] = "treasury"
        out["use"] = (f"The protocol keeps ${R:,.1f}m a year but holders receive ${H:,.1f}m"
                      + (" (currently paused)" if paused else "") + ". For 'what if it all went to holders', use the "
                      "fee-switch option block with the protocol's distributable revenue as the base (not past buybacks).")
        lbl = (f"protocol revenue net of costs ({label})" if (expenses or incentives) else f"protocol revenue ({label}), costs not deducted")
        out["option"] = option_block(base_net, lbl, take_rate)
        out["upper_bound_option"] = option_block(base_net, lbl + ", all of it to holders", 1.0)
        out["take_rate_note"] = tr_note
        if H > 0 and not paused:
            out["use"] += (" Holders already receive a share now: the standard path on holder earnings is the main valuation, "
                           "the option is a what-if.")
        if expenses == 0: flags.append("no DAO operating costs given (--expenses): the base may be overstated; check the budget on the forum")
        out["condition_note"] = ("FILL IN option.condition: the mechanism that would send this to holders (a governance proposal, a "
                                 "documented programme, a paused buyback that can resume) and its source")
    elif F > 0:
        out["case"] = "lp_fees"
        out["use"] = (f"Users pay ${F:,.1f}m a year but the protocol keeps ${R:,.1f}m: a fee switch would take a share of fees "
                      "that currently go to liquidity providers. Use the proposal's fee share as take_rate and run the fee-loss "
                      "brackets: liquidity may leave when providers earn less.")
        out["option"] = option_block(F, f"fees paid by users ({label})", take_rate)
        out["take_rate_note"] = tr_note
        out["condition_note"] = ("FILL IN option.condition: the fee-switch proposal (or other mechanism) that would send fees to "
                                 "holders, and its source")
        out["fee_loss_brackets"] = [dict(option_block(F * b, f"fees paid by users ({label}), {b:.0%} retained after the switch", take_rate))
                                    for b in BRACKETS]
    else:
        out["case"] = "no_revenue"
        out["use"] = "No fees or revenue: cannot be valued from cash flows."
    if R > 0 and H > 0:
        share = holder_share if holder_share is not None else share_meas
        out["revenue_check"] = {
            "revenue_7d": rr["revenue"].get("7d"), "revenue_14d": rr["revenue"].get("14d"), "revenue_30d": rr["revenue"].get("30d"),
            "holder_share": round(min(share, 1.0), 6), "holder_share_measured": round(share_meas, 6),
            "share_basis": "documented (--holder-share)" if holder_share is not None else f"measured: holder / protocol revenue over the {label}",
            "window_end": out["window_end"], "source": "scripts/revenue_stack.py " + engine.__version__}
    return out

def to_md(o, slug=""):
    L = [f"# Revenue stack {slug}".rstrip(), ""]
    if o["case"] == "incomplete":
        L += ["**Incomplete:** at least one series has no usable annual level.", ""] + [f"- {x}" for x in o["flags"]]
        return "\n".join(L)
    w = o["waterfall_musd"]; lv = o["levels"]
    L += [f"Window: **{o['window']}**" + (f", ending {o['window_end']}" if o["window_end"] else ""), "",
          "| Line | $m a year | Measured as |", "|---|---|---|",
          f"| Fees paid by users | {w['fees']:,.1f} | {lv['fees']['how']} |",
          f"| − to suppliers / LPs | {w['supply_side']:,.1f} | fees − protocol revenue |",
          f"| **Protocol revenue** | **{w['protocol_revenue']:,.1f}** | {lv['revenue']['how']} |",
          f"| − retained by the protocol (treasury) | {w['retained']:,.1f} | protocol revenue − holder revenue |",
          f"| **Holder revenue** | **{w['to_holders']:,.1f}** | {lv['holders']['how']} |"]
    if w["expenses"] or w["incentives_from_revenue"]:
        L.append(f"| Distributable (revenue − costs − cash incentives) | {w['distributable']:,.1f} | revenue − {w['expenses']:,.1f} − {w['incentives_from_revenue']:,.1f} |")
    r = o["ratios"]
    if r["revenue_of_fees"] is not None and r["holders_of_revenue"] is not None:
        L += ["", f"Protocol keeps {r['revenue_of_fees']:.1%} of fees; holders receive {r['holders_of_revenue']:.1%} of protocol revenue."]
    rr = o["run_rates_musd"]
    f1 = lambda v: "n/a" if v is None else f"{v:,.1f}"
    L += ["", "Run-rates, $m a year:", "", "| Series | Window level | 30d | 14d | 7d |", "|---|---|---|---|---|"]
    for k, nm in (("fees", "Fees"), ("revenue", "Protocol revenue"), ("holders", "Holder revenue")):
        L.append(f"| {nm} | {f1(lv[k]['level'])} | {f1(rr[k].get('30d'))} | {f1(rr[k].get('14d'))} | {f1(rr[k].get('7d'))} |")
    L += ["", f"**Case: {o['case']}.** {o['use']}"]
    if o.get("option"):
        L += ["", "Option block for facts.json (fee switch):", "```json", json.dumps(o["option"], indent=1), "```"]
        if o.get("take_rate_note"): L.append(f"take_rate: {o['take_rate_note']}.")
        if o.get("condition_note"): L.append(f"condition: {o['condition_note']}.")
    if o.get("upper_bound_option"): L.append("Upper bound (everything distributable to holders): `take_rate` 1.0.")
    if o.get("fee_loss_brackets"): L.append("Fee-loss brackets: run the option with fees_ttm at 100%, 80% and 60% of today's fees.")
    if o.get("revenue_check"):
        L += ["", "Revenue check for facts.json → `earnings.revenue_check` (under a year of history, E0 is capped at what current "
              "protocol revenue supports):", "```json", json.dumps(o["revenue_check"], indent=1), "```"]
    if o["flags"]: L += ["", "**Flags:**"] + [f"- {x}" for x in o["flags"]]
    return "\n".join(L)

def main(argv):
    paths = {k: cm.arg(argv, f"--{k}", required=True) for k in ("fees", "revenue", "holders")}
    as_of = cm.arg(argv, "--as-of")
    if as_of is not None: cm.iso_ts(as_of, "--as-of")
    def fnum(flag):
        v = cm.arg(argv, flag)
        if v is None: return None
        try: return float(v)
        except ValueError: raise cm.InputError(f"{flag} must be a number, got {v!r}")
    exp = cm.num(fnum("--expenses") or 0.0, "--expenses", lo=0)
    inc = cm.num(fnum("--incentives") or 0.0, "--incentives", lo=0)
    tr = fnum("--take-rate")
    tr = None if tr is None else cm.num(tr, "--take-rate", lo=0, lo_open=True, hi=1)
    hs = fnum("--holder-share")
    hs = None if hs is None else cm.num(hs, "--holder-share", lo=0, lo_open=True, hi=1)
    o = build(*(level(paths[k], as_of) for k in ("fees", "revenue", "holders")), expenses=exp, incentives=inc, take_rate=tr,
              holder_share=hs)
    md = to_md(o, cm.arg(argv, "--slug") or "")
    jp, mp = cm.arg(argv, "--json"), cm.arg(argv, "--md")
    if jp: cm.write_json(jp, o, indent=1)
    if mp: cm.write_text(mp, md + "\n")
    print(md)
    return o

if __name__ == "__main__":
    cm.cli(main, sys.argv)

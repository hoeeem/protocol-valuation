#!/usr/bin/env python3
"""Defaults step: turn a facts file into every judgement input (g1, ROE, Ke layers, emissions, weights, gT),
plus a judgement table the user confirms or overrides before anything is valued.

Every rule carries a register id (D1..D20, see reference/CALIBRATION.md) and a class:
  METHOD      a core rule of the method (how the number is produced)
  CALIBRATED  a constant fixed on the calibration case (examples/calibration_facts.json)
  HEURISTIC   a generalising rule chosen by the method; reasonable alternatives exist
  FALLBACK    the free data the method wants does not exist; documented substitute
  JUDGEMENT   a convention, not an estimate (e.g. scenario weights)
Determinism: pure function of the facts file, Decimal half-away-from-zero rounding at fixed steps, fixed tie-breaks.
No network access: facts are gathered (and timestamped) by the caller. Usage:
  python3 defaults.py facts.json [--overrides ov.json] [--md judgement.md] [--json inputs.json]
  (or: python3 engine.py defaults facts.json ...)
"""
import json, sys, copy, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as cm   # shared input validation and CLI error handling

__version__ = "6.6.0"
from decimal import Decimal, ROUND_HALF_UP

SCEN = ("bear", "base", "bull")

def rnd(x, step):
    """Round half away from zero to a multiple of step (deterministic across platforms)."""
    q = (Decimal(repr(x)) / Decimal(repr(step))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(q * Decimal(repr(step)))
def r5(x): return rnd(x, 0.05)          # growth rates, ROE, market CAGRs: nearest 5pp
def bp(x): return rnd(x, 0.0001)        # Ke layers: nearest 0.01pp

# ---------------- constants (register ids in reference/CALIBRATION.md) ----------------
WEIGHTS = {"bear": 0.20, "base": 0.60, "bull": 0.20}            # D17 judgement
G_TERMINAL = {"bear": 0.030, "base": 0.035, "bull": 0.045}       # D16 calibrated: long-run nominal growth anchor
HORIZON = 7                                                      # D18 method: 7 explicit years, then steady-state P/E
MARKET_SPREAD = 0.10                                             # D2 heuristic: bull = base + 10pp, bear = base - 10pp
MARKET_CAP = 0.20                                                # D2 heuristic: base market CAGR capped at +/-20%
CYCLE_RESET = 0.6522                                             # D3 calibrated: year-1 market level = 65.22% of the record year
DEX_TARGET = {"bear": 0.10, "base": 0.30, "bull": 0.35}          # D4 calibrated (perps only): DEX share of total perp volume by year 7
SHARE_MULT_STRONG = {"bear": 0.50, "base": 1.25, "bull": 1.50}   # D5 calibrated ratios (strong moat)
SHARE_MULT_OTHER = {"bear": 0.50, "base": 1.00, "bull": 1.25}    # D5 heuristic (moat below the strong bands)
SHARE_CAP = 0.95
# D7 calibrated band table, capital-light DeFi: Helmer x Porter -> stabilised ROE range
ROE_BANDS = [  # (helmer_min, porter, low, high)  porter: "low" | "high" | "any"
    (2.5, "low", 0.55, 1.20), (2.5, "high", 0.40, 0.80),
    (2.0, "low", 0.35, 0.80), (2.0, "high", 0.25, 0.55),
    (1.5, "any", 0.12, 0.25), (0.0, "any", 0.08, 0.15)]
PORTER_LOW_MAX = 1.0                                             # D7 heuristic: Porter (0-2 scale) <= 1.0 is "low"
REG = {"unresolved_us_no_kyc": {"bear": 0.025, "base": 0.020, "bull": 0.005},   # D10 calibrated
       "us_facing_no_kyc_settled": {"bear": 0.015, "base": 0.010, "bull": 0.005},  # D10 heuristic: no KYC, US-facing,
                                                                                  # past US probes closed without action
       "regulated_or_kyc": {"bear": 0.005, "base": 0.005, "bull": 0.005}}     # D10 heuristic: the floor
REG_FORMAL_ACTION = 0.02                                         # D10 method: +2pp if a formal enforcement action names the protocol
GOV_FULL = 0.0125                                                # D11 calibrated: all three governance drivers present, with offset
GOV_NO_OFFSET = 0.0050                                           # D11 heuristic: no alignment offset
ALIGN = {"mechanical": 0.0, "documented_not_immutable": 0.01, "time_limited": 0.01, "discretionary": 0.02,  # D12
         "paused": 0.02, "fee_switch_off": 0.03}                                     # D12 heuristic: option path only
OPTION_ROUTINGS = ("paused", "fee_switch_off")
# D12 on the option path: the switched-on value is priced at the routing class it would have once switched on.
# Whether and when it switches on is carried by the activation probabilities (D21), so charging the switch-off premium
# as well would price the same risk twice. Default: documented_not_immutable (governance could switch it off again).
ROUTING_ON_DEFAULT = "documented_not_immutable"
# D23 holder rights: how the benefit reaches holders, and what a holder must do to get it (documented facts, not estimates)
BENEFIT_FORMS = {"buyback_burn": "fair_value", "buyback_held": "fair_value", "distribution": "none", "staking_distribution": "none"}
ACCESS = ("all_holders", "stakers_only", "lockers_only")
SHARE_TOL = 1.02         # holder revenue above 102% of protocol revenue: more than revenue can fund (reserves or catch-up buybacks)
# D2/D3/D4 perps fallback (total CEX+DEX perp volume is not free). ONE rule: these three always travel together.
PERPS_FALLBACK = {"trailing_cagr": 0.61, "cycle_factor": 0.6522, "dex_share_0": 0.07,
                  "source": "FALLBACK perps (mid-2026): global perp volume $8.6T (2020) -> $92T (2025) = 61% CAGR; "
                            "post-peak reset 0.6522 ($92T -> ~$60T); DEX share ~7%"}
# D2 structural-decline test (heuristic). A downturn is a cycle (handled by the D3 reset, as in the calibration case,
# where a ~35% fall from the record year still came with +20%/yr growth after). Only a category that falls far more than
# DeFi as a whole, and sits below where it was two years ago, is treated as a possible structural decline: base = flat.
STRUCT_GAP = -0.25       # category latest-year change minus all-DeFi latest-year change, at or below this
STRUCT_BASE = 0.0        # base market CAGR in a structural decline (flat: no boom-era growth, no extrapolation to zero)
YOUNG_YEARS = 3          # trailing CAGR over fewer years than this is flagged YOUNG CATEGORY (no full cycle yet)
YOUNG_LEVEL_RATIO = 0.5  # D2 heuristic: a category whose 365d level two years ago was under half today's TTM is young: its
                         # history is mostly a boom off a small base, so after a fall neither the boom nor the fall is extrapolated
PAUSE_RATIO = 0.10       # D19: 30d run-rate < 10% of E0 -> holder cash flow stopped
DECAY_RATIO = 0.50       # D19: 7d run-rate < 50% of E0 -> DECAYING (same constant as engine.DECAY_RATIO)
REV_FALL_RATIO = 0.50    # D19: from 365 days, revenue-supported run-rate < 50% of TTM -> REVENUE FALLING flag (TTM kept)
EARLY_MIN_DAYS = 30      # D19: early-stage valuation allowed from 30 days of holder earnings
BORDER = 0.05            # D6: a moat score within 0.05 of a band edge is BORDERLINE (the adjacent band is computed)
TRACK_MAX = 0.02         # D22 heuristic: track-record premium 2.0pp at 30 days, falling linearly to 0 at 90 days
# D21 judgement: default activation cases for the option path (user must confirm)
OPTION_DEFAULT_CASES = {
    "paused_buyback": [{"label": "DEFAULT resume within 1y", "p": 0.40, "delay_years": 1},
                       {"label": "DEFAULT resume in 3y", "p": 0.20, "delay_years": 3}],
    "fee_switch": [{"label": "DEFAULT switch on within 1y", "p": 0.20, "delay_years": 1},
                   {"label": "DEFAULT switch on in 3y", "p": 0.20, "delay_years": 3}]}
OPTION_IMPLIED_DELAYS = [0, 1, 3, 5]
SC_START, SC_FLOOR, SC_MONTHS = 0.02, 0.005, 36                  # D13 calibrated: 2.0% at launch, linear to 0.5% at 36 months
EMISSIONS_DISCIPLINED = {"bear": 0.60, "base": 0.10, "bull": 0.00}   # D14 calibrated
EMISSIONS_UNDISCIPLINED = {"bear": 1.00, "base": 0.60, "bull": 0.10} # D14 heuristic: shifted one scenario
EMISSION_RELEASE_BY_T = 0.75                                     # D14 calibrated: 75% of included emissions released by year 7

# ---------------- moat rubric (D6 heuristic: deterministic proxies for qualitative scoring) ----------------
HELMER = ("network_effects", "scale_economies", "counter_positioning", "switching_costs", "branding", "cornered_resource", "process_power")
PORTER = ("rivalry", "new_entrants", "supplier_power", "buyer_power", "substitutes")

def helmer_rubric(f):
    s, rev, age = f["share_30d"], f["holder_rev_ttm_musd"], f["age_months"]
    return {"network_effects": 3 if s >= 0.40 else 2 if s >= 0.20 else 1 if s >= 0.10 else 0,
            "scale_economies": 3 if rev >= 500 else 2 if rev >= 100 else 1 if rev >= 20 else 0,
            "counter_positioning": 2 if f.get("custodial_incumbent") else 1,
            "switching_costs": 3 if f.get("bond_lock") else 0 if f.get("incentive_driven") else 1,
            "branding": 3 if f["rank"] == 1 else 2 if f["rank"] <= 3 else 1,
            "cornered_resource": 3 if f.get("bond_lock") else 2 if f.get("own_chain_or_unique_tech") else 1,
            "process_power": 0 if f.get("major_exploit") else 3 if age >= 18 else 2 if age >= 9 else 1}

def porter_rubric(f):
    n, d = f["n_competitors_ge10"], f["share_change_pp"]
    return {"rivalry": 0 if n == 0 else 1 if n <= 2 else 2,
            "new_entrants": 2 if d <= -10 else 1 if (d <= -2 or f.get("young_top3_competitor")) else 0,
            "supplier_power": 1 if f.get("supplier_dependency") else 0,
            "buyer_power": 2 if f.get("incentive_driven") else 0,
            "substitutes": 1 if f.get("offchain_substitute") else 0}

def segment_scores(seg):
    """Explicit documented scores win; otherwise the rubric. Helmer = mean of 7 powers (0-3); Porter = mean of 5 forces (0-2)."""
    if "helmer" in seg: h, hs = seg["helmer"], "explicit"
    else: h, hs = helmer_rubric(seg["rubric"]), "rubric D6"
    if "porter" in seg: p, ps = seg["porter"], "explicit"
    else: p, ps = porter_rubric(seg["rubric"]), "rubric D6"
    H = h if isinstance(h, (int, float)) else sum(h[k] for k in HELMER) / 7
    P = p if isinstance(p, (int, float)) else sum(p[k] for k in PORTER) / 5
    return H, P, h, p, hs, ps

def moat(segments):
    tw = sum(s["weight"] for s in segments)
    rows = [(s, *segment_scores(s)) for s in segments]
    H = round(sum(s["weight"] * r[0] for s, *r in rows) / tw, 2)   # 2 dp before the band lookup
    P = round(sum(s["weight"] * r[1] for s, *r in rows) / tw, 2)
    porter = "low" if P <= PORTER_LOW_MAX else "high"
    for i, (hmin, pc, lo, hi) in enumerate(ROE_BANDS):
        if H >= hmin and (pc == "any" or pc == porter): return dict(helmer=H, porter=P, porter_class=porter, band_index=i, band=(lo, hi),
                                                                    segments=[dict(name=s["name"], weight=s["weight"], helmer=r[0], porter=r[1],
                                                                                   helmer_detail=r[2], porter_detail=r[3], source=(r[4], r[5])) for s, *r in rows])
    raise ValueError("unreachable")

def roe_from_band(lo, hi, P):
    """D8 heuristic: bear = band low; base = low + span/3; bull = low + span*(1 - Porter/2); each to nearest 5pp.
    Calibration case: band 35-80%, Porter 0.48 -> 35 / 50 / 69.2->70."""
    span = hi - lo
    return {"bear": r5(lo), "base": r5(lo + span / 3), "bull": r5(lo + span * (1 - P / 2))}

def adjacent_band(m, keT, mkt, cyc, N, dex0, sh0, take=None):
    """D6 BORDERLINE: the band across the nearest edge, with its ROE (floored at Ke_T, as D8) and g1 (with that band's share
    set, as D5), plus the overrides that run it as a bracket. A Helmer edge takes precedence over the Porter edge."""
    H, P = m["helmer"], m["porter"]
    near = [e_ for e_ in sorted({b[0] for b in ROE_BANDS if b[0] > 0}) if abs(H - e_) <= BORDER]
    if near:
        e_ = min(near, key=lambda x: abs(H - x))
        H2, P2 = (round(e_ - 0.01, 2) if H >= e_ else e_), P
    else:
        H2, P2 = H, (round(PORTER_LOW_MAX + 0.01, 2) if P <= PORTER_LOW_MAX else PORTER_LOW_MAX)
    pc2 = "low" if P2 <= PORTER_LOW_MAX else "high"
    for i, (hmin, pc, lo, hi) in enumerate(ROE_BANDS):
        if H2 >= hmin and (pc == "any" or pc == pc2): break
    r = roe_from_band(lo, hi, P2)
    roe = {s: (r[s] if r[s] > keT[s] else keT[s]) for s in SCEN}
    mult = SHARE_MULT_STRONG if i <= 2 else SHARE_MULT_OTHER
    take = take or {}
    raw = {s: lever_g1(mkt[s], cyc, N, dex0, DEX_TARGET[s] if dex0 else None, sh0, mult[s], take.get(s, 1.0))[0] for s in SCEN}
    g = {"base": r5(raw["base"]), "bull": r5(raw["bull"]), "bear": r5(mkt["bear"])}
    if g["bear"] > g["base"]: g["bear"] = g["base"]
    if g["bull"] < g["base"]: g["bull"] = g["base"]
    g = {s: g[s] + 0.0 for s in SCEN}                    # no negative zero in the printed flag
    ov = {f"scenarios.{s}.roe": round(roe[s], 6) for s in SCEN}
    ov.update({f"scenarios.{s}.g1": g[s] for s in SCEN})
    return {"helmer": H2, "porter": P2, "band": [lo, hi], "band_index": i, "set": "strong" if i <= 2 else "weaker",
            "roe": roe, "g1": g, "overrides": ov}

def sc_premium(age_months, major_exploit=False):
    """D13: sc = max(0.5%, 2.0% - 1.5% * age/36); an exploit >= $10m resets to 2.0%. Calibration case: age 20 -> 1.17%."""
    if major_exploit: return SC_START
    return bp(max(SC_FLOOR, SC_START - (SC_START - SC_FLOOR) * age_months / SC_MONTHS))

def lever_g1(mkt, cycle, N, dex0, dexT, share0, mult, take=1.0):
    """D1-D5: (1+g)^N = cycle*(1+mkt)^(N-1) * dexT/dex0 * shareT/share0 * take.  shareT capped at 95%."""
    shT = min(share0 * mult, SHARE_CAP) if share0 else None
    X = cycle * (1 + mkt) ** (N - 1) * ((dexT / dex0) if dex0 else 1.0) * ((shT / share0) if share0 else 1.0) * take
    return X ** (1 / N) - 1, X, shT

def market_inputs(mk):
    """D2/D3/D4 inputs from ONE basis, so trailing growth, cycle factor and DEX lever can never mix series.
    basis = "fallback_perps": all three are the PERPS_FALLBACK constants (supplied values are refused).
    basis = "category_series": trailing_cagr, record_365d, ttm_365d (and yoy) from scripts/market_stats.py on the
            on-chain category's own daily series; cycle = min(1, 0.6522 x record/TTM); DEX lever = 1 (migration is already
            inside an on-chain category's growth).
    basis = "none": no category history: trailing 0, cycle 1, no DEX lever."""
    basis = mk.get("basis")
    if basis == "fallback_perps":
        mixed = [k for k in ("trailing_cagr", "cycle_factor", "record_365d", "ttm_365d", "yoy", "dex_share_0") if k in mk]
        if mixed: raise ValueError(f"STOP: market.basis fallback_perps fixes trailing CAGR, cycle factor and DEX share together; "
                                   f"remove {mixed} (or use basis category_series with market_stats.py output)")
        return dict(tr=PERPS_FALLBACK["trailing_cagr"], yoy=None, cyc=PERPS_FALLBACK["cycle_factor"], dex0=PERPS_FALLBACK["dex_share_0"],
                    how=f"{PERPS_FALLBACK['cycle_factor']} (perps fallback)", src=PERPS_FALLBACK["source"], basis=basis)
    if basis == "category_series":
        miss = [k for k in ("trailing_cagr", "record_365d", "ttm_365d") if mk.get(k) is None]
        if miss: raise ValueError(f"STOP: market.basis category_series needs {miss} from scripts/market_stats.py")
        if "cycle_factor" in mk or "dex_share_0" in mk:
            raise ValueError("STOP: with basis category_series the cycle factor is computed (not supplied) and there is no DEX lever; "
                             "remove market.cycle_factor / market.dex_share_0")
        rec, ttm = mk["record_365d"], mk["ttm_365d"]
        cyc = min(1.0, CYCLE_RESET * rec / ttm) if ttm > 0 else 1.0
        return dict(tr=mk["trailing_cagr"], yoy=mk.get("yoy"), bench=mk.get("benchmark_yoy"), lvl2=mk.get("level_2y_ago_365d"),
                    ttm=ttm, years=mk.get("cagr_years"), cyc=cyc, dex0=None,
                    how=f"min(1, {CYCLE_RESET} x record {rec:,.1f} / TTM {ttm:,.1f})", src=mk.get("source", "category series"), basis=basis)
    if basis == "none":
        return dict(tr=0.0, yoy=None, cyc=1.0, dex0=None, how="no category history: 1.0", src=mk.get("source", "no history"), basis=basis)
    raise ValueError(f"STOP: market.basis must be fallback_perps | category_series | none (got {basis!r})")

def market_base(MI):
    """D2. Base = a third of the multi-year trailing CAGR, rounded to 5pp, capped at +/-20% (calibrated rule). A downturn
    is NOT extrapolated: it is a cycle, handled by the D3 reset. Exceptions, judged on the bigger picture:
      - the category shrank over the latest year AND did so at least 25pp worse than all of DeFi AND (where measurable) its TTM
        is below its level two years ago: possible structural decline, base = flat (0%);
      - the category shrank over the latest year AND is young (trailing CAGR over < 3 years, or its level two years ago was under
        half today's TTM): its trailing CAGR is a boom off a small base, so base = flat (0%) as well.
    Returns (base, how, flags)."""
    tr, yoy, bench, lvl2, ttm, yrs = MI["tr"], MI.get("yoy"), MI.get("bench"), MI.get("lvl2"), MI.get("ttm"), MI.get("years")
    flags = []
    base = max(-MARKET_CAP, min(MARKET_CAP, r5(tr / 3)))
    how = f"trailing {tr:.1%}/3" + (f" over {yrs}y" if yrs else "")
    if yrs is not None and yrs < YOUNG_YEARS:
        flags.append(f"YOUNG CATEGORY: trailing CAGR measured over {yrs} years only (no full cycle); treat {tr:+.0%} with caution")
    if yoy is None or yoy >= 0:
        return base, how, flags
    if bench is not None:
        gap = yoy - bench
        below2y = None if (lvl2 is None or ttm is None) else ttm < lvl2
        evidence = (f"category {yoy:+.0%} vs all DeFi {bench:+.0%} over the latest year (gap {gap * 100:+.0f}pp)"
                    + ("" if below2y is None else f"; TTM {ttm:,.1f} vs {lvl2:,.1f} two years ago"))
        if gap <= STRUCT_GAP and below2y is not False:
            flags.append("POSSIBLE STRUCTURAL DECLINE: " + evidence + ("" if below2y is not None else "; 2-year comparison unavailable")
                         + f". Base market growth set flat ({STRUCT_BASE:.0%}), bull/bear +/-10pp; confirm or override")
            return STRUCT_BASE, "STRUCTURAL DECLINE (" + evidence + "): flat", flags
    # A young category in decline: its trailing growth is a boom off a small base, and the two-year test can't show a structural
    # decline when the category barely existed two years ago. Neither the boom nor the fall is extrapolated.
    young_by_level = lvl2 is not None and ttm is not None and lvl2 < YOUNG_LEVEL_RATIO * ttm
    if (yrs is not None and yrs < YOUNG_YEARS) or young_by_level:
        why = (f"two years ago its 365d level was {lvl2:,.1f} vs {ttm:,.1f} now" if young_by_level
               else f"trailing growth measured over {yrs} years only")
        flags.append(f"YOUNG CATEGORY IN DECLINE: the category fell {yoy:+.0%} over the latest year and is young ({why}), so its "
                     f"trailing CAGR ({tr:+.0%}) is a boom off a small base. Base market growth set flat ({STRUCT_BASE:.0%}), "
                     "bull/bear +/-10pp; confirm or override")
        return STRUCT_BASE, f"YOUNG CATEGORY IN DECLINE ({yoy:+.0%} latest year; {why}): flat", flags
    if bench is None:
        flags.append(f"SHRINKING CATEGORY ({yoy:+.0%} latest year) but no all-DeFi benchmark (market.benchmark_yoy): cannot tell "
                     "cycle from structural decline; calibrated rule applied. Supply the benchmark")
        return base, how + "; downturn treated as cycle (no benchmark)", flags
    flags.append("CYCLICAL DOWNTURN: " + evidence + "; calibrated rule applied, the drop is handled by the cycle reset (D3)")
    return base, how + "; downturn treated as cycle", flags

def months_between(d0, d1):
    from datetime import date
    a, b = date.fromisoformat(d0), date.fromisoformat(d1)
    return int(rnd((b - a).days / 30.4375, 1))

# ---------------- input validation ----------------
def validate_facts(f):
    """Clean, specific errors for a malformed facts file (reference/FACTS.md) before any rule runs."""
    if not isinstance(f, dict): raise cm.InputError("facts file must be a JSON object")
    miss = [k for k in ("protocol", "as_of", "price", "earnings", "market", "share", "moat", "risk", "rf", "erp", "supply") if k not in f]
    if miss: raise cm.InputError(f"facts file is missing {miss} (see reference/FACTS.md)")
    cm.iso_ts(f["as_of"], "as_of"); cm.num(f["price"], "price", lo=0, lo_open=True)
    e = f["earnings"]
    if "windows" not in e: cm.num(e.get("history_days"), "earnings.history_days", lo=0)
    for k, v in (e.get("core_by_window") or {}).items(): cm.num(v, f"earnings.core_by_window.{k}", allow_none=True)
    cm.num(e.get("other", 0.0), "earnings.other", lo=0)
    rc = e.get("revenue_check")
    if rc is not None:
        if not isinstance(rc, dict): raise cm.InputError("earnings.revenue_check must be an object (the block written by scripts/revenue_stack.py)")
        for k in ("revenue_7d", "revenue_14d", "revenue_30d"): cm.num(rc.get(k), f"earnings.revenue_check.{k}", lo=0, allow_none=True)
        cm.num(rc.get("holder_share"), "earnings.revenue_check.holder_share", lo=0, allow_none=True)
        cm.num(rc.get("holder_share_measured"), "earnings.revenue_check.holder_share_measured", lo=0, allow_none=True)
    cm.num(f.get("payout", 1.0), "payout", lo=0, hi=1)
    rt = f.get("rights")
    if rt is not None:
        if not isinstance(rt, dict): raise cm.InputError("rights must be an object: {\"benefit_form\": ..., \"access\": ...}")
        bf, ac = rt.get("benefit_form"), rt.get("access", "all_holders")
        if not isinstance(bf, str) or bf not in BENEFIT_FORMS:
            raise cm.InputError(f"rights.benefit_form must be one of {sorted(BENEFIT_FORMS)}, got {bf!r}")
        if not isinstance(ac, str) or ac not in ACCESS:
            raise cm.InputError(f"rights.access must be one of {list(ACCESS)}, got {ac!r}")
    cm.num(f["share"].get("share_0"), "share.share_0", lo=0, lo_open=True, hi=1)
    segs = f["moat"].get("segments")
    if not segs: raise cm.InputError("moat.segments must list at least one segment")
    if sum(cm.num(s_.get("weight"), "moat segment weight", lo=0) for s_ in segs) <= 0: raise cm.InputError("moat segment weights sum to 0")
    rk = f["risk"]
    if rk.get("reg_class") not in REG: raise cm.InputError(f"risk.reg_class must be one of {sorted(REG)}, got {rk.get('reg_class')!r}")
    if rk.get("routing") not in ALIGN: raise cm.InputError(f"risk.routing must be one of {sorted(ALIGN)}, got {rk.get('routing')!r}")
    if "age_months" in rk: cm.num(rk["age_months"], "risk.age_months", lo=0)
    elif "launch_date" in rk:
        ld = cm.iso_date(rk["launch_date"], "risk.launch_date")
        if ld > cm.iso_date(f["as_of"], "as_of"): raise cm.InputError(f"risk.launch_date {rk['launch_date']} is after as_of")
    else: raise cm.InputError("risk needs age_months or launch_date")
    if "first_fees_day" in rk: cm.iso_date(rk["first_fees_day"], "risk.first_fees_day")
    if "option" in f:
        op = f["option"]
        if not isinstance(op, dict): raise cm.InputError("option must be an object (METHOD.md section 9)")
        ron = op.get("routing_on", ROUTING_ON_DEFAULT)
        if ron not in ALIGN or ron in OPTION_ROUTINGS:
            raise cm.InputError(f"option.routing_on must be one of {sorted(k for k in ALIGN if k not in OPTION_ROUTINGS)}, got {ron!r}")
    cm.num(f["rf"].get("value"), "rf.value", lo=-0.05, hi=0.5); cm.num(f["erp"].get("value"), "erp.value", lo=0, hi=0.5)
    sp = f["supply"]
    cm.num(sp.get("S0"), "supply.S0", lo=0, lo_open=True)
    for i, v in enumerate(sp.get("vest", [])): cm.num(v, f"supply.vest[{i}]", lo=0)
    cm.num(sp.get("unissued", 0), "supply.unissued", lo=0)
    mk = f["market"]
    for k in ("trailing_cagr", "record_365d", "ttm_365d", "yoy", "benchmark_yoy", "level_2y_ago_365d"):
        if k in mk: cm.num(mk[k], f"market.{k}", allow_none=True)

# ---------------- main builder ----------------
def build(f):
    validate_facts(f)
    N = HORIZON; T = []   # T = judgement table rows
    def row(rid, name, vals, rule, cls, src):
        T.append(dict(id=rid, input=name, values=vals, rule=rule, cls=cls, source=src))
    trace = []
    # --- E0 (D19) and gates ---
    flags = []
    e = f["earnings"]; rk = f["risk"]
    w = e.get("windows")                          # preferred: the JSON printed by `engine.py windows`
    cbw = dict(e.get("core_by_window", {}))
    if w:
        h = w["history_days"]
        for k in ("7d", "14d", "30d", "90d", "365d", "since_launch"):
            if w.get(k) is not None: cbw.setdefault(k, w[k])
        flags += [f"DATA: {x}" for x in w.get("flags", [])]   # unpublished or low last day, from the windows tool
    else:
        h = e["history_days"]
    option_path = "option" in f
    if rk.get("routing") in OPTION_ROUTINGS and not option_path:
        raise ValueError(f"STOP: routing {rk['routing']!r}: holders receive no cash flow now; add an option block "
                         "(METHOD.md section 9) to value the restart/switch-on")
    early = EARLY_MIN_DAYS <= h < 90 and not option_path
    if h < EARLY_MIN_DAYS and not option_path:
        if not e.get("diagnostic"):
            raise ValueError(f"STOP: only {h} days of holder-earnings history (< {EARLY_MIN_DAYS}, counted from the first non-zero day); "
                             "no defaults table, cannot value from cash flows")
        flags.append(f"DIAGNOSTIC ONLY: {h} days of history (< {EARLY_MIN_DAYS}) - this is not a valuation")
    track = 0.0
    if h >= 365: e0_window, E0c = "365d TTM", cbw.get("365d")
    elif h >= 90 and not option_path:
        d90, d14 = cbw.get("90d"), cbw.get("14d")
        if d90 is None or d14 is None:
            raise ValueError("STOP: a short history (90-364 days) needs both the 90d and the 14d annualised windows "
                             "(engine.py windows gives both; or core_by_window.90d and core_by_window.14d)")
        E0c = min(d90, d14)
        e0_window = f"lower of 90d ${d90:,.2f}m and last-14d ${d14:,.2f}m annualised, short history"
    elif h >= 90: e0_window, E0c = "90d annualised, option path", cbw.get("90d")
    elif early:
        sl, d14 = cbw.get("since_launch"), cbw.get("14d")
        if sl is None or d14 is None:
            raise ValueError("STOP: early stage (30-89 days) needs both the since-launch and the 14d annualised windows "
                             "(engine.py windows gives both; or core_by_window.since_launch and core_by_window.14d)")
        E0c = min(sl, d14)
        e0_window = f"lower of since-launch {h}d ${sl:,.2f}m and last-14d ${d14:,.2f}m annualised, early stage"
        track = bp(TRACK_MAX * (90 - h) / (90 - EARLY_MIN_DAYS))
        flags.append(f"EARLY STAGE: {h} days of holder earnings. E0 is the lower of the since-launch and last-14-day run-rates "
                     f"(${E0c:,.2f}m), and a {track:.2%} track-record premium is added to near-term Ke (D22). Provisional: "
                     "re-run at 90 days")
        if d14 < 0.5 * sl: flags.append(f"LAUNCH DECAY: last 14 days at {d14 / sl:.0%} of the since-launch average")
    else: e0_window, E0c = f"{h}d, DIAGNOSTIC / option path", cbw.get("30d", 0.0) or 0.0
    if E0c is None: raise ValueError(f"STOP: earnings window for {e0_window} missing from core_by_window")
    # pause check on the holder series itself (before any revenue cap)
    rr = (cbw["30d"] / E0c) if (cbw.get("30d") is not None and E0c) else None
    paused = bool(rr is not None and E0c > 0 and rr < PAUSE_RATIO) or bool(w and w.get("paused"))
    if paused and not option_path and not e.get("pause_override_reason"):
        raise ValueError(f"STOP: holder cash flow has stopped (30d run-rate {(rr or 0):.0%} of E0 ${E0c:,.1f}m): buybacks/distributions "
                         "look paused. Add an option block {\"type\": \"paused_buyback\", \"holder_rev_hist\": <E0>} to value the restart, "
                         "or set earnings.pause_override_reason if it is a data artefact")
    if rr is None and not option_path: flags.append("PAUSE CHECK NOT RUN: no 30d window supplied")
    # revenue check (D19): holder flow cannot outrun the protocol revenue that funds it. Buybacks can run weeks behind
    # revenue, so the holder series alone can look healthy after revenue has collapsed (PONS, Oct 2026).
    E0_rule, capped, supported = E0c, False, None
    rc = e.get("revenue_check")
    valuing = not option_path and h >= EARLY_MIN_DAYS
    if rc and valuing:
        rwin = "14d" if rc.get("revenue_14d") is not None else "30d"
        rev, share = rc.get(f"revenue_{rwin}"), rc.get("holder_share")
        meas = rc.get("holder_share_measured", share)
        if meas is not None and meas > SHARE_TOL:
            flags.append(f"HOLDER FLOW ABOVE REVENUE: holders received {meas:.0%} of protocol revenue. The excess is funded from "
                         "outside revenue (reserves, or buybacks catching up), so it isn't recurring business earnings: the revenue "
                         "check counts at most 100%" + ("" if h < 365 else "; from a year of history TTM is kept, so check the methodology"))
        if share is not None: share = min(share, 1.0)
        if rev is not None and share is not None:
            supported = rev * share
            if h < 365 and supported < E0c:
                E0c, capped = supported, True
                e0_window += f"; capped at what the last {rwin} of protocol revenue supports"
                flags.append(f"REVENUE CHECK: holder earnings on the history rule (${E0_rule:,.2f}m) exceed what the last {rwin} of "
                             f"protocol revenue supports (${rev:,.2f}m x {share:.0%} holder share = ${supported:,.2f}m); E0 set to "
                             f"${supported:,.2f}m. Buybacks can run behind revenue")
            elif h >= 365 and supported < REV_FALL_RATIO * E0c:
                flags.append(f"REVENUE FALLING: the last {rwin} of protocol revenue supports ${supported:,.2f}m of holder earnings, "
                             f"under half of TTM (${E0c:,.2f}m). TTM is kept (calibrated rule); consider overriding E0_core")
    elif valuing and h < 365:
        flags.append("REVENUE CHECK NOT RUN: under a year of history; run scripts/revenue_stack.py and add its revenue_check "
                     "block to facts.earnings, so lagging buybacks can't hide a fall in revenue")
    d7 = cbw.get("7d")
    decaying = bool(valuing and d7 is not None and E0c > 0 and d7 < DECAY_RATIO * E0c)
    if decaying:
        flags.append(f"DECAYING: the 7-day run-rate (${d7:,.2f}m) is under half of E0 (${E0c:,.2f}m); bracket with E0_core = {d7:.2f}")
    E0o = e.get("other", 0.0)
    row("D19", "E0 core (holder earnings, $m)", {"all": f"{E0c:,.2f}"},
        f"clean holder earnings; window = {e0_window}; history {h}d from first non-zero day" + (f"; 30d run-rate {rr:.0%} of E0" if rr is not None else "")
        + (f"; 7d run-rate {d7 / E0c:.0%} of E0" if (d7 is not None and E0c) else ""),
        "METHOD (TTM) + FALLBACK (90-364d: lower of 90d and 14d; 30-89d: lower of since-launch and 14d) + HEURISTIC (revenue cap under 365d)",
        e.get("source", ""))
    if E0o: row("D20", "E0 other (own-path yield, $m)", {"all": f"{E0o:,.2f}"}, "collateral x T-bill x capture, own growth path", "METHOD", e.get("other_source", ""))
    # --- earnings counted once: E0 is holder revenue, i.e. already what holders receive ---
    if not option_path and f.get("payout", 1.0) < 1 and not f.get("payout_reason"):
        flags.append(f"PAYOUT BELOW 100% ON HOLDER EARNINGS: E0 is holder revenue, which is already what holders receive, so payout "
                     f"{f['payout']:.0%} applies a holder share twice. Use payout 1.0, or give payout_reason if E0 was built from a "
                     "broader earnings figure")
    # --- D23 holder rights: how the benefit reaches holders and what a holder must do to get it ---
    rt = f.get("rights")
    if rt:
        acc = rt.get("access", "all_holders")
        row("D23", "Holder rights (benefit form / access)", {"all": f"{rt['benefit_form']} / {acc}"},
            "documented: how holder earnings reach holders, and whether staking or locking is required to receive them",
            "DOCUMENTED (from the docs, not an estimate)", rt.get("source", ""))
        if acc != "all_holders":
            flags.append(f"BENEFIT REQUIRES {'STAKING' if acc == 'stakers_only' else 'LOCKING'}: only {acc.split('_')[0]} receive holder "
                         "earnings. The value per token is the network average across all tokens; an unstaked token receives nothing until "
                         "it is staked or locked (check lock-ups, unbonding and slashing)")
    elif not option_path:
        flags.append("HOLDER RIGHTS NOT RECORDED: record how holders receive the benefit and whether staking or locking is required "
                     "(facts.rights: benefit_form, access), from the money map")
    # --- moat / ROE (D6-D8) ---
    m = moat(f["moat"]["segments"])
    lo, hi = m["band"]
    edges = [b[0] for b in ROE_BANDS if b[0] > 0]
    m["borderline"] = any(abs(m["helmer"] - e_) <= BORDER for e_ in edges) or abs(m["porter"] - PORTER_LOW_MAX) <= BORDER
    roe = roe_from_band(lo, hi, m["porter"])
    row("D6", "Moat scores (Helmer 0-3 / Porter 0-2)", {"all": f"{m['helmer']:.2f} / {m['porter']:.2f} ({m['porter_class']} Porter)"},
        "segment scores, weight-blended; documented scores if supplied, else rubric D6" + ("; BORDERLINE (within 0.05 of a band edge): report the adjacent band" if m["borderline"] else ""),
        "METHOD (Helmer 7 Powers / Porter 5 Forces); rubric HEURISTIC", f["moat"].get("source", ""))
    row("D7", "ROE band", {"all": f"{lo:.0%}-{hi:.0%}"}, "Helmer x Porter band table (METHOD.md section 7.2)", "CALIBRATED (band table)", "band table")
    # --- market + levers (D1-D5) ---
    mk = f["market"]
    MI = market_inputs(mk)
    tr, cyc, cyc_how = MI["tr"], MI["cyc"], MI["how"]
    base_m, base_how, mflags = market_base(MI)
    flags += mflags
    mkt = {"base": base_m, "bull": bp(base_m + MARKET_SPREAD), "bear": bp(base_m - MARKET_SPREAD)}
    if MI["basis"] == "fallback_perps": flags.append("PERPS FALLBACK: trailing CAGR, cycle factor and DEX share are mid-2026 constants; g1 is not informed by live data")
    if MI["basis"] == "none":
        flags.append("NO MARKET SERIES: no category series was supplied (market.basis none), so market growth is a flat default "
                     "(0%; bull +10%, bear -10%) and g1 rests on the share lever alone. Add market_stats.py output, or override "
                     "scenarios.*.g1 with your view")
    row("D2", "Market CAGR", {k: mkt[k] for k in SCEN}, f"base = nearest 5pp of {base_how}, capped +/-20%; bull +10pp, bear -10pp (basis {MI['basis']})",
        "CALIBRATED (a third of trailing, +/-20%, +/-10pp) + HEURISTIC (structural-decline test)", MI["src"])
    row("D3", "Market cycle factor (year-1 level / TTM level)", {"all": f"{cyc:.4f}"}, cyc_how,
        "CALIBRATED (post-peak reset)", MI["src"])
    dex0 = MI["dex0"]
    strong = m["band_index"] <= 2
    mult = SHARE_MULT_STRONG if strong else SHARE_MULT_OTHER
    sh0 = f["share"]["share_0"]
    g1 = {}; raw = {}
    for s in SCEN:
        g, X, shT = lever_g1(mkt[s], cyc, N, dex0, DEX_TARGET[s] if dex0 else None, sh0, mult[s], f.get("take_rate_mult", {}).get(s, 1.0))
        raw[s] = g
        trace.append(f"{s}: {cyc:.4f} x (1+{mkt[s]:.2f})^{N-1}" + (f" x {DEX_TARGET[s]:.2f}/{dex0:.3f}" if dex0 else "") +
                     f" x {shT:.3f}/{sh0:.3f} = {X:.4f} -> (1+g)^(1/{N}) - 1 = {g:.2%}")
    g1["base"], g1["bull"] = r5(raw["base"]), r5(raw["bull"])
    g1["bear"] = r5(mkt["bear"])                                   # D1 bear: grows with its market (moat becomes ordinary)
    if g1["bear"] > g1["base"]: g1["bear"] = g1["base"]            # tie-break: keep bear <= base <= bull
    if g1["bull"] < g1["base"]: g1["bull"] = g1["base"]
    row("D4", "DEX share of market: today -> target", {s: (f"{dex0:.1%}->{DEX_TARGET[s]:.0%}" if dex0 else "n/a (on-chain native)") for s in SCEN},
        "perps fallback basis only: targets 10/30/35%", "CALIBRATED (perps); lever = 1 elsewhere", MI["src"] if dex0 else "")
    row("D5", "Protocol share of DEX/category: today -> target", {s: f"{sh0:.1%}->{min(sh0*mult[s],SHARE_CAP):.1%}" for s in SCEN},
        f"x{mult['bear']}/x{mult['base']}/x{mult['bull']} ({'strong moat set' if strong else 'weaker moat set'})",
        "CALIBRATED ratios (strong set); weaker set HEURISTIC", f["share"].get("source", ""))
    row("D1", "g1 (7y core earnings CAGR)", {s: g1[s] for s in SCEN},
        "base/bull: lever product, nearest 5pp (raw " + ", ".join(f"{s} {raw[s]:.1%}" for s in SCEN) + "); bear: bear market CAGR",
        "METHOD (three levers) + CALIBRATED cycle + HEURISTIC rounding and bear rule", "; ".join(trace))
    g_other = {s: mkt[s] for s in SCEN} if E0o else {s: 0.0 for s in SCEN}
    if E0o: row("D20", "g_other (own-path growth)", g_other, "own-path yield grows with the market CAGR per scenario", "METHOD", "market CAGR (D2)")
    # --- Ke (D9-D13) ---
    rf, erp = f["rf"]["value"], f["erp"]["value"]
    reg = dict(REG[rk["reg_class"]])
    if rk.get("formal_action"): reg = {s: reg[s] + REG_FORMAL_ACTION for s in SCEN}
    drivers = sum(bool(rk.get(k)) for k in ("concentrated_control", "team_can_change_rules", "no_legal_wrapper"))
    gov = bp(GOV_FULL * drivers / 3 + (GOV_NO_OFFSET if drivers and not rk.get("alignment_offset") else 0.0))
    align = ALIGN[rk["routing"]]
    align_how = f"routing = {rk['routing']}"
    if option_path:
        ron = f["option"].get("routing_on", ROUTING_ON_DEFAULT)
        align = ALIGN[ron]
        align_how = (f"switched-on state: routing_on = {ron} (today's routing {rk['routing']!r} is priced by the activation "
                     "probabilities, not by Ke)")
        if not f["option"].get("condition"):
            flags.append("NO STATED CONDITION: name the mechanism that would route this revenue to holders (a governance proposal, a "
                         "documented programme, a paused buyback that can resume) with its source, in option.condition. Without one "
                         "the framework can't establish a value from cash flows: the switched-on value is hypothetical")
    age = rk["age_months"] if "age_months" in rk else months_between(rk["launch_date"], f["as_of"][:10])
    first_hr = (w or {}).get("first_nonzero_day") or e.get("first_holder_revenue_day")
    first_fees = rk.get("first_fees_day")
    if rk.get("launch_date") and first_fees and rk["launch_date"] > first_fees:
        flags.append(f"AGE CHECK: launch_date {rk['launch_date']} is after the first fees day {first_fees}; age should run "
                     "from the earlier date")
    elif rk.get("launch_date") and first_hr and rk["launch_date"] == first_hr and not first_fees:
        flags.append("NOTE: launch_date equals the first holder-revenue day. Fine if holders earned from launch (e.g. HYPE); "
                     "otherwise use the first fees day or mainnet date (risk.first_fees_day)")
    sc_now = sc_premium(age, rk.get("major_exploit", False))
    row("D9", "rf / ERP", {"all": f"{rf:.2%} / {erp:.2%}"}, "US 10y Treasury (latest close <= as_of) / Damodaran US ERP (sovereign-CDS column)",
        "METHOD (sources); ERP column HEURISTIC", f"{f['rf'].get('source','')}; {f['erp'].get('source','')}")
    row("D10", "Regulatory premium", {s: reg[s] for s in SCEN}, f"class {rk['reg_class']}" + (" + formal action +2pp" if rk.get("formal_action") else ""),
        "CALIBRATED (no-KYC class) + METHOD (+2pp on formal action); regulated class HEURISTIC", rk.get("reg_source", ""))
    row("D11", "Governance premium", {"all": gov}, f"1.25% x drivers/3 ({drivers}/3) + 0.50% if no alignment offset", "CALIBRATED (1.25%); scaling HEURISTIC", rk.get("gov_source", ""))
    row("D12", "Alignment premium", {"all": align}, align_how, "CALIBRATED (0% mechanical); other classes HEURISTIC", rk.get("align_source", ""))
    row("D13", "Smart-contract premium now -> floor", {"all": f"{sc_now:.2%} -> {SC_FLOOR:.2%} (age {age} months)"},
        "max(0.5%, 2.0% - 1.5% x age/36); exploit >= $10m resets to 2.0%; explicit period discounted at constant near-term Ke",
        "CALIBRATED decay; exploit reset METHOD", (f"launch {rk['launch_date']}; " if rk.get("launch_date") else "") + rk.get("age_source", ""))
    if track:
        row("D22", "Track-record premium (near-term Ke only)", {"all": track},
            f"{TRACK_MAX:.1%} x (90 - {h}) / 60 days of history; 0 from 90 days; not in Ke_T", "HEURISTIC (early stage)",
            f"{h} days of holder earnings")
    keT = {s: rf + erp + reg[s] + gov + align + SC_FLOOR for s in SCEN}
    # --- ROE with no-moat floor (D8) ---
    roe_f = {}
    for s in SCEN:
        roe_f[s] = roe[s] if roe[s] > keT[s] else keT[s]       # no moat: competition drags ROE to Ke -> P/E = 1/Ke
    floored = [s for s in SCEN if roe_f[s] != roe[s]]
    if floored:
        flags.append(f"NO MOAT in {'/'.join(floored)}: band ROE below the cost of equity, so ROE = Ke_T there and P/E = 1/Ke_T. "
                     "ROE then follows Ke (a riskier scenario shows a higher ROE); growth adds no value in those scenarios")
    row("D8", "Stabilised ROE", {s: roe_f[s] for s in SCEN}, "bear = band low; base = low + span/3; bull = low + span x (1 - Porter/2); nearest 5pp; floor at Ke_T",
        "HEURISTIC position (band CALIBRATED)", "band table + moat scores")
    # --- BORDERLINE moat: compute the adjacent band, ready to run as a bracket (SKILL.md step 8) ---
    adj = None
    if m["borderline"]:
        adj = adjacent_band(m, keT, mkt, cyc, N, dex0, sh0, f.get("take_rate_mult", {}))
        flags.append(f"BORDERLINE MOAT: Helmer {m['helmer']:.2f} / Porter {m['porter']:.2f} is within {BORDER} of a band edge. "
                     f"Adjacent band {adj['band'][0]:.0%}-{adj['band'][1]:.0%} ({adj['set']} share set): ROE "
                     + "/".join(f"{adj['roe'][s]:.1%}" for s in SCEN) + ", g1 " + "/".join(f"{adj['g1'][s]:.0%}" for s in SCEN)
                     + " (bear/base/bull). Run it as a bracket with the overrides listed in judgement.md")
    # --- supply (D14-D15) ---
    sp = f["supply"]
    es = (EMISSIONS_DISCIPLINED if sp.get("self_sustaining") and sp.get("team_largest_holder") else EMISSIONS_UNDISCIPLINED) if sp.get("unissued", 0) > 0 else {s: 0.0 for s in SCEN}
    row("D14", "Future-emission inclusion (share of unissued)", {s: es[s] for s in SCEN},
        f"unissued {sp.get('unissued',0):,.1f}m; disciplined & self-sustaining -> 60/10/0%; else 100/60/10%; release 75% by year 7",
        "CALIBRATED set + METHOD (self-sustaining test); other set HEURISTIC", sp.get("source", ""))
    row("D15", "Supply basis", {"all": f"S0 {sp['S0']:,.1f}m + vesting {sum(sp.get('vest', [])):,.1f}m" + (" (CIRCULATING FALLBACK)" if sp.get("fallback_circulating") else "")},
        "every vested token counts, claimed or not; committed vesting in full", "METHOD", sp.get("source", ""))
    row("D16", "Terminal growth gT", {s: G_TERMINAL[s] for s in SCEN}, "long-run nominal growth anchor", "CALIBRATED", "constant")
    row("D17", "Scenario weights", {s: WEIGHTS[s] for s in SCEN}, "20/60/20", "JUDGEMENT (not empirical)", "constant")
    row("D18", "Horizon", {"all": N}, "7 years explicit, then steady-state P/E", "METHOD", "constant")
    # --- engine config ---
    form = (rt or {}).get("benefit_form")
    bb = sp.get("buyback", {"mode": BENEFIT_FORMS.get(form, "fair_value")})
    if form in ("distribution", "staking_distribution") and bb.get("mode", "fair_value") != "none":
        flags.append(f"BENEFIT IS PAID AS CASH ({form}) but supply.buyback.mode is {bb.get('mode', 'fair_value')!r}: buybacks shrink the "
                     "supply in the model and cash payouts don't. Use mode none unless tokens are also bought back")
    if bb.get("years") is not None and bb["years"] < N and bb.get("continue_after"):
        flags.append(f"COMMITMENT ASSUMED TO CONTINUE: buybacks are committed for {bb['years']:g} year(s), and this run assumes they "
                     "continue after that (continue_after true). Run the committed-only bracket with "
                     + json.dumps({f"scenarios.{s}.supply.buyback.continue_after": False for s in SCEN}))
    scen = {}
    for s in SCEN:
        scen[s] = dict(prob=WEIGHTS[s], g1=g1[s], g_other=g_other[s], gT=G_TERMINAL[s], roe=roe_f[s], payout=f.get("payout", 1.0),
                       ke=dict(rf=rf, erp=erp, reg=reg[s], gov=gov, align=align, sc_now=sc_now, sc_floor=SC_FLOOR, sc_years=None,
                               **({"track": track} if track else {})),
                       supply=dict(vest=list(sp.get("vest", [])), unissued=sp.get("unissued", 0.0), emission_share=es[s],
                                   emission_release_by_T=EMISSION_RELEASE_BY_T, floor_frac=sp.get("floor_frac", 0.05),
                                   buyback=copy.deepcopy(bb)))
    cfg = dict(protocol=f["protocol"], as_of=f["as_of"], price=f["price"], E0_core=E0c, E0_other=E0o,
               E0_core_label=f"holder earnings, {e0_window}", E0_other_label="own-path yield", N=N, gT=G_TERMINAL["base"], anchor="base", S0=sp["S0"],
               scenarios=scen, data=dict(history_days=h, e0_window=e0_window, annualised=True, total1y_raw=False),
               judgement=dict(engine="defaults", confirmed=False, table=T, moat=m, overrides={}, market_basis=MI["basis"],
                              **({"adjacent_band": adj} if adj else {})))
    for k in ("price_check", "is_l1", "supply_fallback_circulating", "e0_excludes_company_share", "align_reason", "pe_method_year", "sens_g", "option"):
        if k in f: cfg[k] = copy.deepcopy(f[k])
    cfg["data"].update(paused=paused, run_rate_30d_vs_e0=rr, diagnostic=bool(e.get("diagnostic")) and h < EARLY_MIN_DAYS,
                       early_stage=early, decaying=decaying, run_rate_7d=d7, e0_history_rule=E0_rule,
                       revenue_capped=capped, revenue_supported=supported,
                       pause_override_reason=e.get("pause_override_reason"))
    if option_path:
        op = cfg["option"]
        if not op.get("activation"):
            op["activation"] = copy.deepcopy(OPTION_DEFAULT_CASES.get(op.get("type"), []))
            T.append(dict(id="D21", input="Option activation cases (p, delay)",
                          values={"all": "; ".join(f"{c['label']}: {c['p']:.0%}, {c['delay_years']}y" for c in op["activation"])
                                  + f"; never {1 - sum(c['p'] for c in op['activation']):.0%}"},
                          rule="placeholder cases by option type, not estimates; the main outputs are the value if switched on "
                               "today and the probability the price implies",
                          cls="JUDGEMENT (placeholder: replace with your own cases in option.activation)", source="constant"))
            flags.append("OPTION DEFAULT CASES: activation probabilities are placeholders, not estimates")
        # the implied-probability grid always includes switching on today, plus the delays of the cases
        op.setdefault("implied_delays", sorted(set(OPTION_IMPLIED_DELAYS) | {c.get("delay_years") for c in op["activation"]
                                                                             if isinstance(c.get("delay_years"), (int, float))}))
    cfg["judgement"]["flags"] = flags
    cfg["judgement"]["version"] = __version__
    return cfg

# keys an override may add even though the defaults step does not write them
OPTIONAL_KEYS = {"years", "continue_after", "tokens_per_yr", "sens_weights", "sens_ke_shift", "sens_g", "activation", "implied_delays",
                 "routing_on", "base_label",
                 "pe_method_year", "align_reason", "option", "price_check", "is_l1"}

def set_path(d, path, val):
    """Set a dotted path. Unknown keys are rejected (a typo must never become a silent no-op override)."""
    ks = path.split(".")
    if not isinstance(val, (int, float, str, bool, list, dict)) and val is not None:
        raise cm.InputError(f"override {path!r}: unsupported value {val!r}")
    for i, k in enumerate(ks[:-1]):
        if not isinstance(d, dict) or k not in d:
            raise ValueError(f"override {path!r}: unknown key {k!r} at {'.'.join(ks[:i]) or 'top level'}; "
                             f"valid: {sorted(d) if isinstance(d, dict) else 'n/a'}")
        d = d[k]
    if not isinstance(d, dict): raise cm.InputError(f"override {path!r}: {'.'.join(ks[:-1])} is a value, not a section")
    if ks[-1] not in d and ks[-1] not in OPTIONAL_KEYS:
        raise ValueError(f"override {path!r}: unknown key {ks[-1]!r}; valid at {'.'.join(ks[:-1]) or 'top level'}: {sorted(d)}")
    d[ks[-1]] = val

def apply_overrides(cfg, ov):
    """User overrides: {"scenarios.base.g1": 0.30, ...}. Recorded in the judgement block; confirmed flag set by the user."""
    for p, v in ov.items():
        if p == "confirmed": continue
        set_path(cfg, p, v); cfg["judgement"]["overrides"][p] = v
    if ov.get("confirmed"): cfg["judgement"]["confirmed"] = True
    return cfg

def fmtv(v):
    """Rates are stored as fractions (|v| <= 2.5); money/counts are passed as strings."""
    if isinstance(v, bool) or not isinstance(v, (int, float)): return str(v)
    if isinstance(v, int): return str(v)
    if v == 0: return "0%"
    return f"{v * 100:.2f}".rstrip("0").rstrip(".") + "%"

def to_md(cfg):
    J = cfg["judgement"]
    L = [f"# Judgement table - {cfg['protocol']} - {cfg['as_of']} (protocol-valuation {__version__})",
         "**Confirm or override each row before valuation** (overrides: JSON of dotted paths, e.g. `{\"scenarios.base.g1\": 0.30, \"confirmed\": true}`).",
         f"Status: {'CONFIRMED by user' if J['confirmed'] else 'NOT YET CONFIRMED'}" + (f"; overrides: {J['overrides']}" if J['overrides'] else ""), ""]
    if J.get("flags"): L += ["**Flags:**"] + [f"- {x}" for x in J["flags"]] + [""]
    if J.get("adjacent_band"):
        a = J["adjacent_band"]
        L += [f"**Adjacent band (BORDERLINE moat):** {a['band'][0]:.0%}-{a['band'][1]:.0%}, {a['set']} share set. Run it as a bracket: "
              "save these overrides to a file and re-run this step with `--overrides`.", "", "```json", json.dumps(a["overrides"], indent=1), "```", ""]
    L += [
         "| Id | Input | Bear | Base | Bull | Rule applied | Class | Source / arithmetic |", "|---|---|---|---|---|---|---|---|"]
    for r in J["table"]:
        v = r["values"]
        b = [fmtv(v["all"])] * 3 if "all" in v else [fmtv(v[s]) for s in SCEN]
        L.append(f"| {r['id']} | {r['input']} | {b[0]} | {b[1]} | {b[2]} | {r['rule']} | {r['cls']} | {r['source']} |")
    m = J["moat"]
    L += ["", "**Moat segments**", "", "| Segment | Weight | Helmer | Porter | Scores from |", "|---|---|---|---|---|"]
    for s in m["segments"]: L.append(f"| {s['name']} | {s['weight']} | {s['helmer']:.2f} | {s['porter']:.2f} | {s['source'][0]} / {s['source'][1]} |")
    L += ["", "Model output of the defaults step under stated facts - not financial advice."]
    return "\n".join(L)

def main(argv):
    f = cm.load_json(argv[1] if len(argv) > 1 else None); cfg = build(f)
    ov_path, md_path, json_path = cm.arg(argv, "--overrides"), cm.arg(argv, "--md"), cm.arg(argv, "--json")
    if ov_path:
        ov = cm.load_json(ov_path)
        if not isinstance(ov, dict): raise cm.InputError("overrides must be a JSON object of dotted paths")
        apply_overrides(cfg, ov)
    md = to_md(cfg)
    if md_path: cm.write_text(md_path, md + "\n")
    if json_path: cm.write_json(json_path, cfg, indent=1, sort_keys=True)
    print(md)
    return cfg

if __name__ == "__main__":
    cm.cli(main, sys.argv)

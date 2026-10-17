#!/usr/bin/env python3
"""Protocol valuation engine (protocol-valuation 6.6.0): derived (not borrowed) multiples, two-stage per-token DCF.

Values a token from the cash that reaches holders, discounted at a cost of equity built layer by layer,
with the terminal multiple derived from the protocol's own economics (steady-state P/E), never borrowed from peers.

  Earnings   E_t   = Ec0*(1+g1)^t + Eo0*(1+g_other)^t      core (growing) + own-path (e.g. collateral yield)
  Cash       C_t   = payout * E_t while buybacks/distributions are active in year t, else 0
  Ke path    Ke_t  = rf + ERP + reg + gov + align + sc_t
                     sc_years = None (default from the defaults step): sc_t = sc_now for the whole explicit period
                     sc_years = x: sc_t falls linearly from sc_now to sc_floor over x years (mid-year t-0.5)
                     DF_t = prod_{u<=t} (1 + Ke_u)
  Terminal   Ke_T  = layers with sc_floor;  PE_T = (1 - gT/ROE) / (Ke_T - gT)   (steady-state P/E; gT per scenario)
  Supply     S_t   = S_{t-1} + vest_t + emissions_t - b_t,  b_t = C_t / P_t  (P_t = projected buyback price;
                     mode fair_value | constant_pe | fixed_tokens | none), floored at floor_frac * S0
  Holder     f_t   = f_{t-1} * S_{t-1} / (S_{t-1} + vest_t + emissions_t),  f_0 = 1/S0  (pro-rata holder's share)
  Method 1   DCF   = sum_t f_t*C_t/DF_t + f_N*PE_T*E_N/DF_N    (terminal value only if payouts continue after N)
  Why f_t: a holder who takes part pro rata in every buyback receives the buyback cash and keeps the same share,
  so buyback cash IS the distribution; also crediting the shrunk supply would count it twice. S_t drives EPS_t,
  methods 2-3 and the non-seller check FV_hold = PE_T*E_N/S_N/DF_N, which equals the DCF when buybacks run at fair value.
  Method 2   PE_T * EPS_{t*}   (t* = pe_method_year; undiscounted)
  Method 3   earnings yield EY_t = EPS_t / price
  PW         sum prob_i * FV_i;  break-even g1 = core growth that sets the anchor DCF equal to price.

Option path (cfg has "option"): E0_on = fees_ttm * take_rate | holder_rev_hist (core only);
  OV = sum_j p_j * FV_on / (1+Ke_now)^d_j;  implied activation probability by bisection.

Usage:  python3 engine.py defaults facts.json [--overrides ov.json] [--md judgement.md] [--json inputs.json]
        python3 engine.py windows summary.json [--as-of ISO]       (DefiLlama summary/fees JSON -> E0 windows, complete days only)
        python3 engine.py inputs.json [--md valuation.md] [--json valuation.json]
Units:  earnings in $m, supplies in m tokens -> $/token. Standard-library Python 3.8+ only, no network access.
"""
import json, sys, math, os

__version__ = "6.6.0"
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as cm   # shared input validation and CLI error handling

# ---------------- formatting ----------------
def money(x, sig=4):
    """Significant-figure dollar formatting: never prints $0 for a sub-$1 value."""
    if x is None: return "n/a"
    a = abs(x)
    if a >= 1000: t = f"{a:,.0f}"
    elif a >= 1: t = f"{a:,.2f}"
    elif a == 0: t = "0"
    else: t = f"{a:.{sig - 1 - math.floor(math.log10(a))}f}"
    return ("-$" if x < 0 else "$") + t

def num(x, d=1): return "n/a" if x is None else f"{x:,.{d}f}"

# ---------------- data helpers (gate) ----------------
PAUSE_RATIO = 0.10      # 30d run-rate below 10% of the E0 window -> holder cash flow has stopped (paused / switched off)
DECAY_RATIO = 0.50      # 7d run-rate below 50% of E0 -> flagged "decaying"
EARLY_MIN_DAYS = 30     # early-stage valuations need at least this many days of holder earnings (D19/D22)
LOW_LAST_DAY = 0.50     # last day below 50% of the previous 7-day average -> flagged (the source may not have finished it)
# (the unpublished-days rule, cm.UNPUBLISHED_MAX, lives in common.py: windows, revenue_stack and market_stats share it)

def _as_of_ts(as_of):
    """ISO 8601 (date or datetime; naive = UTC) or unix seconds -> unix seconds. None = now."""
    if as_of is None: return datetime.now(timezone.utc).timestamp()
    if isinstance(as_of, (int, float)): return float(as_of)
    dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()

def e0_windows(chart, as_of=None):
    """Annualised holder-earnings windows from a DefiLlama totalDataChart [[unix_ts, usd], ...] -> $m.
    - Complete UTC days only: the day containing as_of (default: now) and anything later is dropped.
    - Not yet published: if the source has no row for the last 1-2 complete days (DefiLlama posts a day late), the
      windows end on its last row (`windows_end`) instead of counting those days as zero. Flagged.
    - Calendar windows: a 30d window is the 30 calendar days ending on `windows_end`; missing days inside count as 0
      and are reported. A last day far below the week before is flagged (the source may not have finished it).
    - history_days counts from the FIRST NON-ZERO day (leading zero rows before a fee switch are not history).
    - E0 rule (D19): 365d window if history >= 365 days; 90-364 days: the lower of the 90d and 14d run-rates; EARLY STAGE
      (30-89 days): the lower of the since-launch average and the last 14 days. Both short rules take the lower run-rate
      (conservative: catches launch spikes and decay) and meet at 90 days, so E0 does not jump there. Under 30 days none (STOP).
    Never use DefiLlama total1y raw: for a young protocol it covers only the days that exist."""
    pts, notes = cm.series(chart, "totalDataChart")
    by_day = {}
    for t, v in pts:
        d = int(t) // 86400
        by_day[d] = by_day.get(d, 0.0) + v
    if not by_day: raise ValueError("STOP: empty totalDataChart (no fee data)")
    clock_last = int(_as_of_ts(as_of) // 86400) - 1                # last complete UTC day by the clock
    last, gap, pub_flag = cm.published_end(by_day, clock_last)    # last day to measure to
    if last is None: raise ValueError("STOP: no complete days of data before as_of")
    flags = [pub_flag] if pub_flag else []
    days = sorted(d for d in by_day if d <= last)
    nz = [d for d in days if by_day[d] != 0]
    iso = cm.iso_day
    out = {"last_complete_day": iso(clock_last), "windows_end": iso(last), "first_row_day": iso(days[0]),
           "first_nonzero_day": iso(nz[0]) if nz else None,
           "history_days": (last - nz[0] + 1) if nz else 0,
           "partial_or_future_rows_dropped": sum(1 for d in by_day if d > clock_last), "notes": notes}
    prev7 = sum(by_day.get(d, 0.0) for d in range(last - 7, last)) / 7
    if last in by_day and prev7 > 0 and by_day[last] < LOW_LAST_DAY * prev7:
        flags.append(f"LAST DAY LOW: {iso(last)} is {by_day[last] / prev7:.0%} of the previous 7-day average; if the source had "
                     f"not finished that day, re-run with --as-of {iso(last)}T00:00:00Z")
    def ann(n):
        if out["history_days"] < n: return None
        return sum(by_day.get(d, 0.0) for d in range(last - n + 1, last + 1)) / n * 365 / 1e6
    for n in (7, 14, 30, 90, 365): out[f"{n}d"] = ann(n)
    out["since_launch"] = ann(out["history_days"]) if out["history_days"] > 0 else None
    out["missing_days_last_365"] = sum(1 for d in range(last - 364, last + 1) if d not in by_day and d >= (nz[0] if nz else last))
    h = out["history_days"]
    if h >= 365: out["e0_window"], e0 = "365d", out["365d"]
    elif h >= 90:
        e0 = min(out["90d"], out["14d"])
        out["e0_window"] = "short: " + ("90d" if e0 == out["90d"] else "last 14d") + ", the lower of the two"
    elif h >= EARLY_MIN_DAYS:
        e0 = min(out["since_launch"], out["14d"])
        out["e0_window"] = "early: " + (f"since launch ({h}d)" if e0 == out["since_launch"] else "last 14d") + ", the lower of the two"
    else: out["e0_window"], e0 = None, None
    out["flags"] = flags
    out["e0"] = e0
    out["run_rate_30d_vs_e0"] = (out["30d"] / e0) if (e0 and out["30d"] is not None) else None
    out["decaying"] = bool(e0 and out["7d"] is not None and out["7d"] < DECAY_RATIO * e0)
    out["paused"] = bool(e0 and e0 > 0 and out["30d"] is not None and out["30d"] < PAUSE_RATIO * e0)
    return out

def gate(cfg, warnings):
    """History gate. <30 days: STOP. 30-89 days: EARLY STAGE (only when the defaults step marked it). 90-365 days:
    annualised from the daily chart, flagged SHORT HISTORY."""
    d = cfg.get("data")
    if d is None:
        warnings.append("data gate not recorded (cfg.data missing): history length and E0 window unknown")
        return
    h = d.get("history_days")
    if h is None: raise ValueError("STOP: data.history_days missing; count days in totalDataChart")
    diag = d.get("diagnostic", False)
    if h < 90:
        if d.get("early_stage") and h >= EARLY_MIN_DAYS:
            warnings.append(f"EARLY STAGE: only {h} days of holder earnings. E0 = {d.get('e0_window', '?')}; a track-record premium "
                            "is in the near-term Ke (D22). Treat the result as provisional and re-run once 90 days exist")
        elif diag:
            warnings.append(f"DIAGNOSTIC ONLY: {h} days of history (< {EARLY_MIN_DAYS}) - gate FAILED, this is not a valuation")
        else:
            raise ValueError(f"STOP: only {h} days of holder-earnings history (< {EARLY_MIN_DAYS if h < EARLY_MIN_DAYS else 90}"
                             f"{'' if h < EARLY_MIN_DAYS else ' and not built as early stage by the defaults step'}); cannot value from cash flows")
    if d.get("total1y_raw") and h < 365:
        raise ValueError(f"STOP: E0 taken from DefiLlama total1y raw with only {h} days of data; annualise the daily chart instead")
    if EARLY_MIN_DAYS <= h < 365:
        if not d.get("annualised"): raise ValueError(f"STOP: {h} days of history (< 365): E0 must be annualised from totalDataChart (set data.annualised after doing so)")
        if h >= 90: warnings.append(f"SHORT HISTORY: {h} days of holder earnings; E0 = {d.get('e0_window', '?')}")
    if d.get("paused") and "option" not in cfg and not d.get("pause_override_reason"):
        raise ValueError(f"STOP: holder cash flow has stopped (30d run-rate {d.get('run_rate_30d_vs_e0', 0):.0%} of E0): buybacks/distributions "
                         "look paused or switched off. Value it on the option path (add an option block: type paused_buyback, "
                         "holder_rev_hist = TTM) or, if the pause is a data artefact, set data.pause_override_reason")
    if d.get("paused") and d.get("pause_override_reason"):
        warnings.append(f"PAUSE CHECK OVERRIDDEN: {d['pause_override_reason']}")
    if d.get("decaying"):
        r7, e0 = d.get("run_rate_7d"), cfg.get("E0_core")
        warnings.append("DECAYING: the 7-day run-rate" + (f" (${r7:,.2f}m)" if r7 is not None else "") + " is under half of E0"
                        + (f" (${e0:,.2f}m)" if e0 is not None else "") + ", so the latest week points lower. Bracket: re-run with "
                        + (f"E0_core = {r7:.2f}" if r7 is not None else "E0_core at the 7-day run-rate"))

def check_as_of(s):
    try: datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError): raise ValueError(f"STOP: as_of {s!r} is not an ISO 8601 timestamp (e.g. 2026-10-14T09:46:49Z)")

# ---------------- core model ----------------
def ke_layers(k, sc, track=True):
    """Ke = rf + ERP + reg + gov + align + sc (+ track: early-stage track-record premium, near-term only, D22)."""
    return k["rf"] + k["erp"] + k["reg"] + k["gov"] + k["align"] + sc + (k.get("track", 0.0) if track else 0.0)

def sc_at(k, t):
    yrs = k.get("sc_years", 2.0)
    if yrs is None: return k["sc_now"]          # constant near-term premium over the explicit period
    if yrs <= 0: return k["sc_floor"]
    w = max(0.0, 1 - (t - 0.5) / yrs)
    return k["sc_floor"] + (k["sc_now"] - k["sc_floor"]) * min(1.0, w)

def _paths(E0c, E0o, N, sc, g):
    E = [E0c * (1 + g) ** t + E0o * (1 + sc.get("g_other", 0.0)) ** t for t in range(N + 1)]
    sp = sc.get("supply", {})
    vest = list(sp.get("vest", []))
    em = sp.get("emission_share", 0.0) * sp.get("unissued", 0.0) * sp.get("emission_release_by_T", 1.0) / N
    add = [0.0] + [(vest[t - 1] if t - 1 < len(vest) else 0.0) + em for t in range(1, N + 1)]
    return E, add

def _active(sc, t, N):
    """Share of year t covered by the buyback/distribution commitment: 1, 0, or the fraction of a part year
    (e.g. years = 0.54 -> year 1 gets 54% of its cash). continue_after = true keeps every year at 1."""
    bb = sc.get("supply", {}).get("buyback", {})
    yrs = bb.get("years", N)
    if bb.get("continue_after", False) or t <= yrs: return 1.0
    return max(0.0, min(1.0, yrs - (t - 1)))

def value(E0c, E0o, S0, N, gT, sc, price, g=None, ke_shift=0.0, max_iter=200):
    g = sc["g1"] if g is None else g
    gT = sc.get("gT", gT)                      # per-scenario terminal growth (defaults 3.0/3.5/4.5%)
    k = dict(sc["ke"]); k["reg"] = k["reg"] + ke_shift
    if sc["roe"] <= gT: raise ValueError(f"STOP: ROE {sc['roe']:.1%} <= gT {gT:.1%}: steady-state payout <= 0")
    keT = ke_layers(k, k["sc_floor"], track=False)   # the track-record premium is gone by the terminal year
    if keT <= gT: raise ValueError(f"STOP: Ke_T {keT:.1%} <= gT {gT:.1%}: steady-state P/E undefined")
    payout = sc.get("payout", 1.0)
    if not 0 <= payout <= 1: raise ValueError(f"STOP: payout {payout} must be in [0, 1]")
    E, add = _paths(E0c, E0o, N, sc, g)
    if E[0] <= 0: raise ValueError("STOP: E0 <= 0: no holder earnings to capitalise; use the option path")
    ke_t = [None] + [ke_layers(k, sc_at(k, t)) for t in range(1, N + 1)]
    DF = [1.0]
    for t in range(1, N + 1): DF.append(DF[-1] * (1 + ke_t[t]))
    act = [0.0] + [_active(sc, t, N) for t in range(1, N + 1)]
    C = [0.0] + [payout * E[t] * act[t] for t in range(1, N + 1)]
    D = [S0]
    for t in range(1, N + 1): D.append(D[-1] + add[t])
    pe = (1 - gT / sc["roe"]) / (keT - gT)
    tv_on = act[N] >= 1.0  # terminal value only if holders keep receiving cash through and after year N
    TV = pe * E[N] if tv_on else 0.0
    # ---- supply path with buybacks at a projected price ----
    sp = sc.get("supply", {}); bb = sp.get("buyback", {"mode": "fair_value"})
    mode = bb.get("mode", "fair_value")
    # Supply floor. fair_value: buybacks execute at the fair (cum-buyback) price, so they can never retire more than exists
    # and deep retirement is economically consistent; only a numerical floor applies (a 5% floor here bent results:
    # value jumped with growth and could rise with Ke). Other modes buy at an assumed price, so the 5% floor stays.
    floor = (1e-9 if mode == "fair_value" else sp.get("floor_frac", 0.05)) * S0
    pe0 = price * S0 / E[0]
    flags = []
    def build(P):
        S = [S0]; B = [0.0]; capped = []; noprice = []
        for t in range(1, N + 1):
            pre = S[-1] + add[t]
            if mode == "none" or C[t] == 0: b = 0.0
            elif mode == "fixed_tokens": b = bb["tokens_per_yr"]
            elif mode == "constant_pe": c = C[t] / E[t]; b = c * pre / (pe0 + c)   # P_t = PE_0 * E_t / S_t
            elif mode == "fair_value":
                if P[t] is None or P[t] <= 1e-15 * price: b = 0.0; noprice.append(t)
                else: b = C[t] / P[t]
            else: raise ValueError(f"STOP: buyback.mode {mode!r} must be fair_value | constant_pe | fixed_tokens | none")
            if pre - b < floor: capped.append(t); b = max(0.0, pre - floor)
            S.append(pre - b); B.append(b)
        return S, B, capped, noprice
    def pr_value(t, S):
        """Per-token value at end of year t (after the year-t buyback) for a holder who takes part pro rata
        in every later buyback: cash share f_u * C_u, diluted by vesting/emissions issued to others."""
        f = 1.0 / S[t]; v = 0.0; df = 1.0
        for u in range(t + 1, N + 1):
            f *= S[u - 1] / (S[u - 1] + add[u]); df *= 1 + ke_t[u]; v += f * C[u] / df
        return v + f * TV / df
    if mode == "fair_value":
        # Fixed point P_t = value per token after the year-t buyback, given the supply path the buybacks create.
        # Start from the no-retirement path (well defined, close to the answer), then iterate with damping: plain
        # iteration oscillated without converging for some time-limited commitments (found by fuzzing). If it still
        # does not converge, the scenario is valued with cash treated as a distribution (mode none) and flagged.
        S_none = [S0]
        for t in range(1, N + 1): S_none.append(S_none[-1] + add[t])
        P = [None] + [pr_value(t, S_none) for t in range(1, N + 1)]
        converged = False; it = 0
        for lam, n_it in ((1.0, 100), (0.5, 400), (0.2, 1500)):
            for _ in range(n_it):
                it += 1
                S, B, capped, noprice = build(P)
                newP = [None] + [pr_value(t, S) for t in range(1, N + 1)]
                err = max(abs(x - y) / max(abs(y), abs(x), 1e-300) for x, y in zip(newP[1:], P[1:]))
                P = [None] + [lam * x + (1 - lam) * y for x, y in zip(newP[1:], P[1:])]
                if err < 1e-11: converged = True; break
            if converged: break
        if converged:
            S, B, capped, noprice = build(P)
            Ppath = P
        else:
            flags.append(f"fair-value buyback price did not converge ({it} iterations): cash valued as a distribution "
                         "(no tokens retired) for this scenario")
            mode = "none"
            S, B, capped, noprice = build(None)
            Ppath = [None] * (N + 1)
    else:
        S, B, capped, noprice = build(None)
        Ppath = [None] + [(C[t] / B[t]) if B[t] > 0 else None for t in range(1, N + 1)]
    fv = pr_value(0, S)
    f = 1.0 / S0; pv_cash = 0.0; df = 1.0
    for u in range(1, N + 1):
        f *= S[u - 1] / (S[u - 1] + add[u]); df *= 1 + ke_t[u]; pv_cash += f * C[u] / df
    pv_tv = fv - pv_cash
    if noprice: flags.append(f"no positive fair price after the commitment ends (years {noprice}): cash treated as a distribution, no tokens retired")
    if capped: flags.append(f"buybacks capped by supply floor in years {capped}")
    deep = [t for t in range(1, N + 1) if mode == "fair_value" and B[t] > 0.95 * (S[t] + B[t])]
    if deep: flags.append(f"deep buyback in years {deep}: over 95% of supply retired (cash is most of the token's remaining value)")
    eps = [E[t] / S[t] for t in range(N + 1)]
    fv_hold = pe * E[N] / S[N] / DF[N] if tv_on else 0.0
    return dict(g1=g, gT=gT, g_other=sc.get("g_other", 0.0), roe=sc["roe"], payout_explicit=payout,
                ke=ke_layers(k, k["sc_now"]), ke_path=ke_t[1:], ke_T=keT, pe_T=pe, no_moat_pe=1 / keT,
                payout_T=1 - gT / sc["roe"], E=E, E_N=E[N], D=D, S=S, S_T=S[N], buyback_tokens=B,
                buyback_price=Ppath, eps=eps, eps_N=eps[N], pv_cash=pv_cash, pv_tv=pv_tv, fv=fv,
                fv_holder_retains=fv_hold, terminal_included=tv_on, flags=flags, buyback_mode=mode)

def breakeven_g(E0c, E0o, S0, N, gT, sc, price, lo=-0.5, hi=3.0):
    f = lambda g: value(E0c, E0o, S0, N, gT, sc, price, g=g)["fv"] - price
    if f(lo) > 0 or f(hi) < 0: return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if f(mid) < 0: lo = mid
        else: hi = mid
    return (lo + hi) / 2

SCENARIO_ORDER = ("bear", "base", "bull")

def _order(scen):
    """Put scenarios in bear/base/bull order (inputs.json is written with sorted keys). Weight vectors such as
    sens_weights [bear, base, bull] are applied positionally, so the order must be fixed."""
    keys = [k for k in SCENARIO_ORDER if k in scen] + [k for k in scen if k not in SCENARIO_ORDER]
    return {k: scen[k] for k in keys}

def validate_cfg(cfg):
    """Every number the engine uses is a finite real number in range; clean errors otherwise."""
    if not isinstance(cfg, dict): raise cm.InputError("inputs must be a JSON object (the inputs.json written by the defaults step)")
    for key in ("price", "S0", "scenarios"):
        if key not in cfg: raise ValueError(f"STOP: {key} missing")
    cm.num(cfg["price"], "price", lo=0, lo_open=True); cm.num(cfg["S0"], "S0", lo=0, lo_open=True)
    cm.num(cfg.get("E0_core", cfg.get("E0", 0.0)), "E0_core"); cm.num(cfg.get("E0_other", 0.0), "E0_other")
    cm.num(cfg.get("gT", 0.035), "gT"); cm.num(cfg.get("N", 7), "N", lo=1, hi=30)
    if not isinstance(cfg["scenarios"], dict) or not cfg["scenarios"]: raise cm.InputError("scenarios must be a non-empty object")
    for n, sc in cfg["scenarios"].items():
        for k in ("prob", "g1", "roe"): cm.num(sc.get(k), f"scenarios.{n}.{k}")
        for k in ("g_other", "payout", "gT"):
            if k in sc: cm.num(sc[k], f"scenarios.{n}.{k}")
        if sc["g1"] <= -1: raise cm.InputError(f"scenarios.{n}.g1 must be > -100%")
        ke = sc.get("ke")
        if not isinstance(ke, dict): raise cm.InputError(f"scenarios.{n}.ke missing")
        for k in ("rf", "erp", "reg", "gov", "align", "sc_now", "sc_floor"): cm.num(ke.get(k), f"scenarios.{n}.ke.{k}")
        if "track" in ke: cm.num(ke["track"], f"scenarios.{n}.ke.track", lo=0)
        if ke.get("sc_years") is not None: cm.num(ke["sc_years"], f"scenarios.{n}.ke.sc_years")
        sp = sc.get("supply", {})
        for i, v in enumerate(sp.get("vest", [])): cm.num(v, f"scenarios.{n}.supply.vest[{i}]", lo=0)
        for k in ("unissued", "emission_share", "emission_release_by_T", "floor_frac"):
            if k in sp: cm.num(sp[k], f"scenarios.{n}.supply.{k}", lo=0)
        bb = sp.get("buyback", {})
        for k in ("tokens_per_yr", "years"):
            if k in bb: cm.num(bb[k], f"scenarios.{n}.supply.buyback.{k}", lo=0)

def _common(cfg):
    validate_cfg(cfg)
    cfg["scenarios"] = _order(cfg["scenarios"])
    check_as_of(cfg.get("as_of"))
    tp = sum(sc["prob"] for sc in cfg["scenarios"].values())
    if abs(tp - 1) > 1e-6: raise ValueError(f"STOP: scenario probabilities sum to {tp}, not 1")
    return cfg.get("N", 7), cfg.get("gT", 0.035), cfg["price"], cfg["S0"]

def _warn(cfg, warnings):
    j = cfg.get("judgement")
    for fl in (j or {}).get("flags", []):
        # the gate and the commitment check below report these from the final inputs (overrides included)
        if not fl.startswith(("DIAGNOSTIC", "NOTE", "EARLY STAGE", "DECAYING", "COMMITMENT", "NO STATED CONDITION")):
            warnings.append("DEFAULTS: " + fl)
    cont = sorted({sc.get("supply", {}).get("buyback", {}).get("years") for sc in cfg["scenarios"].values()
                   if sc.get("supply", {}).get("buyback", {}).get("continue_after")
                   and sc.get("supply", {}).get("buyback", {}).get("years") is not None
                   and sc["supply"]["buyback"]["years"] < cfg.get("N", 7)})
    if cont:
        names = [n for n, sc in cfg["scenarios"].items() if sc.get("supply", {}).get("buyback", {}).get("continue_after")]
        warnings.append(f"COMMITMENT ASSUMED TO CONTINUE: buybacks are committed for {', '.join(f'{y:g}' for y in cont)} year(s), and this "
                        "run assumes they continue after that (continue_after true). Committed-only bracket: "
                        + json.dumps({f"scenarios.{n}.supply.buyback.continue_after": False for n in names}))
    if j is not None and not j.get("confirmed"):
        warnings.append("JUDGEMENT TABLE NOT CONFIRMED: default judgement inputs were not confirmed/overridden by the user (show judgement.md, then apply overrides with confirmed: true)")
    pc = cfg.get("price_check")
    if pc:
        alt = pc.get("alt_price"); lim = pc.get("max_divergence", 0.05)
        if alt:
            dv = abs(alt / cfg["price"] - 1)
            if dv > lim: warnings.append(f"PRICE QUALITY: CoinGecko vs alt source differ by {dv:.1%} (> {lim:.0%})")
        for note in pc.get("notes", []): warnings.append(f"PRICE QUALITY: {note}")
    if cfg.get("supply_fallback_circulating"):
        warnings.append("SUPPLY FALLBACK: S0 = circulating supply (vesting data not free/available); see max-supply bracket")
    if cfg.get("is_l1"):
        warnings.append("L1 ADAPTATION: base-layer token; monetary/collateral premium and gas burn are not modelled")
    if cfg.get("e0_excludes_company_share"):
        al = [n for n, s in cfg["scenarios"].items() if s["ke"].get("align", 0) > 0]
        if al and not cfg.get("align_reason"):
            warnings.append(f"ALIGNMENT: E0 already excludes the company share but align > 0 in {al}; state the residual risk being priced (align_reason) or set align 0 to avoid a double penalty")

def run(cfg):
    N, gT, P, S0 = _common(cfg)
    warnings = []
    gate(cfg, warnings); _warn(cfg, warnings)
    E0c = cfg.get("E0_core", cfg.get("E0")); E0o = cfg.get("E0_other", 0.0)
    if E0c is None: raise ValueError("STOP: E0_core missing")
    if E0c + E0o <= 0: raise ValueError("STOP: E0 <= 0: no holder earnings to capitalise; use the option path")
    out = {"engine": "protocol-valuation " + __version__, "label": "MODEL OUTPUT under stated assumptions - not investment advice",
           "inputs": cfg, "scenarios": {}, "warnings": warnings}
    for name, sc in cfg["scenarios"].items():
        r = value(E0c, E0o, S0, N, gT, sc, P)
        r["prob"] = sc["prob"]; r["upside"] = r["fv"] / P - 1
        out["scenarios"][name] = r
        warnings += [f"{name}: {f}" for f in r["flags"]]
    R = out["scenarios"].values()
    out["pw_fv"] = sum(r["prob"] * r["fv"] for r in R); out["pw_upside"] = out["pw_fv"] / P - 1
    out["pw_fv_holder_retains"] = sum(r["prob"] * r["fv_holder_retains"] for r in R)
    out["pw_pe_T"] = sum(r["prob"] * r["pe_T"] for r in R)
    out["eps_0"] = (E0c + E0o) / S0; out["earnings_yield_0"] = out["eps_0"] / P
    ty = cfg.get("pe_method_year", 5)
    if not 1 <= ty <= N: raise ValueError(f"STOP: pe_method_year {ty} must be in 1..N")
    m2 = {n: r["pe_T"] * r["eps"][ty] for n, r in out["scenarios"].items()}
    out["method2"] = {"year": ty, "per_scenario": m2, "pw": sum(out["scenarios"][n]["prob"] * v for n, v in m2.items())}
    out["method3"] = {"pw_yield_path": [sum(r["prob"] * r["eps"][t] for r in R) / P for t in range(N + 1)],
                      "per_scenario": {n: [e / P for e in r["eps"]] for n, r in out["scenarios"].items()}}
    pw_eps = [sum(r["prob"] * r["eps"][t] for r in R) for t in range(N + 1)]
    out["pw_eps_cagr"] = (pw_eps[N] / pw_eps[0]) ** (1 / N) - 1 if pw_eps[N] > 0 else None
    anchor = cfg.get("anchor", "base"); base = cfg["scenarios"][anchor]
    out["breakeven_g1"] = breakeven_g(E0c, E0o, S0, N, gT, base, P)
    if out["breakeven_g1"] is not None:
        chk = value(E0c, E0o, S0, N, gT, base, P, g=out["breakeven_g1"])["fv"]
        if abs(chk / P - 1) > 1e-4:
            warnings.append(f"BREAK-EVEN APPROXIMATE: the anchor value jumps across the price near g1 {out['breakeven_g1']:.1%} "
                            f"(value there {money(chk)} vs price {money(P)}), from deep buybacks or a solver fallback in an extreme "
                            "growth region; treat market-implied growth as approximate")
    # scenario-weight sensitivity (weights are judgement, not data)
    ws = cfg.get("sens_weights", [[0.2, 0.6, 0.2], [1/3, 1/3, 1/3], [0.3, 0.6, 0.1], [0.1, 0.6, 0.3], [0.4, 0.5, 0.1]])
    names = list(cfg["scenarios"])
    out["weight_sensitivity"] = [{"weights": w, "pw_fv": sum(wi * out["scenarios"][n]["fv"] for wi, n in zip(w, names))}
                                 for w in ws if len(w) == len(names)]
    gs = cfg.get("sens_g", [base["g1"] + d for d in (-0.15, -0.10, -0.05, 0, 0.05, 0.10, 0.15)])
    ks = cfg.get("sens_ke_shift", [-0.02, -0.01, 0, 0.01, 0.02])
    out["sensitivity"] = {"g": gs, "ke_shift": ks,
                          "grid": [[value(E0c, E0o, S0, N, gT, base, P, g=g, ke_shift=d)["fv"] for d in ks] for g in gs]}
    gset = {sc["g1"] for sc in cfg["scenarios"].values()} | ({out["breakeven_g1"]} if out["breakeven_g1"] is not None else set())
    out["growth_index"] = {f"{g:.2%}": 100 * (1 + g) ** N for g in sorted(gset)}
    out["extreme"] = extreme_checks(out["pw_upside"], out["breakeven_g1"], out["earnings_yield_0"],
                                    max(r["pe_T"] for r in out["scenarios"].values()), cfg)
    warnings[:0] = out["extreme"]
    out["basis"] = BASIS_EXISTING
    out["confidence"] = confidence(cfg, out["extreme"])
    return out

EXTREME = {"pw_up": 1.50, "pw_down": -0.60,   # symmetric in multiples: 2.5x price up, 0.4x price down
           "g_hi": 1.00, "g_lo": -0.20, "ey0": 0.25, "pe": 30.0}

def extreme_checks(pw_up, be, ey0, pe_max, cfg):
    """Results this far from the price are usually an input error. Flag them loudly, with what to re-check."""
    why = []
    if pw_up > EXTREME["pw_up"]: why.append(f"PW value {pw_up:+.0%} vs price")
    if pw_up < EXTREME["pw_down"]: why.append(f"PW value {pw_up:+.0%} vs price")
    if be is None: why.append("no break-even growth in -50%..300%")
    elif be > EXTREME["g_hi"] or be < EXTREME["g_lo"]: why.append(f"break-even g1 {be:.0%}")
    if ey0 is not None and ey0 > EXTREME["ey0"]: why.append(f"current earnings yield {ey0:.0%}")
    if pe_max > EXTREME["pe"]: why.append(f"steady-state P/E {pe_max:.0f}x")
    if not why: return []
    # name the likely cause first when the inputs already show it, then the general list
    d = (cfg or {}).get("data") or {}; j = (cfg or {}).get("judgement") or {}
    first = []
    if d.get("decaying") and d.get("run_rate_7d") is not None:
        first.append(f"the latest week is under half of E0 (DECAYING): re-run with E0_core = {d['run_rate_7d']:.2f}")
    if d.get("revenue_capped"):
        first.append("E0 is already capped at what current protocol revenue supports (REVENUE CHECK)")
    if j.get("market_basis") == "none":
        first.append("market growth is a flat default because no category series was supplied")
    return ["EXTREME RESULT (" + "; ".join(why) + "). Before reporting, re-check: " + "; ".join(first + [
            "E0 window and one-off spikes (7d and 30d vs E0), units ($m and m tokens), S0 vs the tracker's supply, market basis "
            "and growth (D2), and whether the category is shrinking"]) + ". Report the result only with this flag and the re-check outcome."]

BASIS_EXISTING = "existing holder earnings: buybacks or distributions already operating (the value still depends on the forecasts)"

def confidence(cfg, extreme, option=False):
    """Input confidence (reporting rule, not a valuation input): LOW, MEDIUM or HIGH with the reasons, from the final inputs.
    LOW: under a year of holder-earnings history, decaying earnings, an extreme result, a diagnostic run, or a conditional
    valuation with no stated condition. MEDIUM: growth not from live category data (no series, or the perps constants),
    a moat score on a band edge, buybacks assumed to outlive their commitment, falling revenue, holder flow above revenue,
    or supply from the circulating fallback. HIGH: none of these. Precise numbers are not the same as reliable inputs."""
    d = cfg.get("data") or {}; j = cfg.get("judgement") or {}; fl = " ".join(j.get("flags", []))
    low, med = [], []
    h = d.get("history_days")
    if d.get("diagnostic"): low.append("diagnostic run")
    if not option and h is not None and h < 365: low.append(f"{h} days of holder earnings, under a year")
    if not option and d.get("decaying"): low.append("earnings decaying")
    if extreme: low.append("result far from the price")
    if option and not (cfg.get("option") or {}).get("condition"): low.append("no stated condition")
    mb = j.get("market_basis")
    if mb == "none": med.append("market growth is a flat default")
    if mb == "fallback_perps": med.append("growth from fixed perps constants, not live data")
    if (j.get("moat") or {}).get("borderline"): med.append("moat score on a band edge")
    N = cfg.get("N", 7)
    if any((sc.get("supply", {}).get("buyback", {}).get("continue_after") and sc["supply"]["buyback"].get("years") is not None
            and sc["supply"]["buyback"]["years"] < N) for sc in cfg["scenarios"].values()):
        med.append("buybacks assumed to outlive their commitment")
    if "REVENUE FALLING" in fl: med.append("protocol revenue falling")
    if "HOLDER FLOW ABOVE REVENUE" in fl: med.append("holder flow above revenue")
    if cfg.get("supply_fallback_circulating"): med.append("supply from the circulating fallback")
    return {"level": "LOW" if low else "MEDIUM" if med else "HIGH", "reasons": low + med}

def basis_line(o):
    cf = o["confidence"]
    return (f"**Valuation basis:** {o['basis']} · **Input confidence: {cf['level']}**"
            + (f" ({'; '.join(cf['reasons'])})" if cf["reasons"] else ""))

def to_md(o):
    c = o["inputs"]; P = c["price"]; N = c.get("N", 7)
    E0c = c.get("E0_core", c.get("E0")); E0o = c.get("E0_other", 0.0)
    L = [f"# {c.get('protocol','Protocol')} valuation - {c.get('as_of','')} (protocol-valuation {__version__})",
         "**Model output under stated assumptions - not financial advice.**", "",
         f"Price {money(P)} · E0 core ({c.get('E0_core_label','core earnings')}) ${num(E0c)}m"
         + (f" + own-path ({c.get('E0_other_label','other')}) ${num(E0o)}m" if E0o else "")
         + f" · S0 {num(c['S0'])}m · horizon {N}y · gT {c.get('gT',0.035):.1%}", "", basis_line(o)]
    if o["warnings"]: L += ["", "**Flags:**"] + [f"- {w}" for w in o["warnings"]]
    L += ["", "| Scenario | Prob | g1 | g_other | Ke now | Ke_T | ROE | gT | PE_T | S_T (m) | EPS_N | PV cash | PV TV | DCF FV | Upside |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, r in o["scenarios"].items():
        L.append(f"| {n} | {r['prob']:.0%} | {r['g1']:.1%} | {r['g_other']:.1%} | {r['ke']:.2%} | {r['ke_T']:.2%} | {r['roe']:.0%} | {r['gT']:.1%} | {r['pe_T']:.2f}x | {num(r['S_T'])} | {money(r['eps_N'])} | {money(r['pv_cash'])} | {money(r['pv_tv'])} | {money(r['fv'])} | {r['upside']:+.0%} |")
    no_tv = [n for n, r in o["scenarios"].items() if not r["terminal_included"]]
    if no_tv: L += ["", f"Terminal value excluded in {no_tv}: payouts end with the committed buyback period (continue_after = false)."]
    L += ["", f"**Method 1 DCF, probability-weighted:** {money(o['pw_fv'])} ({o['pw_upside']:+.0%}) · PW PE_T {o['pw_pe_T']:.2f}x",
          f"Non-seller check (TV on buyback-reduced supply, no interim cash): PW {money(o['pw_fv_holder_retains'])}",
          f"**Method 2 steady-state P/E x EPS year {o['method2']['year']} (undiscounted):** PW {money(o['method2']['pw'])} · "
          + " · ".join(f"{n} {money(v)}" for n, v in o["method2"]["per_scenario"].items()),
          f"**Method 3 earnings yield (PW EPS_t / price):** " + " → ".join(f"y{t} {y:.1%}" for t, y in enumerate(o["method3"]["pw_yield_path"])),
          (f"**Market-implied core growth (break-even g1 at {money(P)}):** {o['breakeven_g1']:.1%}" if o["breakeven_g1"] is not None
           else "**Market-implied growth:** outside -50%..300% (price not reachable by g1 alone)"),
          f"**Current EPS / earnings yield:** {money(o['eps_0'])} / {o['earnings_yield_0']:.1%} · PW EPS CAGR " + (f"{o['pw_eps_cagr']:.1%}" if o['pw_eps_cagr'] is not None else "n/a")]
    L += ["", "**Per-year path (anchor scenario)**", "", "| Year | Ke_t | E_t ($m) | Dilution D_t (m) | Supply S_t (m) | Bought back (m) | Buyback price | EPS_t |", "|---|---|---|---|---|---|---|---|"]
    a = o["scenarios"][c.get("anchor", "base")]
    for t in range(1, N + 1):
        L.append(f"| {t} | {a['ke_path'][t-1]:.2%} | {num(a['E'][t])} | {num(a['D'][t])} | {num(a['S'][t])} | {num(a['buyback_tokens'][t],2)} | {money(a['buyback_price'][t]) if a['buyback_tokens'][t] > 0 else 'n/a (none)'} | {money(a['eps'][t])} |")
    L += ["", "**Scenario-weight sensitivity (weights are judgement)**", "", "| Weights | PW DCF |", "|---|---|"]
    for w in o["weight_sensitivity"]:
        L.append(f"| {'/'.join(f'{x:.0%}' for x in w['weights'])} | {money(w['pw_fv'])} |")
    s = o["sensitivity"]
    L += ["", "**Sensitivity: anchor DCF (rows core g1, cols parallel Ke shift)**", "",
          "| g1 \\ ΔKe | " + " | ".join(f"{d:+.0%}" for d in s["ke_shift"]) + " |", "|---|" + "---|" * len(s["ke_shift"])]
    for g, row in zip(s["g"], s["grid"]):
        L.append(f"| {g:.1%} | " + " | ".join(money(v) for v in row) + " |")
    L += ["", "**Growth index (100 compounded over horizon)**", "", "| g | Index |", "|---|---|"]
    for g, v in o["growth_index"].items(): L.append(f"| {g} | {v:,.0f} |")
    return "\n".join(L)

# ---------------- option path ----------------
def option_e0(o):
    kind = o.get("type")
    if kind == "fee_switch":
        fees, tr = o.get("fees_ttm"), o.get("take_rate")
        if fees is None: raise ValueError("STOP: fees_ttm missing (DefiLlama dailyFees, annualised); no fee data -> cannot value from cash flows")
        if fees <= 0: raise ValueError(f"STOP: fees_ttm = {fees} <= 0; nothing for a fee switch to capture")
        if tr is None: raise ValueError("STOP: take_rate missing; it must be the rate stated in docs/governance proposal, not invented")
        if not 0 < tr <= 1: raise ValueError(f"STOP: take_rate {tr} must be in (0, 1]")
        return fees * tr
    if kind == "paused_buyback":
        h = o.get("holder_rev_hist")
        if h is None: raise ValueError("STOP: holder_rev_hist missing (DefiLlama dailyHoldersRevenue before the pause)")
        if h <= 0: raise ValueError(f"STOP: holder_rev_hist = {h} <= 0; no historical holder earnings to restore")
        return h
    raise ValueError(f"STOP: option.type must be 'fee_switch' or 'paused_buyback', got {kind!r}")

def check_cases(cases):
    if not cases: raise ValueError("STOP: option.activation needs at least one {label, p, delay_years} case (user-supplied)")
    for c in cases:
        p, d = c.get("p"), c.get("delay_years")
        if p is None or not 0 <= p <= 1: raise ValueError(f"STOP: activation prob {p!r} for {c.get('label')!r} must be in [0, 1]")
        if d is None or d < 0: raise ValueError(f"STOP: delay_years {d!r} for {c.get('label')!r} must be >= 0")
    tp = sum(c["p"] for c in cases)
    if tp > 1 + 1e-9: raise ValueError(f"STOP: activation probabilities sum to {tp:.3f} > 1 (remainder = never activates)")
    return tp

def option_value(fv_on, ke, cases):
    return sum(c["p"] * fv_on / (1 + ke) ** c["delay_years"] for c in cases)

def implied_p(per_unit, price, lo=0.0, hi=1.0):
    if per_unit <= 0 or price > per_unit * hi: return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if mid * per_unit < price: lo = mid
        else: hi = mid
    return (lo + hi) / 2

def run_option(cfg):
    N, gT, P, S0 = _common(cfg)
    op = cfg["option"]
    for k in ("fees_ttm", "take_rate", "holder_rev_hist"):
        if op.get(k) is not None: cm.num(op[k], f"option.{k}")
    warnings = []; _warn(cfg, warnings)
    o = cfg["option"]; E0_on = option_e0(o)
    if not o.get("condition"):
        warnings.append("NO STATED CONDITION: name the mechanism that would route this revenue to holders (a governance proposal, a "
                        "documented programme, a paused buyback that can resume) and its source, in option.condition. Without one "
                        "the framework can't establish a value from cash flows: the switched-on value is hypothetical")
    cases = o.get("activation", []); tp_act = check_cases(cases)
    out = {"engine": "protocol-valuation " + __version__, "mode": "option", "label": "MODEL OUTPUT under stated assumptions - not investment advice",
           "E0_on": E0_on, "p_never": 1 - tp_act, "scenarios": {}, "inputs": cfg, "warnings": warnings}
    for name, sc in cfg["scenarios"].items():
        r = value(E0_on, 0.0, S0, N, gT, sc, P)
        r["fv_on"] = r.pop("fv"); r["option_fv"] = option_value(r["fv_on"], r["ke"], cases)
        r["upside"] = r["option_fv"] / P - 1; r["prob"] = sc["prob"]
        out["scenarios"][name] = r
    S = out["scenarios"].values()
    out["pw_fv_on"] = sum(r["prob"] * r["fv_on"] for r in S)
    out["pw_option_fv"] = sum(r["prob"] * r["option_fv"] for r in S)
    out["pw_upside"] = out["pw_option_fv"] / P - 1
    out["pw_upside_on"] = out["pw_fv_on"] / P - 1
    out["default_cases"] = all(str(c.get("label", "")).startswith("DEFAULT") for c in cases)
    # The activation cases are judgement (D21 placeholders unless the user supplied them), so the weighted value is not the
    # headline and is only checked for extremes when the cases are the user's own
    if not out["default_cases"] and (out["pw_upside"] > EXTREME["pw_up"] or out["pw_upside"] < EXTREME["pw_down"]):
        warnings.insert(0, f"EXTREME RESULT (PW option value {out['pw_upside']:+.0%} vs price, on your activation cases): re-check "
                           "fees_ttm, take_rate/holder_rev_hist and the activation cases")
    delays = o.get("implied_delays", sorted({0} | {c["delay_years"] for c in cases}))
    out["implied_p"] = {}
    for d in delays:
        if d < 0: raise ValueError(f"STOP: implied_delays entry {d} must be >= 0")
        unit = sum(r["prob"] * r["fv_on"] / (1 + r["ke"]) ** d for r in S)
        out["implied_p"][str(d)] = implied_p(unit, P)
    if P > out["pw_fv_on"]:   # whatever implied delays were asked for: even an immediate switch-on doesn't reach the price
        warnings.insert(0, f"PRICE ABOVE THE SWITCHED-ON VALUE: even switched on today, the value is {money(out['pw_fv_on'])} against a "
                           f"price of {money(P)}. On these inputs the price assumes more than this mechanism can deliver")
    out["basis"] = "conditional holder earnings: value if " + (o.get("condition") or "an unstated condition (see flags)")
    out["confidence"] = confidence(cfg, [w for w in warnings if w.startswith("EXTREME")], option=True)
    return out

def to_md_option(o):
    c, P, op = o["inputs"], o["inputs"]["price"], o["inputs"]["option"]
    src = (f"{op.get('base_label', 'fees_ttm')} ${num(op['fees_ttm'])}m × take_rate {op['take_rate']:.1%}" if op["type"] == "fee_switch"
           else f"historical holder revenue ${num(op['holder_rev_hist'])}m (buybacks paused)")
    L = [f"# {c.get('protocol','Protocol')} CONDITIONAL valuation ({op['type']}) - {c.get('as_of','')} (protocol-valuation {__version__})",
         "**Model output under stated assumptions - not financial advice.**", "",
         f"Price {money(P)} · switched-on E0 = {src} = ${num(o['E0_on'])}m · horizon {c.get('N',7)}y", "", basis_line(o)]
    if o["warnings"]: L += ["", "**Flags:**"] + [f"- {w}" for w in o["warnings"]]
    L += ["", f"**Value if switched on today (probability-weighted across scenarios):** {money(o['pw_fv_on'])} ({o['pw_upside_on']:+.0%} vs price)", "",
          "**What the price implies: probability that it switches on**", "", "| If it switches on in (years) | Implied probability |", "|---|---|"]
    for d, p in o["implied_p"].items():
        L.append(f"| {d} | " + (f"{p:.1%}" if p is not None else "above 100%: the price exceeds the value even if it switches on") + " |")
    L += ["", "| Scenario | Prob | g1 | Ke now | PE_T | Value if on today | With activation cases |", "|---|---|---|---|---|---|---|"]
    for n, r in o["scenarios"].items():
        L.append(f"| {n} | {r['prob']:.0%} | {r['g1']:.1%} | {r['ke']:.2%} | {r['pe_T']:.2f}x | {money(r['fv_on'])} | {money(r['option_fv'])} |")
    who = ("D21 placeholders: judgement, not estimates; replace them with your own view" if o.get("default_cases")
           else "your cases")
    L += ["", f"With activation cases ({who}): " + "; ".join(
              f"{a.get('label','case')}: p={a['p']:.0%}, in {a['delay_years']}y" for a in op["activation"]) + f"; never {o['p_never']:.0%}"
          + f" → probability-weighted {money(o['pw_option_fv'])} ({o['pw_upside']:+.0%} vs price)"]
    return "\n".join(L)

def windows_cli(argv):
    """python3 engine.py windows summary.json [--as-of ISO]: E0 windows (complete days only) from a saved DefiLlama
    summary/fees response (or a bare [[ts, usd], ...] list). Prints JSON."""
    d = cm.load_json(argv[1] if len(argv) > 1 else None)
    chart = d.get("totalDataChart") if isinstance(d, dict) else d
    if chart is None:
        raise cm.InputError(f"{argv[1]} has no daily chart: expected a DefiLlama summary/fees response with "
                            "totalDataChart, or a list of [unix_ts, usd] pairs")
    as_of = cm.arg(argv, "--as-of")
    if as_of is not None: cm.iso_ts(as_of, "--as-of")
    out = e0_windows(chart, as_of)
    print(json.dumps(out, indent=1))
    return out

def main(argv):
    if len(argv) < 2:
        print(__doc__); return
    if argv[1] in ("--version", "version"):
        print(__version__); return
    if argv[1] in ("defaults", "windows") and len(argv) > 2:
        if argv[1] == "windows": return windows_cli(argv[1:])
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # defaults.py lives next to this file
        import defaults as dv
        return dv.main(argv[1:])
    if argv[1] in ("defaults", "windows"): raise cm.InputError(f"{argv[1]} needs a file argument")
    cfg = cm.load_json(argv[1])
    md_path, json_path = cm.arg(argv, "--md"), cm.arg(argv, "--json")
    is_opt = isinstance(cfg, dict) and "option" in cfg
    o = run_option(cfg) if is_opt else run(cfg)
    md = to_md_option(o) if is_opt else to_md(o)
    if md_path: cm.write_text(md_path, md + "\n")
    if json_path: cm.write_json(json_path, o, indent=2)
    print(md)

if __name__ == "__main__":
    cm.cli(main, sys.argv)

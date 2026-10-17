#!/usr/bin/env python3
"""Edge-case tests: gate stops, short history, rubric-only moat, non-perps, exploit, enforcement, option path,
override validation, buyback commitments, CLI error handling. Complements selftest.py (which pins the numbers).
Usage: python3 scripts/test_edge_cases.py   (exit code 1 on any failure)"""
import sys, os, json, copy, subprocess, tempfile
SK = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(SK, "scripts"))
import defaults as dv, engine

BASE = json.load(open(os.path.join(SK, "examples", "calibration_facts.json")))
results = []
def t(name):
    def deco(fn):
        try:
            fn(); results.append((name, "PASS", ""))
        except AssertionError as e:
            results.append((name, "FAIL", str(e)))
        except Exception as e:
            results.append((name, "ERROR", f"{type(e).__name__}: {e}"))
        return fn
    return deco

def facts(**mods):
    f = copy.deepcopy(BASE)
    for path, v in mods.items():
        d = f; ks = path.split("__")
        for k in ks[:-1]: d = d[k]
        if v is DEL: d.pop(ks[-1], None)
        else: d[ks[-1]] = v
    return f
DEL = object()

def value(f, confirm=True, ov=None):
    cfg = dv.build(f)
    if ov: dv.apply_overrides(cfg, ov)
    if confirm: cfg["judgement"]["confirmed"] = True
    return cfg, (engine.run_option(cfg) if "option" in cfg else engine.run(cfg))

def stops(fn, needle):
    try: fn()
    except ValueError as e:
        assert "STOP" in str(e) and needle in str(e), f"wrong stop: {e}"
        return
    raise AssertionError("expected STOP, none raised")

@t("short history (200d) -> lower of 90d and 14d, SHORT HISTORY flag; 14d required")
def _():
    f = facts(earnings__history_days=200, earnings__core_by_window={"90d": 700, "14d": 720, "30d": 650})
    cfg, o = value(f)
    assert cfg["E0_core"] == 700, cfg["E0_core"]
    assert any("SHORT HISTORY" in w for w in o["warnings"]), o["warnings"]
    cfg, o = value(facts(earnings__history_days=200, earnings__core_by_window={"90d": 700, "14d": 500, "30d": 650}))
    assert cfg["E0_core"] == 500, cfg["E0_core"]
    stops(lambda: value(facts(earnings__history_days=200, earnings__core_by_window={"90d": 700, "30d": 650})), "14d")

@t("history < 30d -> STOP; 30-89d without the early-stage windows -> STOP asking for them")
def _():
    stops(lambda: value(facts(earnings__history_days=20, earnings__core_by_window={"30d": 500})), "< 30")
    stops(lambda: value(facts(earnings__history_days=60, earnings__core_by_window={"30d": 500})), "since-launch")

@t("rubric-only moat, weak protocol -> lower band, weak share set")
def _():
    seg = {"name": "Spot DEX", "weight": 1.0, "rubric": {"share_30d": 0.12, "holder_rev_ttm_musd": 30, "age_months": 30, "rank": 4,
           "n_competitors_ge10": 3, "share_change_pp": -5, "incentive_driven": True}}
    f = facts(moat__segments=[seg], market={"basis": "category_series", "trailing_cagr": 0.30, "record_365d": 100.0, "ttm_365d": 100.0, "yoy": 0.10}, share__share_0=0.12)
    cfg, o = value(f)
    m = cfg["judgement"]["moat"]
    assert m["helmer"] < 1.5, m
    assert tuple(m["band"]) == (0.08, 0.15), m["band"]
    roe = {s: cfg["scenarios"][s]["roe"] for s in ("bear", "base", "bull")}
    keT = {s: o["scenarios"][s]["ke_T"] for s in roe}
    assert all(abs(roe[s] - keT[s]) < 1e-12 for s in roe), (roe, keT)   # no-moat floor -> ROE = Ke_T
    assert all(abs(o["scenarios"][s]["pe_T"] - (1 - o["scenarios"][s]["gT"]/roe[s])/(keT[s]-o["scenarios"][s]["gT"])) < 1e-9 for s in roe)

@t("no-moat check: ROE = Ke_T gives PE_T = 1/Ke_T only when gT payout adjusts (sanity)")
def _():
    # with ROE = Ke_T: PE = (1 - g/Ke)/(Ke - g) = 1/Ke exactly
    for ke, g in ((0.13, 0.035), (0.2, 0.045)):
        assert abs((1 - g/ke)/(ke - g) - 1/ke) < 1e-12

@t("non-perps (category_series basis) -> DEX lever 1")
def _():
    f = facts(market={"basis": "category_series", "trailing_cagr": 0.30, "record_365d": 100.0, "ttm_365d": 100.0, "yoy": 0.10})
    cfg, o = value(f)
    tr = [r for r in cfg["judgement"]["table"] if r["id"] == "D1"][0]["source"]
    assert "/0.070" not in tr, tr

@t("exploit >= $10m -> sc 2.0%")
def _():
    cfg, _ = value(facts(risk__major_exploit=True))
    assert cfg["scenarios"]["base"]["ke"]["sc_now"] == 0.02

@t("formal enforcement action -> +2pp in every scenario")
def _():
    cfg, _ = value(facts(risk__formal_action=True))
    got = [cfg["scenarios"][s]["ke"]["reg"] for s in ("bear", "base", "bull")]
    assert [round(x, 4) for x in got] == [0.045, 0.04, 0.025], got

@t("launch_date instead of age_months")
def _():
    f = facts(risk__age_months=DEL, risk__launch_date="2024-11-29")
    cfg, _ = value(f)
    assert abs(cfg["scenarios"]["base"]["ke"]["sc_now"] - 0.0117) < 1e-9, cfg["scenarios"]["base"]["ke"]["sc_now"]

@t("ONE cycle rule: category series -> min(1, 0.6522 x record/TTM); perps fallback fixed; mixing refused")
def _():
    cfg, _ = value(facts(market={"basis": "category_series", "trailing_cagr": 0.61, "record_365d": 92, "ttm_365d": 92}))
    row = [r for r in cfg["judgement"]["table"] if r["id"] == "D3"][0]
    assert "0.6522" in str(row["values"]), row
    cfg, _ = value(facts(market={"basis": "category_series", "trailing_cagr": 0.61, "record_365d": 92, "ttm_365d": 50}))
    row = [r for r in cfg["judgement"]["table"] if r["id"] == "D3"][0]
    assert "1.0000" in str(row["values"]), row
    for bad in ({"basis": "fallback_perps", "cycle_factor": 1.0}, {"basis": "category_series", "trailing_cagr": 0.6, "record_365d": 1, "ttm_365d": 1, "cycle_factor": 0.9},
                {"basis": "category_series", "trailing_cagr": 0.6, "record_365d": 1, "ttm_365d": 1, "dex_share_0": 0.07}, {"trailing_cagr": 0.6}):
        stops(lambda: value(facts(market=bad)), "market")

@t("HYPE live-style facts give one answer whichever doc you followed (fallback basis only)")
def _():
    a, _ = value(facts(market={"basis": "fallback_perps"}))
    assert [a["scenarios"][s]["g1"] for s in ("bear", "base", "bull")] == [0.10, 0.40, 0.55]

@t("negative trailing CAGR -> capped at -20%, bear <= base <= bull")
def _():
    cfg, o = value(facts(market={"basis": "category_series", "trailing_cagr": -0.9, "record_365d": 100, "ttm_365d": 30}))
    g = [cfg["scenarios"][s]["g1"] for s in ("bear", "base", "bull")]
    assert g[0] <= g[1] <= g[2], g

@t("young category (trailing 200%) -> market CAGR capped at 20%")
def _():
    cfg, _ = value(facts(market={"basis": "category_series", "trailing_cagr": 2.0, "record_365d": 100, "ttm_365d": 100}))
    row = [r for r in cfg["judgement"]["table"] if r["id"] == "D2"][0]
    assert row["values"]["base"] == 0.2, row["values"]

@t("STRUCTURAL: launchpad-style collapse (trailing +202%, latest year -60% vs DeFi -20%, below 2y ago) -> flat base, not +20%, not negative")
def _():
    m = {"basis": "category_series", "trailing_cagr": 2.02, "cagr_years": 2, "record_365d": 1000, "ttm_365d": 400, "yoy": -0.60,
         "benchmark_yoy": -0.20, "level_2y_ago_365d": 700}
    cfg, o = value(facts(market=m))
    row = [r for r in cfg["judgement"]["table"] if r["id"] == "D2"][0]
    assert row["values"] == {"base": 0.0, "bull": 0.1, "bear": -0.1}, row["values"]
    fl = " ".join(cfg["judgement"]["flags"])
    assert "POSSIBLE STRUCTURAL DECLINE" in fl and "YOUNG CATEGORY" in fl, fl

@t("CYCLICAL: UNI-style DEX category -34% while all DeFi -30% -> calibrated rule (+20% cap), drop handled by cycle reset")
def _():
    m = {"basis": "category_series", "trailing_cagr": 0.75, "cagr_years": 5, "record_365d": 1500, "ttm_365d": 990, "yoy": -0.34,
         "benchmark_yoy": -0.30, "level_2y_ago_365d": 800}
    cfg, o = value(facts(market=m))
    row = [r for r in cfg["judgement"]["table"] if r["id"] == "D2"][0]
    assert row["values"]["base"] == 0.2, row["values"]
    assert any("CYCLICAL DOWNTURN" in x for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]
    d3 = [r for r in cfg["judgement"]["table"] if r["id"] == "D3"][0]
    assert "0.9882" in str(d3["values"]) or "0.9881" in str(d3["values"]), d3   # 0.6522 x 1500/990: reset already happened

@t("Bigger picture required: big category-specific fall but TTM still above 2 years ago -> cycle, not structural")
def _():
    m = {"basis": "category_series", "trailing_cagr": 0.6, "record_365d": 1000, "ttm_365d": 500, "yoy": -0.50,
         "benchmark_yoy": -0.10, "level_2y_ago_365d": 300}
    cfg, _ = value(facts(market=m))
    assert [r for r in cfg["judgement"]["table"] if r["id"] == "D2"][0]["values"]["base"] == 0.2

@t("Shrinking with no benchmark -> calibrated rule + flag asking for the benchmark")
def _():
    m = {"basis": "category_series", "trailing_cagr": 0.6, "record_365d": 1000, "ttm_365d": 400, "yoy": -0.60}
    cfg, _ = value(facts(market=m))
    assert [r for r in cfg["judgement"]["table"] if r["id"] == "D2"][0]["values"]["base"] == 0.2
    assert any("no all-DeFi benchmark" in x for x in cfg["judgement"]["flags"])

@t("REPORTED: paused buybacks (AAVE-style: 30d run-rate $0) -> STOP, not a normal valuation")
def _():
    f = facts(earnings__core_by_window={"365d": 120.0, "90d": 60.0, "30d": 0.0})
    stops(lambda: value(f), "paused")
    f2 = facts(earnings__core_by_window={"365d": 120.0, "90d": 60.0, "30d": 0.0}); f2["option"] = {"type": "paused_buyback", "holder_rev_hist": 120.0}
    cfg, o = value(f2)
    assert o["mode"] == "option" and cfg["option"]["activation"], cfg["option"]
    assert any(r["id"] == "D21" for r in cfg["judgement"]["table"])

@t("REPORTED: paused flag also caught by the engine on a hand-built inputs.json")
def _():
    cfg = dv.build(facts(earnings__core_by_window={"365d": 120.0, "30d": 60.0})); cfg["judgement"]["confirmed"] = True
    cfg["data"]["paused"] = True
    stops(lambda: engine.run(cfg), "paused")

@t("routing paused / fee_switch_off without option block -> STOP")
def _():
    stops(lambda: value(facts(risk__routing="paused")), "option")
    stops(lambda: value(facts(risk__routing="fee_switch_off")), "option")

@t("REPORTED: < 30 days -> defaults step refuses (no table)")
def _():
    f = facts(earnings__history_days=20, earnings__core_by_window={"30d": 500})
    try: dv.build(f)
    except ValueError as e:
        assert "STOP" in str(e) and "< 30" in str(e); return
    raise AssertionError("defaults built a table for a 20-day token")

@t("REPORTED: UNI-style late fee switch: history from first non-zero day, age check flags launch == first holder revenue")
def _():
    last = 1791849600
    ch = [[last - i * 86400, 2e6 if i < 270 else 0] for i in range(2500)]
    w = engine.e0_windows(ch, "2026-10-14T10:00:00Z")
    assert w["history_days"] == 270 and w["e0_window"].startswith("short: 90d"), w
    f = facts(earnings={"windows": w, "other": 0}, risk__age_months=DEL, risk__launch_date=w["first_nonzero_day"])
    cfg, o = value(f)
    assert any(x.startswith("NOTE: launch_date equals") for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]
    assert not any("NOTE" in w for w in o["warnings"])          # a note, not a warning
    f = facts(earnings={"windows": w, "other": 0}, risk__age_months=DEL, risk__launch_date="2025-12-29", risk__first_fees_day="2018-11-02")
    cfg, o = value(f)
    assert any("AGE CHECK" in x for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]
    f = facts(earnings={"windows": w, "other": 0}, risk__age_months=DEL, risk__launch_date="2018-11-02")
    cfg, o = value(f)
    assert cfg["scenarios"]["base"]["ke"]["sc_now"] == 0.005 and not any("AGE" in x or "NOTE" in x for x in cfg["judgement"]["flags"])

@t("REPORTED: extreme result (+500%) is flagged loudly")
def _():
    cfg, o = value(facts(price=15))
    assert o["warnings"][0].startswith("EXTREME RESULT"), o["warnings"][:2]
    cfg, o = value(facts())
    assert not any(w.startswith("EXTREME") for w in o["warnings"])

@t("REPORTED: windows drop today's partial day; no 'lead' figure")
def _():
    last = 1791849600   # 2026-10-13
    ch = [[last - i * 86400, 1e6] for i in range(400)] + [[last + 86400, 1.0]]   # today's partial row
    w = engine.e0_windows(ch, "2026-10-14T12:00:00Z")
    assert w["partial_or_future_rows_dropped"] == 1 and abs(w["30d"] - 365.0) < 1e-9, w
    assert "lead" not in w and "lead_window" not in w

@t("version is stamped on outputs")
def _():
    cfg, o = value(facts())
    assert o["engine"].endswith(engine.__version__) and cfg["judgement"]["version"] == dv.__version__ == engine.__version__

@t("borderline moat flagged")
def _():
    f = facts()
    f["moat"]["segments"] = [{"name": "x", "weight": 1, "helmer": 2.52, "porter": 0.5}]
    cfg, _ = value(f)
    assert cfg["judgement"]["moat"]["borderline"] is True

@t("undisciplined emissions -> 100/60/10")
def _():
    cfg, _ = value(facts(supply__team_largest_holder=False))
    assert [cfg["scenarios"][s]["supply"]["emission_share"] for s in ("bear", "base", "bull")] == [1.0, 0.6, 0.1]

@t("time-limited buyback, no continuation -> terminal value excluded")
def _():
    cfg, o = value(facts(supply__buyback={"mode": "fair_value", "years": 3, "continue_after": False}))
    assert o["scenarios"]["base"]["terminal_included"] is False
    cfg2, o2 = value(facts(supply__buyback={"mode": "fair_value", "years": 3, "continue_after": True}))
    assert o2["scenarios"]["base"]["fv"] > o["scenarios"]["base"]["fv"]

@t("fair_value buybacks converge and non-seller check equals DCF")
def _():
    cfg, o = value(facts(supply__buyback={"mode": "fair_value"}))
    for s, r in o["scenarios"].items():
        assert abs(r["fv_holder_retains"] - r["fv"]) / r["fv"] < 1e-6, (s, r["fv_holder_retains"], r["fv"])

@t("constant_pe and none buyback modes run")
def _():
    for m in ("constant_pe", "none"):
        value(facts(supply__buyback={"mode": m}))

@t("unknown buyback mode -> STOP")
def _():
    stops(lambda: value(facts(supply__buyback={"mode": "magic"})), "buyback.mode")

@t("E0 = 0 without option block -> STOP")
def _():
    f = facts(earnings__core_by_window={"365d": 0}, earnings__other=0)
    stops(lambda: value(f), "E0 <= 0")

@t("option path via facts file (fee switch off)")
def _():
    f = facts(earnings__core_by_window={"365d": 0}, earnings__other=0)
    f["option"] = {"type": "fee_switch", "fees_ttm": 2000, "take_rate": 0.25,
                   "activation": [{"label": "vote", "p": 0.4, "delay_years": 1}], "implied_delays": [0, 1, 3]}
    cfg, o = value(f)
    assert o["mode"] == "option" and o["pw_option_fv"] > 0, o.get("pw_option_fv")

@t("option: missing take_rate -> STOP")
def _():
    f = facts(); f["option"] = {"type": "fee_switch", "fees_ttm": 2000, "activation": [{"p": 0.4, "delay_years": 1}]}
    stops(lambda: value(f), "take_rate")

@t("probabilities not summing to 1 -> STOP")
def _():
    stops(lambda: value(facts(), ov={"scenarios.bear.prob": 0.3}), "sum to")

@t("non-ISO as_of -> STOP")
def _():
    try: value(facts(as_of="14/10/2026")); raise AssertionError("non-ISO as_of accepted")
    except ValueError as e: assert "ISO" in str(e), e

@t("ROE <= gT -> STOP")
def _():
    stops(lambda: value(facts(), ov={"scenarios.base.roe": 0.03}), "ROE")

@t("override typo (unknown key) is rejected, not silently recorded")
def _():
    cfg = dv.build(facts())
    try:
        dv.apply_overrides(cfg, {"scenarios.base.g_1": 0.3})
    except (KeyError, ValueError):
        return
    raise AssertionError("typo override accepted silently: scenarios.base.g_1 recorded but has no effect")

@t("override of a whole-table value applies (scenarios.base.ke.reg)")
def _():
    cfg, o = value(facts(), ov={"scenarios.base.ke.reg": 0.03})
    assert abs(o["scenarios"]["base"]["ke"] - (0.1368 + 0.01)) < 1e-9, o["scenarios"]["base"]["ke"]

@t("unconfirmed -> flag; confirmed via overrides -> no flag")
def _():
    cfg, o = value(facts(), confirm=False)
    assert any("NOT CONFIRMED" in w for w in o["warnings"])
    cfg, o = value(facts(), confirm=False, ov={"confirmed": True})
    assert not any("NOT CONFIRMED" in w for w in o["warnings"])

@t("supply fallback + price-quality flags surface")
def _():
    f = facts(); f["supply_fallback_circulating"] = True; f["price_check"] = {"alt_price": 80}
    cfg, o = value(f)
    ws = " ".join(o["warnings"])
    assert "SUPPLY FALLBACK" in ws and "PRICE QUALITY" in ws, ws

@t("CLI: run from an unrelated cwd, all subcommands")
def _():
    with tempfile.TemporaryDirectory() as td:
        fp = os.path.join(SK, "examples", "calibration_facts.json")
        r = subprocess.run([sys.executable, os.path.join(SK, "scripts", "engine.py"), "defaults", fp, "--md", "j.md", "--json", "i.json"], cwd=td, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        r = subprocess.run([sys.executable, os.path.join(SK, "scripts", "engine.py"), "i.json", "--md", "v.md"], cwd=td, capture_output=True, text=True)
        assert r.returncode == 0 and os.path.exists(os.path.join(td, "v.md")), r.stderr
        r = subprocess.run([sys.executable, os.path.join(SK, "scripts", "engine.py"), "windows", "i.json"], cwd=td, capture_output=True, text=True)
        # i.json is not a chart: expect a clean error, not a crash with a traceback
        assert r.returncode != 0
        assert "Traceback" not in r.stderr, "windows on a wrong file gives a raw traceback: " + r.stderr.strip().splitlines()[-1]

@t("windows: decaying flag and short chart")
def _():
    last = 1791849600
    ch = [[last - i * 86400, 1e6 if i >= 7 else 1e5] for i in range(400)]
    w = engine.e0_windows(ch, "2026-10-14T00:00:01Z")
    assert w["decaying"] is True and w["history_days"] == 400, w
    w = engine.e0_windows(ch[:50], "2026-10-14T00:00:01Z")
    assert w["365d"] is None and w["90d"] is None and w["e0_window"].startswith("early"), w
    w = engine.e0_windows(ch[:20], "2026-10-14T00:00:01Z")
    assert w["e0_window"] is None and w["e0"] is None

@t("market_stats: < 365 days -> basis none; complete days; yoy for shrinking series")
def _():
    import market_stats as ms
    s = ms.stats([[1791849600 - i * 86400, 1.0] for i in range(100)], "2026-10-14")
    assert s["basis"] == "none", s
    last = 1791849600
    ch = [[last - i * 86400, 1e6 if i >= 365 else 4e5] for i in range(1500)] + [[last + 86400, 9e9]]   # fell 60%, partial today
    s = ms.stats(ch, "2026-10-14T12:00:00Z")
    assert s["basis"] == "category_series" and abs(s["yoy"] + 0.60) < 1e-9 and abs(s["ttm_365d"] - 146.0) < 1e-6, s
    assert "cycle_factor" not in s

@t("category_stats -> market_stats -> defaults chain (synthetic DefiLlama overview)")
def _():
    import category_stats as cs, market_stats as ms
    last = 1791849600
    prots = [{"name": "Pump Launchpad", "displayName": "Pump Launchpad", "parentProtocol": "parent#pump", "category": "Launchpad", "total30d": 6e6, "total1y": 300e6},
             {"name": "Pump AMM", "parentProtocol": "parent#pump", "category": "Dexs", "total30d": 1e6, "total1y": 20e6},
             {"name": "LetsBonk", "category": "Launchpad", "total30d": 3e6, "total1y": 150e6},
             {"name": "Tiny", "category": "Launchpad", "total30d": 1e6, "total1y": 50e6}]
    bd = [[last - i * 86400, {"Pump Launchpad": 2e5 if i < 365 else 6e5, "LetsBonk": 1e5, "Pump AMM": 5e4}] for i in range(800)]
    out, series, bench = cs.stats({"protocols": prots, "totalDataChartBreakdown": bd}, "parent#pump")
    assert bench and abs(bench[0][1] - 3.5e5) < 1e-6, bench[:1]
    assert out["category"] == "Launchpad" and out["rank"] == 1 and out["n_competitors_ge10"] == 2, out   # Tiny at exactly 10% counts (>= 10%)
    assert abs(out["share_30d"] - 0.6) < 1e-9 and out["share_change_pp"] == 0.0, out
    assert out["series_protocols_matched"] == 2, out
    m = ms.stats(series, "2026-10-14T12:00:00Z")
    assert m["yoy"] < 0, m
    bm = ms.stats(bench, "2026-10-14T12:00:00Z")
    mk = {k: m[k] for k in ("basis", "trailing_cagr", "record_365d", "ttm_365d", "yoy")}; mk["benchmark_yoy"] = bm["yoy"]
    cfg, o = value(facts(market=mk, share__share_0=out["share_30d"]))
    assert m["yoy"] - bm["yoy"] < 0 and cfg["scenarios"]["base"]["g1"] <= 0.40

@t("part-year buyback commitment (0.54y) counts 54% of year 1, nothing after, no terminal value")
def _():
    import engine as en
    cfg, o = value(facts(supply__buyback={"mode": "fair_value", "years": 0.54, "continue_after": False}))
    r = o["scenarios"]["base"]
    cfg1, o1 = value(facts(supply__buyback={"mode": "fair_value", "years": 1, "continue_after": False}))
    assert 0 < r["fv"] < o1["scenarios"]["base"]["fv"] and r["terminal_included"] is False, (r["fv"], o1["scenarios"]["base"]["fv"])
    assert abs(en._active({"supply": {"buyback": {"years": 0.54}}}, 1, 7) - 0.54) < 1e-12 and en._active({"supply": {"buyback": {"years": 0.54}}}, 2, 7) == 0

@t("NO MOAT flag explains ROE following Ke when floored")
def _():
    seg = {"name": "x", "weight": 1.0, "helmer": 1.0, "porter": 1.5}
    cfg, o = value(facts(moat__segments=[seg]))
    assert any(x.startswith("NO MOAT in bear/base/bull") for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]

@t("EXTREME bar symmetric: -65% flagged, -55% not")
def _():
    import engine as en
    assert en.extreme_checks(-0.65, 0.3, 0.05, 10, {}) and not en.extreme_checks(-0.55, 0.3, 0.05, 10, {})

@t("third regulatory class us_facing_no_kyc_settled = 1.5/1.0/0.5%")
def _():
    cfg, _ = value(facts(risk__reg_class="us_facing_no_kyc_settled"))
    assert [cfg["scenarios"][s]["ke"]["reg"] for s in ("bear", "base", "bull")] == [0.015, 0.01, 0.005]

@t("market_stats: two-year level and benchmark")
def _():
    import market_stats as ms
    last = 1791849600
    ch = [[last - i * 86400, 1e6 if i < 365 else 2e6 if i < 730 else 3e6] for i in range(1200)]
    m = ms.stats(ch, "2026-10-14T12:00:00Z")
    assert abs(m["level_2y_ago_365d"] - 1095.0) < 1e-6 and abs(m["yoy"] + 0.5) < 1e-9, m

@t("EARLY STAGE: 60-day token values, E0 = lower run-rate, 1.0pp track premium in near-term Ke only")
def _():
    last = 1791849600
    ch = [[last - i * 86400, 3e6] for i in range(60)]          # flat $3m/day for 60 days
    w = engine.e0_windows(ch, "2026-10-14T12:00:00Z")
    assert w["history_days"] == 60 and abs(w["e0"] - 1095.0) < 1e-6, w
    cfg, o = value(facts(earnings={"windows": w, "other": 0}))
    k = cfg["scenarios"]["base"]["ke"]
    assert k["track"] == 0.01, k
    r = o["scenarios"]["base"]
    assert abs((r["ke"] - r["ke_T"]) - (k["sc_now"] - k["sc_floor"] + 0.01)) < 1e-9, (r["ke"], r["ke_T"])
    assert any(x.startswith("EARLY STAGE") for x in o["warnings"]) and not any("SHORT HISTORY" in x for x in o["warnings"]), o["warnings"]
    assert any(r_["id"] == "D22" for r_ in cfg["judgement"]["table"])

@t("EARLY STAGE: launch spike then decay -> E0 from the last 14 days, LAUNCH DECAY flagged")
def _():
    last = 1791849600
    ch = [[last - i * 86400, 1e6 if i < 30 else 9e6] for i in range(45)]
    w = engine.e0_windows(ch, "2026-10-14T12:00:00Z")
    assert abs(w["e0"] - w["14d"]) < 1e-9 and w["14d"] < w["since_launch"], w
    cfg, o = value(facts(earnings={"windows": w, "other": 0}))
    assert any(x.startswith("LAUNCH DECAY") for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]
    assert abs(cfg["E0_core"] - 365.0) < 1e-6, cfg["E0_core"]

@t("EARLY STAGE: premium shrinks to 0 at 90 days; 89 days still early, 90 days is SHORT HISTORY")
def _():
    last = 1791849600
    for d, want in ((30, 0.02), (89, 0.0003)):
        w = engine.e0_windows([[last - i * 86400, 1e6] for i in range(d)], "2026-10-14T12:00:00Z")
        cfg, _ = value(facts(earnings={"windows": w, "other": 0}))
        assert cfg["scenarios"]["base"]["ke"].get("track") == want, (d, cfg["scenarios"]["base"]["ke"])
    w = engine.e0_windows([[last - i * 86400, 1e6] for i in range(90)], "2026-10-14T12:00:00Z")
    cfg, o = value(facts(earnings={"windows": w, "other": 0}))
    assert "track" not in cfg["scenarios"]["base"]["ke"] and any("SHORT HISTORY" in x for x in o["warnings"])

@t("EARLY STAGE: engine refuses a hand-built 60-day input not built as early stage")
def _():
    last = 1791849600
    w = engine.e0_windows([[last - i * 86400, 1e6] for i in range(60)], "2026-10-14T12:00:00Z")
    cfg = dv.build(facts(earnings={"windows": w, "other": 0})); cfg["judgement"]["confirmed"] = True
    cfg["data"]["early_stage"] = False
    stops(lambda: engine.run(cfg), "early stage")

@t("STRESS: fair-value solver converges on a time-limited commitment that plain iteration could not solve")
def _():
    f = facts(supply={"S0": 531.3, "vest": [138.5, 112.8, 73.9, 11.3, 117.0, 21.4], "unissued": 641.4, "self_sustaining": False,
                      "team_largest_holder": False, "buyback": {"mode": "fair_value", "years": 5.2, "continue_after": False}})
    cfg, o = value(f)
    for n, r in o["scenarios"].items():
        assert not any("did not converge" in x for x in r["flags"]), (n, r["flags"])
        if r["terminal_included"]: assert abs(r["fv_holder_retains"] - r["fv"]) < 1e-6 * r["fv"]

@t("STRESS: higher Ke never raises value on a deep-buyback case (no 5% floor distortion in fair-value mode)")
def _():
    f = facts(supply={"S0": 293.4, "vest": [53.4] + [13.6] * 6, "unissued": 0, "self_sustaining": True, "team_largest_holder": True,
                      "buyback": {"mode": "fair_value", "years": 4.23, "continue_after": False}})
    cfg, o = value(f)
    c2 = copy.deepcopy(cfg); c2["scenarios"]["base"]["ke"]["reg"] += 0.01
    assert engine.run(c2)["scenarios"]["base"]["fv"] <= o["scenarios"]["base"]["fv"] * (1 + 1e-9)

@t("STRESS: infinite / NaN / text price and launch date after as_of are refused")
def _():
    for bad in (float("inf"), float("nan"), "70"):
        c = dv.build(facts()); c["price"] = bad; c["judgement"]["confirmed"] = True
        try: engine.run(c); raise AssertionError(f"price {bad!r} accepted")
        except ValueError: pass
    try: dv.build(facts(risk__age_months=DEL, risk__launch_date="2027-01-01")); raise AssertionError("future launch accepted")
    except ValueError as e: assert "launch_date" in str(e)

@t("STRESS: windows count exact duplicate rows once and read millisecond timestamps")
def _():
    last = 1791849600
    ch = [[last - i * 86400, 1e6] for i in range(400)]
    w = engine.e0_windows(ch + [[last, 1e6]], "2026-10-14T12:00:00Z")
    assert abs(w["7d"] - 365.0) < 1e-9 and any("duplicate" in n for n in w["notes"]), w
    w = engine.e0_windows([[t * 1000, v] for t, v in ch], "2026-10-14T12:00:00Z")
    assert w["history_days"] == 400 and any("milliseconds" in n for n in w["notes"]), w

@t("FEE SWITCH: switched-on value uses the post-switch premium (default 1%), not the switch-off premium")
def _():
    f = facts(risk__routing="fee_switch_off"); f["option"] = {"type": "fee_switch", "fees_ttm": 4000, "take_rate": 0.25}
    cfg, o = value(f)
    assert all(cfg["scenarios"][s]["ke"]["align"] == 0.01 for s in ("bear", "base", "bull")), cfg["scenarios"]["base"]["ke"]
    d12 = [r for r in cfg["judgement"]["table"] if r["id"] == "D12"][0]
    assert "switched-on state" in d12["rule"], d12
    f2 = copy.deepcopy(f); f2["option"]["routing_on"] = "mechanical"
    cfg2, o2 = value(f2)
    assert cfg2["scenarios"]["base"]["ke"]["align"] == 0.0 and o2["pw_fv_on"] > o["pw_fv_on"]
    f3 = copy.deepcopy(f); f3["option"]["routing_on"] = "fee_switch_off"
    try: dv.build(f3); raise AssertionError("routing_on = fee_switch_off accepted")
    except ValueError as e: assert "routing_on" in str(e)

@t("FEE SWITCH: base_label shows in the option report")
def _():
    f = facts(risk__routing="fee_switch_off"); f["option"] = {"type": "fee_switch", "fees_ttm": 89.5, "take_rate": 1.0, "base_label": "protocol revenue (TTM)"}
    cfg = dv.build(f); cfg["judgement"]["confirmed"] = True
    assert "protocol revenue (TTM) $89.5m" in engine.to_md_option(engine.run_option(cfg))

def _rs_chart(level_musd_per_year, days=500, zero_last=0):
    last = 1791849600
    return {"totalDataChart": [[last - i * 86400, 0.0 if i < zero_last else level_musd_per_year * 1e6 / 365] for i in range(days)]}

@t("REVENUE STACK: routed (HYPE-like), treasury (Aave-like, paused), LP fees (Uniswap-pre-switch-like), no revenue")
def _():
    import revenue_stack as rs
    L = lambda c: rs.level_from(c, "2026-10-14T12:00:00Z")
    o = rs.build(L(_rs_chart(900)), L(_rs_chart(880)), L(_rs_chart(870)))
    assert o["case"] == "routed" and "option" not in o, o["case"]
    o = rs.build(L(_rs_chart(691)), L(_rs_chart(89.5)), L(_rs_chart(18.2, zero_last=40)), expenses=20)
    assert o["case"] == "treasury" and abs(o["option"]["fees_ttm"] - 69.5) < 1e-6 and o["option"]["take_rate"] is None, o.get("option")
    assert o["option"]["base_label"].startswith("protocol revenue net of costs") and any("stopped" in x for x in o["flags"])
    o = rs.build(L(_rs_chart(1000)), L(_rs_chart(0.0)), L(_rs_chart(0.0)), take_rate=0.16)
    assert o["case"] == "lp_fees" and o["option"]["take_rate"] == 0.16 and len(o["fee_loss_brackets"]) == 3, o
    assert abs(o["fee_loss_brackets"][1]["fees_ttm"] - 800) < 1e-6
    o = rs.build(L(_rs_chart(0.0)), L(_rs_chart(0.0)), L(_rs_chart(0.0)))
    assert o["case"] in ("no_revenue", "incomplete"), o["case"]

@t("REVENUE STACK: inconsistent series flagged; totals files accepted and flagged")
def _():
    import revenue_stack as rs
    L = lambda c: rs.level_from(c, "2026-10-14T12:00:00Z")
    o = rs.build(L(_rs_chart(100)), L(_rs_chart(150)), L(_rs_chart(160)))
    fl = " ".join(o["flags"])
    assert "exceeds fees" in fl and "exceeds protocol revenue" in fl, fl
    t = rs.level_from({"total1y": 89486657, "total30d": 5062205, "history_days": 2141}, None)
    assert abs(t["ttm"] - 89.486657) < 1e-9 and t["from_totals"] is True

@t("REVENUE STACK: the treasury option block values end to end (take rate filled in)")
def _():
    import revenue_stack as rs
    L = lambda c: rs.level_from(c, "2026-10-14T12:00:00Z")
    o = rs.build(L(_rs_chart(691)), L(_rs_chart(89.5)), L(_rs_chart(18.2, zero_last=40)), take_rate=0.5)
    f = facts(risk__routing="paused"); f["option"] = o["option"]
    cfg, out = value(f)
    assert out["mode"] == "option" and out["E0_on"] == o["option"]["fees_ttm"] * 0.5, (out["E0_on"], o["option"])
    f2 = facts(risk__routing="paused"); f2["option"] = dict(o["option"], take_rate=None)
    try: value(f2); raise AssertionError("missing take_rate accepted")
    except ValueError as e: assert "take_rate" in str(e)

# ---------------- 6.4.0: found in the live four-token test (HYPE, PUMP, STONK, PONS; 15 Oct 2026) ----------------
LAST = 1791849600   # 2026-10-13
def _ch(vals):
    """Daily chart ending 2026-10-13; vals[0] is the latest day."""
    return [[LAST - i * 86400, v] for i, v in enumerate(vals)]

@t("LIVE: DECAYING reaches the output (from the windows tool and from core_by_window), and EXTREME names it")
def _():
    w = engine.e0_windows(_ch([2e5] * 7 + [1e6] * 93), "2026-10-14T12:00:00Z")
    rc = {"revenue_14d": 1000.0, "holder_share": 1.0}
    cfg, o = value(facts(earnings={"windows": w, "other": 0, "revenue_check": rc}))
    assert cfg["data"]["decaying"] is True and abs(cfg["data"]["run_rate_7d"] - 73.0) < 1e-9, cfg["data"]
    assert any(x.startswith("DECAYING") and "E0_core = 73.00" in x for x in o["warnings"]), o["warnings"]
    assert sum(x.count("DECAYING:") for x in o["warnings"]) == 1, o["warnings"]          # reported once, by the gate
    cfg, o = value(facts(earnings__core_by_window={"365d": 700.0, "30d": 600.0, "7d": 300.0}, price=10))
    assert any(x.startswith("DECAYING") for x in o["warnings"]), o["warnings"]
    assert o["warnings"][0].startswith("EXTREME") and "E0_core = 300.00" in o["warnings"][0], o["warnings"][0]

@t("LIVE: latest day not yet published -> windows end on the source's last day; older data flagged out of date; low last day flagged")
def _():
    w = engine.e0_windows(_ch([1e6] * 400), "2026-10-15T07:44:51Z")
    assert w["windows_end"] == "2026-10-13" and w["last_complete_day"] == "2026-10-14" and abs(w["7d"] - 365.0) < 1e-9, w
    assert any(x.startswith("LATEST DAY NOT PUBLISHED") for x in w["flags"]), w["flags"]
    w = engine.e0_windows(_ch([1e6] * 400), "2026-10-19T07:00:00Z")      # the file stops 5 days before the valuation date
    assert w["windows_end"] == "2026-10-13" and abs(w["7d"] - 365.0) < 1e-9, w   # no zeros counted
    assert any(x.startswith("DATA OUT OF DATE: the data ends on 2026-10-13, 5 days") for x in w["flags"]), w["flags"]
    w = engine.e0_windows(_ch([3e5] + [1e6] * 399), "2026-10-14T07:00:00Z")
    assert any(x.startswith("LAST DAY LOW: 2026-10-13 is 30%") for x in w["flags"]), w["flags"]
    cfg, o = value(facts(earnings={"windows": w, "other": 0}))
    assert any(x.startswith("DATA: LAST DAY LOW") for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]

@t("LIVE: no E0 jump at day 90 (89 days early stage and 90 days short history both take the 14-day rate when it is lower)")
def _():
    e = {}
    for d in (89, 90):
        w = engine.e0_windows(_ch([1e6] * 14 + [5e6] * (d - 14)), "2026-10-14T12:00:00Z")
        rc = {"revenue_14d": 1e4, "holder_share": 1.0}
        cfg, _ = value(facts(earnings={"windows": w, "other": 0, "revenue_check": rc}))
        e[d] = cfg["E0_core"]
    assert abs(e[89] - 365.0) < 1e-9 and abs(e[90] - 365.0) < 1e-9, e

@t("LIVE: revenue check caps E0 under a year, only flags from a year, and is asked for when missing")
def _():
    cbw = {"90d": 700.0, "14d": 650.0, "30d": 680.0, "7d": 640.0}
    cfg, o = value(facts(earnings__history_days=200, earnings__core_by_window=cbw,
                         earnings__revenue_check={"revenue_14d": 500.0, "revenue_7d": 480.0, "holder_share": 0.8}))
    assert abs(cfg["E0_core"] - 400.0) < 1e-9 and cfg["data"]["revenue_capped"] is True, cfg["E0_core"]
    assert any(x.startswith("REVENUE CHECK:") for x in cfg["judgement"]["flags"])
    cfg, o = value(facts(earnings__core_by_window={"365d": 700.0, "30d": 690.0},
                         earnings__revenue_check={"revenue_30d": 600.0, "holder_share": 0.5}))
    assert cfg["E0_core"] == 700.0 and any(x.startswith("REVENUE FALLING") for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]
    cfg, o = value(facts(earnings__history_days=200, earnings__core_by_window=cbw))
    assert any(x.startswith("REVENUE CHECK NOT RUN") for x in cfg["judgement"]["flags"])
    f = facts(earnings__history_days=200, earnings__core_by_window=cbw, earnings__revenue_check={"revenue_14d": 1.0, "holder_share": 0.5})
    f["option"] = {"type": "paused_buyback", "holder_rev_hist": 700.0}
    cfg = dv.build(f)
    assert not any(x.startswith("REVENUE") for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]   # option path: not applied

@t("LIVE: revenue stack measures all three series on one window (STONK-like) and flags a sharp fall and lagging buybacks (PONS-like)")
def _():
    import revenue_stack as rs
    P = lambda vals: rs.parse({"totalDataChart": _ch(vals)}, "2026-10-14T12:00:00Z")
    rev = [1e6] * 72 + [100.0] * 8                     # tiny revenue for 8 days before holder revenue starts
    o = rs.build(P([x * 1.1 for x in rev]), P(rev), P([6e5] * 72 + [0.0] * 8))
    assert abs(o["ratios"]["holders_of_revenue"] - 0.6) < 1e-12 and "72d annualised, since holder revenue began" in o["window"], o["window"]
    assert "TTM" not in o["option"]["base_label"] and o["revenue_check"]["holder_share"] == 0.6, o["option"]
    rev = [2e5] * 7 + [1e6] * 90                        # revenue fell 80% in the last week; buybacks still run at the old rate
    o = rs.build(P([x * 5 for x in rev]), P(rev), P([6e5] * 97))
    fl = " ".join(o["flags"])
    assert "SHARP FALL" in fl and "HOLDER FLOW LAGS REVENUE" in fl, fl
    rc = o["revenue_check"]
    assert abs(rc["revenue_7d"] - 73.0) < 1e-9 and rc["revenue_14d"] is not None and rc["share_basis"].startswith("measured"), rc
    o = rs.build(P([x * 5 for x in rev]), P(rev), P([6e5] * 97), holder_share=0.8)
    assert o["revenue_check"]["holder_share"] == 0.8 and o["revenue_check"]["share_basis"].startswith("documented")
    fees_behind = rs.parse({"totalDataChart": [[LAST - (i + 1) * 86400, 5e6] for i in range(99)]}, "2026-10-14T12:00:00Z")
    o = rs.build(fees_behind, P([1e6] * 100), P([8e5] * 100))  # fees one day behind: all three measured to the fees' last day
    assert o["window_end"] == "2026-10-12" and any("measured to 2026-10-12" in x for x in o["flags"]), (o["window_end"], o["flags"])

@t("LIVE: silent defaults are flagged: no market series, commitment assumed to continue (once), borderline moat with runnable overrides")
def _():
    cfg, o = value(facts(market={"basis": "none"}))
    assert any(x.startswith("NO MARKET SERIES") for x in cfg["judgement"]["flags"]) and cfg["judgement"]["market_basis"] == "none"
    cfg, o = value(facts())
    assert not any(x.startswith("NO MARKET SERIES") for x in cfg["judgement"]["flags"])
    cfg, o = value(facts(supply__buyback={"mode": "fair_value", "years": 0.53, "continue_after": True}))
    assert sum("COMMITMENT ASSUMED TO CONTINUE" in x for x in o["warnings"]) == 1, o["warnings"]
    cfg, o = value(facts(supply__buyback={"mode": "fair_value", "years": 0.53, "continue_after": False}))
    assert not any("COMMITMENT ASSUMED" in x for x in o["warnings"])
    f = facts(); f["moat"]["segments"] = [{"name": "x", "weight": 1, "helmer": 2.0, "porter": 0.6}]
    cfg = dv.build(f)
    a = cfg["judgement"]["adjacent_band"]
    assert tuple(a["band"]) == (0.12, 0.25) and a["set"] == "weaker", a
    assert any(x.startswith("BORDERLINE MOAT") for x in cfg["judgement"]["flags"]) and "Adjacent band" in dv.to_md(cfg)
    dv.apply_overrides(cfg, a["overrides"]); cfg["judgement"]["confirmed"] = True
    o = engine.run(cfg)
    assert all(abs(o["scenarios"][s]["roe"] - a["roe"][s]) < 1e-6 for s in ("bear", "base", "bull")), [o["scenarios"][s]["roe"] for s in o["scenarios"]]

@t("LIVE: young category in decline -> flat market growth, with or without a benchmark; a young category still growing keeps the calibrated rule")
def _():
    m = {"basis": "category_series", "trailing_cagr": 1.5, "cagr_years": 4, "record_365d": 1200, "ttm_365d": 600, "yoy": -0.44,
         "benchmark_yoy": -0.10, "level_2y_ago_365d": 150}
    for mk in (m, {k: v for k, v in m.items() if k != "benchmark_yoy"}):
        cfg, _ = value(facts(market=mk))
        d2 = [r for r in cfg["judgement"]["table"] if r["id"] == "D2"][0]
        assert d2["values"] == {"base": 0.0, "bull": 0.1, "bear": -0.1}, d2["values"]
        assert any(x.startswith("YOUNG CATEGORY IN DECLINE") for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]
    cfg, _ = value(facts(market=dict(m, yoy=0.30)))
    assert [r for r in cfg["judgement"]["table"] if r["id"] == "D2"][0]["values"]["base"] == 0.2

@t("LIVE: chart_from_text builds a verified chart and refuses a listing that doesn't sum to totalAllTime")
def _():
    import chart_from_text as cf
    txt = "timestamp,value\n" + "\n".join(f"{t}, {v:.0f}" for t, v in _ch([1000.0, 2000.0, 0.0, 3000.0])) + "\n\n"
    out = cf.build(cf.parse_lines(txt), 6000.0)
    assert len(out["totalDataChart"]) == 4 and out["check"]["date_gaps"] == [] and out["check"]["last_day"] == "2026-10-13", out["check"]
    for bad_total in (6045.0, 5000.0):
        try: cf.build(cf.parse_lines(txt), bad_total); raise AssertionError("wrong total accepted")
        except ValueError as e: assert "all-time total" in str(e)
    w = engine.e0_windows(cf.build(cf.parse_lines("\n".join(f"{t}\t{v}" for t, v in _ch([1e6] * 40))), 4e7)["totalDataChart"], "2026-10-14T12:00:00Z")
    assert w["history_days"] == 40, w

@t("LIVE: market_stats ends on the source's last day when the latest day isn't published (TTM not diluted)")
def _():
    import market_stats as ms
    s = ms.stats(_ch([1e6] * 800), "2026-10-15T07:00:00Z")
    assert s["last_complete_day"] == "2026-10-13" and abs(s["ttm_365d"] - 365.0) < 1e-9 and "data_note" in s, s

# ---------------- 6.5.0: user-supplied data (CSV downloads, screenshot figures) ----------------
@t("USER DATA: a DefiLlama-style CSV (ISO dates, three series, a missing cell) gives the same chart as the raw listing")
def _():
    import chart_from_text as cf
    from datetime import datetime, timezone
    vals = [(LAST - i * 86400, 1000.0 + i) for i in range(40)]
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).date().isoformat()
    csv_txt = "﻿Date,Fees,Revenue,Holders Revenue\n" + "\n".join(f"{iso(t)},{'' if i == 0 else v * 5},{v * 2},{v}" for i, (t, v) in enumerate(vals))
    rows, name = cf.parse_table(csv_txt.lstrip("﻿"), "x.csv", "holders revenue")
    out = cf.build(rows, sum(v for _, v in vals))
    assert name == "Holders Revenue" and out["totalDataChart"] == sorted([[t, v] for t, v in vals]), out["check"]
    fees, _ = cf.parse_table(csv_txt.lstrip("﻿"), "x.csv", "Fees")
    assert len(fees) == 39                                      # the blank cell is skipped, not read as zero
    for bad, needle in (({"column": None}, "several value columns"), ({"column": "Volume"}, "not found")):
        try: cf.parse_table(csv_txt.lstrip("﻿"), "x.csv", bad["column"]); raise AssertionError("accepted")
        except ValueError as e: assert needle in str(e), e
    weekly = "Timestamp,Fees\n" + "\n".join(f"{LAST - i * 7 * 86400},5" for i in range(10))
    try: cf.build(cf.parse_table(weekly)[0], None); raise AssertionError("weekly rows accepted")
    except ValueError as e: assert "weekly or monthly" in str(e), e
    listed = "total24h: 5, total7d: 9, totalAllTime: 3\n1791849600,1\n1791763200,2\n"   # summary line left at the top
    assert cf.build(cf.parse_lines(listed), 3.0)["check"]["rows"] == 2

@t("USER DATA: screenshot figures in a totals file: under a year, cumulative over days since launch; from a year, TTM")
def _():
    import revenue_stack as rs
    t = rs.parse({"totalAllTime": 22.58e6, "total30d": 8.09e6, "total7d": 1.35e6, "history_days": 92}, None)
    assert abs(t["level"] - 22.58 * 365 / 92) < 1e-9 and "since launch" in t["how"] and abs(t["rr"]["7d"] - 1.35 * 365 / 7) < 1e-9, t
    t = rs.parse({"total1y": 284.5e6, "totalAllTime": 386.5e6, "total30d": 29.9e6, "history_days": 456}, None)
    assert abs(t["level"] - 284.5) < 1e-9 and t["how"].startswith("TTM"), t

# ---------------- 6.6.0: valuation basis and input confidence, conditional reports, earnings counted once, holder rights ----------------
@t("BASIS/CONFIDENCE: calibration MEDIUM (perps constants, band edge); clean live-data case HIGH; under a year LOW; shown in the report")
def _():
    cfg, o = value(facts())
    assert o["basis"].startswith("existing holder earnings") and o["confidence"]["level"] == "MEDIUM", o["confidence"]
    assert any("perps constants" in r for r in o["confidence"]["reasons"]), o["confidence"]
    md = engine.to_md(o)
    assert "**Valuation basis:** existing holder earnings" in md and "**Input confidence: MEDIUM**" in md
    assert md.index("**Valuation basis:**") < md.index("**Flags:**")
    clean = facts(price=35, moat__segments=[{"name": "core", "weight": 1.0, "helmer": 2.3, "porter": 0.5}],
                  market={"basis": "category_series", "trailing_cagr": 0.30, "cagr_years": 3.0, "record_365d": 120.0, "ttm_365d": 100.0,
                          "yoy": 0.10, "benchmark_yoy": 0.05, "level_2y_ago_365d": 60.0})
    cfg, o = value(clean)
    assert o["confidence"] == {"level": "HIGH", "reasons": []}, o["confidence"]
    cfg, o = value(facts(earnings__history_days=200, earnings__core_by_window={"90d": 700, "14d": 720, "30d": 650}))
    assert o["confidence"]["level"] == "LOW" and "200 days of holder earnings, under a year" in o["confidence"]["reasons"], o["confidence"]

@t("CONDITIONAL: leads with the value if switched on today; D21 cases labelled placeholders and never EXTREME; no condition -> flagged once, LOW")
def _():
    f = facts(risk__routing="fee_switch_off", price=5); f["option"] = {"type": "fee_switch", "fees_ttm": 4000, "take_rate": 0.25}
    cfg, o = value(f)
    assert o["default_cases"] and o["pw_upside"] > engine.EXTREME["pw_up"], o["pw_upside"]
    assert not any(w.startswith("EXTREME") for w in o["warnings"]), o["warnings"]           # placeholders aren't a result
    assert sum("NO STATED CONDITION" in w for w in o["warnings"]) == 1, o["warnings"]
    assert o["confidence"]["level"] == "LOW" and "no stated condition" in o["confidence"]["reasons"], o["confidence"]
    assert "0" in o["implied_p"] and o["basis"].startswith("conditional holder earnings"), (o["implied_p"], o["basis"])
    md = engine.to_md_option(o)
    i_on, i_imp, i_cases = (md.index(s) for s in ("**Value if switched on today", "**What the price implies", "With activation cases (D21 placeholders"))
    assert i_on < i_imp < i_cases, (i_on, i_imp, i_cases)
    f["option"].update(condition="a governance proposal (test)", activation=[{"label": "vote", "p": 0.4, "delay_years": 2}])
    cfg, o = value(f)
    assert o["warnings"][0].startswith("EXTREME RESULT") and not any("NO STATED CONDITION" in w for w in o["warnings"]), o["warnings"]
    assert set(o["implied_p"]) == {"0", "1", "2", "3", "5"} and "your cases" in engine.to_md_option(o), o["implied_p"]
    f["price"] = 1000; f["option"].pop("activation")
    cfg, o = value(f)
    assert o["warnings"][0].startswith("PRICE ABOVE THE SWITCHED-ON VALUE") and o["implied_p"]["0"] is None, o["warnings"][:2]
    h = json.load(open(os.path.join(SK, "examples", "option_example.json"))); h.pop("implied_delays", None); h["option"].pop("implied_delays")
    assert "0" in engine.run_option(h)["implied_p"]                                        # hand-built input: today is always in the grid

@t("EARNINGS ONCE: payout < 100% on holder earnings flagged unless explained; holder share above 100% capped and flagged")
def _():
    fl = lambda f: " ".join(dv.build(f)["judgement"]["flags"])
    assert "PAYOUT BELOW 100%" in fl(facts(payout=0.8)) and "PAYOUT BELOW 100%" not in fl(facts())
    assert "PAYOUT BELOW 100%" not in fl(facts(payout=0.8, payout_reason="E0 built from total protocol earnings, 80% routed"))
    rc = {"revenue_7d": 520, "revenue_14d": 500, "revenue_30d": 510, "holder_share": 1.3}
    cfg = dv.build(facts(earnings__history_days=200, earnings__core_by_window={"90d": 700, "14d": 720, "30d": 650}, earnings__revenue_check=rc))
    assert cfg["E0_core"] == 500 and "HOLDER FLOW ABOVE REVENUE" in " ".join(cfg["judgement"]["flags"]), cfg["E0_core"]
    import revenue_stack as rs
    L = lambda c: rs.level_from(c, "2026-10-14T12:00:00Z")
    o = rs.build(L(_rs_chart(300)), L(_rs_chart(150)), L(_rs_chart(160)))
    assert o["revenue_check"]["holder_share"] == 1.0 and abs(o["revenue_check"]["holder_share_measured"] - 160 / 150) < 1e-5, o["revenue_check"]
    for bad in (1.5, -0.1):
        try: dv.build(facts(payout=bad)); raise AssertionError(f"payout {bad} accepted")
        except ValueError as e: assert "payout" in str(e), e

@t("RIGHTS (D23): recorded in the table; cash payouts default to no buyback; staking-only and mode mismatch flagged; missing flagged on the standard path only")
def _():
    cfg = dv.build(facts())
    d23 = [r for r in cfg["judgement"]["table"] if r["id"] == "D23"]
    assert d23 and d23[0]["values"] == {"all": "buyback_burn / all_holders"}, d23
    assert not any(x.startswith(("HOLDER RIGHTS NOT RECORDED", "BENEFIT")) for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]
    cfg = dv.build(facts(rights={"benefit_form": "staking_distribution", "access": "stakers_only"}, supply__buyback=DEL))
    assert all(cfg["scenarios"][s]["supply"]["buyback"]["mode"] == "none" for s in ("bear", "base", "bull"))
    assert any(x.startswith("BENEFIT REQUIRES STAKING") for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]
    cfg = dv.build(facts(rights={"benefit_form": "distribution"}))                         # calibration buyback block kept
    assert any(x.startswith("BENEFIT IS PAID AS CASH") for x in cfg["judgement"]["flags"]), cfg["judgement"]["flags"]
    assert any(x.startswith("HOLDER RIGHTS NOT RECORDED") for x in dv.build(facts(rights=DEL))["judgement"]["flags"])
    f = facts(rights=DEL, risk__routing="fee_switch_off"); f["option"] = {"type": "fee_switch", "fees_ttm": 400, "take_rate": 0.25}
    assert not any(x.startswith("HOLDER RIGHTS") for x in dv.build(f)["judgement"]["flags"])
    for rt, needle in (({"benefit_form": "airdrop"}, "rights.benefit_form"), ({"benefit_form": "distribution", "access": "whales"}, "rights.access"),
                       ("buyback", "rights must be an object")):
        try: dv.build(facts(rights=rt)); raise AssertionError(f"rights {rt!r} accepted")
        except ValueError as e: assert needle in str(e), e

for n, st, msg in results:
    print(f"{st:5s}  {n}" + (f"\n       -> {msg}" if msg else ""))
n_ok = sum(s == 'PASS' for _, s, _ in results)
print(f"\n{n_ok}/{len(results)} passed")
sys.exit(0 if n_ok == len(results) else 1)

"""Property-based fuzzing: random but plausible facts files through defaults + engine. Usage: t2_fuzz.py <skill> <n> <seed>"""
import sys, json, copy, random, math, traceback, collections
SK = sys.argv[1]; N_CASES = int(sys.argv[2]); SEED = int(sys.argv[3])
sys.path.insert(0, SK + "/scripts")
import defaults as dv, engine

rng = random.Random(SEED)
BASE = json.load(open(SK + "/examples/calibration_facts.json"))
fails = collections.defaultdict(list); stops = collections.Counter(); valued = 0; option_runs = 0; flags_seen = collections.Counter()

def rand_facts():
    f = copy.deepcopy(BASE)
    f["protocol"] = "FUZZ"; f["as_of"] = "2026-10-14T12:00:00Z"
    f["price"] = 10 ** rng.uniform(-4, 3)
    h = rng.choice([rng.randint(0, 29), rng.randint(30, 89), rng.randint(90, 364), rng.randint(365, 2000)])
    e0 = 10 ** rng.uniform(-1, 3.5)
    w = {"history_days": h}
    if h >= 365: cbw = {"365d": e0, "90d": e0 * rng.uniform(0.5, 1.5), "30d": e0 * rng.choice([rng.uniform(0.5, 1.6), 0.0, rng.uniform(0, 0.12)])}
    elif h >= 90: cbw = {"90d": e0, "14d": e0 * rng.uniform(0.3, 1.6), "30d": e0 * rng.choice([rng.uniform(0.5, 1.6), 0.0])}
    else: cbw = {"since_launch": e0, "14d": e0 * rng.uniform(0.2, 1.8), "30d": e0 * rng.uniform(0.5, 1.5)}
    if rng.random() < 0.5: cbw["7d"] = e0 * rng.uniform(0.1, 1.5)
    f["earnings"] = {"history_days": h, "core_by_window": cbw, "other": rng.choice([0.0, e0 * rng.uniform(0, 0.5)])}
    if rng.random() < 0.6:
        f["earnings"]["revenue_check"] = {"revenue_14d": rng.choice([None, e0 * rng.uniform(0.1, 3)]), "revenue_30d": e0 * rng.uniform(0.1, 3),
                                          "revenue_7d": e0 * rng.uniform(0.05, 3), "holder_share": rng.uniform(0.2, 1.1)}
    if rng.random() < 0.05: f["earnings"]["diagnostic"] = True
    b = rng.choice(["fallback_perps", "category_series", "none"])
    if b == "fallback_perps": f["market"] = {"basis": b}
    elif b == "none": f["market"] = {"basis": b}
    else:
        rec = 10 ** rng.uniform(0, 4); ttm = rec * rng.uniform(0.1, 1.0)
        f["market"] = {"basis": b, "trailing_cagr": rng.uniform(-0.5, 3.0), "cagr_years": rng.choice([2, 3, 4, 5, None]),
                       "record_365d": rec, "ttm_365d": ttm, "yoy": rng.choice([None, rng.uniform(-0.8, 1.5)]),
                       "benchmark_yoy": rng.choice([None, rng.uniform(-0.6, 0.8)]), "level_2y_ago_365d": rng.choice([None, rec * rng.uniform(0.1, 1.2)])}
    f["share"] = {"share_0": rng.uniform(0.01, 0.9)}
    if rng.random() < 0.5:
        f["moat"] = {"segments": [{"name": "s", "weight": 1, "rubric": {
            "share_30d": rng.uniform(0, 0.9), "holder_rev_ttm_musd": e0, "age_months": rng.randint(0, 100), "rank": rng.randint(1, 10),
            "n_competitors_ge10": rng.randint(0, 5), "share_change_pp": rng.uniform(-30, 10),
            **{k: rng.random() < 0.5 for k in ("custodial_incumbent", "bond_lock", "incentive_driven", "own_chain_or_unique_tech",
                                               "major_exploit", "young_top3_competitor", "supplier_dependency", "offchain_substitute")}}}]}
    f["risk"].update(reg_class=rng.choice(["unresolved_us_no_kyc", "us_facing_no_kyc_settled", "regulated_or_kyc"]),
                     formal_action=rng.random() < 0.1, routing=rng.choice(["mechanical", "documented_not_immutable", "time_limited", "discretionary", "paused", "fee_switch_off"]),
                     age_months=rng.randint(0, 120), major_exploit=rng.random() < 0.1,
                     **{k: rng.random() < 0.5 for k in ("concentrated_control", "team_can_change_rules", "no_legal_wrapper", "alignment_offset")})
    f["rf"] = {"value": rng.uniform(0.0, 0.07)}; f["erp"] = {"value": rng.uniform(0.03, 0.07)}
    S0 = 10 ** rng.uniform(0, 4)
    f["supply"] = {"S0": S0, "vest": [S0 * rng.uniform(0, 0.3) for _ in range(rng.randint(0, 7))], "unissued": rng.choice([0, S0 * rng.uniform(0, 2)]),
                   "self_sustaining": rng.random() < 0.5, "team_largest_holder": rng.random() < 0.5,
                   "buyback": rng.choice([{"mode": "fair_value"}, {"mode": "none"}, {"mode": "constant_pe"},
                                          {"mode": "fixed_tokens", "tokens_per_yr": S0 * rng.uniform(0, 0.1)},
                                          {"mode": "fair_value", "years": rng.uniform(0.1, 6), "continue_after": rng.random() < 0.5}])}
    if f["risk"]["routing"] in ("paused", "fee_switch_off") or rng.random() < 0.05:
        f["option"] = rng.choice([{"type": "paused_buyback", "holder_rev_hist": e0},
                                  {"type": "fee_switch", "fees_ttm": e0 * 4, "take_rate": rng.uniform(0.05, 1)}])
        if rng.random() < 0.5: f["option"]["condition"] = "fuzz: a stated mechanism"
    # 6.6.0: holder rights (D23), payout, and the buyback mode left to the benefit form
    if rng.random() < 0.75:
        f["rights"] = {"benefit_form": rng.choice(sorted(dv.BENEFIT_FORMS)), "access": rng.choice(dv.ACCESS)}
    else: f.pop("rights", None)
    if rng.random() < 0.3: f["supply"].pop("buyback")
    if rng.random() < 0.2: f["payout"] = rng.uniform(0.3, 1.0)
    f.pop("sens_g", None)
    return f

def bad(kind, f, msg): fails[kind].append((msg, json.dumps(f)[:300]))

for i in range(N_CASES):
    f = rand_facts()
    try:
        c1 = dv.build(copy.deepcopy(f)); c2 = dv.build(copy.deepcopy(f))
    except ValueError as e:
        if not str(e).startswith("STOP"): bad("defaults non-STOP ValueError", f, str(e))
        stops["defaults: " + str(e)[:60]] += 1; continue
    except Exception as e:
        bad("defaults crash", f, traceback.format_exc(limit=2)); continue
    if json.dumps(c1, sort_keys=True) != json.dumps(c2, sort_keys=True): bad("non-deterministic", f, "two builds differ")
    for fl in c1["judgement"].get("flags", []): flags_seen[fl.split(":")[0][:30]] += 1
    S = c1["scenarios"]
    rc = f["earnings"].get("revenue_check")
    h_ = f["earnings"]["history_days"]
    if rc and "option" not in f and 30 <= h_ < 365:
        r = rc.get("revenue_14d") if rc.get("revenue_14d") is not None else rc.get("revenue_30d")
        if c1["E0_core"] > r * min(rc["holder_share"], 1.0) * (1 + 1e-12): bad("E0 above what revenue supports (under a year, share capped at 100%)", f, f"{c1['E0_core']} vs {r * rc['holder_share']}")
    jf = " ".join(c1["judgement"].get("flags", []))
    if rc and "option" not in f and h_ >= 30 and rc["holder_share"] > dv.SHARE_TOL and "HOLDER FLOW ABOVE REVENUE" not in jf:
        bad("holder share above revenue not flagged", f, str(rc["holder_share"]))
    form = (f.get("rights") or {}).get("benefit_form")
    if "buyback" not in f["supply"] and form in ("distribution", "staking_distribution") and any(S_["supply"]["buyback"].get("mode") != "none" for S_ in c1["scenarios"].values()):
        bad("cash payout modelled as a buyback", f, form)
    if "option" not in f and not f.get("rights") and "HOLDER RIGHTS NOT RECORDED" not in jf: bad("missing rights not flagged", f, "")
    if "option" not in f and f.get("payout", 1.0) < 1 and "PAYOUT BELOW 100%" not in jf: bad("payout below 100% not flagged", f, str(f.get("payout")))
    if "option" not in f and 90 <= h_ < 365 and c1["E0_core"] > min(f["earnings"]["core_by_window"]["90d"], f["earnings"]["core_by_window"]["14d"]) * (1 + 1e-12):
        bad("short-history E0 above the lower of 90d and 14d", f, "")
    if "option" not in f and h_ >= 365 and c1["E0_core"] != f["earnings"]["core_by_window"]["365d"]: bad("TTM rule changed from 365 days", f, "")
    g = [S[s]["g1"] for s in ("bear", "base", "bull")]
    if not (g[0] <= g[1] <= g[2]): bad("g1 order", f, str(g))
    if abs(sum(S[s]["prob"] for s in S) - 1) > 1e-9: bad("probs", f, "")
    for s in S:
        k = S[s]["ke"]; keT = k["rf"] + k["erp"] + k["reg"] + k["gov"] + k["align"] + k["sc_floor"]
        if S[s]["roe"] < keT - 1e-12: bad("ROE below Ke_T", f, s)
        if k.get("track", 0) < 0 or k.get("track", 0) > 0.02 + 1e-12: bad("track premium range", f, str(k.get("track")))
    c1["judgement"]["confirmed"] = True
    try:
        o = engine.run_option(copy.deepcopy(c1)) if "option" in c1 else engine.run(copy.deepcopy(c1))
    except ValueError as e:
        if not str(e).startswith("STOP"): bad("engine non-STOP ValueError", f, str(e))
        stops["engine: " + str(e)[:60]] += 1; continue
    except Exception as e:
        bad("engine crash", f, traceback.format_exc(limit=3)); continue
    cf = o.get("confidence") or {}
    if cf.get("level") not in ("LOW", "MEDIUM", "HIGH") or (cf.get("level") == "HIGH") != (not cf.get("reasons")): bad("confidence label malformed", f, str(cf))
    if any(x.startswith("EXTREME") for x in o["warnings"]) and cf.get("level") != "LOW": bad("extreme result not LOW confidence", f, str(cf))
    if "option" in c1:
        option_runs += 1
        for r in o["scenarios"].values():
            if not (r["option_fv"] <= r["fv_on"] + 1e-9 or r["fv_on"] < 0): bad("option value > switch-on value", f, "")
        if not o["basis"].startswith("conditional holder earnings"): bad("option basis label", f, o["basis"])
        if not c1["option"].get("condition") and not (cf.get("level") == "LOW" and any("NO STATED CONDITION" in x for x in o["warnings"])):
            bad("missing condition not flagged LOW", f, str(cf))
        if (c1["price"] > o["pw_fv_on"]) != any(x.startswith("PRICE ABOVE THE SWITCHED-ON VALUE") for x in o["warnings"]):
            bad("price-above-switched-on flag mismatch", f, f"{c1['price']} vs {o['pw_fv_on']}")
        if "0" not in o["implied_p"]: bad("implied grid misses switching on today", f, str(o["implied_p"]))
        if o["default_cases"] and any(x.startswith("EXTREME") for x in o["warnings"]): bad("EXTREME from placeholder cases", f, "")
        continue
    if f["earnings"]["history_days"] < 365 and cf.get("level") != "LOW": bad("under a year not LOW confidence", f, str(cf))
    valued += 1
    R = o["scenarios"]
    nums = [o["pw_fv"]] + [r["fv"] for r in R.values()] + [r["pe_T"] for r in R.values()]
    if any(not math.isfinite(x) for x in nums): bad("non-finite output", f, str(nums)); continue
    w = [x for x in o["weight_sensitivity"] if [round(v, 2) for v in x["weights"]] == [0.2, 0.6, 0.2]]
    if not w or abs(w[0]["pw_fv"] - o["pw_fv"]) > 1e-9 * max(1, abs(o["pw_fv"])): bad("weights row != PW", f, "")
    for n, r in R.items():
        if r["fv"] < -1e-12: bad("negative fair value", f, n)
        if c1["scenarios"][n]["supply"]["buyback"].get("mode") == "fair_value" and r["terminal_included"] and not r["flags"]:
            if abs(r["fv_holder_retains"] - r["fv"]) > 1e-6 * max(1e-12, abs(r["fv"])): bad("non-seller check != DCF (fair_value)", f, f"{r['fv_holder_retains']} vs {r['fv']}")
    be = o["breakeven_g1"]
    if be is not None:
        bc = copy.deepcopy(c1["scenarios"]["base"])
        v = engine.value(c1["E0_core"], c1["E0_other"], c1["S0"], 7, 0.035, bc, c1["price"], g=be)["fv"]
        if abs(v / c1["price"] - 1) > 1e-6 and not any(x.startswith("BREAK-EVEN APPROXIMATE") for x in o["warnings"]): bad("break-even does not hit price (unflagged)", f, f"{v} vs {c1['price']}")
    ext = any(x.startswith("EXTREME") for x in o["warnings"])
    should = o["pw_upside"] > 1.5 or o["pw_upside"] < -0.6 or be is None or (be is not None and (be > 1 or be < -0.2)) \
        or o["earnings_yield_0"] > 0.25 or max(r["pe_T"] for r in R.values()) > 30
    if ext != should: bad("extreme flag mismatch", f, f"flag {ext} should {should} up {o['pw_upside']}")
    # metamorphic: E0 x2 -> FV x2 (linear) for modes none/fixed/fair_value
    mode = c1["scenarios"]["base"]["supply"]["buyback"].get("mode")
    if mode in ("none", "fair_value") and not any(r["flags"] for r in R.values()):
        c3 = copy.deepcopy(c1); c3["E0_core"] *= 2; c3["E0_other"] *= 2
        o3 = engine.run(c3)
        if abs(o3["pw_fv"] / o["pw_fv"] - 2) > 1e-6: bad(f"E0 x2 not FV x2 ({mode})", f, f"{o3['pw_fv'] / o['pw_fv']}")
    # metamorphic: +1pp reg (Ke) -> lower base FV; +5pp g1 -> higher base FV; doubling S0 lowers FV
    c4 = copy.deepcopy(c1); c4["scenarios"]["base"]["ke"]["reg"] += 0.01
    try:
        if engine.run(c4)["scenarios"]["base"]["fv"] > R["base"]["fv"] * (1 + 1e-9): bad("higher Ke raised FV", f, "")
    except ValueError: pass
    c5 = copy.deepcopy(c1); c5["scenarios"]["base"]["g1"] += 0.05
    r5_ = engine.run(c5)["scenarios"]["base"]
    # a solver fallback (non-convergence, or no positive price after a commitment ends) is flagged in the output and can
    # switch treatment between the two runs; monotonicity is only claimed when neither run fell back
    if not (R["base"]["flags"] or r5_["flags"]) and r5_["fv"] < R["base"]["fv"] * (1 - 1e-9): bad("higher g1 lowered FV", f, "")

print(f"cases {N_CASES} | valued {valued} | option path {option_runs} | stopped {sum(stops.values())}")
print("stop reasons:"); [print(f"  {v:5d}  {k}") for k, v in stops.most_common(12)]
print("flags seen:"); [print(f"  {v:5d}  {k}") for k, v in flags_seen.most_common(20)]
print(f"FAILURE KINDS: {len(fails)}")
for k, v in fails.items():
    print(f"  [{len(v)}] {k}: {v[0][0][:300]}\n        e.g. {v[0][1][:300]}")
sys.exit(1 if fails else 0)

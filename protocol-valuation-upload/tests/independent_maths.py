"""Usage: python3 tests/independent_maths.py <skill_dir>
Independent re-derivation of the engine's numbers from METHOD.md formulas (written without calling engine maths)."""
import sys, json, copy, math
SK = sys.argv[1]; sys.path.insert(0, SK + "/scripts")
import defaults as dv, engine

res = []
def check(name, got, want, tol=1e-9):
    ok = abs(got - want) <= tol * max(1.0, abs(want))
    res.append((name, ok, f"got {got!r} want {want!r}"))

def my_value(E0c, E0o, S0, N, sc, price, mode):
    g, go, roe, gT = sc["g1"], sc["g_other"], sc["roe"], sc["gT"]
    k = sc["ke"]; track = k.get("track", 0.0)
    ke_now = k["rf"] + k["erp"] + k["reg"] + k["gov"] + k["align"] + k["sc_now"] + track
    keT = k["rf"] + k["erp"] + k["reg"] + k["gov"] + k["align"] + k["sc_floor"]
    pe = (1 - gT / roe) / (keT - gT)
    E = [E0c * (1 + g) ** t + E0o * (1 + go) ** t for t in range(N + 1)]
    sp = sc["supply"]
    em = sp["emission_share"] * sp["unissued"] * sp["emission_release_by_T"] / N
    add = [0.0] + [(sp["vest"][t - 1] if t - 1 < len(sp["vest"]) else 0.0) + em for t in range(1, N + 1)]
    C = [0.0] + [sc.get("payout", 1.0) * E[t] for t in range(1, N + 1)]
    S = [S0]
    for t in range(1, N + 1):
        pre = S[-1] + add[t]
        b = 0.0 if mode == "none" else sp["buyback"]["tokens_per_yr"]
        S.append(pre - b)
    f, fv, df = 1.0 / S0, 0.0, 1.0
    for t in range(1, N + 1):
        f *= S[t - 1] / (S[t - 1] + add[t]); df *= 1 + ke_now; fv += f * C[t] / df
    fv += f * pe * E[N] / df
    eps5 = E[5] / S[5]
    return dict(fv=fv, pe=pe, ke=ke_now, keT=keT, S_T=S[N], E_N=E[N], m2=pe * eps5)

facts = json.load(open(SK + "/examples/calibration_facts.json"))
cfg = dv.build(facts); cfg["judgement"]["confirmed"] = True

# 1. judgement arithmetic re-derived by hand
lev = lambda m, dex, sh: (0.6522 * (1 + m) ** 6 * dex / 0.07 * sh / 0.40) ** (1 / 7) - 1
check("D1 base lever g = 39.79%", lev(0.20, 0.30, 0.50), 0.397866, tol=1e-4)
check("D1 bull lever g = 57.09%", lev(0.30, 0.35, 0.60), 0.570873, tol=1e-4)
check("D13 sc at 20 months = 1.17%", cfg["scenarios"]["base"]["ke"]["sc_now"], 0.0117)
check("D8 base ROE = 35 + 45/3", cfg["scenarios"]["base"]["roe"], 0.50)
check("D8 bull ROE = round5(35 + 45*(1-0.48/2)) = 70", cfg["scenarios"]["bull"]["roe"], 0.70)
check("D6 Helmer core = 17/7", sum([3, 3, 2, 1, 3, 2, 3]) / 7, 2.428571, tol=1e-6)
check("D6 blended Helmer 0.7*2.4286+0.3*2.5714 = 2.47", round(0.7 * 17 / 7 + 0.3 * 18 / 7, 2), cfg["judgement"]["moat"]["helmer"])

# 2. full DCF, fixed_tokens and none modes, every scenario
for mode in ("fixed_tokens", "none"):
    c = copy.deepcopy(cfg)
    if mode == "none":
        for s in c["scenarios"].values(): s["supply"]["buyback"] = {"mode": "none"}
    o = engine.run(c)
    for n, sc in c["scenarios"].items():
        m = my_value(c["E0_core"], c["E0_other"], c["S0"], 7, sc, c["price"], mode)
        r = o["scenarios"][n]
        check(f"{mode} {n} DCF", r["fv"], m["fv"]); check(f"{mode} {n} PE_T", r["pe_T"], m["pe"])
        check(f"{mode} {n} Ke now", r["ke"], m["ke"]); check(f"{mode} {n} Ke_T", r["ke_T"], m["keT"])
        check(f"{mode} {n} S_T", r["S_T"], m["S_T"]); check(f"{mode} {n} E_N", r["E_N"], m["E_N"])
        check(f"{mode} {n} method 2", o["method2"]["per_scenario"][n], m["m2"])
    check(f"{mode} PW = 0.2/0.6/0.2", o["pw_fv"], sum(c["scenarios"][n]["prob"] * o["scenarios"][n]["fv"] for n in c["scenarios"]))

# 3. break-even: my own bisection on my own DCF
c = copy.deepcopy(cfg); o = engine.run(c); base = c["scenarios"]["base"]
lo, hi = -0.5, 3.0
for _ in range(200):
    mid = (lo + hi) / 2; b2 = dict(base, g1=mid)
    if my_value(c["E0_core"], c["E0_other"], c["S0"], 7, b2, c["price"], "fixed_tokens")["fv"] < c["price"]: lo = mid
    else: hi = mid
check("break-even g1 (independent bisection)", o["breakeven_g1"], (lo + hi) / 2, tol=1e-6)

# 4. early-stage premium: Ke now includes it, Ke_T doesn't, DCF matches
c = copy.deepcopy(cfg)
for s in c["scenarios"].values(): s["ke"]["track"] = 0.01
o = engine.run(c)
for n, sc in c["scenarios"].items():
    m = my_value(c["E0_core"], c["E0_other"], c["S0"], 7, sc, c["price"], "fixed_tokens")
    check(f"track 1pp {n} DCF", o["scenarios"][n]["fv"], m["fv"]); check(f"track 1pp {n} Ke_T excludes track", o["scenarios"][n]["ke_T"], m["keT"])

# 5. option path: OV = sum p * FV_on / (1+Ke)^d, implied p * unit = price
opt = json.load(open(SK + "/examples/option_example.json"))
oo = engine.run_option(copy.deepcopy(opt))
for n, r in oo["scenarios"].items():
    want = sum(a["p"] * r["fv_on"] / (1 + r["ke"]) ** a["delay_years"] for a in opt["option"]["activation"])
    check(f"option {n} OV", r["option_fv"], want)
for d, p in oo["implied_p"].items():
    unit = sum(r["prob"] * r["fv_on"] / (1 + r["ke"]) ** int(d) for r in oo["scenarios"].values())
    if p is not None: check(f"implied p at {d}y * unit = price", p * unit, opt["price"], tol=1e-8)

# 6. part-year commitment: cash in year 1 scaled by 0.54, none after, no TV
c = copy.deepcopy(cfg)
for s in c["scenarios"].values(): s["supply"]["buyback"] = {"mode": "none", "years": 0.54, "continue_after": False}
o = engine.run(c); sc = c["scenarios"]["base"]; k = sc["ke"]
ke = k["rf"] + k["erp"] + k["reg"] + k["gov"] + k["align"] + k["sc_now"]
E1 = c["E0_core"] * (1 + sc["g1"]) + c["E0_other"] * (1 + sc["g_other"])
add1 = sc["supply"]["vest"][0] + sc["supply"]["emission_share"] * sc["supply"]["unissued"] * 0.75 / 7
check("part-year 0.54: DCF = 0.54*E1/(S0+add1)/(1+Ke)", o["scenarios"]["base"]["fv"], 0.54 * E1 / (c["S0"] + add1) / (1 + ke))

# 7. E0 rules (6.4.0): under a year, the lower of the history rule's run-rates and of what 14d revenue supports; TTM from a year
base_f = json.load(open(SK + "/examples/calibration_facts.json"))
def e0_of(earn):
    f = copy.deepcopy(base_f); f["earnings"] = earn
    return dv.build(f)["E0_core"]
cbw = {"90d": 700.0, "14d": 640.0, "30d": 690.0}
check("short history: E0 = min(90d, 14d)", e0_of({"history_days": 200, "core_by_window": cbw, "other": 0}), min(700.0, 640.0))
check("short history + revenue check: E0 = min(90d, 14d, r14 x share)",
      e0_of({"history_days": 200, "core_by_window": cbw, "other": 0, "revenue_check": {"revenue_14d": 500.0, "holder_share": 0.9}}), 450.0)
check("revenue check falls back to 30d revenue when 14d is missing",
      e0_of({"history_days": 200, "core_by_window": cbw, "other": 0, "revenue_check": {"revenue_30d": 600.0, "holder_share": 0.5}}), 300.0)
check("early stage + revenue check: E0 = min(since-launch, 14d, r14 x share)",
      e0_of({"history_days": 60, "core_by_window": {"since_launch": 300.0, "14d": 280.0, "30d": 290.0}, "other": 0,
             "revenue_check": {"revenue_14d": 400.0, "holder_share": 0.6}}), 240.0)
check("from a year: TTM, not moved by the revenue check",
      e0_of({"history_days": 400, "core_by_window": {"365d": 700.0, "30d": 690.0}, "other": 0,
             "revenue_check": {"revenue_14d": 100.0, "holder_share": 0.5}}), 700.0)
last = 1791849600; vals = [2e5] * 14 + [1e6] * 106                # latest day first
w = engine.e0_windows([[last - i * 86400, v] for i, v in enumerate(vals)], "2026-10-14T12:00:00Z")
check("windows: 120-day E0 = min(90d, 14d) from the raw days", w["e0"], min(sum(vals[:90]) / 90, sum(vals[:14]) / 14) * 365 / 1e6)

bad = [r for r in res if not r[1]]
for n, ok, msg in res: print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  " + msg))
print(f"\n{len(res) - len(bad)}/{len(res)} independent checks passed")
sys.exit(1 if bad else 0)

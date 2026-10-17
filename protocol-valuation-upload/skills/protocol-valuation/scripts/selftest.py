#!/usr/bin/env python3
"""Self-test: run before every valuation session (takes < 1 s, no network).

1. Defaults step on examples/calibration_facts.json must regenerate the calibrated judgement inputs exactly.
2. The same facts file run twice must give byte-identical inputs.json (determinism).
3. The valuation must reproduce the frozen calibration outputs (relative tolerance 0.1%).
4. The 20/60/20 row of the weight sensitivity must equal the probability-weighted DCF (scenario order check).
5. The option-path example must reproduce its frozen outputs.

Usage: python3 scripts/selftest.py        (prints PASS/FAIL per check; exit code 1 on any failure)
"""
import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import defaults as dv   # noqa: E402
import engine           # noqa: E402

FAILS = []
def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok: FAILS.append(name)

def close(a, b, rel=1e-3, abs_=1e-9):
    return abs(a - b) <= max(abs_, rel * abs(b))

def main():
    facts = json.load(open(os.path.join(ROOT, "examples", "calibration_facts.json")))
    cfg = dv.build(facts)
    S = cfg["scenarios"]
    want = {"g1": (0.10, 0.40, 0.55), "roe": (0.35, 0.50, 0.70), "gT": (0.030, 0.035, 0.045), "prob": (0.2, 0.6, 0.2)}
    for k, vals in want.items():
        got = tuple(S[s][k] for s in ("bear", "base", "bull"))
        check(f"defaults {k} = {vals}", all(close(a, b) for a, b in zip(got, vals)), f"got {got}")
    got = tuple(S[s]["ke"]["reg"] for s in ("bear", "base", "bull"))
    check("defaults reg = 2.5/2.0/0.5%", all(close(a, b) for a, b in zip(got, (0.025, 0.02, 0.005))), f"got {got}")
    k = S["base"]["ke"]
    check("defaults gov 1.25%, align 0%, sc 1.17% -> 0.5%",
          close(k["gov"], 0.0125) and k["align"] == 0 and close(k["sc_now"], 0.0117) and close(k["sc_floor"], 0.005), str(k))
    got = tuple(S[s]["supply"]["emission_share"] for s in ("bear", "base", "bull"))
    check("defaults emissions 60/10/0%", got == (0.6, 0.1, 0.0), f"got {got}")
    m = cfg["judgement"]["moat"]
    check("moat 2.47 / 0.48, band 35-80%", m["helmer"] == 2.47 and m["porter"] == 0.48 and tuple(m["band"]) == (0.35, 0.80), str((m["helmer"], m["porter"], m["band"])))

    with tempfile.TemporaryDirectory() as td:
        a, b = os.path.join(td, "a.json"), os.path.join(td, "b.json")
        for p in (a, b):
            json.dump(dv.build(json.load(open(os.path.join(ROOT, "examples", "calibration_facts.json")))), open(p, "w"), indent=1, sort_keys=True)
        check("determinism: identical inputs.json across runs", open(a).read() == open(b).read())

    cfg["judgement"]["confirmed"] = True
    o = engine.run(cfg)
    R = o["scenarios"]
    frozen = {"bear": (20.4082, 8.6992, 602.05, 2092.92), "base": (100.2907, 9.7792, 456.175, 9971.53), "bull": (278.0393, 13.3483, 427.0, 20132.24)}
    for s, (fv, pe, st, en) in frozen.items():
        r = R[s]
        check(f"valuation {s}: DCF ${fv}, PE_T {pe}x, S_T {st}m, E_N ${en}m",
              close(r["fv"], fv) and close(r["pe_T"], pe) and close(r["S_T"], st) and close(r["E_N"], en),
              f"got {r['fv']:.4f} {r['pe_T']:.4f} {r['S_T']:.3f} {r['E_N']:.2f}")
    check("PW DCF $119.86", close(o["pw_fv"], 119.8639), f"got {o['pw_fv']:.4f}")
    check("P/E method PW $119.01", close(o["method2"]["pw"], 119.0105), f"got {o['method2']['pw']:.4f}")
    check("break-even g1 31.35%", close(o["breakeven_g1"], 0.313463), f"got {o['breakeven_g1']:.6f}")
    check("Ke base 13.68%, Ke_T base 13.01%", close(R["base"]["ke"], 0.1368) and close(R["base"]["ke_T"], 0.1301))
    w = [x for x in o["weight_sensitivity"] if [round(v, 2) for v in x["weights"]] == [0.2, 0.6, 0.2]]
    check("weight sensitivity 20/60/20 row = PW DCF", bool(w) and close(w[0]["pw_fv"], o["pw_fv"], rel=1e-9), str(w))
    check("unconfirmed table is flagged", any("NOT CONFIRMED" in x for x in engine.run(dv.build(facts))["warnings"]))

    try:
        dv.apply_overrides(dv.build(facts), {"scenarios.base.g_1": 0.3}); ok = False
    except ValueError:
        ok = True
    check("override typo rejected (no silent no-op)", ok)

    opt = engine.run_option(json.load(open(os.path.join(ROOT, "examples", "option_example.json"))))
    check("option example PW option value $24.84", close(opt["pw_option_fv"], 24.84, rel=2e-3), f"got {opt['pw_option_fv']:.4f}")
    check("option example implied p at 1y 27.6%", close(opt["implied_p"]["1"], 0.276, rel=5e-3), f"got {opt['implied_p']['1']:.4f}")

    print(f"\n{'ALL CHECKS PASSED' if not FAILS else f'{len(FAILS)} CHECK(S) FAILED: ' + '; '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)

if __name__ == "__main__":
    main()

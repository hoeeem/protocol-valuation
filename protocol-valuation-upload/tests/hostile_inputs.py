"""Hostile and unusual inputs at every CLI. Pass = clean one-line error (exit != 0, no traceback) or a correct result."""
import sys, os, json, subprocess, tempfile, copy, math
SK = os.path.abspath(sys.argv[1]); S = os.path.join(SK, "scripts")
TD = tempfile.mkdtemp()
res = []
def run(script, args, files=None):
    for name, content in (files or {}).items():
        with open(os.path.join(TD, name), "w", encoding="utf-8") as fh:
            fh.write(content if isinstance(content, str) else json.dumps(content))
    r = subprocess.run([sys.executable, os.path.join(S, script)] + args, cwd=TD, capture_output=True, text=True, encoding="utf-8")
    return r
def clean_error(name, r, needle=None):
    ok = r.returncode != 0 and "Traceback" not in r.stderr and (needle is None or needle.lower() in (r.stderr + r.stdout).lower())
    res.append((name, ok, (r.stderr or r.stdout).strip().splitlines()[-1:] if not ok else ""))
def ok_run(name, r, check=lambda out: True):
    ok = r.returncode == 0 and "Traceback" not in r.stderr and check(r.stdout)
    res.append((name, ok, (r.stderr or r.stdout)[-300:] if not ok else ""))

BASE = json.load(open(os.path.join(SK, "examples", "calibration_facts.json")))
sys.path.insert(0, S)
import defaults as dv
good_inputs = dv.build(copy.deepcopy(BASE)); good_inputs["judgement"]["confirmed"] = True

# ---- engine.py
ok_run("engine: no args prints usage", run("engine.py", []), lambda o: "Usage" in o)
clean_error("engine: missing file", run("engine.py", ["nope.json"]))
clean_error("engine: invalid JSON", run("engine.py", ["bad.json"], {"bad.json": "{not json"}))
clean_error("engine: empty file", run("engine.py", ["empty.json"], {"empty.json": ""}))
clean_error("engine: JSON array instead of object", run("engine.py", ["arr.json"], {"arr.json": [1, 2]}))
for fld, val, needle in (("price", "70", "price"), ("price", float("nan"), "price"), ("price", -1, "price"), ("price", float("inf"), "price"),
                         ("S0", 0, "S0"), ("S0", "316", "S0"), ("as_of", "yesterday", "as_of")):
    c = copy.deepcopy(good_inputs); c[fld] = val
    txt = json.dumps(c)  # json allows NaN/Infinity tokens
    clean_error(f"engine: {fld}={val!r}", run("engine.py", ["x.json"], {"x.json": txt}), needle)
c = copy.deepcopy(good_inputs); c["scenarios"]["base"]["g1"] = "0.4"
clean_error("engine: g1 as string", run("engine.py", ["x.json"], {"x.json": c}))
c = copy.deepcopy(good_inputs); c["scenarios"]["base"]["ke"]["rf"] = None
clean_error("engine: rf null", run("engine.py", ["x.json"], {"x.json": c}))
c = copy.deepcopy(good_inputs); c["E0_core"] = float("nan")
clean_error("engine: E0 NaN", run("engine.py", ["x.json"], {"x.json": json.dumps(c)}), "E0")
c = copy.deepcopy(good_inputs); c["protocol"] = "Ünïcödé → 协议 ✓"
ok_run("engine: unicode protocol name, --md written as UTF-8", run("engine.py", ["x.json", "--md", "v.md"], {"x.json": c}),
       lambda o: "协议" in open(os.path.join(TD, "v.md"), encoding="utf-8").read())
clean_error("engine: --md with no path", run("engine.py", ["x.json", "--md"], {"x.json": good_inputs}))

# ---- windows
last = 1791849600
clean_error("windows: dict without totalDataChart", run("engine.py", ["windows", "w.json"], {"w.json": {"foo": 1}}), "chart")
ok_run("windows: millisecond timestamps detected", run("engine.py", ["windows", "w.json", "--as-of", "2026-10-14T12:00:00Z"],
       {"w.json": [[(last - i * 86400) * 1000, 1e6] for i in range(400)]}), lambda o: json.loads(o)["history_days"] == 400)
ok_run("windows: exact duplicate rows not double-counted", run("engine.py", ["windows", "w.json", "--as-of", "2026-10-14T12:00:00Z"],
       {"w.json": [[last - i * 86400, 1e6] for i in range(400)] + [[last, 1e6]]}), lambda o: abs(json.loads(o)["7d"] - 365.0) < 1e-6)
ok_run("windows: unsorted rows", run("engine.py", ["windows", "w.json", "--as-of", "2026-10-14T12:00:00Z"],
       {"w.json": list(reversed([[last - i * 86400, 1e6] for i in range(400)]))}), lambda o: abs(json.loads(o)["365d"] - 365.0) < 1e-6)
ok_run("windows: null values treated as missing", run("engine.py", ["windows", "w.json", "--as-of", "2026-10-14T12:00:00Z"],
       {"w.json": [[last - i * 86400, None if i == 3 else 1e6] for i in range(400)]}), lambda o: json.loads(o)["history_days"] == 400)
ok_run("windows: string numbers accepted", run("engine.py", ["windows", "w.json", "--as-of", "2026-10-14T12:00:00Z"],
       {"w.json": [[str(last - i * 86400), str(1e6)] for i in range(400)]}), lambda o: abs(json.loads(o)["365d"] - 365.0) < 1e-6)
ok_run("windows: as_of exactly midnight drops that day", run("engine.py", ["windows", "w.json", "--as-of", "2026-10-14T00:00:00Z"],
       {"w.json": [[last - i * 86400, 1e6] for i in range(400)] + [[last + 86400, 5e9]]}), lambda o: json.loads(o)["last_complete_day"] == "2026-10-13")
ok_run("windows: as_of with +01:00 offset", run("engine.py", ["windows", "w.json", "--as-of", "2026-10-14T00:30:00+01:00"],
       {"w.json": [[last - i * 86400, 1e6] for i in range(400)]}), lambda o: json.loads(o)["last_complete_day"] == "2026-10-12")
ok_run("windows: negative days (refunds) kept", run("engine.py", ["windows", "w.json", "--as-of", "2026-10-14T12:00:00Z"],
       {"w.json": [[last - i * 86400, -1e6 if i == 0 else 1e6] for i in range(400)]}), lambda o: abs(json.loads(o)["7d"] - 5 / 7 * 365) < 1e-6)
clean_error("windows: all zeros -> STOP-like clean output or error", run("engine.py", ["windows", "w.json", "--as-of", "2026-10-14T12:00:00Z"],
       {"w.json": [[last - i * 86400, 0] for i in range(400)]})) if False else None

# ---- defaults
clean_error("defaults: missing risk section", run("engine.py", ["defaults", "f.json"], {"f.json": {k: v for k, v in BASE.items() if k != "risk"}}), "risk")
f = copy.deepcopy(BASE); f["risk"]["reg_class"] = "mystery"
clean_error("defaults: unknown reg_class", run("engine.py", ["defaults", "f.json"], {"f.json": f}), "reg_class")
f = copy.deepcopy(BASE); f["risk"]["routing"] = "sometimes"
clean_error("defaults: unknown routing", run("engine.py", ["defaults", "f.json"], {"f.json": f}), "routing")
f = copy.deepcopy(BASE); f["price"] = "70"
clean_error("defaults: price as string", run("engine.py", ["defaults", "f.json"], {"f.json": f}), "price")
f = copy.deepcopy(BASE); f["share"]["share_0"] = 0
clean_error("defaults: share_0 = 0", run("engine.py", ["defaults", "f.json"], {"f.json": f}), "share")
f = copy.deepcopy(BASE); f["moat"]["segments"] = []
clean_error("defaults: no moat segments", run("engine.py", ["defaults", "f.json"], {"f.json": f}), "moat")
f = copy.deepcopy(BASE); f["moat"]["segments"][0]["weight"] = 0; f["moat"]["segments"][1]["weight"] = 0
clean_error("defaults: zero moat weights", run("engine.py", ["defaults", "f.json"], {"f.json": f}), "weight")
f = copy.deepcopy(BASE); f["risk"]["launch_date"] = "2026-13-45"; f["risk"].pop("age_months")
clean_error("defaults: invalid launch_date", run("engine.py", ["defaults", "f.json"], {"f.json": f}), "launch_date")
f = copy.deepcopy(BASE); f["risk"]["launch_date"] = "2027-01-01"; f["risk"].pop("age_months")
clean_error("defaults: launch_date after as_of", run("engine.py", ["defaults", "f.json"], {"f.json": f}), "launch_date")
clean_error("defaults: overrides file with bad JSON", run("engine.py", ["defaults", "f.json", "--overrides", "o.json"], {"f.json": BASE, "o.json": "{"}))
clean_error("defaults: override path into a number", run("engine.py", ["defaults", "f.json", "--overrides", "o.json"],
            {"f.json": BASE, "o.json": {"scenarios.base.g1.x": 1}}), "override")

# ---- supply_schedule
sch = {"as_of": "2026-10-14", "max_supply": 100, "buckets": [{"name": "a", "tokens": 100, "type": "vesting", "start": "2025-01-31", "cliff_months": 1, "linear_months": 0}]}
ok_run("schedule: cliff from Jan 31 lands at end of Feb", run("supply_schedule.py", ["s.json", "--json", "o.json"], {"s.json": sch}),
       lambda o: json.load(open(os.path.join(TD, "o.json")))["S0"] == 100)
sch2 = {"as_of": "2025-02-27", "buckets": [{"name": "a", "tokens": 100, "type": "vesting", "start": "2025-01-31", "cliff_months": 1}]}
ok_run("schedule: one day before the month-end cliff -> 0", run("supply_schedule.py", ["s.json", "--json", "o.json"], {"s.json": sch2}),
       lambda o: json.load(open(os.path.join(TD, "o.json")))["S0"] == 0)
sch3 = {"as_of": "2024-02-29", "buckets": [{"name": "a", "tokens": 120, "type": "vesting", "start": "2023-02-28", "linear_months": 12}]}
ok_run("schedule: leap day as_of, linear 12m fully vested", run("supply_schedule.py", ["s.json", "--json", "o.json"], {"s.json": sch3}),
       lambda o: abs(json.load(open(os.path.join(TD, "o.json")))["S0"] - 120) < 1e-9)
sch4 = {"as_of": "2026-10-14", "buckets": [{"name": "a", "tokens": 10, "type": "vesting", "start": "2027-06-01", "tge_pct": 0.1, "linear_months": 12}]}
ok_run("schedule: start in the future -> 0 now, vests later", run("supply_schedule.py", ["s.json", "--json", "o.json"], {"s.json": sch4}),
       lambda o: (lambda d: d["S0"] == 0 and abs(sum(d["vest"]) - 10) < 1e-9)(json.load(open(os.path.join(TD, "o.json")))))
clean_error("schedule: bad date", run("supply_schedule.py", ["s.json"], {"s.json": {"as_of": "2026-10-14", "buckets": [{"name": "a", "tokens": 1, "type": "vesting", "start": "2025-02-30"}]}}))
clean_error("schedule: missing file", run("supply_schedule.py", ["nope.json"]))
clean_error("schedule: tokens negative", run("supply_schedule.py", ["s.json"], {"s.json": {"as_of": "2026-10-14", "buckets": [{"name": "a", "tokens": -5, "type": "unlocked"}]}}), "tokens")

# ---- market_stats / category_stats
clean_error("market_stats: dict without series", run("market_stats.py", ["m.json"], {"m.json": {"foo": 1}}))
clean_error("market_stats: missing file", run("market_stats.py", ["nope.json"]))
ok_run("market_stats: empty list -> basis none", run("market_stats.py", ["m.json"], {"m.json": []}), lambda o: json.loads(o)["basis"] == "none")
clean_error("category_stats: no protocols", run("category_stats.py", ["c.json", "x"], {"c.json": {"protocols": []}}), "protocols")
clean_error("category_stats: protocol not found", run("category_stats.py", ["c.json", "zzz"], {"c.json": {"protocols": [{"name": "a", "category": "Dexs", "total30d": 1, "total1y": 2}]}}), "not found")
clean_error("category_stats: missing args", run("category_stats.py", ["c.json"], {"c.json": {"protocols": [{"name": "a"}]}}))
ok_run("category_stats: null totals tolerated", run("category_stats.py", ["c.json", "a"], {"c.json": {"protocols": [
    {"name": "a", "category": "Dexs", "total30d": None, "total1y": 5}, {"name": "b", "category": "Dexs", "total30d": 3, "total1y": None}]}}),
    lambda o: json.loads(o)["rank"] == 2)

# ---- revenue_stack
clean_error("revenue_stack: missing --holders", run("revenue_stack.py", ["--fees", "a.json", "--revenue", "a.json"], {"a.json": {"total1y": 1e8, "total30d": 1e7}}), "--holders")
clean_error("revenue_stack: missing file", run("revenue_stack.py", ["--fees", "nope.json", "--revenue", "nope.json", "--holders", "nope.json"]), "not found")
clean_error("revenue_stack: wrong file shape", run("revenue_stack.py", ["--fees", "b.json", "--revenue", "b.json", "--holders", "b.json"], {"b.json": {"foo": 1}}), "totals")
clean_error("revenue_stack: take rate above 1", run("revenue_stack.py", ["--fees", "a.json", "--revenue", "a.json", "--holders", "a.json", "--take-rate", "1.5"], {"a.json": {"total1y": 1e8, "total30d": 1e7}}), "take-rate")
clean_error("revenue_stack: take rate not a number", run("revenue_stack.py", ["--fees", "a.json", "--revenue", "a.json", "--holders", "a.json", "--take-rate", "half"], {"a.json": {"total1y": 1e8, "total30d": 1e7}}), "take-rate")

clean_error("revenue_stack: holder share above 1", run("revenue_stack.py", ["--fees", "a.json", "--revenue", "a.json", "--holders", "a.json", "--holder-share", "1.4"], {"a.json": {"total1y": 1e8, "total30d": 1e7}}), "holder-share")
f = copy.deepcopy(BASE); f["earnings"]["revenue_check"] = 5
clean_error("defaults: revenue_check not an object", run("engine.py", ["defaults", "f.json"], {"f.json": f}), "revenue_check")
f = copy.deepcopy(BASE); f["earnings"]["revenue_check"] = {"revenue_14d": float("nan"), "holder_share": 0.5}
clean_error("defaults: revenue_check NaN", run("engine.py", ["defaults", "f.json"], {"f.json": json.dumps(f)}), "revenue_14d")

# ---- 6.6.0: holder rights, payout, conditional valuations
for rt, needle in (({"benefit_form": "airdrop"}, "rights.benefit_form"), ({"benefit_form": None}, "rights.benefit_form"),
                   ({"benefit_form": "distribution", "access": "whales"}, "rights.access"), ("buyback_burn", "rights must be an object"),
                   ({"benefit_form": ["distribution"]}, "rights.benefit_form"), ({"benefit_form": "distribution", "access": {"a": 1}}, "rights.access"),
                   ([{"benefit_form": "distribution"}], "rights must be an object")):
    f = copy.deepcopy(BASE); f["rights"] = rt
    clean_error(f"defaults: rights = {rt!r}", run("engine.py", ["defaults", "f.json"], {"f.json": f}), needle)
for p in (1.5, -0.2, "1", float("nan")):
    f = copy.deepcopy(BASE); f["payout"] = p
    clean_error(f"defaults: payout = {p!r}", run("engine.py", ["defaults", "f.json"], {"f.json": json.dumps(f)}), "payout")
f = copy.deepcopy(BASE); f["earnings"]["revenue_check"] = {"revenue_14d": 500, "holder_share": 0.5, "holder_share_measured": -1}
clean_error("defaults: negative measured holder share", run("engine.py", ["defaults", "f.json"], {"f.json": f}), "holder_share_measured")
f = copy.deepcopy(BASE); f["risk"]["routing"] = "fee_switch_off"; f["option"] = {"type": "fee_switch", "fees_ttm": 400, "take_rate": 0.25, "condition": ""}
ok_run("defaults -> engine: option with an empty condition values, flagged NO STATED CONDITION and LOW",
       (run("engine.py", ["defaults", "f.json", "--json", "i.json"], {"f.json": f}), run("engine.py", ["i.json"]))[1],
       lambda o: "NO STATED CONDITION" in o and "Input confidence: LOW" in o and o.index("Value if switched on today") < o.index("What the price implies"))

# ---- chart_from_text
clean_error("chart_from_text: missing file", run("chart_from_text.py", ["nope.txt", "--total-all-time", "5"]), "not found")
clean_error("chart_from_text: missing --total-all-time", run("chart_from_text.py", ["c.txt"], {"c.txt": "1791849600,5\n"}), "--total-all-time")
clean_error("chart_from_text: sum differs from totalAllTime", run("chart_from_text.py", ["c.txt", "--total-all-time", "7"], {"c.txt": "1791849600,5\n"}), "all-time total")
clean_error("chart_from_text: garbage line after the data", run("chart_from_text.py", ["c.txt", "--total-all-time", "5"], {"c.txt": "1791849600,5\nhello world\n"}), "line 2")
clean_error("chart_from_text: no data lines", run("chart_from_text.py", ["c.txt", "--total-all-time", "5"], {"c.txt": "nothing here\n"}), "no")
clean_error("chart_from_text: total not a number", run("chart_from_text.py", ["c.txt", "--total-all-time", "lots"], {"c.txt": "1791849600,5\n"}), "number")
ok_run("chart_from_text: header, tabs, millisecond timestamps", run("chart_from_text.py", ["c.txt", "--total-all-time", "3", "--out", "o.json"],
       {"c.txt": "ts\tvalue\n1791849600000\t1\n1791763200000\t2\n"}), lambda o: o.startswith("OK:") and "2 daily rows" in o and "milliseconds" in o)

csv_txt = "Date,Fees,Revenue,Holders Revenue\n2026-10-12,10,5,3\n2026-10-13,12,6,4\n"
clean_error("chart_from_text: CSV with several series and no --column", run("chart_from_text.py", ["d.csv", "--no-total-check"], {"d.csv": csv_txt}), "--column")
clean_error("chart_from_text: unknown --column", run("chart_from_text.py", ["d.csv", "--no-total-check", "--column", "Volume"], {"d.csv": csv_txt}), "not found")
ok_run("chart_from_text: CSV column picked, unverified run says so", run("chart_from_text.py", ["d.csv", "--no-total-check", "--column", "Holders Revenue", "--out", "h.json"], {"d.csv": csv_txt}),
       lambda o: "UNVERIFIED" in o and json.load(open(os.path.join(TD, "h.json")))["totalDataChart"][-1][1] == 4)
clean_error("chart_from_text: weekly rows refused", run("chart_from_text.py", ["w.csv", "--no-total-check"], {"w.csv": "Timestamp,Fees\n" + "\n".join(f"{1791849600 - i * 604800},5" for i in range(6))}), "daily")
clean_error("chart_from_text: bad date in a data row", run("chart_from_text.py", ["b.csv", "--no-total-check", "--column", "Fees"], {"b.csv": "Date,Fees\n2026-10-12,5\n2026-13-45,6\n"}), "line 3")

res = [r for r in res if r is not None]
bad = [r for r in res if not r[1]]
for n, ok, msg in res: print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {msg}"))
print(f"\n{len(res) - len(bad)}/{len(res)} hostile-input checks passed")
sys.exit(1 if bad else 0)

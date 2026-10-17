#!/usr/bin/env bash
# Literal SKILL.md workflow via the CLI only. Usage: t5_workflow.sh <skill_dir> <python>
set -u
SK="$1"; PY="${2:-python3}"; W=$(mktemp -d); cd "$W"; FAIL=0
step() { echo "== $1"; }
must() { if ! "$@" > out.txt 2> err.txt; then echo "FAIL: $*"; cat err.txt; FAIL=1; fi; }
mustfail() { if "$@" > out.txt 2> err.txt; then echo "FAIL (expected a STOP): $*"; FAIL=1; elif grep -q Traceback err.txt; then echo "FAIL (traceback): $*"; FAIL=1; else echo "   stopped cleanly: $(head -c 150 err.txt)"; fi; }

step "1. self-test";                must $PY "$SK/scripts/selftest.py"; tail -1 out.txt
step "synthetic raw API files"
$PY - <<'EOF'
import json
last = 1791849600
day = lambda i: last - i * 86400
# holder revenue: 3 years, steady $0.5m/day; DEX category: grew then fell 30%; all DeFi fell 25%
json.dump({"totalDataChart": [[day(i), 5e5] for i in range(1100)]}, open("summary.json", "w"))
prots = [{"name": "SynthDEX", "category": "Dexs", "parentProtocol": "parent#synth", "total30d": 15e6, "total1y": 180e6},
         {"name": "RivalA", "category": "Dexs", "total30d": 10e6, "total1y": 150e6},
         {"name": "RivalB", "category": "Dexs", "total30d": 5e6, "total1y": 60e6},
         {"name": "LendCo", "category": "Lending", "total30d": 40e6, "total1y": 500e6}]
lvl = lambda i, a, b: a if i < 365 else b
bd = [[day(i), {"SynthDEX": lvl(i, 0.7e6, 1.0e6), "RivalA": lvl(i, 0.5e6, 0.7e6), "RivalB": 0.2e6, "LendCo": lvl(i, 1.5e6, 2.0e6)}] for i in range(1900)]
json.dump({"protocols": prots, "totalDataChartBreakdown": bd}, open("overview.json", "w"))
json.dump({"as_of": "2026-10-14", "horizon": 7, "max_supply": 1000, "total_supply": 990, "tracker_circulating": 400,
           "buckets": [{"name": "community", "tokens": 450, "type": "vesting", "start": "2023-01-01", "tge_pct": 1.0},
                       {"name": "team", "tokens": 200, "type": "vesting", "start": "2023-01-01", "cliff_months": 12, "linear_months": 36},
                       {"name": "treasury", "tokens": 100, "type": "discretionary"},
                       {"name": "emissions", "tokens": 250, "type": "emission", "distributed": 50}]}, open("schedule.json", "w"))
EOF
step "3. windows";                   must $PY "$SK/scripts/engine.py" windows summary.json --as-of 2026-10-14T12:00:00Z; cp out.txt windows.json; grep -E '"e0_window"|"paused"' windows.json
step "3. listed chart -> verified chart (summarised-tools fallback)"
$PY -c "
import json; d=json.load(open('summary.json'))['totalDataChart']
open('listed.txt','w').write('timestamp,value\n'+'\n'.join(f'{t},{v:.0f}' for t,v in d)+'\n')
open('total.txt','w').write(str(round(sum(v for _,v in d))))"
must $PY "$SK/scripts/chart_from_text.py" listed.txt --total-all-time "$(cat total.txt)" --out listed.json; cut -c1-110 out.txt
must $PY "$SK/scripts/engine.py" windows listed.json --as-of 2026-10-14T12:00:00Z; cmp -s out.txt windows.json && echo "   listed chart gives the same windows" || { echo "FAIL: listed chart windows differ"; FAIL=1; }
step "0. user-supplied CSV (DefiLlama download, three series) -> chart"
$PY -c "
import json; from datetime import datetime, timezone
d=json.load(open('summary.json'))['totalDataChart']
iso=lambda t: datetime.fromtimestamp(t, timezone.utc).date().isoformat()
open('dl.csv','w').write('Date,Fees,Revenue,Holders Revenue\n'+'\n'.join(f'{iso(t)},{v*2.5:.0f},{v*1.04:.0f},{v:.0f}' for t,v in sorted(d))+'\n')"
must $PY "$SK/scripts/chart_from_text.py" dl.csv --column "Holders Revenue" --total-all-time "$(cat total.txt)" --out dl.json; cut -c1-110 out.txt
must $PY "$SK/scripts/engine.py" windows dl.json --as-of 2026-10-14T12:00:00Z; cmp -s out.txt windows.json && echo "   CSV gives the same windows" || { echo "FAIL: CSV windows differ"; FAIL=1; }
step "3. revenue stack (all three series) -> revenue_check"
$PY -c "
import json; last=1791849600
json.dump({'totalDataChart':[[last-i*86400, 1.25e6] for i in range(1100)]}, open('fees.json','w'))
json.dump({'totalDataChart':[[last-i*86400, 5.2e5] for i in range(1100)]}, open('rev.json','w'))"
must $PY "$SK/scripts/revenue_stack.py" --fees fees.json --revenue rev.json --holders summary.json --as-of 2026-10-14T12:00:00Z --json stack3.json; grep -E "Case:|Window:" out.txt | cut -c1-100
step "3. category_stats";            must $PY "$SK/scripts/category_stats.py" overview.json SynthDEX --series-out cat.json --benchmark-out all_defi.json; cp out.txt cat_stats.json; grep -E '"category"|"share_30d"|"rank"|"n_competitors_ge10"' cat_stats.json
step "3. market_stats + benchmark";  must $PY "$SK/scripts/market_stats.py" cat.json --benchmark all_defi.json --as-of 2026-10-14T12:00:00Z; cp out.txt market.json; grep -E '"yoy"|"benchmark_yoy"|"trailing_cagr"' market.json
step "4. supply_schedule";           must $PY "$SK/scripts/supply_schedule.py" schedule.json --md supply.md --json supply_out.json; grep -E "^\*\*S0" supply.md
step "5. facts.json"
$PY - <<'EOF'
import json
w, m, c, s = (json.load(open(x)) for x in ("windows.json", "market.json", "cat_stats.json", "supply_out.json"))
f = {"protocol": "SynthDEX (workflow test)", "as_of": "2026-10-14T12:00:00Z", "price": 2.5,
     "earnings": {"windows": w, "other": 0, "source": "synthetic", "revenue_check": json.load(open("stack3.json"))["revenue_check"]},
     "market": {k: m[k] for k in ("basis", "trailing_cagr", "cagr_years", "record_365d", "ttm_365d", "yoy", "benchmark_yoy", "level_2y_ago_365d")},
     "share": {"share_0": c["share_30d"]},
     "moat": {"segments": [{"name": "core", "weight": 1, "rubric": {"share_30d": c["share_30d"], "holder_rev_ttm_musd": w["e0"], "age_months": 46,
              "rank": c["rank"], "n_competitors_ge10": c["n_competitors_ge10"], "share_change_pp": c["share_change_pp"]}}]},
     "risk": {"reg_class": "us_facing_no_kyc_settled", "routing": "mechanical", "launch_date": "2022-12-01", "first_fees_day": "2022-12-01"},
     "rf": {"value": 0.052}, "erp": {"value": 0.0469},
     "supply": {"S0": s["S0"], "vest": s["vest"], "unissued": s["unissued"], "self_sustaining": True, "team_largest_holder": False, "buyback": {"mode": "fair_value"}}}
json.dump(f, open("facts.json", "w"), indent=1)
EOF
step "6. defaults";                  must $PY "$SK/scripts/engine.py" defaults facts.json --md judgement.md --json inputs.json; grep -E "^- " judgement.md | head -5; grep -E "^\| D2 " judgement.md | cut -c1-120
step "7. overrides (typo rejected, then confirmed)"
echo '{"scenarios.base.g_1": 0.3}' > bad_ov.json; mustfail $PY "$SK/scripts/engine.py" defaults facts.json --overrides bad_ov.json
echo '{"scenarios.base.g1": 0.25, "confirmed": true}' > ov.json; must $PY "$SK/scripts/engine.py" defaults facts.json --overrides ov.json --md judgement.md --json inputs.json; grep -E "^Status" judgement.md
step "8. value";                     must $PY "$SK/scripts/engine.py" inputs.json --md valuation.md --json valuation.json; grep -E "probability-weighted|break-even|protocol-valuation|Valuation basis" valuation.md | cut -c1-140
grep -q "Input confidence: " valuation.md || { echo "FAIL: no valuation basis / input confidence line"; FAIL=1; }
step "8b. paused buybacks: STOP, then option path"
$PY - <<'EOF'
import json
last = 1791849600
json.dump({"totalDataChart": [[last - i * 86400, 0 if i < 40 else 5e5] for i in range(800)]}, open("paused.json", "w"))
EOF
must $PY "$SK/scripts/engine.py" windows paused.json --as-of 2026-10-14T12:00:00Z; cp out.txt wp.json
$PY -c "import json;f=json.load(open('facts.json'));f['earnings']={'windows':json.load(open('wp.json')),'other':0};json.dump(f,open('fp.json','w'))"
mustfail $PY "$SK/scripts/engine.py" defaults fp.json
$PY -c "import json;f=json.load(open('fp.json'));f['option']={'type':'paused_buyback','holder_rev_hist':182.5};json.dump(f,open('fo.json','w'))"
must $PY "$SK/scripts/engine.py" defaults fo.json --json io.json; must $PY "$SK/scripts/engine.py" io.json; grep -E "CONDITIONAL valuation|Value if switched on today|NO STATED CONDITION" out.txt | cut -c1-140
grep -q "Input confidence: LOW" out.txt || { echo "FAIL: conditional run without a condition is not LOW confidence"; FAIL=1; }
step "8c. 50-day token: early stage"
$PY -c "
import json; last=1791849600
json.dump({'totalDataChart':[[last-i*86400, 4e5] for i in range(50)]}, open('young.json','w'))"
must $PY "$SK/scripts/engine.py" windows young.json --as-of 2026-10-14T12:00:00Z; cp out.txt wy.json
$PY -c "import json;f=json.load(open('facts.json'));f['earnings']={'windows':json.load(open('wy.json')),'other':0};json.dump(f,open('fy.json','w'))"
must $PY "$SK/scripts/engine.py" defaults fy.json --json iy.json; must $PY "$SK/scripts/engine.py" iy.json; grep -E "EARLY STAGE|probability-weighted" out.txt | cut -c1-140
step "8e. treasury protocol: revenue stack -> fee-switch block -> value"
$PY -c "
import json; last=1791849600
d=lambda lvl,zero=0: {'totalDataChart':[[last-i*86400, 0 if i<zero else lvl*1e6/365] for i in range(800)]}
json.dump(d(691),open('f.json','w')); json.dump(d(89.5),open('r.json','w')); json.dump(d(18.2,40),open('h.json','w'))"
must $PY "$SK/scripts/revenue_stack.py" --fees f.json --revenue r.json --holders h.json --expenses 20 --take-rate 0.5 --json stack.json --as-of 2026-10-14T12:00:00Z; grep -E "Case:" out.txt | cut -c1-120
$PY -c "import json;s=json.load(open('stack.json'));f=json.load(open('facts.json'));f['risk']['routing']='paused';f['option']=s['option'];json.dump(f,open('ft.json','w'))"
must $PY "$SK/scripts/engine.py" defaults ft.json --json it.json; must $PY "$SK/scripts/engine.py" it.json; grep -E "switched-on E0|Value if switched on today|probability-weighted" out.txt | cut -c1-150
step "8d. 20-day token: STOP"
$PY -c "
import json; last=1791849600
json.dump({'totalDataChart':[[last-i*86400, 4e5] for i in range(20)]}, open('baby.json','w'))"
must $PY "$SK/scripts/engine.py" windows baby.json --as-of 2026-10-14T12:00:00Z; cp out.txt wb.json
$PY -c "import json;f=json.load(open('facts.json'));f['earnings']={'windows':json.load(open('wb.json')),'other':0};json.dump(f,open('fb.json','w'))"
mustfail $PY "$SK/scripts/engine.py" defaults fb.json
echo; [ $FAIL = 0 ] && echo "WORKFLOW: ALL STEPS OK" || echo "WORKFLOW: FAILURES ABOVE"
exit $FAIL

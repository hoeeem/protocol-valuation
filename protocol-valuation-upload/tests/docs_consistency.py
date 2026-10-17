"""Docs <-> code consistency."""
import sys, os, re, glob
SK = sys.argv[1]
res = []
def check(name, ok, msg=""): res.append((name, ok, msg))
rd = lambda p: open(os.path.join(SK, p), encoding="utf-8").read()
skill, method, facts, calib, chlog = rd("SKILL.md"), rd("reference/METHOD.md"), rd("reference/FACTS.md"), rd("reference/CALIBRATION.md"), rd("CHANGELOG.md")
code = {os.path.basename(p): open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(SK, "scripts", "*.py"))}

# 1 files referenced exist / files exist are referenced
refs = set(re.findall(r"`((?:scripts|reference|examples)/[\w./-]+)`", skill + method + facts + calib))
missing = [r for r in refs if not os.path.exists(os.path.join(SK, r.rstrip("/")))]
check("every file path cited in the docs exists", not missing, str(missing))
unlisted = [f for f in code if f"scripts/{f}" not in skill]
check("every script is listed in SKILL.md", not unlisted, str(unlisted))

# 2 versions
ver = re.search(r'__version__ = "([\d.]+)"', code["engine.py"]).group(1)
dver = re.search(r'__version__ = "([\d.]+)"', code["defaults.py"]).group(1)
check("engine and defaults versions match", ver == dver, f"{ver} vs {dver}")
check("SKILL.md version matches code", f"**Version {ver}**" in skill, ver)
for name, txt in (("METHOD.md", method), ("FACTS.md", facts), ("CALIBRATION.md", calib)):
    check(f"{name} header version matches code", f"protocol-valuation {ver}" in txt.splitlines()[0], txt.splitlines()[0])
for f in ("market_stats.py", "category_stats.py", "revenue_stack.py", "chart_from_text.py"):
    check(f"{f} docstring version matches", f"protocol-valuation {ver}" in code[f], f)
check("CHANGELOG has an entry for this version", f"## {ver} " in chlog, ver)

# 3 register ids: every D-id used in code appears in METHOD and CALIBRATION
ids = sorted(set(re.findall(r'row\("(D\d+)"', code["defaults.py"])) | {"D21", "D22"}, key=lambda x: int(x[1:]))
for d in ids:
    check(f"{d} documented in METHOD.md", re.search(rf"\b{d}\b", method) is not None)
    check(f"{d} documented in CALIBRATION.md", re.search(rf"\| {d} \|", calib) is not None)

# 4 facts fields: documented fields are read by the code, fields the code reads are documented
doc_fields = set(re.findall(r"^\| `([a-z_0-9]+)`", facts, re.M)) | set(re.findall(r"^\| `([a-z_0-9]+)`, `([a-z_0-9]+)`", facts, re.M) and
             [x for t in re.findall(r"^\| `([a-z_0-9]+)`, `([a-z_0-9]+)`", facts, re.M) for x in t])
d = code["defaults.py"] + code["engine.py"]
unread = sorted(f for f in doc_fields if f'"{f}"' not in d and f"'{f}'" not in d)
check("every field documented in FACTS.md is read by the code", not unread, str(unread))
read = set(re.findall(r'(?:f|e|rk|mk|sp|f\["share"\]|f\["moat"\]|f\["rf"\]|f\["erp"\]|f\["supply"\]|f\["earnings"\]|f\["risk"\]|f\["market"\])(?:\.get\(|\[)"([a-z_0-9]+)"', code["defaults.py"]))
undoc = sorted(x for x in read if x not in facts and x not in ("windows",))
check("every facts field the defaults step reads is documented in FACTS.md", not undoc, str(undoc))

# 5 thresholds in docs match code constants
check("EXTREME down bar documented as -60%", "−60%" in skill and '"pw_down": -0.60' in code["engine.py"])
check("pause ratio 10% in code and docs", "PAUSE_RATIO = 0.10" in code["defaults.py"] and "10%" in skill)
check("early-stage minimum 30 days in code and docs", "EARLY_MIN_DAYS = 30" in code["defaults.py"] and "< 30 days" in skill)
check("structural gap -25pp in code and docs", "STRUCT_GAP = -0.25" in code["defaults.py"] and "25 points" in skill)
check("decay ratio 50% identical in engine and defaults, and documented", "DECAY_RATIO = 0.50" in code["engine.py"]
      and "DECAY_RATIO = 0.50" in code["defaults.py"] and "half of E0" in skill)
check("unpublished-days rule (up to 2 days) in code and docs", "UNPUBLISHED_MAX = 2" in code["common.py"] and "day or two" in skill)
check("young-category level ratio (half) in code and docs", "YOUNG_LEVEL_RATIO = 0.5" in code["defaults.py"] and "under half" in skill)
check("revenue-falling ratio (half of TTM) in code and docs", "REV_FALL_RATIO = 0.50" in code["defaults.py"] and "half of TTM" in method)
n_tests = len(re.findall(r'^@t\(', code["test_edge_cases.py"], re.M))
check("SKILL.md test count matches test_edge_cases.py", f"{n_tests} edge-case" in skill, str(n_tests))
check("credits present exactly in SKILL.md Credits and CALIBRATION.md", skill.count("blocmates.com") == 1 and calib.count("blocmates.com") == 1)

# 6 (6.6.0) holder rights, the share cap and the confidence rule match the code
forms = re.search(r"BENEFIT_FORMS = \{([^}]*)\}", code["defaults.py"]).group(1)
forms = re.findall(r'"([a-z_]+)":', forms)
acc = re.findall(r'"([a-z_]+)"', re.search(r"ACCESS = \(([^)]*)\)", code["defaults.py"]).group(1))
undoc_r = [x for x in forms + acc if f"`{x}`" not in facts or f"`{x}`" not in method]
check("every rights.benefit_form and rights.access value is documented in FACTS.md and METHOD.md", forms and acc and not undoc_r, str(undoc_r))
check("holder-share tolerance (102%) in code and FACTS.md", "SHARE_TOL = 1.02" in code["defaults.py"] and "102%" in facts)
lv = re.search(r"\*\*Valuation basis and input confidence\*\*(.*?)\n\n", method, re.S)
check("input-confidence levels documented in METHOD.md (LOW, MEDIUM, HIGH)", lv is not None and all(f"**{x}:**" in lv.group(1) for x in ("LOW", "MEDIUM", "HIGH")))
check("conditional report order (value if on, then implied probability) in code and METHOD.md",
      code["engine.py"].index("Value if switched on today") < code["engine.py"].index("What the price implies")
      and "First the value if switched on today" in method)

bad = [r for r in res if not r[1]]
for n, ok, msg in res: print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {msg}"))
print(f"\n{len(res) - len(bad)}/{len(res)} docs checks passed")
sys.exit(1 if bad else 0)

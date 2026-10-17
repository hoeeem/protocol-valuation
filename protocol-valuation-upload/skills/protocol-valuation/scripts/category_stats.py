#!/usr/bin/env python3
"""Category facts from a saved DefiLlama overview response. protocol-valuation 6.6.0

Input: the JSON of  api.llama.fi/overview/fees?dataType=dailyRevenue  (keep totalDataChartBreakdown in it if you want the
category series). Rules (METHOD.md section 5.2):
  - the target's category = category of its child protocol with the largest 30d revenue (alphabetical on ties)
  - protocols are grouped by parentProtocol (a protocol without a parent is its own group)
  - share_30d / share_365d = group revenue / category revenue; ranks sort by share_30d, then name
  - share_change_pp = (share_30d - share_365d) x 100   (negative = losing share)
  - n_competitors_ge10 = other groups with share_30d >= 10%
Output: JSON for facts.share and the rubric fields; --series-out writes the category's daily series and
--benchmark-out the all-DeFi daily series (every protocol in the response), both [[ts, usd], ...] for
scripts/market_stats.py (category series as input, benchmark via --benchmark).
Usage: python3 category_stats.py overview.json "<protocol or parent name/slug>" [--category NAME] [--series-out cat.json]
       [--benchmark-out all_defi.json]
Verified on a live overview response (Oct 2026). It reports how many breakdown keys it matched: if that is 0, the
response format has changed. Protocols listed in several categories are assigned by their lead child (largest 30d).
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as cm   # shared input validation and CLI error handling

def _key(p): return (p.get("parentProtocol") or p.get("name") or "").lower()
def _names(p): return {str(p.get(k)).lower() for k in ("name", "displayName", "slug", "module", "defillamaId") if p.get(k)}

def stats(ov, target, category=None):
    prots = ov.get("protocols") or []
    if not prots: raise ValueError("STOP: no 'protocols' list in the overview response")
    t = target.lower()
    mine = [p for p in prots if t in _names(p) or t == (p.get("parentProtocol") or "").lower()
            or t == (p.get("parentProtocol") or "").lower().replace("parent#", "")]
    if not mine: raise ValueError(f"STOP: protocol {target!r} not found (match on name/displayName/slug/parentProtocol)")
    group = _key(mine[0])
    children = [p for p in prots if _key(p) == group]
    if category is None:
        lead = sorted(children, key=lambda p: (-(p.get("total30d") or 0), str(p.get("name"))))[0]
        category = lead.get("category")
    members = [p for p in prots if (p.get("category") or "").lower() == (category or "").lower()]
    if not members: raise ValueError(f"STOP: no protocols in category {category!r}")
    groups = {}
    for p in members:
        g = groups.setdefault(_key(p), {"name": p.get("parentProtocol") or p.get("name"), "r30": 0.0, "r365": 0.0, "children": []})
        g["r30"] += p.get("total30d") or 0.0; g["r365"] += p.get("total1y") or 0.0; g["children"].append(p.get("name"))
    c30 = sum(g["r30"] for g in groups.values()); c365 = sum(g["r365"] for g in groups.values())
    for g in groups.values():
        g["share_30d"] = g["r30"] / c30 if c30 else 0.0; g["share_365d"] = g["r365"] / c365 if c365 else 0.0
    ranked = sorted(groups.items(), key=lambda kv: (-kv[1]["share_30d"], str(kv[1]["name"])))
    rank = [k for k, _ in ranked].index(group) + 1 if group in groups else None
    me = groups.get(group, {"share_30d": 0.0, "share_365d": 0.0})
    comp = [g for k, g in ranked if k != group and g["share_30d"] >= 0.10]
    out = {"category": category, "matched_group": group, "group_children_in_category": me.get("children", []),
           "category_30d_musd": round(c30 / 1e6, 3), "category_365d_musd": round(c365 / 1e6, 3),
           "share_30d": round(me["share_30d"], 4), "share_365d": round(me["share_365d"], 4),
           "share_change_pp": round((me["share_30d"] - me["share_365d"]) * 100, 2), "rank": rank,
           "n_competitors_ge10": len(comp),
           "competitors_ge10": [{"name": g["name"], "share_30d": round(g["share_30d"], 4)} for g in comp],
           "top5": [{"name": g["name"], "share_30d": round(g["share_30d"], 4)} for _, g in ranked[:5]]}
    series = None
    bd = ov.get("totalDataChartBreakdown")
    if bd:
        keys = set().union(*(_names(p) for p in members))
        series, hits = [], set()
        for ts, row in bd:
            v = 0.0
            for k, x in (row or {}).items():
                if str(k).lower() in keys: v += float(x or 0); hits.add(str(k).lower())
            series.append([int(ts), v])
        out["series_points"] = len(series); out["series_protocols_matched"] = len(hits)
        if not hits: out["series_warning"] = "no breakdown keys matched category members: check the key names"
    bench = None
    if bd:
        bench = [[int(ts), sum(float(x or 0) for x in (row or {}).values())] for ts, row in bd]
    elif ov.get("totalDataChart"):
        bench = [[int(ts), float(v)] for ts, v in ov["totalDataChart"]]
    return out, series, bench

def main(argv):
    if len(argv) < 3: raise cm.InputError('usage: category_stats.py overview.json "<protocol>" [--category NAME] [--series-out f] [--benchmark-out f]')
    ov = cm.load_json(argv[1])
    if not isinstance(ov, dict): raise cm.InputError("overview must be a JSON object with a protocols list")
    out, series, bench = stats(ov, argv[2], cm.arg(argv, "--category"))
    so, bo = cm.arg(argv, "--series-out"), cm.arg(argv, "--benchmark-out")
    if so and series is not None: cm.write_json(so, series)
    if bo and bench is not None: cm.write_json(bo, bench)
    print(json.dumps(out, indent=1))

if __name__ == "__main__":
    cm.cli(main, sys.argv)

---
name: protocol-valuation
description: Value a crypto/DeFi protocol token from the cash flows that reach holders, deriving the multiple instead of borrowing it (risk-built cost of equity, fully diluted supply path, two-stage DCF with steady-state P/E, bear/base/bull). Deterministic defaults for every judgement input, confirmed by the user before valuing. Use when asked to value a protocol or token, estimate fair value, or find the growth the market is pricing in.
---

# Protocol valuation: derive the multiple, don't borrow it

**Version 6.6.0** (2026-10-15) · changes in `CHANGELOG.md` · `python3 scripts/engine.py --version`

A token is worth the cash that reaches its holders, discounted at a cost of equity that prices the token's actual risks, divided over every token that has a claim on that cash. The exit multiple is not taken from peers: it is **derived** from the protocol's own return on equity, growth and cost of equity (steady-state P/E). Every judgement input comes from a fixed decision table, so two runs on the same facts give the same numbers, and the user sees and confirms those inputs before anything is valued.

Every run produces fair values **under stated assumptions**, never a recommendation. Label every number as model output and end every report with: **"Model output under stated assumptions, not financial advice."**

## Folder

| Path | What it is |
|---|---|
| `SKILL.md` | This file: the workflow. Enough to run a valuation end to end. |
| `CHANGELOG.md` | What changed in each version. |
| `reference/METHOD.md` | The full method: model, data rules, the defaults decision table, moat rubric, ROE bands, Ke layers, option path. Read it before your first valuation. |
| `reference/FACTS.md` | Schema of the facts file the defaults step reads (every field, unit, where to get it). |
| `reference/DOCS-RESEARCH.md` | Finding and reading the protocol's official docs and whitepaper: official-domain check, `llms.txt` page maps, what to extract, source tiers, evidence log. |
| `reference/CALIBRATION.md` | Every constant (D1–D21) with value, class, rationale and limits; the calibration case's expected outputs; credits. |
| `scripts/engine.py` | Valuation engine (standard-library Python 3.8+, no network). Subcommands `defaults`, `windows`, `--version`. |
| `scripts/defaults.py` | Defaults step: facts → judgement table + engine inputs. |
| `scripts/category_stats.py` | DefiLlama overview → category, share, rank, competitors, the category's daily series and the all-DeFi benchmark series. |
| `scripts/market_stats.py` | Category daily series → multi-year trailing CAGR, latest-year change, two-year-ago level, record and TTM, plus the all-DeFi latest-year change. |
| `scripts/revenue_stack.py` | Fees → protocol revenue → holder revenue from DefiLlama, reconciled on one window with 30/14/7-day run-rates; says which number the valuation should use, writes the revenue check for the facts file, and the fee-switch block when revenue doesn't reach holders. |
| `scripts/chart_from_text.py` | A chart a fetch tool typed out as text, or a DefiLlama Pro CSV download → a checked daily chart file (refused unless the rows add up to the all-time total, or if the rows aren't daily). |
| `scripts/supply_schedule.py` | Documented allocation and vesting → S0, yearly vesting, unissued pool, reconciliation to tracker supply. |
| `scripts/common.py` | Shared input checks used by every script: clean one-line errors for bad files, fields and numbers (`PV_DEBUG=1` shows full tracebacks). |
| `scripts/selftest.py` | Regression test on the calibration case. Run it first. |
| `scripts/test_edge_cases.py` | 77 edge-case and regression tests. Run after any change to the scripts. |
| `examples/` | Calibration case (Hyperliquid, mid-July 2026) and an option-path example. |

Run scripts by path from a working folder (`python3 <skill>/scripts/engine.py ...`); they import each other from their own folder. Every STOP and every input error prints one line and exits with code 2.

## Workflow

Make a task list. Record every input with **value, unit, source URL, ISO 8601 access timestamp and class**. The order is fixed: **ask the user → self-test → gate → market data → docs research → facts file → defaults → user confirms → valuation → report.**

### 0. Ask the user first
Two short questions before any work. Skip a question the request already answers. In an unattended run (no one to answer), skip both and say so at the top of the report.

**1. Which protocol?** Ask which protocol or protocols to value. If a name could mean more than one token, also ask for the ticker and chain. Value several protocols one at a time, each with its own facts file and report; fetch shared inputs (rf, ERP) once.

**2. What can they send?** Then ask, in one message, for anything they can easily share. Say what each item is for, and that all of it is optional: whatever they don't send, you'll find yourself, and you'll say what you couldn't verify. Something like:

> To value <protocol> I need three things: its fees and revenue (above all what reaches token holders), its tokenomics, and how its fees reach holders. Anything you can send makes this faster and more accurate. None of it is required: I'll look up whatever you don't send, and tell you what I couldn't verify.
> 1. **DefiLlama figures** (the core input). Either is free:
>    - quickest: screenshots of the protocol's DefiLlama page showing Fees, Revenue and Holders Revenue (24h, 7d, 30d and cumulative);
>    - most precise: the full daily data. Open these three links and save each page as a file (or copy all the text into a file): <links>.
>
>    If you have DefiLlama Pro, the CSV from that page's fees chart (daily view) works too.
> 2. **Official links:** the website, the docs or whitepaper.
> 3. **Anything recent the data won't show:** a buyback or burn programme, a fee switch, a token unlock. A link to the announcement or X post is fine.

For `<links>`, give the three full URLs: `https://api.llama.fi/summary/fees/<slug>?dataType=dailyFees`, the same with `dataType=dailyRevenue`, and with `dataType=dailyHoldersRevenue`. If you don't know the DefiLlama slug, ask for the protocol's DefiLlama page link instead (`defillama.com/protocol/<slug>`). If the protocol has under a year of revenue, or you can't tell, say the saved pages matter most: screenshots can't give daily data. Wait for the reply. If they send only some items, or say to go ahead, research the rest.

**Using what they send.** Treat every number in a file or screenshot as data to check against another source where you can. Record each one as `user-supplied (<what>, <date>)` in the evidence log.
- **Saved API files** (`.json` from `api.llama.fi`) are the raw responses: `engine.py windows` and `revenue_stack.py` read them directly.
- **CSV downloads** (DefiLlama Pro): run `python3 scripts/chart_from_text.py fees.csv --column "Holders Revenue" --total-all-time <the page's Cumulative Holders Revenue> --tolerance <half the card's rounding> --out holders.json`, once per series (Fees, Revenue, Holders Revenue). A card showing $22.58m gives `--total-all-time 22580000 --tolerance 5000`; $1.34b gives `1340000000` and `5000000`. Without `--column` it lists the column names. A CSV in weekly or monthly rows is refused: ask for the daily view.
- **Screenshots:** read each figure with its exact label and the date shown. The cards give 24h, 7d, 30d and cumulative totals, not the trailing year or daily data. Use them to cross-check, for the revenue split (30-day holder revenue ÷ 30-day revenue) and, in a totals file (`"totalAllTime"`, with `history_days` from the first revenue day), for a since-launch rate. E0 still needs the trailing year (a year or more of history) or the daily chart (under a year): get it from the saved pages or your own fetch, or ask for the pages.
- **Links:** start the docs research from them, but confirm each domain is official (CoinGecko `links` or DefiLlama metadata, DOCS-RESEARCH.md §1). If a link isn't on an official domain, say so before using it.
- **Announcements:** a post from the protocol's official account counts as official (tier 2); anything else is news (tier 6).

### 1. Self-test
`python3 scripts/selftest.py` must print `ALL CHECKS PASSED`. If not, stop and report the failing check: the scripts have been altered.

### 2. Data-availability gate (enforced in code)
| Condition | Outcome |
|---|---|
| No live price | **STOP**: list what is missing |
| No fee data for the protocol | **STOP**: cannot be valued from cash flows |
| Holder-earnings history < 30 days, counted from the **first non-zero** day | **STOP**: the defaults step refuses and writes no table |
| History 30–89 days | **EARLY STAGE** valuation: E0 = the lower of the since-launch and last-14-day run-rates, plus a track-record premium in near-term Ke (2.0pp at 30 days, falling to 0 at 90). Every output is flagged provisional; re-run at 90 days |
| History 90–364 days | Continue; E0 = the lower of the 90-day and last-14-day run-rates, flagged SHORT HISTORY. The two short rules meet at 90 days, so E0 doesn't jump there |
| Under 365 days of history | E0 is also capped at what current protocol revenue supports: 14-day protocol revenue × holder share, from `revenue_stack.py` (`earnings.revenue_check`). Buybacks can run weeks behind revenue, so the holder series alone can hide a collapse |
| 7-day run-rate under half of E0 | **DECAYING** flag, with the 7-day rate as a ready bracket |
| 30-day run-rate < 10% of E0 (buybacks/distributions paused), or routing `paused` / `fee_switch_off` | **STOP** → option path (METHOD.md §9) |
| Holder earnings ≤ 0 | Option path, if a stated mechanism (a proposal, a paused programme) could send revenue to holders; otherwise report that the method can't value it from cash flows |
| Vesting schedule not found in docs, whitepaper or trackers (step 4) | S0 = circulating, flagged, plus a bracket run to max supply |
| Base-layer (L1) token | `is_l1: true`: cash-flow floor only, monetary premium not modelled |

### 3. Market data (free, keyless sources)
| Fact | Source → tool |
|---|---|
| Price, supplies, `as_of` | CoinGecko `api.coingecko.com/api/v3/coins/<id>?localization=false&tickers=false&community_data=false&developer_data=false&sparkline=false` (or a CoinGecko connector). Cross-check `coins.llama.fi/prices/current/coingecko:<id>`; flag > 5% apart. |
| Fees, protocol revenue, holder revenue | DefiLlama `api.llama.fi/summary/fees/<parent-slug>?dataType=` `dailyFees`, `dailyRevenue` and `dailyHoldersRevenue`: **always all three**. Then `python3 scripts/revenue_stack.py --fees fees.json --revenue revenue.json --holders holders.json` (see *Finding protocol revenue* below). |
| Holder earnings (daily) | The holder-revenue file → `python3 scripts/engine.py windows holders.json --as-of <as_of>`. Paste the whole output into `facts.earnings.windows`. |
| Category, share, rank, competitors, category series, all-DeFi benchmark | `api.llama.fi/overview/fees?dataType=dailyRevenue` → `python3 scripts/category_stats.py overview.json <protocol> --series-out cat.json --benchmark-out all_defi.json` |
| Market growth (D2, D3) | `python3 scripts/market_stats.py cat.json --benchmark all_defi.json --as-of <as_of>` → paste into `facts.market` (it carries `basis: category_series`). **Perps:** use `{"basis": "fallback_perps"}` and nothing else (see step 6). |
| Protocol age | From **launch**: the first day of `dailyFees` (or the documented mainnet date), whichever is earlier. Never the first holder-revenue day: a protocol that switched its fee on last year is not a year old. |
| Exploits | DefiLlama hacks list (≥ $10m counts); the docs' incident pages |
| rf | US Treasury daily par yield curve CSV, "10 Yr", latest row ≤ `as_of` |
| ERP | Damodaran `ctryprem.html`, United States, sovereign-CDS ERP column |
| Official links | CoinGecko `links` and DefiLlama `api.llama.fi/protocol/<slug>` (used in step 4) |

The windows tool uses **complete UTC days only** (today's partial day is dropped). DefiLlama posts each day late, so if the last day or two have no row yet, the windows end on the source's last day and the output says so. If the data ends more than two days before the valuation date, the windows still end on its last day and the output says **DATA OUT OF DATE**: get a fresh copy. Other missing days count as zero and are reported, and a last day far below the week before is flagged (the source may not have finished it). It counts history from the first non-zero day, picks the E0 window by rule (365d; 90–364 days the lower of 90d and 14d; 30–89 days the lower of since-launch and 14d) and reports the pause and decay checks. Never take DefiLlama `total1y` at face value.

**Finding protocol revenue.** "Revenue" means three different numbers, and the valuation needs the right one:

| Number | What it is | Used for |
|---|---|---|
| Fees | what users pay | the fee-switch base when the protocol keeps nothing today (fees go to liquidity providers) |
| Protocol revenue | what the protocol keeps: treasury plus holders | the fee-switch base when revenue sits in a treasury |
| Holder revenue | what actually reaches token holders | E0 on the standard path |

`revenue_stack.py` measures all three series on one calendar window ending on the same day (the latest day all three have published), builds the waterfall with 30/14/7-day run-rates, checks fees ≥ protocol revenue ≥ holder revenue, and classifies the protocol:
- **routed:** holders get at least 80% of revenue. Standard path on holder revenue.
- **treasury:** the protocol keeps revenue that doesn't reach holders, as with Aave: $89.5m protocol revenue against $18.2m to holders, paused, in Oct 2026. The fee-switch question uses protocol revenue net of DAO costs (`--expenses`), never past buybacks.
- **lp_fees:** the protocol keeps under 5% of fees (Uniswap before its switch). The base is fees × the proposal's share, run at 100/80/60% of today's fees, because liquidity can leave when providers earn less.

It flags paused holder flows, revenue run-rates far from the window level, a SHARP FALL in the last week, holder flow that LAGS REVENUE (buybacks catching up on earlier revenue), missing costs and series that don't reconcile. It also prints a **revenue check** block: paste it into `facts.earnings.revenue_check` (pass `--holder-share` with the documented share if the docs state one; otherwise the measured share is used). Cross-check against the docs and the governance proposal (DOCS-RESEARCH.md §3a). If DefiLlama doesn't track revenue, or it disagrees with the docs by more than 20%, use the lower figure, bracket with the higher and flag it.

Files the user sent in step 0 come first. If you have neither those nor raw API access (a web-fetch tool that summarises pages, for example):
- **Under a year of history: list the daily chart.** DefiLlama's `total7d` and `total30d` are not complete-day windows (they can cover 6 or 29 days and include a part day). Ask the fetch tool for `totalAllTime` and then every `totalDataChart` entry as `timestamp,value` lines, save them, and run `python3 scripts/chart_from_text.py listed.txt --total-all-time <totalAllTime> --out holders.json`. It refuses a list that doesn't sum to the all-time total, so a dropped or mistyped row is caught. Do this for all three series, then use the normal tools (`engine.py windows`, `revenue_stack.py`).
- **A year or more:** totals are acceptable. Write each of the three summaries as a totals file, `{"total1y": ..., "total30d": ..., "total7d": ..., "history_days": ...}` in dollars, and run `revenue_stack.py` on those (it flags that windows weren't recomputed). For holder earnings put `total1y` and `total30d` (annualised, × 365/days) in `facts.earnings.core_by_window` with `history_days`, and flag that windows were not recomputed. Always include `30d` so the pause check runs.
- The DefiLlama `overview/*` endpoints are too large to summarise reliably. Take category share and competitors from a dated, sourced article and flag it; use `basis: none` for the market unless you can get the category series.
- `share_0` cancels out of the growth lever (only `share_T / share_0` enters g1, unless the 95% cap binds); it still matters for the moat rubric's network-effects score (≥ 40% → 3, ≥ 20% → 2).

### 4. Docs and whitepaper research
Follow `reference/DOCS-RESEARCH.md`. In short:
1. **Official sources only.** Start from links the user sent (step 0), and take the docs, whitepaper and forum domains from CoinGecko `links` and DefiLlama protocol metadata. A site found only through search, or a link that isn't on one of those domains, is not official until confirmed.
2. **Map the docs first.** Fetch `<docs-root>/llms.txt` (GitBook, Mintlify) for a page index, or `sitemap.xml`; GitBook pages also serve as `<page>.md`. Pick the pages for tokenomics, fees, buybacks and burns, staking, governance and validators, legal and KYC, audits and incidents, collateral and yield, launch history.
3. **Extract** every field in the DOCS-RESEARCH.md §3 table, with a quote (< 15 words), URL and access time per fact, into `evidence.md`.
4. **Fall back down the source tiers** when the docs are silent (official blog/forum → on-chain → unlock trackers → research → news), recording the tier.
5. **Build the supply schedule**: allocation buckets → `schedule.json` → `python3 scripts/supply_schedule.py schedule.json --md supply.md`. Use its `S0`, `vest` and `unissued` (`fallback_circulating: false`); run the tracker figure as a bracket when it flags a > 10% gap.

6. **Map where the money goes** (DOCS-RESEARCH.md §3a): what users pay for, who receives each part, what comes out before holders, what share reaches holders and how (buyback and burn, buyback and hold, distribution, staking distribution), whether that is automatic, discretionary or only proposed, and whether holders must stake or lock. Record it in `facts.rights` and `risk.routing`; it goes into the report.

Never invent a schedule no source states. Unevidenced booleans stay `false` and go on the gaps list.

### 5. Write facts.json
Follow `reference/FACTS.md`. Every documented boolean cites a row in `evidence.md`.

### 6. Defaults step
```
python3 scripts/engine.py defaults facts.json --md judgement.md --json inputs.json
```
A pure function of the facts file. It applies the decision table (METHOD.md §5), writes the judgement table with each row's rule, class and arithmetic, and lists **flags** at the top (shrinking market, perps fallback, age check, option defaults, pause check not run).

- **Bear, base and bull follow the calibrated scenario structure** (from the source article): market growth = a third of the multi-year trailing CAGR, capped at ±20%, with bull and bear 10 points either side; share levers ×0.5/1.25/1.5; ROE band positions; regulatory 2.5/2.0/0.5%; emissions 60/10/0%; gT 3.0/3.5/4.5%; weights 20/60/20.
- **A downturn is a cycle, not a trend (D2/D3).** A fall in the category is handled by the cycle reset (a one-off drop in level), never by extrapolating the decline. If the category is already well below its record, the reset has already happened and growth resumes from the lower base. The calibration case does exactly this: perp volume falls ~35% from its record year and still grows 20% a year afterwards.
- **Bigger picture before calling a decline structural.** Only if the category shrank over the latest year, fell at least 25 points more than DeFi as a whole, and (where measurable) sits below its level two years ago does the table flag **POSSIBLE STRUCTURAL DECLINE** and set base market growth to **flat (0%)**, bull +10%, bear −10%, for the user to confirm. If DeFi fell with it, the table says **CYCLICAL DOWNTURN** and the calibrated rule applies. Without the all-DeFi benchmark it applies the calibrated rule and asks for the benchmark. Categories with under three years of history are flagged YOUNG CATEGORY.
- **Young category in decline.** If the category shrank over the latest year and is young (trailing growth over under three years, or its level two years ago was under half today's), its trailing CAGR is a boom off a small base and the two-year test can't fire. Base market growth is then **flat (0%)**, ±10pp, flagged **YOUNG CATEGORY IN DECLINE** for the user to confirm (for example, a launchpad category after a memecoin boom).
- **No category series** (`basis: none`): market growth is a flat default (0%, ±10pp), flagged **NO MARKET SERIES**. Say so next to the table and ask for the user's view on g1.
- **One cycle-factor rule (D3).** min(1, 0.6522 × record 365d level / TTM level), computed by the defaults step from the same series as the trailing CAGR. It is never supplied directly. With `basis: fallback_perps` the trailing CAGR (61%), cycle factor (0.6522) and DEX share (7%) are fixed constants that always travel together. Mixing a fallback with live series values is refused.
- **Perps caveat.** On the fallback basis g1 is 10/40/55% whatever the live data says: the calibration case's (Hyperliquid's) inputs, not a rule. Say so next to the table and ask the user for their view on g1.
- **Growth from a business forecast.** If you or the user can forecast year-7 holder earnings from the business's own drivers (activity × share × effective fee rate; METHOD.md §6 has the drivers by protocol type), convert with g1 = (year-7 holder earnings / E0)^(1/7) − 1 and enter it as an override labelled MODELLED.

### 7. User confirms or overrides (mandatory)
Show `judgement.md` to the user **before valuing**. Point out the flags, any BORDERLINE moat score, FALLBACK rows and the gaps list. Overrides are dotted paths in a JSON file:
```json
{"scenarios.base.g1": 0.30, "scenarios.bull.roe": 0.60, "confirmed": true}
```
Apply with `--overrides ov.json` (re-run step 6 with it). Keys are validated: a typo is rejected with the list of valid keys. Overrides are recorded in `inputs.json → judgement.overrides` and labelled as the user's. Never change a default silently. Until `confirmed` is true the engine prints `JUDGEMENT TABLE NOT CONFIRMED`. If the user is not available, run on the defaults, keep that flag and say so at the top of the report.

### 8. Value
```
python3 scripts/engine.py inputs.json --md valuation.md --json valuation.json
```
- Any `STOP:` is a finding, not an error to work around: report it.
- **EXTREME RESULT** (weighted value above +150% or below −60% of price, i.e. 2.5× or 0.4×, break-even growth above 100% or below −20%, earnings yield above 25%, or a P/E above 30x) is the first flag in the output. Re-check the inputs it lists, starting with any cause it names (a decaying latest week, an E0 already capped by revenue, a flat default market), and report the result only together with the flag and what the re-check found.
- **Option path** (paused buybacks, fee switch off, or "what if the fee switch turns on").
  - **Base:** the `option` block comes from `revenue_stack.py`: protocol revenue for treasury protocols, fees × the proposal's share for LP-fee protocols. Fill `take_rate` from the proposal or docs; the engine refuses a missing rate.
  - **Premium:** the switched-on value is priced at the routing it would have once on (`option.routing_on`, default `documented_not_immutable`, 1%). Whether and when it switches on is carried by the activation probabilities, so the switch-off premium isn't charged as well.
  - **Condition:** name the mechanism that would switch it on, with its source, in `option.condition`. Without one the output says the switched-on value is hypothetical (NO STATED CONDITION, input confidence LOW).
  - **What to report:** lead with the value if switched on today and the activation probability today's price implies. The activation cases come second; with no `option.activation`, D21 placeholder cases are inserted and labelled as judgement, not estimates.
- **Brackets.** For a circulating-supply fallback, also run the max-supply bracket. For a time-limited buyback commitment, run with and without `continue_after` (a part-year commitment such as `years: 0.54` counts that share of year 1); the COMMITMENT ASSUMED TO CONTINUE flag prints the overrides for the committed-only run. For a BORDERLINE moat, run the adjacent band: `judgement.md` prints its overrides (ROE and g1 for that band). For a DECAYING flag, run `E0_core` at the 7-day rate.

### 9. Report
Write `valuation_<protocol>_<YYYY-MM-DD>.md` containing, in this order:
1. One-paragraph answer: the valuation basis and input confidence (from the engine output), PW DCF vs price, break-even growth vs base g1, and the inputs that move the answer most. For a conditional valuation, the value if switched on today and the probability the price implies take the place of PW DCF and break-even growth. Any EXTREME RESULT flag goes here. For LOW confidence, say plainly that the inputs are weak however precise the numbers look.
2. The money map with holder rights (DOCS-RESEARCH.md §3a).
3. Input snapshot with sources and ISO timestamps, each marked observed, documented, modelled (overrides) or default; the evidence log's key rows; the supply schedule; gaps list and docs red flags (DOCS-RESEARCH.md §7).
4. The confirmed judgement table with its flags, overrides marked.
5. E0 windows and fee waterfall; Ke build with the layer sum; supply path.
6. Scenario table, method 2 (P/E × EPS) and method 3 (earnings-yield path), PW and the weight sensitivity.
7. Break-even g1 and the g1 × Ke sensitivity grid.
8. All engine flags, verbatim.
9. What would invalidate the result: missing evidence, and the monitors (emissions deployment, market-share loss, formal enforcement (+2pp Ke), exploit ≥ $10m, fee-routing changes).
10. The skill version, and "Model output under stated assumptions, not financial advice."

Quote numbers only from engine output. Use the engine's significant-figure dollar formatting.

## Before delivering
- Self-test passed (and `test_edge_cases.py` if the scripts were changed); defaults step run; table and flags shown; confirmed/overridden rows marked.
- E0 from the windows tool on complete days (or flagged if it couldn't be); pause and decay checks run; under a year of history, the revenue check in the facts file.
- Ke layer sum stated and the ERP column named.
- Every URL listed with HTTP status and access time; a failed source is a gap, not a guess.
- Engine flags repeated in the report; any EXTREME RESULT addressed.

## Credits
The method (derived rather than borrowed multiples, the risk-built cost of equity, the three growth levers and the moat-to-ROE bands) is adapted from Jean-Yves Devloo, ["Hyperliquid: Stop Borrowing Multiples, Start Deriving Them"](https://www.blocmates.com/articles/hyperliquid-stop-borrowing-multiples-start-deriving-them), Blocmates, 16 July 2026. The generalised decision rules, data pipeline, scripts and any errors are this skill's own; `reference/CALIBRATION.md` lists which parts come from the article and which this skill adds.

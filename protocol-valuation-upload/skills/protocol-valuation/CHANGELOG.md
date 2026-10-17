# Changelog

## 6.6.0 (2026-10-15): what each result rests on

From a review of how the method carries beyond Hyperliquid. The valuation maths is unchanged: the calibration case still gives PW DCF $119.86, and the four live tokens give the same values as before.

### Added
- **Valuation basis and input confidence on every report**, on the line under the price. The basis says whether the value rests on existing holder earnings (buybacks or distributions operating today) or on conditional holder earnings (the value if a stated mechanism happens). Input confidence is LOW, MEDIUM or HIGH, with the reasons (METHOD.md §10):
  - LOW: under a year of history, decaying earnings, an extreme result, or no stated condition;
  - MEDIUM: growth from defaults rather than live data, a moat score on a band edge, buybacks assumed to outlast their commitment, falling revenue, or holder flow above revenue.

  Precise numbers built on weak inputs now say so.
- **Holder rights (D23).** `facts.rights` records two things from the docs: how holders receive the benefit (`buyback_burn`, `buyback_held`, `distribution`, `staking_distribution`) and what they must do to get it (`all_holders`, `stakers_only`, `lockers_only`).
  - Cash distributions default to buyback mode `none`, because paying cash doesn't shrink the supply. A mismatch with the buyback mode is flagged, as is a benefit that needs staking or locking.
  - Missing rights are flagged on the standard path.
- **A money map before any number** (DOCS-RESEARCH.md §3a, METHOD.md §3). It records:
  - what users pay for and who receives each part;
  - which costs and incentives come out;
  - what share reaches holders, and whether that share is automatic, discretionary or only proposed.

  It stops a valuation from counting money holders never receive, such as interest that belongs to lenders or fees that belong to liquidity providers.
- **Growth from a business forecast** (METHOD.md §6): activity × market share × effective fee rate, with the drivers for each protocol type (perps, lending, DEX, liquid staking, launchpad, stablecoin/RWA). It is turned into the engine's single rate with g1 = (year-7 earnings / E0)^(1/7) − 1 and entered as an override with its source.
- **The source article and this skill's additions are listed separately** (CALIBRATION.md). The article supplies the cash-to-holders principle, the layered cost of equity, the two-stage DCF with a derived multiple, 20/60/20 weights and Hyperliquid's inputs. The skill adds the defaults table, the short-history and revenue checks, the option path's placeholder cases and the confidence rule.

### Changed
- **Conditional valuations lead with the value if switched on today.** Next comes the activation probability the price implies, a grid that now always includes an immediate switch-on, then the scenario table.
  - The value weighted by activation cases is a secondary line. The D21 cases are labelled as placeholders, and the EXTREME check applies to them only when they are the user's own.
  - A conditional valuation needs `option.condition`: the mechanism that would switch it on, with its source. Without one the output says NO STATED CONDITION and confidence is LOW.
  - If even an immediate switch-on can't reach the price, the output says PRICE ABOVE THE SWITCHED-ON VALUE.
- **Earnings are counted once.** E0 is holder revenue, which is already what holders receive.
  - A payout below 100% is flagged unless `payout_reason` explains it.
  - The revenue check caps the holder share at 100%. Holder flow above protocol revenue comes from reserves or catch-up buybacks, so it isn't recurring business earnings; it is flagged HOLDER FLOW ABOVE REVENUE.
  - `revenue_stack.py` keeps the uncapped figure as `holder_share_measured`.
- Labels no longer nest brackets inside brackets (the E0 window and the confidence reasons).

### Considered and not added
- **A forecast-only route** for protocols with no holder earnings yet. It would make the method a valuation of forecasts alone. Such protocols are reported as not valuable from cash flows with this method (METHOD.md §10, CALIBRATION.md limitation 16).
- **A full business model for each protocol type.** The drivers table guides a growth override instead; a model per type would need inputs the skill can't verify.
- **A status label on every input.** The judgement table already gives each row its class (METHOD, CALIBRATED, HEURISTIC, JUDGEMENT, DOCUMENTED) and source, and the report marks figures as observed, documented, modelled or default.

### Results on the live test (same data, values unchanged)
| Token | Value | Input confidence |
|---|---|---|
| HYPE | $85.13 (+6%) | MEDIUM: growth from the perps constants |
| PUMP | $0.003912 (−9%) | MEDIUM: flat default market, moat on a band edge, buybacks assumed to continue past the commitment |
| STONK | $0.7584 (+616%) | LOW: 72 days, decaying, extreme result, flat default market |
| PONS | $0.3023 (−2%) | LOW: 93 days, flat default market |

## 6.5.1 (2026-10-15): free data first, and out-of-date files called out

- **The intake asks for free data first.** DefiLlama's CSV download is a Pro (paid) feature, so the user is offered screenshots (quickest) or the three raw data pages saved from the browser (free and exact). The CSV is mentioned only for users who have DefiLlama Pro.
- **Out-of-date data is named as such.** If a file's data ends more than two days before the valuation date, the windows end on its last day (no longer counted as zero days, which understated earnings) and the output says DATA OUT OF DATE: get a fresh copy. The same rule applies in `revenue_stack.py` and `market_stats.py`.

## 6.5.0 (2026-10-15): asks first, and works from what the user can send

### Added
- **Step 0: ask the user first.** The skill asks which protocol or protocols to value. Then, in one message, it asks for whatever the user can easily share: DefiLlama screenshots, the CSV from the protocol's fees chart, or the three raw API pages saved from the browser; the official website and docs; and any recent buyback, fee-switch or unlock announcement. It says why each helps, and that it will research anything not sent and report what it couldn't verify. It skips questions the request already answers, and skips both in an unattended run.
- **Rules for user-supplied material.** Saved API files are used as raw responses. CSVs go through `chart_from_text.py`. Screenshot figures are recorded with their labels and date, used to cross-check, and never alone for E0, since the cards show no trailing year and no daily data. Links are checked against the official domains. Everything is logged as `user-supplied` with its source tier.
- **`chart_from_text.py` reads DefiLlama CSV downloads:** a header row, a date or timestamp column, and `--column` to pick Fees, Revenue or Holders Revenue. It refuses weekly or monthly rows. The total check can use the page's rounded "Cumulative" figure with a tolerance, or be skipped with `--no-total-check` for a file downloaded straight from the source. A summary line left at the top of a typed-out listing is ignored.
- **`revenue_stack.py` totals files take `totalAllTime`:** under a year of history, the level is the cumulative total over the days since the first revenue day (useful with screenshot figures).

### Changed
- **The package holds only what the skill needs.** The stress-test harness and its report moved to a separate development bundle; the self-test and the edge-case tests stay in `scripts/`.

## 6.4.0 (2026-10-15): young tokens, data timing and silent defaults

Found in a live test on HYPE, PUMP, STONK and PONS (15 Oct 2026). The two three-month-old launchpads came out at 3–7× their price: their revenue had collapsed over the month and the earnings windows lagged it. None of the changes moves the calibration case (PW DCF $119.86).

### Fixed
- **The DECAYING warning can appear.** `engine.py windows` computed it, but the defaults step never passed it on, so it could not reach the output. It is now computed against the final E0 (from the windows tool or `core_by_window.7d`), shown in the judgement table and the valuation, and gives the 7-day rate as a ready bracket.
- **A day DefiLlama hasn't published yet is no longer counted as zero.** At 07:45 UTC DefiLlama's last row was usually the day before yesterday; the windows tool counted yesterday as a zero day, cutting STONK's E0 by 17%. If the last day or two have no row, windows end on the source's last day and say so; a longer gap still counts as zero and is flagged. A last day far below the week before is flagged LAST DAY LOW. The same rule applies in `revenue_stack.py` and `market_stats.py`.
- **`revenue_stack.py` on short histories.**
  - All three series are measured on one calendar window ending on the same day. STONK's fees had been measured over 80 days and its holder revenue over 72, which showed a 66% holder share instead of 60%.
  - Levels carry their real label (TTM, 90d or the young series' history) instead of always "TTM", including in the option block's `base_label`.
  - New 30/14/7-day run-rates, a SHARP FALL flag (last week under half the window level) and a HOLDER FLOW LAGS REVENUE flag. The old check compared only 30 days with the window, and reported STONK's revenue as +72% while the last week was −55%.
- **Silent defaults are flagged.** PUMP's output had raised no flags at all:
  - NO MARKET SERIES when `market.basis` is `none` (growth is a flat default);
  - COMMITMENT ASSUMED TO CONTINUE when a time-limited buyback runs with `continue_after: true`, with the overrides for the committed-only bracket;
  - BORDERLINE MOAT as a flag, with the adjacent band's ROE and g1 computed and its overrides printed in `judgement.md`.
- **EXTREME RESULT names the likely cause first** (a decaying week with the bracket to run, an E0 already capped by revenue, a flat default market), then the general re-check list.

### Changed
- **E0 for 90–364 days = the lower of the 90-day and 14-day run-rates** (was the 90-day window). The early-stage rule takes the lower of since-launch and 14 days, so the two now meet at 90 days. Before, PONS's E0 rose 42% between day 89 and day 90 on the same data.
- **Revenue check (D19).** `revenue_stack.py` writes `earnings.revenue_check` (protocol-revenue run-rates and the holder share, measured or documented via `--holder-share`). Under a year of history, E0 is capped at 14-day protocol revenue × holder share. Buybacks can run weeks behind revenue: PONS's holder revenue was 251% of the week's protocol revenue, so the holder series looked healthy while revenue was down 81%. From a year on, TTM stands; a revenue-supported rate under half of TTM is flagged REVENUE FALLING.
- **Young category in decline (D2).** A category that shrank over the latest year and is young (trailing growth over under three years, or its level two years ago under half today's) gets flat base market growth (0%, ±10pp), flagged for confirmation. Its trailing CAGR is a boom off a small base, and the two-year structural test can't fire for a category that barely existed two years ago. A young category that is still growing keeps the calibrated rule.

### Added
- **`scripts/chart_from_text.py`** for summarising fetch tools: a daily chart listed as text becomes a chart file, refused unless it sums to DefiLlama's `totalAllTime`. DefiLlama's `total7d`/`total30d` can cover 6 or 29 days and include a part day, so they aren't used as windows for young protocols.

### Results on the live test (same data, 6.3.0 → 6.4.0)
| Token | 6.3.0 | 6.4.0 | What changed |
|---|---|---|---|
| HYPE | $85.13 (+6%) | $85.13 (+6%) | nothing |
| PUMP | $0.003912 (−9%), no flags | $0.003912 (−9%) | three flags: no market series, borderline moat (adjacent band −34%), commitment to April 2027 (committed-only −95%) |
| STONK | $0.7584 (+616%), EXTREME | $0.7584 (+616%), EXTREME + DECAYING | the flag now points at the latest week (E0 $42.3m → +235%) |
| PONS | $0.9389 (+204%), EXTREME | $0.3023 (−2%) | E0 capped at what current revenue supports ($29.1m) |

### Known open items
- STONK still comes out far above its price: its revenue was still falling weekly. The method values run-rates with flat growth; the DECAYING flag and break-even growth (−45% a year) show the market pricing a continued fall.
- Protocols that route a documented share below 80% are classed "treasury" by `revenue_stack.py` (see CALIBRATION.md limitation 15).
- The strong-moat base still assumes share gains for a protocol losing share (limitation 14).

## 6.3.0 (2026-10-15): finding protocol revenue, and an unbiased fee-switch value

### Added
- **`scripts/revenue_stack.py`.** Reads DefiLlama's three series together (fees, protocol revenue, holder revenue), from raw charts or from summary totals.
  - Builds the waterfall and checks fees ≥ revenue ≥ holder revenue.
  - Classifies the protocol: routed, treasury, LP fees or no revenue.
  - Writes the input the valuation should use: holder earnings on the standard path, or a fee-switch block with the right base. Treasury protocols use protocol revenue net of DAO costs; LP-fee protocols use fees × the proposal's share, run at 100/80/60% of today's fees.
  - Flags paused holder flows, revenue run-rates far from TTM, missing costs and series that don't reconcile.
- **DOCS-RESEARCH.md §3a, Finding protocol revenue:** where to confirm the fee split, the switch proposal, DAO costs and treasury inflows; the 20% disagreement rule; never use past buybacks as the base when revenue is larger.

### Fixed
- **The switched-on value no longer charges the switch-off premium.** It is priced at the routing it would have once on (`option.routing_on`, default `documented_not_immutable`, 1%). Whether and when the switch happens is carried by the activation probabilities. Before, the 3% switch-off premium was charged on top, understating the switched-on value by about a fifth and overstating the market-implied activation probability.
- The option report names its base (`base_label`) instead of always printing "fees_ttm".

Found in a live check: Aave, Oct 2026. Fees $691m, protocol revenue $89.5m, holder revenue $18.2m (paused). An earlier run had used the $18.2m as the switched-on base.

## 6.2.1 (2026-10-14): hardening from the final stress test

### Fixed
- **Fair-value buyback solver.** Plain fixed-point iteration silently failed to converge in about 5% of runs with time-limited commitments, returning its last guess (present since v5; found by fuzzing). It now starts from the no-retirement path, iterates with damping and checks convergence. If it still doesn't converge, the scenario is valued with cash treated as a distribution and flagged. In 10,000 fuzzed cases, 99% of fair-value runs converge.
- **Supply floor in fair-value mode.** The 5% floor bent results (value jumped with growth and could rise with a higher Ke). Fair-value buybacks can't over-retire, so only a numerical floor applies there; retiring over 95% of supply is flagged "deep buyback". Other modes keep the 5% floor.
- **Break-even honesty.** If the anchor value jumps across the price (extreme growth regions only), the result carries a BREAK-EVEN APPROXIMATE flag.
- **Input validation everywhere** (`scripts/common.py`):
  - Missing or empty files, invalid JSON, text where a number belongs, NaN or infinity, unknown classes, and launch dates after `as_of` now give a one-line error, never a traceback or a silent result. An infinite price previously produced a full valuation.
  - Daily series: millisecond timestamps are detected, exact duplicate rows are counted once (previously double-counted), and null values are skipped.
  - Outputs are written as UTF-8 on every platform.

Tests: 57 edge-case tests (4 new from the stress test); plus the final stress test (kept with the development files): 66 independent maths checks, 51 hostile-input checks, 62 docs checks and 25,000 fuzzed cases. Runs on Python 3.8–3.13.

## 6.2.0 (2026-10-14): early-stage valuations (30–89 days of revenue)

### Added
- **Early-stage mode.** Tokens with 30–89 days of holder earnings can now be valued instead of being refused:
  - **E0** = the lower of the since-launch average and the last 14 days, both annualised. This guards against a launch spike and against a fast ramp that may not hold. A last-14-day rate below half the since-launch rate is flagged LAUNCH DECAY.
  - **Track-record premium (D22)** in the near-term cost of equity: 2.0pp at 30 days, falling linearly to 0 at 90 days, so there is no jump at 90. It is left out of the terminal Ke.
  - Every output carries an **EARLY STAGE** flag marking the result as provisional, to be re-run at 90 days.
- `engine.py windows` now also reports `14d` and `since_launch` run-rates, and picks the early-stage E0 by the rule above.

### Changed
- The hard minimum moves from 90 days to **30 days**: under 30 days is still a STOP with no table (a diagnostic table remains available). The engine also refuses a 30–89-day input that wasn't built as early stage by the defaults step.

Tests: 53; calibration case unchanged.

## 6.1.0 (2026-10-14): article-first scenarios, downturns treated as cycles

### Changed
- **Market growth back to the calibrated rule.** 6.0.0's shrink rule (half the latest year's decline, extrapolated for seven years) is removed: it contradicted the calibration case, where perp volume falls ~35% from its record year and still grows 20% a year afterwards. It took UNI's DEX category (−34%) to −15% a year, two-thirds gone by 2032. The "never above the latest year" cap is removed too. Base = a third of the multi-year trailing CAGR, ±20%, bull/bear ±10pp, as calibrated.
- **Downturns are cycles.** A fall is handled by the cycle reset (D3), a one-off drop in level, and growth resumes from the lower base.
- **Structural decline needs the bigger picture.** Only when the category shrank over the latest year, fell at least 25pp more than all of DeFi, and sits below its level two years ago (where measurable) does the table flag POSSIBLE STRUCTURAL DECLINE. Base market growth is then flat (0%), bull +10%, bear −10%, for the user to confirm. A category that falls with DeFi is flagged CYCLICAL DOWNTURN and keeps the calibrated rule. Without an all-DeFi benchmark the calibrated rule applies, with a flag asking for one.
- `category_stats.py --benchmark-out` writes the all-DeFi daily series; `market_stats.py --benchmark` adds `benchmark_yoy`, plus `level_2y_ago_365d`. Trailing CAGRs over fewer than three years are flagged YOUNG CATEGORY.

### Fixes from the 6.0.0 test report
- **NO MOAT flag** when ROE is floored at Ke_T, explaining why a riskier scenario can show a higher ROE (correct maths, previously silent).
- **Part-year buyback commitments**: `buyback.years` may be fractional (0.54 → 54% of year 1's cash).
- **EXTREME RESULT bar symmetric in multiples**: above 2.5× or below 0.4× price (+150% / −60%; was −75%).
- **Age**: launch date equal to the first holder-revenue day is now a NOTE to confirm (true for HYPE), not a warning; `risk.first_fees_day` earlier than `launch_date` raises AGE CHECK.
- **Third regulatory class** `us_facing_no_kyc_settled` (1.5/1.0/0.5%, HEURISTIC) for no-KYC, US-facing protocols whose US probes closed without action.
- `category_stats.py` caveat updated: verified on a live overview response.

Tests: 49 edge-case and regression tests; calibration case unchanged (PW DCF $119.86, break-even g1 31.3%).

## 6.0.0 (2026-10-14): first standalone release

Versions up to 5 depended on the source article being on hand. 6.0.0 carries the whole method in the skill, adds docs research, and fixes the issues found in independent testing on six tokens.

### Fixes from testing
- **Paused buybacks stop the run.** A 30-day holder run-rate below 10% of E0, or routing `paused` / `fee_switch_off`, is a STOP pointing to the option path (previously AAVE was valued normally with no warning). Caught in both the defaults step and the engine.
- **Under 90 days of history: no defaults table.** The defaults step refuses (previously it built a table and only the engine stopped). `earnings.diagnostic: true` gives a table marked DIAGNOSTIC, never a valuation.
- **Shrinking markets.** Base market growth is capped at the latest year's change, and a category that shrank over the latest year gets half that decline (capped at −20%). Previously a collapsing launchpad category with a high trailing CAGR got +20% (PONS, PUMP).
- **History from the first non-zero holder-revenue day; age from launch.** Zero rows before a fee switch no longer count as earnings history. Protocol age (smart-contract premium, process power) runs from launch, not from the first holder-revenue row, and the defaults step flags it if the two match (previously UNI looked 9 months old).
- **EXTREME RESULT flag.** Weighted value above +150% or below −75% of price, break-even growth outside −20%..100%, earnings yield above 25% or P/E above 30x puts a loud first flag on the output with what to re-check (previously PONS at +533% passed silently).
- **One cycle-factor rule.** `market.basis` decides where trailing growth, the cycle factor and the DEX lever come from (`category_series`, `fallback_perps` or `none`). The cycle factor is always computed, never supplied, and mixing series is refused. Previously the instructions allowed two readings for HYPE ($94.06 vs $76.15 weighted).
- **Earnings windows: complete days only, no "lead".** `engine.py windows` drops today's partial day, uses calendar windows with missing days counted as zero, picks the E0 window by rule and reports the pause check. The "lead" figure (minimum of windows, which showed $0 for AAVE and contradicted the 12-month rule) is gone.
- **Option path defaults.** With no activation cases supplied, default cases (D21, JUDGEMENT) are inserted and flagged for confirmation.
- **Scenario-weight sensitivity** applied weights in the wrong scenario order (sorted keys); fixed.
- **Override typos** were accepted silently; unknown keys are now rejected with the valid list.
- **STOPs print one clean line** (exit code 2) instead of a Python traceback.
- **Version number** on every output; **credit** to the source article restored (SKILL.md, CALIBRATION.md).

### Added
- Docs and whitepaper research step (`reference/DOCS-RESEARCH.md`): official-domain check, `llms.txt` page maps, field-by-field extraction table, source tiers, evidence log, red flags.
- `scripts/supply_schedule.py`: documented allocation and vesting → S0, yearly vesting, unissued pool, reconciliation to tracker supply (calendar months, so cliffs land on their anniversary).
- `scripts/category_stats.py`: DefiLlama overview → category, share, rank, competitors, category daily series. Tested on synthetic data shaped like the documented response; verify against a real response on first use.
- `scripts/market_stats.py`: now complete days only, with the latest-year change and drawdown.
- `scripts/test_edge_cases.py`: 42 tests, including a regression test for each issue above.

### Unchanged
Valuation maths (two-stage per-token DCF, steady-state P/E, Ke layers) and the calibrated constants. The calibration case reproduces exactly: PW DCF $119.86, break-even g1 31.3%.

### Known open items
- Default growth for perps is still the fixed fallback set (61% / 0.6522 / 7%) until total CEX + DEX perp volume is available.
- Bear g1 for a protocol losing share in a growing market is still the (positive) bear market rate.

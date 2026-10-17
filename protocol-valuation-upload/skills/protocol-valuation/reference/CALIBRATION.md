# Calibration register (protocol-valuation 6.6.0)

Every constant the defaults step uses, why it has that value, and how far to trust it. Constants were fixed on one calibration case (Hyperliquid, mid-July 2026: `examples/calibration_facts.json`), and the method was then frozen. `scripts/selftest.py` checks that the scripts still reproduce that case.

The calibration targets and the method's core ideas come from Jean-Yves Devloo, ["Hyperliquid: Stop Borrowing Multiples, Start Deriving Them"](https://www.blocmates.com/articles/hyperliquid-stop-borrowing-multiples-start-deriving-them) (Blocmates, 16 July 2026). The generalising rules (HEURISTIC rows) are this skill's.

Classes: **METHOD** core rule · **CALIBRATED** constant fixed on the calibration case · **HEURISTIC** generalising rule, alternatives exist · **FALLBACK** substitute for data that isn't free · **JUDGEMENT** convention.

## Register

| Id | Input | Value / rule | Class | Rationale | Calibration case |
|---|---|---|---|---|---|
| D19 | E0 | TTM holder earnings (complete days, history from first non-zero day; the source's unpublished last day or two are not counted as zero); 90–364 days → lower of 90d and 14d run-rates; 30–89 days → early stage, lower of since-launch and 14d run-rates; under 365 days also capped at 14d protocol revenue × holder share (revenue check), from 365 days a revenue-supported rate under half of TTM is flagged only; < 30 → STOP, no table; 30d run-rate < 10% of E0 → STOP (paused, option path); 7d run-rate < 50% of E0 → DECAYING flag with a 7d bracket | METHOD + FALLBACK + HEURISTIC (short-history rules, revenue cap, 10% pause and 50% decay thresholds) | A full year smooths seasonality and incentive spikes; a young protocol is valued on its more conservative run-rate, and the two short rules meet at 90 days so E0 doesn't jump; holder flow can't outrun the revenue that funds it, but buybacks can lag revenue by weeks; under 30 days there is nothing to annualise; a stopped cash flow can't be valued as if it were running | $880m core + $194m own-path |
| D20 | E0_other, g_other | collateral × T-bill × capture; grows at the market CAGR per scenario | METHOD | Yield on deposits scales with activity, not with share gains | 10/20/30% |
| D6 | Moat scores | Helmer 7 Powers mean (0–3), Porter 5 Forces mean (0–2), segment-weighted, 2 dp | METHOD; rubric HEURISTIC | Separates durable advantage (Helmer) from competitive pressure (Porter) | 2.47 / 0.48 (rubric on core segment gives 2.43, same band) |
| D7 | ROE band | table in METHOD.md §7.2 | CALIBRATED | Capital-light businesses with real moats sustain very high returns on equity; bands sized against TradFi and DeFi comparables | 35–80% |
| D8 | ROE position | bear = low; base = low + span/3; bull = low + span × (1 − Porter/2); round5; floor Ke_T | HEURISTIC | Base sits in the lower third of the band; bull is pulled down by competitive pressure | 35/50/70% |
| D2 | Market CAGR | trailing/3 over 5/4/3/2 years, round5, ±20%; bull/bear ±10pp; structural decline (latest year < 0, ≥ 25pp worse than all DeFi, below 2y-ago level) → flat 0% ±10pp; young category in decline (latest year < 0 and trailing over < 3 years, or 2y-ago level under half of TTM) → flat 0% ±10pp; basis none → 0% ±10pp, flagged NO MARKET SERIES | CALIBRATED + HEURISTIC (structural and young-category tests) | Trailing growth in young markets doesn't repeat; downturns are cycles handled by D3; only a category-specific collapse confirmed by the bigger picture, or a fall in a category whose history is one boom, goes flat, never negative | trailing 61% → 10/20/30% |
| D3 | Cycle factor | min(1, 0.6522 × record/TTM) from the same series as D2, never supplied; perps fallback basis: 0.6522 with 61% and 7% as a set | CALIBRATED | After a record year the first projected year is assumed ~35% lower, then compounding resumes; one series for D2–D4 so they can't be mixed | 0.6522 |
| D4 | DEX-share lever | perps: today → 10/30/35% | CALIBRATED | On-chain share of perp volume rising from single digits to about a third in the base case | 7% today |
| D5 | Protocol-share lever | ×0.5/1.25/1.5 (strong moat), ×0.5/1.0/1.25 (weaker); cap 95% | CALIBRATED + HEURISTIC | Bear halves share; only a strong moat earns share gains in the base case | 40% → 20/50/60% |
| D1 | g1 | (1+g)^7 = cycle × (1+m)^6 × levers; base/bull round5; bear = bear market CAGR | METHOD + CALIBRATED + HEURISTIC | Growth built from observable levers rather than asserted | raw 39.8/57.1% → 10/40/55% |
| D9 | rf, ERP | US 10y; Damodaran US ERP, sovereign-CDS column | METHOD; column HEURISTIC | Standard market inputs, refreshed every run | 4.56% / 4.70% |
| D10 | Regulatory | no-KYC/unresolved US 2.5/2.0/0.5%; no-KYC/US-facing/settled 1.5/1.0/0.5%; regulated 0.5%; +2pp on formal action | CALIBRATED + METHOD + HEURISTIC | Price of enforcement or forced product withdrawal; the middle class is this skill's interpolation for protocols whose US probes closed without action | 2.5/2.0/0.5% |
| D11 | Governance | 1.25% × drivers/3 + 0.5% without alignment offset | CALIBRATED + HEURISTIC | Concentrated control, rule-changing power and no legal wrapper each add risk | 1.25% |
| D12 | Alignment | mechanical 0%; documented/time-limited 1%; discretionary 2%; option path: the switched-on value uses `routing_on` (default documented 1%) | CALIBRATED + HEURISTIC | The gap between earnings and what holders actually receive; on the option path that gap is priced by the activation probabilities, so it isn't charged twice | 0% |
| D13 | Smart contract | max(0.5%, 2.0% − 1.5% × age/36); exploit ≥ $10m → 2.0% | CALIBRATED + METHOD | Risk falls with each month of exploit-free operation, reaching its floor at three years | 20 months → 1.17% |
| D14 | Emissions | disciplined 60/10/0%, else 100/60/10%; 75% released by year 7 | CALIBRATED + METHOD + HEURISTIC | A self-funding protocol shouldn't need its emission pool; the bear assumes it is spent anyway | 60/10/0% of 389m |
| D15 | Supply basis | S0 incl. vested-unclaimed + committed vesting | METHOD | Every vested token is an economic claim on the cash | 316m + 221.6m |
| D16 | gT | 3.0/3.5/4.5% | CALIBRATED | Long-run nominal growth anchor | PE_T 8.70/9.78/13.35x |
| D17 | Weights | 20/60/20% | JUDGEMENT | Convention; the report shows a weight sensitivity | — |
| D18 | Horizon | 7 years, then steady-state P/E | METHOD | Long enough for levers to play out; short enough to forecast | — |
| D21 | Option activation | paused: 40% within 1y, 20% in 3y; fee switch: 20% within 1y, 20% in 3y; rest never | JUDGEMENT | Placeholders so the option path always runs, labelled as such in the report; the value if switched on today and the market-implied probabilities are the real output | — |
| D23 | Holder rights | benefit form (`buyback_burn`, `buyback_held`, `distribution`, `staking_distribution`) and access (`all_holders`, `stakers_only`, `lockers_only`) from the docs; distributions keep supply unchanged | DOCUMENTED (METHOD) | Says how the benefit reaches holders and what a holder must do to get it; cash payouts don't retire tokens | `buyback_burn`, all holders |
| D22 | Track-record premium | 2.0pp × (90 − days)/60 in near-term Ke for 30–89 days of history; 0 from 90 days; not in Ke_T | HEURISTIC | Prices the risk that a young revenue stream doesn't hold; fades smoothly so there is no jump at 90 days | — (calibration case has a full year) |

## From the source article, and added by this skill

**From the article** (Devloo, Blocmates, 16 July 2026): valuing the cash that reaches holders; the risk-built cost of equity (rf, ERP, regulatory, governance, alignment, smart-contract layers); seven explicit years, then a steady-state P/E derived from ROE, growth and Ke; the three growth levers (market, migration to on-chain, share) with a post-peak cycle reset; the moat-to-ROE bands; dilution and buyback accounting; bear/base/bull at 20/60/20. The calibration case's numbers (61% trailing growth, the 0.6522 reset, 7% → 30% DEX share, 40% share, 35–80% ROE band, 20 months' age) are Hyperliquid's inputs in that article, not rules for other protocols.

**Added by this skill** (HEURISTIC, FALLBACK and JUDGEMENT rows, and reporting rules): the deterministic defaults table and moat rubric; history rules for under a year (early stage, the track-record premium, the revenue check); the structural-decline and young-category tests; the paused-buyback stop and the option path with its D21 placeholder probabilities; the fee-switch base from the revenue stack; holder rights (D23); the EXTREME, DECAYING and other flags; the valuation basis and input-confidence labels; the data pipeline and scripts.

## Calibration case: expected outputs (frozen)

Defaults: g1 10/40/55%, ROE 35/50/70%, reg 2.5/2.0/0.5%, gov 1.25%, align 0%, sc 1.17% → 0.5%, emissions 60/10/0%, gT 3.0/3.5/4.5%, weights 20/60/20%. Price $70.

| Output | Bear | Base | Bull | PW |
|---|---|---|---|---|
| DCF fair value | $20.41 | $100.29 | $278.04 | $119.86 |
| PE_T | 8.70x | 9.78x | 13.35x | 10.28x |
| Ke now / Ke_T | 14.18 / 13.51% | 13.68 / 13.01% | 12.18 / 11.51% | |
| Year-7 earnings ($m) | 2,093 | 9,972 | 20,132 | |
| Terminal supply (m) | 602.1 | 456.2 | 427.0 | |
| P/E method (EPS yr 5) | $25.78 | $106.38 | $250.12 | $119.01 |

Break-even g1 at $70: 31.3%. Earnings yield today 4.9%; PW EPS CAGR 31.6%.

### Sensitivity to modelling choices (one change each)
| Variant | Bear | Base | Bull | PW DCF | P/E method PW | Break-even g1 |
|---|---|---|---|---|---|---|
| Reference | 20.4 | 100.3 | 278.0 | 119.9 | 119.0 | 31.3% |
| Own-path yield grows 35% in every scenario | 28.5 | 108.6 | 283.0 | 127.4 | 126.3 | 28.3% |
| Smart-contract premium decays to floor over 16 months | 21.0 | 103.7 | 288.2 | 124.1 | 119.0 | 30.6% |
| No cycle reset (base g1 55%, bull 75%) | 20.4 | 185.3 | 603.9 | 236.0 | 195.7 | 31.3% |
| Buybacks at fair value instead of a fixed count | 19.2 | 100.3 | 279.4 | 119.9 | 120.8 | 31.4% |

The cycle reset is by far the most consequential single constant: removing it nearly doubles the PW value.

## Known limitations

1. **Bear g1** is set to the bear market CAGR, not the bear lever product (−2.7% on the calibration case). It goes negative only in a structural decline (−10%); a protocol losing share in a growing market still gets a positive bear g1, so override if that is the realistic bear.
2. **ROE position in the band** is fitted to one case. Other rules (e.g. base = low + 15pp) fit equally well.
3. **Moat rubric thresholds** are proxies for qualitative scoring. They reproduce the calibration case's core score exactly but are not validated across protocols. Segment weights are judgement.
4. **Market-CAGR cap (±20%), spread (±10pp) and the structural-decline test (−25pp gap to all DeFi, below the 2-year-ago level, flat base)** are this skill's generalisations. The test is deliberately strict: a category that falls with the market is treated as cyclical, as in the calibration case.
5. **Governance scaling, the no-offset +0.5%, alignment 1%/2%, regulated class 0.5% and the undisciplined emission set** each rest on a single calibration point.
6. **Own-path yield growth** follows the market CAGR; a flat higher rate (35%) is a defensible alternative (see variants).
7. **Segment-level growth** (different g1 per revenue line) is not modelled; g1 is one core rate.
8. **Circulating-supply fallback front-loads dilution.** With S0 = circulating, everything in total supply that is neither circulating nor unissued is treated as committed vesting spread evenly over 7 years. For a protocol whose buyback fund holds repurchased tokens outside circulating supply, that counts retired tokens as future dilution. Prefer a documented vesting schedule; otherwise show the max-supply bracket.
9. **Data that isn't free**: total CEX + DEX perp volume (trailing CAGR and DEX share fall back to mid-2026 values), vesting schedules (circulating fallback), collateral balances (E0_other = 0 if unstated). Flag every fallback in the report.
10. **Pause threshold (10%) and extreme-result thresholds** are judgement: they are set to catch a stopped cash flow and an input error respectively, and both can be overridden with a stated reason.
11. **Early-stage valuations (30–89 days)** rest on the lower of two short run-rates and a 2pp premium that are this skill's judgement, not calibrated. Treat them as provisional and re-run once 90 days exist.
12. **Fee-switch values ignore how users respond** beyond the fee-loss brackets (100/80/60% of fees for LP-fee switches). Staker-only designs are valued per token across all supply, which is the cautious choice.
13. **Short-window E0 is volatile.** Under a year of history, E0 rests on 14-day run-rates of holder and protocol revenue; on a fast-moving young token a single day entering or leaving the window can move them by a fifth. The revenue cap uses the measured holder share unless the documented share is supplied (`--holder-share`). A token whose revenue is still collapsing can come out above its price even on these rules (STONK, October 2026): read the DECAYING flag and the break-even growth, which show the market pricing a continued fall.
14. **Share gain for a share loser.** A protocol in the strong-moat bands gets the ×1.25 base share multiplier even if it lost share over the latest year (PUMP, October 2026: about −20pp, base g1 +5% from the share lever alone). The BORDERLINE adjacent band, or an override of `scenarios.base.g1`, shows the flat-share case.
15. **Policy-share protocols are classed "treasury" by `revenue_stack.py`** when holders get under 80% of protocol revenue by design (PUMP 50% of net revenue, STONK ~60%, PONS 80% of protocol fees). The standard path on holder earnings is still the main valuation there; the fee-switch block is only a what-if. A protocol that routes exactly 80% sits on the threshold.
16. **No forecast-only route.** A protocol with no holder earnings (or under 30 days) is valued only on the option path with a stated condition; otherwise the method reports that it can't establish a value from cash flows. Valuing a business from forecasts alone would need an explicit earnings-path input, which the engine doesn't take.
17. **Input confidence** (LOW/MEDIUM/HIGH) is a reporting rule built from the flags, not a statistical measure.

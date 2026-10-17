# Method (protocol-valuation 6.6.0)

The full specification. `SKILL.md` has the workflow; this file has the reasoning and every rule the scripts apply. Register ids (D1–D20) match the judgement table and `CALIBRATION.md`.

## 1. The model

```
E_t   = Ec0 (1+g1)^t + Eo0 (1+g_other)^t     core growing earnings + own-path earnings, t = 1..N (N = 7)
C_t   = payout × E_t while buybacks/distributions are active, else 0
Ke_t  = rf + ERP + reg + gov + align + sc_t   sc_t = sc_now over the explicit period (default)
Ke_T  = same layers with sc at its floor
PE_T  = (1 − gT/ROE) / (Ke_T − gT)           steady-state P/E, gT per scenario
S_t   = S_{t−1} + vest_t + emissions_t − b_t,   b_t = C_t / P_t   (tokens retired at projected price P_t)
f_t   = f_{t−1} × S_{t−1} / (S_{t−1} + vest_t + emissions_t),  f_0 = 1/S0   (a pro-rata holder's share)
DCF   = Σ_t f_t C_t / Π(1+Ke_u)  +  f_N × PE_T × E_N / Π(1+Ke_u)          method 1, two-stage
M2    = PE_T × EPS_t*   (EPS_t = E_t/S_t; t* = pe_method_year, default 5)  method 2, steady-state P/E
M3    = EPS_t / price for t = 0..N                                         method 3, earnings yield path
PW    = Σ prob_i × DCF_i   (20/60/20)
```

**Why steady-state P/E.** From the dividend discount model, P = payout × EPS / (Ke − g). Growth has to be funded by reinvestment at the return on equity (g = retention × ROE), so in steady state payout = 1 − g/ROE. The multiple therefore follows from three numbers the protocol actually has: how much it earns on capital (ROE), how fast it can keep growing (gT) and how risky its cash is (Ke_T).

**No-moat check.** With ROE = Ke_T, PE_T = 1/Ke_T whatever the growth: growth adds value only while a moat keeps ROE above the cost of capital. If the ROE the band gives is below Ke_T, ROE is set to Ke_T and the table flags NO MOAT. ROE then follows each scenario's Ke, so a riskier bear can show a higher ROE than the base: that is correct (growth adds no value with no moat), not a bug.

**Buyback cash and the shrinking supply are not double-counted.** A holder who takes part pro rata in each buyback receives the buyback cash, f_t × C_t, and keeps the same share. Valuing the cash *and* crediting the holder with the shrunk supply would count the same dollars twice. The engine also prints a non-seller check, `PE_T × E_N / S_N / Π(1+Ke)`, which equals the DCF exactly when buybacks run at fair value.

**Break-even growth** is the core g1 that sets the anchor (base) DCF equal to today's price: the growth the market is pricing in.

## 2. Earnings (E0)

**Clean holder earnings** = gross fees − builder/front-end distributions − incentives and one-offs, excluding supply-side costs (LP or vault revenue that never reaches the token). On DefiLlama this is `dailyHoldersRevenue`. Show the waterfall (fees → revenue → holder revenue): `revenue_stack.py` measures all three series on one calendar window ending on the same day, so the holder share compares like with like, and it adds 30/14/7-day run-rates.

**Earnings are counted once.** E0 is holder revenue: what holders already receive. Don't apply a holder share to it again: `payout` stays 1.0, and the defaults step flags a lower payout unless `payout_reason` says E0 was built from a broader earnings figure. Holder revenue above protocol revenue is funded from outside revenue (reserves, or buybacks catching up) and isn't recurring business earnings: the revenue check counts at most 100% of protocol revenue, and the table flags HOLDER FLOW ABOVE REVENUE.

**Windows (D19).** `engine.py windows summary.json --as-of <as_of>` computes everything from the daily chart, and the defaults step reads its output (`facts.earnings.windows`):
- **Complete UTC days only.** The day containing `as_of` (and anything later) is dropped. Windows are calendar windows ending on the last complete day, missing days count as zero and are reported.
- **Not yet published.** DefiLlama posts each day with a lag. If the source has no row for the last day or two, the windows end on its last row (`windows_end`) instead of counting those days as zero, and the output says so. If the data stops earlier than that, the file is most likely out of date: the windows still end on its last row (zeros would understate earnings) and the output says DATA OUT OF DATE, to get a fresh copy (if the source really has nothing since, revenue may have stopped). A last day below half the previous week's average is flagged LAST DAY LOW: the source may not have finished it.
- **History counts from the first non-zero day.** Zero rows from before a fee switch are not earnings history.
- **E0** = 365-day (TTM) window if history ≥ 365 days. For 90–364 days, the lower of the 90-day and last-14-day run-rates, flagged SHORT HISTORY.
- **Early stage (30–89 days).** E0 = the lower of two annualised run-rates: the average since the first non-zero day and the last 14 days. This catches both a launch spike (since-launch above recent) and a fast ramp that may not hold (recent above since-launch). The two short rules meet at 90 days (the since-launch average is then the 90-day window), so E0 doesn't jump when a token crosses 90 days. A **track-record premium** (D22) is added to the near-term cost of equity: 2.0pp at 30 days, falling linearly to 0 at 90 days, so there is no cliff at 90 there either. It is left out of Ke_T, because the track record exists by the terminal year. Every output carries an EARLY STAGE flag, and a last-14-day rate below half the since-launch rate is flagged LAUNCH DECAY.
- **Revenue check.** Holder flow can't outrun the protocol revenue that funds it, but buybacks can run weeks behind revenue, so after a collapse the holder series can still look healthy (PONS in October 2026: holder revenue 251% of the week's protocol revenue). `revenue_stack.py` writes `earnings.revenue_check`: the 7/14/30-day protocol-revenue run-rates and the holder share (measured on the common window, or the documented share with `--holder-share`). Under a year of history, E0 is capped at the last 14 days of protocol revenue × the holder share (30 days if 14 aren't available), flagged REVENUE CHECK. From a year on, TTM stands (calibrated rule); a revenue-supported run-rate under half of TTM is flagged REVENUE FALLING for the user to judge.
- **Under 30 days: STOP**, and the defaults step writes no table (`earnings.diagnostic: true` produces a table marked DIAGNOSTIC, never a valuation). A couple of weeks can't be annualised meaningfully.
- **Pause check.** A 30-day run-rate below 10% of E0 means holder cash flow has stopped (buybacks or distributions paused): STOP, and value it on the option path (§9). If the zero is a data artefact, `earnings.pause_override_reason` lets it through with a flag.
- **Decay.** A 7-day run-rate below half of E0 is flagged DECAYING, with the 7-day rate as a ready-made bracket (`E0_core`). There is no "lead" figure: the E0 window is fixed by the rules above.

**Split (D20).** E0_core grows with the business at g1. E0_other is own-path yield that grows with the market, not with share gains (e.g. collateral × T-bill × capture rate). If no free source states it, E0_other = 0 and it goes on the gaps list. Check it isn't already inside DefiLlama's holder revenue before adding it.

**Scope.** For LSTs value the governance token. Governance tokens without cash-flow rights go to the option path. Where an equity entity captures part of the value, count only the flows that reach token holders and don't also charge an alignment premium for the same leak (`e0_excludes_company_share`). Launchpads have real fees but memecoin-like flow: expect a weak moat.

## 3. Fee routing and holder rights

Confirm routing from the official docs and quote it (< 15 words, with URL). Routing sets `payout` and the alignment class (D12):

| Routing | Class |
|---|---|
| ~100% of earnings to buybacks/distributions, automatic, no vote | `mechanical` (0%) |
| Documented but changeable by governance | `documented_not_immutable` (1%) |
| Committed for a fixed period | `time_limited` (1%) |
| Discretionary treasury decision | `discretionary` (2%) |
| Fee switch off / buybacks paused | option path (§9) |

**Map where the money goes first** (DOCS-RESEARCH.md §3a): what users pay for, who receives each part (liquidity providers, lenders, builders, the treasury, token holders), what costs and incentives come out, what share reaches holders, and whether that share is automatic, discretionary or only proposed. This is what stops a valuation from using money its holders never receive.

**Holder rights (D23)**, recorded in `facts.rights` from the docs:

| `benefit_form` | What holders get | Supply in the model |
|---|---|---|
| `buyback_burn` | tokens bought and burned | shrinks (buyback mode `fair_value`) |
| `buyback_held` | tokens bought and held by a fund, not resold | shrinks; put the held tokens in a `retired` bucket in the supply schedule |
| `distribution` | cash (or other assets) paid to holders | unchanged (buyback mode `none`) |
| `staking_distribution` | cash paid to stakers | unchanged (buyback mode `none`) |

`access` says what a holder must do to receive it: `all_holders`, `stakers_only` or `lockers_only`. The value per token is the network's holder earnings spread over every token, the right average because any holder can stake; the table flags that an unstaked token receives nothing until it is staked or locked, and that staking can carry lock-ups, unbonding and slashing. Rewards paid in newly issued tokens are dilution (D14), never holder earnings.

## 4. Supply path

**Basis (D15).** Every vested token counts, claimed or not: it is an economic claim on the cash. Use neither circulating nor FDV but total outstanding supply. Committed vesting counts in full on its schedule; authorised-but-unissued tokens enter only through the emission share (D14).

**Build it from the docs**: allocation buckets and vesting terms → `scripts/supply_schedule.py` (DOCS-RESEARCH.md §5).

**Fallback** when no source gives the vesting schedule: S0 = circulating, committed non-circulating = total − circulating − unissued spread evenly over N, `supply_fallback_circulating: true`, plus a bracket run with S0 = max supply.

**Emissions (D14).** The test is accretion: a protocol whose earnings fund its own growth doesn't need to spend its emission pool on incentives. Disciplined (self-sustaining *and* the team is the largest holder): 60/10/0% of the unissued pool included in bear/base/bull; otherwise 100/60/10%. 75% of the included amount is released by year 7.

**Buybacks.** Mode `fair_value` (default): tokens retired at the model's own value path. `fixed_tokens` only when a source states a count. `constant_pe` and `none` are also available. Supply is floored at 5% of S0. `buyback.years` = the documented commitment, fractional allowed (0.54 → 54% of year 1's cash); `continue_after` says whether payouts continue after it (terminal value only if they do). Run a time-limited commitment both ways: with `continue_after: true` the output says COMMITMENT ASSUMED TO CONTINUE and prints the overrides for the committed-only run.

## 5. Defaults step: the judgement table

`engine.py defaults facts.json` → `defaults.py`. Pure function of the facts file; fetches nothing.

### 5.1 Decision table (applied in this order)

| Step | Id | Input | Rule | Class |
|---|---|---|---|---|
| 1 | D19 | E0 | 365d window if history ≥ 365 days; 90–364 days: lower of 90d and 14d run-rates; 30–89 days: early stage, lower of since-launch and 14d run-rates; under 365 days also capped at 14d protocol revenue × holder share (revenue check); < 30 days STOP | METHOD + FALLBACK + HEURISTIC (short-history rules, revenue cap) |
| 2 | D6 | Moat scores | per segment: Helmer = mean of 7 powers (0–3), Porter = mean of 5 forces (0–2); documented scores if available, else rubric (§7.1); blend by segment weight; 2 dp | METHOD; rubric HEURISTIC |
| 3 | D7 | ROE band | first row of §7.2 with Helmer ≥ min and matching Porter class (low if ≤ 1.0) | CALIBRATED |
| 4 | D2 | Market CAGR | base = clamp(round5(trailing/3), −20%, +20%), trailing over the longest of 5/4/3/2 years; bull = base + 10pp; bear = base − 10pp. Downturns go through D3, not here. Structural-decline test (category latest year < 0, ≥ 25pp worse than all DeFi, TTM below two years ago where measurable) → base 0%, flagged for confirmation. Young category in decline (latest year < 0 and trailing measured over < 3 years, or the level two years ago under half today's TTM) → base 0% as well | CALIBRATED + HEURISTIC (structural and young-category tests) |
| 5 | D3 | Cycle factor | min(1, 0.6522 × record 365d level / TTM level), computed from the same series as D2 (never supplied); perps fallback basis: 0.6522 | CALIBRATED |
| 6 | D4 | DEX-share lever (perps fallback basis only) | DEX share of total perp volume: 7% → 10/30/35%; lever = 1 on a category-series basis (migration is already inside on-chain category growth) | CALIBRATED |
| 7 | D5 | Protocol-share lever | share_T = min(95%, share_0 × m); m = 0.5/1.25/1.5 for bands at or above "Helmer 2.0–2.5, low Porter", else 0.5/1.0/1.25 | CALIBRATED + HEURISTIC |
| 8 | D1 | g1 | (1+g)^7 = cycle × (1+mkt)^6 × DEX lever × share lever × take-rate lever (default 1); base and bull = round5(g); bear = round5(bear market CAGR); force bear ≤ base ≤ bull | METHOD + CALIBRATED + HEURISTIC |
| 9 | D20 | g_other | = market CAGR per scenario | METHOD |
| 10 | D9 | rf, ERP | sources in §8, as fractions to 4 dp | METHOD |
| 11 | D10 | Regulatory | `unresolved_us_no_kyc` 2.5/2.0/0.5%; `us_facing_no_kyc_settled` (no KYC, US-facing, past US probes closed without action) 1.5/1.0/0.5%; `regulated_or_kyc` 0.5% flat; +2pp in every scenario if a formal SEC/CFTC/DOJ action names the protocol | CALIBRATED + METHOD + HEURISTIC (other classes) |
| 12 | D11 | Governance | 1.25% × (drivers present)/3 + 0.50% if drivers present and no alignment offset; drivers = concentrated control, team can change rules, no legal wrapper | CALIBRATED + HEURISTIC |
| 13 | D12 | Alignment | routing class (§3) | CALIBRATED + HEURISTIC |
| 14 | D13 | Smart contract | sc_now = max(0.5%, 2.0% − 1.5% × age/36), age in whole months (days/30.4375) **from launch** (first fees day or documented mainnet date, never the first holder-revenue day; a NOTE asks to confirm when they match, an AGE CHECK flag fires when `risk.first_fees_day` is earlier than `launch_date`); exploit ≥ $10m → 2.0%; floor 0.5% for Ke_T; explicit period discounted at constant sc_now | CALIBRATED + METHOD |
| 15 | D8 | ROE | bear = band low; base = low + span/3; bull = low + span × (1 − Porter/2); round5 each; floor at Ke_T | HEURISTIC |
| 16 | D14 | Emissions | §4 | CALIBRATED + HEURISTIC |
| 17 | D15 | Supply basis | §4 | METHOD |
| 18 | D16 | gT | 3.0/3.5/4.5% | CALIBRATED |
| 19 | D17 | Weights | 20/60/20% | JUDGEMENT |
| 20 | D18 | Horizon | 7 years explicit, then steady-state P/E | METHOD |
| 20a | D22 | Track-record premium (early stage only) | 2.0pp × (90 − days)/60, near-term Ke only, 0 from 90 days | HEURISTIC |
| 20b | D23 | Holder rights | benefit form and access from the docs (§3); distributions keep supply unchanged (buyback mode `none`) | DOCUMENTED |
| 21 | D21 | Option activation (option path only, when none supplied) | paused buybacks: resume within 1y 40%, in 3y 20%; fee switch: on within 1y 20%, in 3y 20%; the rest never | JUDGEMENT |

Classes: **METHOD** = a core rule of the method. **CALIBRATED** = a constant fixed on the calibration case. **HEURISTIC** = a generalising rule; reasonable alternatives exist. **FALLBACK** = the data the method wants isn't free; documented substitute. **JUDGEMENT** = a convention, not an estimate.

### 5.2 Rounding and tie-breaks (identical across runs and models)
- `round5` = nearest 5pp, half away from zero (`Decimal`, ROUND_HALF_UP). Ke layers to 0.01pp. Moat scores to 2 dp before the band lookup. Age to whole months.
- Band edges are half-open: [2.0, 2.5) belongs to "2.0–2.5". Within 0.05 of an edge the table flags **BORDERLINE MOAT** and computes the adjacent band across that edge: its ROE (floored at Ke_T) and its g1 (with that band's share-multiplier set), with the overrides that run it as a bracket printed in `judgement.md`. The report shows the adjacent-band run too.
- Category: the child protocol with the largest 30d revenue, alphabetical on ties. Ranks sort by share, then name.
- Scenario order forced: bear ≤ base ≤ bull for g1.
- The same facts file always gives a byte-identical `inputs.json` (sorted keys).

### 5.3 Confirm or override
Show `judgement.md` before valuing. Overrides are dotted paths (`{"scenarios.base.g1": 0.30, "confirmed": true}`), applied with `--overrides`, recorded in `judgement.overrides`. The engine flags `JUDGEMENT TABLE NOT CONFIRMED` until confirmed. Never change a default silently; an override is the user's input and is labelled that way.

## 6. Growth: three levers and a cycle reset

Core earnings grow from three compounding levers: **market growth** (the category's volume or revenue), **migration** (for perps, the on-chain share of all perp volume moving from today's level toward 10/30/35%), and **market share** (the protocol's share of its on-chain category). An optional take-rate lever defaults to 1.

**Market growth (D2).** Trailing growth comes from the category's own daily series (`market_stats.py`): the CAGR of the trailing-365-day level over the longest of 5/4/3/2 years. Base = a third of it, rounded to 5pp and capped at ±20%, because trailing rates in young categories aren't repeatable. Bull and bear are 10 points either side. This is the calibrated scenario structure and is not changed by a bad year.

**Downturns are cycles (D2/D3).** A fall in the category is not extrapolated. It is a drop in level, handled by the cycle reset (D3): if the category is already well off its record, the reset has already happened (factor near 1) and growth resumes from the lower base. In the calibration case perp volume falls ~35% from its record year and the market still grows 20% a year afterwards.

**Bigger picture before calling a decline structural.** One bad year is compared with the rest of the market before anything changes. Three conditions together mark a **possible structural decline**:
1. The category shrank over the latest year.
2. It fell at least 25pp more than DeFi as a whole (`benchmark_yoy`, the all-DeFi revenue change from `category_stats.py --benchmark-out` and `market_stats.py --benchmark`).
3. Its TTM is below its level two years ago, where the history allows (otherwise the table says the 2-year comparison was unavailable).

Then base market growth is set **flat (0%)**, with bull +10% and bear −10%: no boom-era growth, and no extrapolation to zero. The table shows the evidence for the user to confirm or override. If DeFi fell with it, the table says **CYCLICAL DOWNTURN** and the calibrated rule stands. Without a benchmark the calibrated rule stands, with a flag asking for one. Trailing CAGRs measured over fewer than three years are flagged YOUNG CATEGORY.

**Young categories in decline.** The two-year test can't show a structural decline in a category that barely existed two years ago: a memecoin launchpad category that fell 44% last year can still be far above its level two years earlier. Its trailing CAGR is a boom off a small base, so a third of it (capped at +20%) would be the most bullish setting the rule has. So when the category shrank over the latest year *and* is young (trailing growth measured over fewer than three years, or its 365-day level two years ago was under half today's TTM), base market growth is also **flat (0%)**, bull/bear ±10pp, flagged YOUNG CATEGORY IN DECLINE for the user to confirm. A young category that is still growing keeps the calibrated rule.

**Market basis: one rule per number.** `facts.market.basis` decides where D2–D4 come from:
- `category_series`: trailing CAGR, latest-year change, two-year-ago level, record, TTM and the all-DeFi benchmark from `market_stats.py`. The cycle factor is computed from them, and there is no DEX lever.
- `fallback_perps`: trailing 61%, cycle 0.6522 and DEX share 7%, as a set. Total CEX + DEX perp volume isn't free.
- `none`: no category history, so trailing 0 and cycle 1: market growth is a flat default (0%, ±10pp), flagged NO MARKET SERIES so it is never mistaken for a data-driven number.

Supplying a cycle factor or DEX share alongside a category series, or live values on the fallback basis, is refused. This removes the earlier ambiguity where one reading of the docs gave HYPE a live DEX-only cycle factor and another the fallback.

**Cycle reset (D3).** Compounding market growth for all seven years from a record year overstates the path, because a record year is usually followed by a drawdown. The method assumes the first projected year sits at 65.22% of the record trailing-year level and compounds from there for the remaining six years. If the category's latest TTM is already below its record (a market that has already reset), the factor moves toward 1 (capped at 1). Example: perps, record year $92T, next year ~$60T → 0.6522; levers 1.2^6 × 30/7 × 50/40 × 0.6522 = 10.43x over seven years → 39.8%/yr → 40%. Without the reset the same levers give 52.5%.

**Bear case.** Running the bear levers (migration stalls, share halves) can produce a negative CAGR. The method instead sets bear g1 = the bear market CAGR: in the bear case the moat becomes ordinary and the protocol grows with its market, not below it. In a structural decline the bear market CAGR is −10%, so bear g1 is too.

Show the lever arithmetic in the table (the `Source / arithmetic` column does this).

**Growth from a business forecast.** The levers already have the shape of revenue: market activity × the protocol's share × its effective fee rate (the take-rate lever, `take_rate_mult`, default 1). The perps constants are the calibration case's (Hyperliquid's) inputs, not a rule for other businesses. When you or the user can forecast the business from its own drivers, build year-7 holder earnings from them and convert to the engine's single growth rate:

g1 = (year-7 holder earnings / E0)^(1/7) − 1

Enter it as an override (`scenarios.<s>.g1`), labelled MODELLED in the report, with the drivers shown. It needs E0 > 0: a protocol with no holder earnings goes to §9 or can't be valued from cash flows.

| Protocol type | Drivers to forecast |
|---|---|
| Perpetuals exchange | trading volume, market share, fees kept after rebates and builder fees |
| Lending | outstanding borrowing, borrow rates, the protocol's reserve share, credit losses |
| DEX | trading volume, effective fee rate, the protocol's share of fees (LPs keep the rest) |
| Liquid staking | assets staked, staking yield, the protocol's commission |
| Launchpad | fee-generating launches and trading, effective fee rate, user retention |
| Stablecoin / RWA | supply outstanding, reserve yield, the share kept after distribution costs |

## 7. Moat → stabilised ROE

### 7.1 Scoring rubric (HEURISTIC, used only when no documented per-power scores exist)
Helmer's 7 Powers (0–3):
- **Network effects**: 3/2/1/0 at category share ≥ 40/20/10/< 10%.
- **Scale economies**: 3/2/1/0 at TTM holder earnings ≥ $500m/$100m/$20m/less.
- **Counter-positioning**: 2 if the incumbent is custodial (CEX or broker), else 1.
- **Switching costs**: 3 with a bond or lock; 0 if usage is incentive-driven; else 1.
- **Branding**: 3 for category rank 1, 2 for rank 2–3, else 1.
- **Cornered resource**: 3 with a bond lock; 2 with own chain or unique tech; else 1.
- **Process power**: 0 after an exploit ≥ $10m; else 3/2/1 at age ≥ 18/9/< 9 months.

Porter's 5 Forces (0–2, higher = more pressure):
- **Rivalry**: 0/1/2 with 0 / 1–2 / ≥ 3 competitors at ≥ 10% share.
- **New entrants**: 2 if share fell ≥ 10pp (365d → 30d); 1 if it fell ≥ 2pp or a top-3 competitor is under 1 year old; else 0.
- **Supplier power**: 1 with a single third-party dependency.
- **Buyer power**: 2 if incentive-driven.
- **Substitutes**: 1 with an off-chain substitute.

Score each revenue segment separately and blend by weight (earnings share is the natural weight).

### 7.2 Band table (CALIBRATED, capital-light DeFi)
| Helmer | Porter | Stabilised ROE range |
|---|---|---|
| 2.5–3.0 | low (≤ 1.0) | 55–120% |
| 2.5–3.0 | high | 40–80% |
| 2.0–2.5 | low | 35–80% |
| 2.0–2.5 | high | 25–55% |
| 1.5–2.0 | any | 12–25% |
| < 1.5 | any | 8–15% |

Comparables for sense-checking: CME ~18%, Mastercard ~40%, Visa ~48%, Aave ~40%, Lido ~60%, Sky ~80%. DeFi needs little balance sheet, so stabilised ROE can sit above TradFi; it is unadjusted for risk until Ke is applied.

## 8. Cost of equity, layer by layer

| Layer | Rule | Source |
|---|---|---|
| rf | US 10-year Treasury, latest close ≤ as_of | home.treasury.gov daily par yield curve CSV |
| ERP | US equity risk premium, sovereign-CDS column (rating-based column as fallback, flagged) | Damodaran `ctryprem.html` |
| Regulatory | D10 | docs, enforcement news |
| Governance | D11 | docs, validator set, legal structure |
| Alignment | D12 | fee-routing docs |
| Smart contract | D13 | launch date, DefiLlama hacks |

The explicit period is discounted at the near-term Ke (constant `sc_now`, `sc_years: null`); the floor applies only to the terminal multiple. A linear decay is available as an override (`scenarios.<s>.ke.sc_years` = years to the floor). Always report the layer sum.

## 9. Option path: fee switch off, buybacks paused, or "what if the switch turns on"

**What the switched-on earnings are (E0_on).** Never past buybacks alone: use `revenue_stack.py`, which reads fees, protocol revenue and holder revenue together and picks the base by case.

| Case (from `revenue_stack.py`) | E0_on | Notes |
|---|---|---|
| treasury: revenue kept by the protocol, little or none reaching holders (Aave) | (protocol revenue − DAO operating costs − incentives paid out of revenue) × take_rate | take_rate = the share a proposal or the docs would route; 1.0 is the upper bound. Incentives paid in new tokens belong in the supply schedule, not here |
| lp_fees: the protocol keeps < 5% of fees (Uniswap before its switch) | fees × take_rate (the proposal's share of fees) | Run at 100/80/60% of today's fees: charging liquidity providers can push liquidity and volume away |
| paused_buyback (`holder_rev_hist`) | pre-pause holder revenue | Only when holder revenue, not protocol revenue, is what would resume; otherwise use the treasury case |

**Discount rate for the switched-on value.** FV_on is priced at the routing the protocol would have once switched on: `option.routing_on` (default `documented_not_immutable`, 1%, because governance could switch it off again; `mechanical` 0% if the switch is automatic and immutable). The risk that it never switches on, or switches on late, is carried by the activation cases. Charging the switch-off premium as well would price that risk twice. On the calibration inputs, the 3% switch-off premium would cut the switched-on value by about a fifth.

**A stated condition.** A conditional valuation needs an economically plausible mechanism: a governance proposal, a documented programme, a paused buyback that can resume. Name it with its source in `option.condition`. Without one, the output says NO STATED CONDITION and the framework can't establish a value from cash flows: the switched-on value is hypothetical (input confidence LOW).

**What the report leads with.** First the value if switched on today (FV_on, probability-weighted across scenarios), then what the price implies: the activation probability that makes the option worth the price, for each delay (now, 1, 3 and 5 years, plus the delays of the cases; `option.implied_delays` replaces the grid). The activation cases `{label, p, delay_years}` (Σp ≤ 1, the remainder = never) give OV = Σ p × FV_on / (1+Ke)^d as a secondary line. If the facts supply none, the defaults step inserts D21 placeholder cases, labelled as judgement in the report; they come from this skill, not the source article. The EXTREME check runs on the weighted value only when the cases are the user's own. If the price is above the value even with an immediate switch-on, the output says PRICE ABOVE THE SWITCHED-ON VALUE.

The `option` block goes in the facts file (it passes through to `inputs.json`); `base_label` names the base in the report. See `examples/option_example.json`.

## 10. Engine stops

The defaults step and engine raise `STOP:` on: history < 30 days from the first non-zero day (no table), 30–89 days without the since-launch and 14d windows, or 90–364 days without the 90d and 14d windows; holder cash flow paused (30d run-rate < 10% of E0) or routing `paused`/`fee_switch_off` without an option block; a market basis that mixes series; `total1y` raw on short history; short history not annualised; non-ISO `as_of`; E0 ≤ 0 (use §9); ROE ≤ gT; Ke_T ≤ gT; payout outside [0, 1]; probabilities not summing to 1; unknown buyback mode; option inputs missing or invalid. Treat every stop as a finding.

**EXTREME RESULT flag** (not a stop): the weighted value above +150% or below −60% of price (2.5× or 0.4×, symmetric in multiples), break-even g1 above 100% or below −20% (or none), current earnings yield above 25%, or steady-state P/E above 30x. The flag lists what to re-check, naming the likely cause first when the inputs already show it (a DECAYING latest week with the bracket to run, an E0 already capped by the revenue check, a flat default market), then the general list (E0 spikes, units, S0 vs tracker, market basis, shrinking category). Report the result only together with the flag and the re-check outcome.

**Valuation basis and input confidence** (a reporting rule, not an input). Every output states its basis: existing holder earnings (buybacks or distributions operating today) or conditional holder earnings (value if a stated mechanism happens). It also gives an input-confidence level with reasons, because precise numbers are not the same as reliable inputs:
- **LOW:** under a year of holder earnings, earnings decaying, an extreme result, a diagnostic run, or a conditional valuation with no stated condition.
- **MEDIUM:** growth not from live category data (no category series, or the perps constants), a moat score on a band edge, buybacks assumed to outlive their commitment, falling revenue, holder flow above revenue, or supply from the circulating fallback.
- **HIGH:** none of these.

There is no route for forecast-only value: a protocol with under 30 days of holder earnings, or no holder earnings and no stated condition, is reported as not valuable from cash flows with this method.

## 11. Monitors (what would change the answer)
- Emission pool being deployed (D14 set changes).
- Category share falling, or on-chain share of the market falling (D5/D6).
- Formal enforcement action naming the protocol (+2pp regulatory, D10).
- Exploit ≥ $10m (smart-contract premium back to 2%, process power 0).
- Fee routing changed by governance (alignment class, D12).

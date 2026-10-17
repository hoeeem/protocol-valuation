# Facts file schema (protocol-valuation 6.6.0)

`facts.json` is the only input to the defaults step. Units: money in **$ millions**, supplies in **millions of tokens**, rates as **fractions** (0.045 = 4.5%). Every `*source` field should hold the URL and ISO access time (or the doc quote). `examples/calibration_facts.json` is a complete example.

## Top level
| Field | Req. | Meaning |
|---|---|---|
| `protocol` | yes | Display name |
| `as_of` | yes | ISO 8601 timestamp of the price (CoinGecko `last_updated`), e.g. `2026-10-14T09:46:49Z` |
| `price` | yes | Token price, $ |
| `payout` | no | Leave at 1.0: E0 is holder revenue, already what holders receive. Below 1 only if E0 was built from a broader earnings figure (flagged otherwise) |
| `payout_reason` | no | Why `payout` is below 1 (what E0 measures) |
| `take_rate_mult` | no | `{bear, base, bull}` take-rate lever for g1 (default 1) |
| `pe_method_year` | no | EPS year for method 2 (default 5) |
| `sens_g` | no | g1 values for the sensitivity grid rows |
| `price_check` | no | `{alt_price, max_divergence, notes[]}`: second price source; flagged if > 5% apart |
| `is_l1` | no | `true` for a base-layer token |
| `supply_fallback_circulating` | no | `true` if S0 is circulating supply (vesting not available) |
| `e0_excludes_company_share` | no | `true` if an equity entity's cut is already excluded from E0; then give `align_reason` if align > 0 |
| `option` | no | Option-path block (METHOD.md §9), normally written by `scripts/revenue_stack.py`: `type` (`fee_switch` with `fees_ttm` = the base in $m and `take_rate`; or `paused_buyback` with `holder_rev_hist`); `base_label` (what the base is, shown in the report); `routing_on` (routing once switched on: `documented_not_immutable` by default, or `mechanical`, `time_limited`, `discretionary`); `condition` (the mechanism that would switch it on, with its source: without it the output says the value is hypothetical); `activation` optional (D21 placeholders otherwise); `implied_delays` optional (default: now, 1, 3 and 5 years, plus the cases' delays) |
| `rights` | yes on the standard path | Holder rights (D23, METHOD.md §3): `benefit_form` (`buyback_burn`, `buyback_held`, `distribution`, `staking_distribution`), `access` (`all_holders`, `stakers_only`, `lockers_only`), `source`. Sets the default buyback mode (`none` for distributions). Missing → flagged |

## `earnings`
| Field | Req. | Meaning |
|---|---|---|
| `windows` | preferred | The JSON printed by `engine.py windows summary.json --as-of <as_of>` (complete days, history from first non-zero day, pause check) |
| `history_days`, `core_by_window` | else | If you can't run the windows tool: days of holder-earnings history **from the first non-zero day**, and annualised $m windows: `{"365d": x, "30d": z}` from 365 days; `{"90d": y, "14d": w, "30d": z}` for 90–364 days; `{"since_launch": s, "14d": w, "30d": z}` for 30–89 days (early stage). Always include `30d` (pause check), and `7d` when you have it (decay check) |
| `revenue_check` | under 365 days | The `revenue_check` block printed by `scripts/revenue_stack.py`: protocol-revenue run-rates and the holder share. Under a year of history E0 is capped at `revenue_14d` (or `revenue_30d`) × `holder_share`; from a year it only raises a flag. Leave it out and the table says REVENUE CHECK NOT RUN |
| `revenue_7d`, `revenue_14d` | in `revenue_check` | Protocol revenue annualised over the last 7 and 14 complete days, $m (from the daily chart; null from totals) |
| `revenue_30d`, `holder_share` | in `revenue_check` | Protocol revenue annualised over the last 30 days, $m; and the share of protocol revenue that reaches holders (measured on the common window, or documented via `--holder-share`), capped at 100% |
| `holder_share_measured` | in `revenue_check` | The measured share before the cap; above 102% the table flags HOLDER FLOW ABOVE REVENUE. The block also carries `share_basis`, `window_end` and `source` for the report |
| `other` | no | Own-path yield E0_other, $m (default 0) |
| `pause_override_reason` | no | Only if a zero 30d run-rate is a data artefact (e.g. a DefiLlama adapter outage); shown as a flag |
| `diagnostic` | no | `true` to get a DIAGNOSTIC-marked table for a < 30-day token (never a valuation) |
| `source`, `other_source` | | provenance |

## `market`
| Field | Req. | Meaning |
|---|---|---|
| `basis` | yes | `category_series` (paste `market_stats.py` output, which carries it), `fallback_perps` (perps; nothing else allowed in the block except `source`), or `none` (no category history) |
| `trailing_cagr`, `record_365d`, `ttm_365d` | category_series | From `market_stats.py` |
| `yoy` | category_series | Latest 365d vs the 365d before (negative = shrinking) |
| `benchmark_yoy` | category_series (needed if `yoy` < 0) | The same change for all of DeFi (`market_stats.py --benchmark all_defi.json`). Lets the defaults step tell a cycle from a category-specific collapse |
| `level_2y_ago_365d`, `cagr_years` | category_series | From `market_stats.py`: the 365d level two years ago, and the years the trailing CAGR covers (< 3 → YOUNG CATEGORY) |
| `source` | | provenance |

There is no `cycle_factor` or `dex_share_0` field: the cycle factor is always computed (D3), and the DEX lever exists only on the perps fallback basis, where trailing CAGR 61%, cycle 0.6522 and DEX share 7% are fixed together. While on that basis, g1 is the same 10/40/55% for every perps protocol: say so in the report.

## `share`
| Field | Req. | Meaning |
|---|---|---|
| `share_0` | yes | Protocol's share of its on-chain category (`category_stats.py` → `share_30d`, by parent group) |
| `source` | | provenance |

`share_0` cancels out of g1 (only share_T/share_0 enters, unless the 95% cap binds), so an approximate, dated figure is acceptable; feed the same figure to the rubric's `share_30d`, where the 20% and 40% thresholds do matter. `category_stats.py` also gives `rank`, `n_competitors_ge10` and `share_change_pp` for the rubric.

## `moat`
`segments`: list of revenue segments, each:
| Field | Req. | Meaning |
|---|---|---|
| `name`, `weight` | yes | Segment and its weight (earnings share; weights need not sum to 1) |
| `helmer` | either | Documented scores: `{network_effects, scale_economies, counter_positioning, switching_costs, branding, cornered_resource, process_power}` (0–3 each) or a single mean |
| `porter` | either | Documented scores: `{rivalry, new_entrants, supplier_power, buyer_power, substitutes}` (0–2 each) or a single mean |
| `rubric` | else | Inputs for the rubric when `helmer`/`porter` are absent: `share_30d`, `holder_rev_ttm_musd`, `age_months`, `rank`, `n_competitors_ge10`, `share_change_pp` (365d → 30d, in pp, negative = loss), booleans `custodial_incumbent`, `bond_lock`, `incentive_driven`, `own_chain_or_unique_tech`, `major_exploit`, `young_top3_competitor`, `supplier_dependency`, `offchain_substitute` |

Prefer the rubric unless you have a documented, sourced per-power scoring. Scores you make up yourself are judgement: put them in overrides, not in the facts file.

## `risk`
| Field | Req. | Meaning |
|---|---|---|
| `reg_class` | yes | `unresolved_us_no_kyc`, `us_facing_no_kyc_settled` (no KYC, US-facing, past US probes closed without action) or `regulated_or_kyc` |
| `formal_action` | no | `true` if a formal SEC/CFTC/DOJ action names the protocol |
| `concentrated_control`, `team_can_change_rules`, `no_legal_wrapper` | no | Governance drivers |
| `alignment_offset` | no | `true` if mechanical value routing partly offsets governance risk |
| `routing` | yes | `mechanical`, `documented_not_immutable`, `time_limited`, `discretionary`; `paused` or `fee_switch_off` require an `option` block |
| `age_months` or `launch_date` | yes | Protocol age from **launch**: first `dailyFees` day or documented mainnet date, whichever is earlier (`YYYY-MM-DD`). Not the first holder-revenue day (flagged if equal) |
| `first_fees_day` | no | First day of `dailyFees` on DefiLlama; if earlier than `launch_date`, the table flags AGE CHECK |
| `first_holder_revenue_day` | no | Only if you are not passing `earnings.windows` (which carries it): the first non-zero holder-revenue day, used for the launch-date note |
| `major_exploit` | no | `true` if an exploit ≥ $10m |
| `reg_source`, `gov_source`, `align_source`, `age_source` | | provenance |

## `rf`, `erp`
`{"value": 0.0456, "source": "..."}` each.

## `supply`
| Field | Req. | Meaning |
|---|---|---|
| `S0` | yes | Total outstanding incl. vested-unclaimed (m tokens). Build it with `scripts/supply_schedule.py` from the documented allocation (DOCS-RESEARCH.md §5); circulating supply only as the flagged fallback |
| `vest` | no | Committed vesting additions per year `[y1, y2, ...]` (m tokens) |
| `unissued` | no | Authorised but unissued emission pool (m tokens) |
| `self_sustaining`, `team_largest_holder` | no | Emissions-discipline test (both true → disciplined set) |
| `fallback_circulating` | no | `true` if S0 is circulating (shown in the table) |
| `buyback` | no | `{"mode": "fair_value" \| "fixed_tokens" \| "constant_pe" \| "none", "tokens_per_yr": x, "years": n (fractional allowed, e.g. 0.54), "continue_after": bool}` (default `fair_value`) |
| `floor_frac` | no | Supply floor as share of S0 (default 0.05) |
| `source` | | provenance |

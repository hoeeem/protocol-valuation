# Final stress test: protocol-valuation 6.2.1 (2026-10-14), re-run for 6.3.0, 6.4.0, 6.5.0, 6.5.1 and 6.6.0

**Verdict: ready to publish**, with the known limitations below. The stress test found eight problems: one serious maths fault, silent acceptance of bad inputs, and several robustness gaps. All are fixed, each has a regression test, and the calibration case still reproduces exactly.

Rerun everything with `bash tests/run_all.sh /path/to/protocol-valuation` (a few minutes).

## What was tested

| Test | Scope | Result |
|---|---|---|
| Self-test | Calibration case (Hyperliquid, mid-July 2026): judgement inputs and frozen outputs | All checks pass; PW DCF $119.86, break-even 31.3% unchanged since v5 |
| Edge cases | 57 targeted and regression tests (stops, option path, early stage, structural decline, overrides, parsers) | 57/57 |
| Independent maths | DCF, steady-state P/E, Ke build, lever growth, ROE bands, method 2, break-even, option value, early-stage premium and part-year commitments, each re-derived from METHOD.md formulas in separate code | 66/66 match to 1e-9 |
| Fuzzing | 25,000 random facts files across every path (12,000 on the final code) (history length, market basis, buyback mode, routing, option, moat rubric). Invariants: no crashes, deterministic output, bear ≤ base ≤ bull, ROE ≥ Ke_T, weights row = PW, non-seller check = DCF, break-even reprices to market, extreme flag fires exactly at its thresholds, value linear in earnings, monotonic in Ke and growth | 0 failures on the final code (the earlier rounds found problems 1, 3 and 5) |
| Hostile inputs | 51 cases: missing or empty files, bad JSON, text/NaN/infinite numbers, unknown classes, impossible dates, millisecond timestamps, duplicates, nulls, unicode, month-end and leap-day cliffs | 51/51: clean one-line errors or correct results |
| Docs consistency | Every cited file exists; every script listed; versions agree; every register id documented; every facts field read and every read field documented; thresholds in docs = code | 62/62 |
| Workflow | SKILL.md followed literally on the command line: windows → category stats → market stats with benchmark → supply schedule → facts → defaults → rejected typo → confirmed overrides → valuation; plus paused buybacks (stop, then option path), a 50-day token (early stage) and a 20-day token (stop) | All steps OK |
| Python versions | Static check (vermin) and full runs | Minimum 3.7; suites and workflow pass on 3.8, 3.11, 3.12, 3.13 |
| Live run | Hyperliquid at $81.14 (CoinGecko, 2026-10-14T20:37Z), docs-derived supply schedule, perps fallback basis | PW DCF $85.13 (+5%), break-even growth 42.9%; same value as before the fixes |

## Problems found and fixed

| # | Severity | Problem | Fix |
|---|---|---|---|
| 1 | High | **Fair-value buyback solver silently failed to converge** in ~5.5% of runs with time-limited commitments, returning its last guess. Present since v5; only fuzzing exposed it. | Starts from the no-retirement path, damped iteration, convergence verified. Now 99% converge; the rest are valued with cash as a distribution and flagged. |
| 2 | High | **Bad numbers accepted silently**: an infinite price produced a full valuation; a price typed as text passed the defaults step; a launch date after `as_of` gave a negative age (smart-contract premium above 2%); negative token buckets were accepted. | Shared validation (`scripts/common.py`) in every script. |
| 3 | Medium | **5% supply floor in fair-value mode** distorted results: value jumped with growth, and could rise with a higher Ke. | Numerical floor only in fair-value mode (buybacks at the fair price can't over-retire); "deep buyback" flag above 95% retired. |
| 4 | Medium | **Duplicate daily rows double-counted** in the earnings windows; **millisecond timestamps** read as "no data"; null values crashed. | Series normalisation: duplicates once, ms detected, nulls skipped, all reported in `notes`. |
| 5 | Low | **Break-even could land on a jump** in extreme negative-growth regions (one case in ~2,700: value $42.89 vs price $42.97). | BREAK-EVEN APPROXIMATE flag when the result doesn't reprice to market. |
| 6 | Low | **14 crash paths printed raw Python tracebacks** (missing file, missing field, bad override path, missing flag value), and several more gave unhelpful messages. | One-line errors, exit code 2; `PV_DEBUG=1` shows full detail. |
| 7 | Low | Output files used the platform's default encoding (would fail on Windows with arrows and other non-ASCII). | All files written as UTF-8. |
| 8 | Low | Docs drift: new script unlisted, stale version strings, one undocumented optional field. | Fixed; now checked automatically by `tests/docs_consistency.py`. |

## Known limitations (not defects)

- **Under 1% of fair-value runs still don't converge.** These are extreme configurations (a short commitment, no value after it, heavy vesting). They are valued with cash treated as a distribution and flagged. Near such a configuration, a small change in an input can switch between two flagged fallbacks and move the value the "wrong" way (seen once in 18,000 fuzzed cases).
- **Judgement constants are calibrated on one case** (Hyperliquid). The tests prove the scripts apply the rules correctly and consistently. They can't prove the rules are right for every protocol: that's what the confirm/override step is for.
- **Perps growth uses the fixed fallback set** (61% / 0.6522 / 7%) until total CEX + DEX perp volume is freely available.
- **Not run on Windows or macOS directly.** Pure standard-library Python; the encoding risk is fixed.
- **Live DefiLlama raw data couldn't be fetched from the test environment** (summaries only), so the live run used DefiLlama totals. The parsers were tested on synthetic data shaped like DefiLlama's responses and, by an independent tester, on live responses.

## Re-run for 6.3.0 (2026-10-15)

After adding `revenue_stack.py` and the post-switch premium on the option path, the full suite was re-run from a fresh unzip:

| Test | Result |
|---|---|
| Self-test | All checks pass; calibration case unchanged (PW DCF $119.86) |
| Edge cases | 62/62 (5 new: post-switch premium, base label, four revenue cases, reconciliation flags, end-to-end treasury block) |
| Independent maths | 66/66 |
| Hostile inputs | 56/56 (5 new for `revenue_stack.py`) |
| Docs consistency | 62/62 |
| Workflow | All steps OK, including treasury protocol → revenue stack → fee-switch block → valuation |
| Fuzzing | 3,000 cases, 0 failures |
| Python | 3.8 and 3.13 |
| Live | Aave revenue stack from DefiLlama totals: fees $691.1m, protocol revenue $89.5m, holder revenue $18.2m (last 30 days $0); classified "treasury", base = protocol revenue |

## 6.4.0 (2026-10-15): live four-token test, fixes and re-run

A live run on HYPE, PUMP, STONK and PONS found one bug (the DECAYING warning never reached the output), data-timing and labelling problems, defaults that passed without a flag, and earnings rules that lagged a collapse in young tokens. All are fixed (see CHANGELOG.md 6.4.0), each with a regression test. The full suite was re-run from the final code:

| Test | Result |
|---|---|
| Self-test | All checks pass; calibration case unchanged (PW DCF $119.86, break-even 31.3%) |
| Edge cases | 71/71 (9 new: decay end to end, unpublished and low last day, no jump at day 90, revenue check, common-window revenue stack with sharp-fall and lag flags, silent-default flags and runnable adjacent band, young category in decline, chart_from_text, market_stats timing) |
| Independent maths | 72/72 (6 new: short-history and early-stage E0 with the revenue cap, TTM untouched, windows E0 from raw days) |
| Hostile inputs | 66/66 (10 new: chart_from_text, revenue check fields, holder share bounds) |
| Docs consistency | 68/68 (6 new: new scripts' versions, decay ratio identical in both scripts, unpublished-days rule, young-category and revenue-falling thresholds documented) |
| Workflow | All steps OK, now including listed chart → verified chart → identical windows, and revenue stack → revenue check → facts |
| Fuzzing | 18,000 cases on six seeds, 0 failures. One pre-existing case (identical on 6.3.0) showed value falling as growth rose across two different solver fallbacks, both flagged in the output; the monotonicity check now applies only when neither run fell back |
| Python | 3.8 and 3.13: identical outputs |

**Live re-run, same data (prices 15 Oct 07:44 UTC):**

| Token | 6.3.0 | 6.4.0 | Brackets the output now prints |
|---|---|---|---|
| HYPE | $85.13 (+6%) | $85.13 (+6%) | — |
| PUMP | $0.003912 (−9%), no flags | $0.003912 (−9%), 3 flags | adjacent band $0.002845 (−34%); committed only $0.0002281 (−95%) |
| STONK | $0.7584 (+616%) | $0.7584 (+616%), EXTREME names DECAYING | E0 at the 7-day rate: $0.3544 (+235%) |
| PONS | $0.9389 (+204%), EXTREME | $0.3023 (−2%) | E0 capped at what current revenue supports ($29.1m); unchanged when re-run to the last fully published day |

STONK stays far above its price because its revenue was still falling weekly: the method values run-rates with flat growth, and the output says so (DECAYING, break-even growth −45% a year).

## 6.5.0 (2026-10-15): asks first, works from user-supplied data, clean package

The skill now asks which protocol to value and what data the user can send, and reads DefiLlama CSV downloads, saved API files and screenshot figures. The stress-test harness and this report moved out of the skill package into these development files; the runner takes the skill folder as its first argument. Re-run from the final code, against the clean skill folder:

| Test | Result |
|---|---|
| Self-test | All checks pass; calibration case unchanged |
| Edge cases | 73/73 (2 new: a DefiLlama-style CSV with three series and a blank cell gives the same chart as the raw listing; screenshot figures in a totals file) |
| Independent maths | 72/72 |
| Hostile inputs | 71/71 (5 new: CSV without `--column`, unknown column, weekly rows, a bad date, an unverified run that says so) |
| Docs consistency | 68/68, on the clean package |
| Workflow | All steps OK, now including a three-series CSV download → chart → windows identical to the raw file |
| Fuzzing | 3,000 cases, 0 failures |
| Python | 3.8 and 3.13 |

Valuation maths and defaults are unchanged from 6.4.0, so the four-token results stand.

## 6.5.1 (2026-10-15)

The intake now offers free data first (DefiLlama's CSV download is a Pro feature), and data ending more than two days before the valuation date is flagged DATA OUT OF DATE with windows ending on its last day instead of counting zeros. Full suite re-run against the clean skill: self-test pass, edge cases 73/73, independent maths 72/72, hostile inputs 71/71, docs consistency 68/68, workflow OK, fuzzing 0 failures, on Python 3.8 and 3.13.

## 6.6.0 (2026-10-15): basis and confidence labels, conditional reports, earnings counted once, holder rights

The valuation maths is unchanged, so the calibration case and the four live tokens give the same values. New tests cover each change; full suite re-run against the clean skill folder:

| Test | Result |
|---|---|
| Self-test | All checks pass; PW DCF $119.86 unchanged |
| Edge cases | 77/77 (4 new: basis and confidence labels; conditional report order, placeholder cases never EXTREME, missing condition flagged once and LOW, PRICE ABOVE THE SWITCHED-ON VALUE; payout and the 100% holder-share cap; holder rights D23) |
| Independent maths | 72/72 |
| Hostile inputs | 84/84 (13 new: bad `rights` values, types and shapes, payout outside [0, 1] or not a number, a negative measured share, an empty condition run end to end) |
| Docs consistency | 74/74 (4 new: rights values documented, the 102% tolerance, the three confidence levels, the conditional report order) |
| Workflow | All steps OK; now checks the basis and confidence line, and that a conditional run with no condition is LOW |
| Fuzzing | 3,000 cases, 0 failures. New properties: the confidence label is well formed, LOW for an extreme result and for under a year; cash payouts never modelled as buybacks; missing rights, payout below 100% and holder flow above revenue always flagged; on the option path the basis is conditional, a missing condition is LOW, the price-above flag fires exactly when the price exceeds the switched-on value, today is always in the implied grid, and placeholder cases never raise EXTREME |
| Python | 3.8 and 3.13 |

Live tokens on 6.6.0 (same data as 6.4.0): HYPE MEDIUM (perps constants), PUMP MEDIUM (flat default market, band-edge moat, buybacks assumed to continue), STONK LOW (72 days, decaying, extreme result, flat default market), PONS LOW (93 days, flat default market).

Model output under stated assumptions, not financial advice.

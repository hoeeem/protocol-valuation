# Contributing

Thanks for helping. The skill's value is that the same facts always give the same answer, and every number can be traced to a rule or a source. Changes need to keep that true.

## Before you open a pull request

1. **Run the tests:** `bash tests/run_all.sh` must end with `ALL SUITES PASSED`.
2. **Keep the calibration case fixed.** `python3 skills/protocol-valuation/scripts/selftest.py` pins the Hyperliquid case (PW DCF $119.86). If your change moves it, say why in the pull request: that is a change to the method, not a fix.
3. **Add a regression test** in `skills/protocol-valuation/scripts/test_edge_cases.py` for any bug you fix or rule you add, and update the test count in `SKILL.md` (the docs check will remind you).
4. **Document the rule.** A new or changed default needs its row in `reference/METHOD.md` and `reference/CALIBRATION.md` (value, class, rationale, limits), and a `CHANGELOG.md` entry.
5. **No dependencies.** The scripts are standard-library Python 3.8+ so any agent can run them anywhere.

## Versioning

`engine.py` and `defaults.py` carry the version (`__version__`), and the docs and changelog must match it (checked by `tests/docs_consistency.py`). Releases are tagged `v<version>`; pushing the tag builds `protocol-valuation.zip` and attaches it to a GitHub release.

## Reporting a problem with a valuation

Open an issue with the facts file (`facts.json`), the token, the date, and the flag or number you think is wrong. A result you disagree with is not necessarily a bug: check the judgement table and the input-confidence reasons first.

## Style

British spelling, plain words, short sentences. Every flag says what happened and what to do next.

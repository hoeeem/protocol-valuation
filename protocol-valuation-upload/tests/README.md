# Stress tests

These tests check the skill; the skill itself doesn't need them (it carries its own self-test and edge-case tests in `skills/protocol-valuation/scripts/`).

| File | What it checks |
|---|---|
| `independent_maths.py` | Re-derives the DCF, steady-state P/E, cost of equity, growth levers, ROE bands, break-even and option value from the formulas in METHOD.md, in separate code |
| `fuzz.py` | Thousands of random but plausible facts files through the defaults step and the engine; checks invariants (no crashes, deterministic output, bear ≤ base ≤ bull, value linear in earnings, flags fire exactly at their thresholds, confidence labels well formed) |
| `hostile_inputs.py` | Malformed, missing, non-numeric and odd inputs at every command line: clean one-line errors, never a traceback |
| `docs_consistency.py` | Docs match the code: versions, file paths, register ids, facts fields, thresholds, test counts |
| `workflow.sh` | Follows SKILL.md literally on the command line, end to end, including the stop and option paths |
| `run_all.sh` | Runs everything; exits non-zero if any suite fails |

```bash
bash tests/run_all.sh                                   # the skill in this repo
bash tests/run_all.sh path/to/protocol-valuation python3.8 5000   # another copy, another Python, more fuzz cases
```

Standard-library Python 3.8+ only.

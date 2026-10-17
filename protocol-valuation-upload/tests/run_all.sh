#!/usr/bin/env bash
# Full test run of a protocol-valuation skill folder (a few minutes). Exits non-zero if any suite fails.
# Usage: bash tests/run_all.sh [path to the skill folder] [python] [fuzz_cases]
#        (defaults: skills/protocol-valuation, python3, 2000)
T="$(cd "$(dirname "$0")" && pwd)"
SK="$(cd "${1:-$T/../skills/protocol-valuation}" && pwd)"; PY="${2:-python3}"; N="${3:-2000}"
FAILED=0
run() {  # run <label> <command...>: print the command's last line, record a failure
  local label="$1"; shift
  local out; out="$("$@" 2>&1)"; local rc=$?
  printf "%-19s %s\n" "$label" "$(printf '%s\n' "$out" | tail -1)"
  if [ $rc -ne 0 ]; then FAILED=1; printf '%s\n' "$out" | grep -E "^(FAIL|ERROR)" | head -20; fi
}
echo "skill:              $SK ($($PY "$SK/scripts/engine.py" --version))"
run "selftest:"          $PY "$SK/scripts/selftest.py"
run "edge cases:"        $PY "$SK/scripts/test_edge_cases.py"
run "independent maths:" $PY "$T/independent_maths.py" "$SK"
run "hostile inputs:"    $PY "$T/hostile_inputs.py" "$SK"
run "docs consistency:"  $PY "$T/docs_consistency.py" "$SK"
run "workflow:"          bash "$T/workflow.sh" "$SK" "$PY"
echo "fuzz ($N cases):"
FZ="$($PY "$T/fuzz.py" "$SK" "$N" 7)"; rc=$?
printf '%s\n' "$FZ" | sed -n '1p;/FAILURE KINDS/,$p'
[ $rc -ne 0 ] && FAILED=1
echo; [ $FAILED = 0 ] && echo "ALL SUITES PASSED" || echo "SOME SUITES FAILED"
exit $FAILED

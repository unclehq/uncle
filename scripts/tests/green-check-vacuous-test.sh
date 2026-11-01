#!/usr/bin/env bash
# A verification command that ran no tests verifies nothing. The green-check report must say so, by name, instead of
# listing it as PREEXISTING under "No regressions" (issue 117: `unittest discover -p "*-test.py"` ran zero tests on Uncle's
# own repository, every time, because discover cannot import hyphenated module names).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
. "$ROOT/scripts/lib/green-check.sh"

log() { printf '%b' "$1" > "$TMP/log"; }
vacuous() { green_vacuous_commands "$TMP/log"; }

log '\n$ bash scripts/run-shell-tests.sh\nShell suites: 145 passed, 0 failed, 0 skipped.\n\n$ python3 -B -m unittest discover -s scripts/tests -p "*-test.py"\n\n----------------------------------------------------------------------\nRan 0 tests in 0.000s\n\nNO TESTS RAN\n'
check "the command that ran zero tests is named" test "$(vacuous)" == 'python3 -B -m unittest discover -s scripts/tests -p "*-test.py"'
check "the command that ran tests is not" bash -c '[[ "$1" != *run-shell-tests* ]]' _ "$(vacuous)"

log '$ python3 -m unittest\n\nRan 7 tests in 0.2s\n\nOK\n'
check "a run with tests is not vacuous" test -z "$(vacuous)"
log '$ npx pytest\ncollected 0 items\n\n============ no tests ran in 0.01s ============\n'
check "pytest's 'collected 0 items' is vacuous" test "$(vacuous)" == 'npx pytest'
log '$ node --test\nno tests ran\n'
check "'no tests ran' is vacuous" test "$(vacuous)" == 'node --test'
log '$ python3 -m unittest\n\x1b[1mNO TESTS RAN\x1b[0m\n'
check "colour codes around the message do not hide it" test "$(vacuous)" == 'python3 -m unittest'
log '$ echo hi\nthe docs say NO TESTS RAN appears when none are collected\nRan 3 tests in 0.1s\nOK\n'
check "the phrase in the middle of a line is not a verdict" test -z "$(vacuous)"
log '$ a\nRan 0 tests in 0.000s\n$ a\nRan 0 tests in 0.000s\n$ b\nRan 0 tests in 0.0s\n'
check "each vacuous command is listed once" test "$(vacuous | wc -l | tr -d ' ')" == 2
check "a missing log is not an error" bash -c '. "$1/scripts/lib/green-check.sh"; green_vacuous_commands /nonexistent/log; echo ok' _ "$ROOT"

# In the report a human reads at the gate.
printf '5\tpython3 -B -m unittest discover -s scripts/tests -p "*-test.py"\n0\tbash scripts/run-shell-tests.sh\n' > "$TMP/classified.raw"
printf 'PREEXISTING\tpython3 -B -m unittest discover -s scripts/tests -p "*-test.py"\nPASS\tbash scripts/run-shell-tests.sh\n' > "$TMP/classified"
log '\n$ bash scripts/run-shell-tests.sh\nShell suites: 145 passed.\n\n$ python3 -B -m unittest discover -s scripts/tests -p "*-test.py"\nRan 0 tests in 0.000s\n\nNO TESTS RAN\n'
for baseline in 1 0; do
    green_report "$TMP/classified" "$TMP/report.md" ".uncle/docs/PLAN.md" "$TMP/log" "$baseline"
    report="$(cat "$TMP/report.md")"
    check "report (baseline=$baseline) carries the warning" grep -q '^\*\*Ran no tests\.\*\*' "$TMP/report.md"
    check "report (baseline=$baseline) names the command in the warning" grep -q '^- `python3 -B -m unittest discover -s scripts/tests -p "\*-test.py"`$' "$TMP/report.md"
    check "report (baseline=$baseline) does not name a command that ran tests as vacuous" bash -c '! grep -q "^- \`bash scripts/run-shell-tests.sh\`" "$1"' _ "$TMP/report.md"
    check "report (baseline=$baseline) still has its table" grep -q '^| Result | Command |$' "$TMP/report.md"
done
log '\n$ bash scripts/run-shell-tests.sh\nShell suites: 145 passed.\n'
green_report "$TMP/classified" "$TMP/report.md" ".uncle/docs/PLAN.md" "$TMP/log" 1
check "no warning when every command ran tests" bash -c '! grep -q "Ran no tests" "$1"' _ "$TMP/report.md"

[[ "$fails" == 0 ]] && echo "green-check-vacuous-test.sh: all checks passed" || { echo "green-check-vacuous-test.sh: $fails failure(s)"; exit 1; }

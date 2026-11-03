#!/usr/bin/env bash
set -euo pipefail
WORKFLOW_REPAIR=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT

sed -n '/^# A failed assertion can be useful delivery evidence/,/^promote_winner_work() {/p' "$ROOT/scripts/stagegate.sh" \
    | sed '$d' > "$temp/helpers.sh"
STATE_DIR="$temp/state"
LOG_DIR="$temp/logs"
GREEN_MD="$temp/green-check.md"
GREEN_CUR="$temp/green-check.current.tsv"
GREEN_CLASS="$temp/green-check.class.tsv"
GREEN_OVERRIDE_FILE="$STATE_DIR/green-check-override"
mkdir -p "$STATE_DIR/documents" "$STATE_DIR/parallel-implementation-groups" \
    "$STATE_DIR/parallel/notes" "$LOG_DIR" "$temp/.uncle/docs"
cd "$temp"
touch "$GREEN_MD"
set_state() { printf '%s\n' "$1" > "$STATE_DIR/next"; }
# shellcheck disable=SC1090
source "$temp/helpers.sh"

printf '%s\n' 'AssertionError: expected 5 to equal 6' > "$LOG_DIR/green-check.log"
if green_application_not_runnable; then
    echo 'ordinary assertion failure was incorrectly treated as a runtime failure' >&2
    exit 1
fi

printf '%s\n' 'src/App.jsx (2:31): "formatDisplay" is not exported by "src/calc.js"' > "$LOG_DIR/green-check.log"
touch "$STATE_DIR/parallel-implementation-complete" \
      "$STATE_DIR/parallel-implementation-report-complete" \
      "$STATE_DIR/parallel-implementation-serial-fallback" \
      "$STATE_DIR/green-check.fingerprint" \
      "$GREEN_OVERRIDE_FILE" \
      "$STATE_DIR/parallel-implementation-groups/group-1" \
      "$STATE_DIR/parallel/notes/step-1.json" \
      "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json" \
      "$STATE_DIR/documents/AUTOMATED_TEST_REPORT.json"
printf '%s\n' 'old report' > .uncle/docs/IMPLEMENTATION_NOTES.md
printf '%s\n' 'old report' > .uncle/docs/AUTOMATED_TEST_REPORT.md
green_application_not_runnable
UNATTENDED=1
if route_unrunnable_application; then
    echo 'runtime route should request a transition' >&2
    exit 1
else
    [[ "$?" == 2 ]]
fi
# A forced full IMPLEMENT re-entry used to discard every merged worker's
# completion marker here, so IMPLEMENT reran the entire parallel fan-out
# from scratch for what was usually a small, localized fix. REPAIR is the
# bounded path every other green-check failure already uses -- it builds
# on top of the existing merged implementation rather than discarding it,
# so none of that state should be touched.
[[ "$(<"$STATE_DIR/next")" == REPAIR ]] || { echo 'runtime route did not go to the bounded REPAIR path' >&2; exit 1; }
# Deliberately not $GREEN_MD: that source (and TEST_REVIEW.md) makes
# REPAIR's own ineligibility fallback skip straight to FINAL_AUDIT on the
# assumption that test-review/checklist already ran and judged the
# evidence. That assumption is false here -- this fires from inside
# TEST_REVIEW, before any of that pipeline has run even once -- so an
# exhausted repair budget must stop for a person instead (see the static
# check on REPAIR's own source code below), never silently skip the whole
# checklist pipeline with zero evidence the app works at all.
[[ "$(cat "$STATE_DIR/repair-source")" == "$STATE_DIR/runtime-unrunnable-application" ]] \
    || { echo 'runtime repair recorded a source REPAIRs ineligibility fallback treats as already-judged evidence' >&2; exit 1; }
[[ -s "$STATE_DIR/runtime-unrunnable-application" ]] || { echo 'runtime repair lacks a readable failure report' >&2; exit 1; }
grep -q 'green-check.log' "$STATE_DIR/runtime-unrunnable-application" || { echo 'runtime repair lacks execution evidence reference' >&2; exit 1; }
[[ -e "$LOG_DIR/green-check.log" ]] || { echo 'runtime repair discarded green-check evidence' >&2; exit 1; }
for kept in \
    "$STATE_DIR/parallel-implementation-complete" \
    "$STATE_DIR/parallel-implementation-report-complete" \
    "$STATE_DIR/parallel-implementation-serial-fallback" \
    "$STATE_DIR/green-check.fingerprint" \
    "$GREEN_OVERRIDE_FILE" \
    "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json" \
    "$STATE_DIR/documents/AUTOMATED_TEST_REPORT.json" \
    .uncle/docs/IMPLEMENTATION_NOTES.md \
    .uncle/docs/AUTOMATED_TEST_REPORT.md \
    "$STATE_DIR/parallel-implementation-groups/group-1" \
    "$STATE_DIR/parallel/notes/step-1.json"; do
    [[ -e "$kept" ]] || { echo "runtime repair discarded completed implementation state: $kept" >&2; exit 1; }
done

printf '%s\n' 'Error: No test files found' > "$LOG_DIR/green-check.log"
green_application_not_runnable || { echo 'empty test discovery was incorrectly treated as nonblocking' >&2; exit 1; }

# Checklist workers must not run until the implementation green check has
# completed and the runtime route has handled fatal build/module/test-discovery
# failures. Final audit keeps the same guard as a reuse safety net.
validate_review="$(sed -n '/^        VALIDATE_TEST_REVIEW)/,/^        MANUAL_CHECKLIST)/p' "$ROOT/scripts/stagegate.sh")"
[[ "$validate_review" == *'green_wait_final'* ]] || { echo 'missing checklist green-check wait' >&2; exit 1; }
[[ "$validate_review" == *'route_unrunnable_application'* ]] || { echo 'checklist runtime errors were not routed to implementation' >&2; exit 1; }
python3 - "$validate_review" <<'PY'
import sys
block = sys.argv[1]
if block.index('green_wait_final') > block.rindex('route_unrunnable_application'):
    raise SystemExit('runtime route precedes checklist verification')
PY

review="$(sed -n '/^        TEST_REVIEW)/,/^        VALIDATE_TEST_REVIEW)/p' "$ROOT/scripts/stagegate.sh")"
python3 - "$review" <<'PYTEST'
import sys
block = sys.argv[1]
assert block.index('run_green_check_auto') < block.index('green_wait_final'), 'interrupted verification must restart before review waits'
PYTEST

final_audit="$(sed -n '/^        FINAL_AUDIT)/,/^        VALIDATE_AUDIT)/p' "$ROOT/scripts/stagegate.sh")"
[[ "$final_audit" == *'green_wait_final'* ]] || { echo 'final audit lost green-check reuse guard' >&2; exit 1; }

# The repair was spent and the verdict stands. Unattended there is nobody to answer a triage prompt, so the failure is recorded for
# the audit and the run goes on (the checklists look at the application directly); it must not ask for a person, and not twice.
printf '%s\n' 'run-1' > "$STATE_DIR/run-started-at"
record_nonblocking_failure() { printf '%s\n' "$*" >> "$temp/nonblocking"; }
record_test_failure_disposition() { return 0; }
rm -f "$STATE_DIR/next"
route_unrunnable_application || { echo 'a repeated runtime failure must be carried to the audit unattended, not stop the run' >&2; exit 1; }
[[ ! -e "$STATE_DIR/next" ]] || { echo 'carrying the failure to the audit must not change the state' >&2; exit 1; }
[[ "$(wc -l < "$temp/nonblocking" | tr -d ' ')" == 1 ]] || { echo 'the failure must be recorded exactly once' >&2; exit 1; }
route_unrunnable_application || exit 1
[[ "$(wc -l < "$temp/nonblocking" | tr -d ' ')" == 1 ]] || { echo 'a second pass recorded the same failure again' >&2; exit 1; }
UNATTENDED=0
rm -f "$STATE_DIR/runtime-unrunnable-recorded"
if route_unrunnable_application 2> /dev/null; then
    echo 'attended, a persistent runtime failure should still stop for a person' >&2
    exit 1
else
    [[ "$?" == 1 ]]
fi

# The mutation runner's own output says nothing about the application (run 14: two preview servers on one port).
cat > "$LOG_DIR/green-check.log" <<'LOG'
$ npx playwright test --config playwright.config.js
  10 passed (4.2s)

$ node tests/mutations/run.mjs
CONTROL FAIL  npm run build && npx playwright test 'tests/e2e/theme.spec.js'  (0.9s)
[WebServer] error when starting preview server:
[WebServer] Error: Port 4173 is already in use
Error: Process from config.webServer was not able to start. Exit code: 1
LOG
if green_application_not_runnable; then
    echo 'a port collision inside the mutation runner was treated as an unrunnable application' >&2
    exit 1
fi
# The same lines from the application's own e2e command still count.
cat > "$LOG_DIR/green-check.log" <<'LOG'
$ npx playwright test --config playwright.config.js
[WebServer] error when starting preview server:
Error: Process from config.webServer was not able to start. Exit code: 1

$ node tests/mutations/run.mjs
CONTROL OK    npx vitest run 'tests/unit/calc.test.js'  (0.7s)
LOG
green_application_not_runnable || { echo 'a real webServer failure in the e2e command was ignored' >&2; exit 1; }
# A failure after the mutation section belongs to the next command, not to the mutation runner.
cat > "$LOG_DIR/green-check.log" <<'LOG'
$ node tests/mutations/run.mjs
CONTROL OK    x  (0.7s)

$ npx vite build
Build failed with 1 error
LOG
green_application_not_runnable || { echo 'a build failure after the mutation section was ignored' >&2; exit 1; }

# Static check on the real REPAIR state: an unrunnable-application repair
# must be an eligible source (so it gets a real attempt when the budget
# allows), but must NOT appear in the "continuing it to final audit as
# unresolved evidence" fallback's source list -- that shortcut skips
# straight to FINAL_AUDIT/MANUAL_CHECKLIST on the assumption test-review
# already ran, which is never true for this failure.
repair_block="$(sed -n '/^        REPAIR)$/,/^        [A-Z_]*)$/p' "$ROOT/scripts/stagegate.sh")"
[[ "$repair_block" == *'runtime-unrunnable-application'* ]] \
    || { echo 'REPAIR no longer accepts the unrunnable-application source at all' >&2; exit 1; }
python3 - "$repair_block" <<'PY'
import sys
block = sys.argv[1]
start = block.index('WORKFLOW_CONTINUE_ON_TEST_FAILURE')
end = block.index('continuing it to final audit')
fallback_condition = block[start:end]
if 'runtime-unrunnable-application' in fallback_condition:
    raise SystemExit('the unrunnable-application source must not take the skip-to-final-audit shortcut')
PY

echo 'runtime readiness tests passed'

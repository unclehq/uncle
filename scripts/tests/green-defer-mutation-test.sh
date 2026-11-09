#!/usr/bin/env bash
set -uo pipefail

# The defect-injection command runs after the ordinary verification commands have published, so the checklist does not wait for it
# (scripts/lib/background-verify.sh). Hermetic: the project copy, the fingerprint and the test runner are stubbed; the phase
# orchestration, the interim publish, the merge and the two waits are the real code.

REAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILED=0 COUNT=0
ok() { COUNT=$((COUNT + 1)); }
bad() { COUNT=$((COUNT + 1)); FAILED=$((FAILED + 1)); echo "FAIL: $1"; }
expect() { if eval "$2"; then ok; else bad "$1"; fi; }

# A fake driver root: the real libraries the code under test calls, and stubs for the ones that need a real project.
ROOT="$TMP/root"; mkdir -p "$ROOT/scripts/lib"
for f in filter_commands.py; do cp "$REAL_ROOT/scripts/lib/$f" "$ROOT/scripts/lib/"; done
cat > "$ROOT/scripts/lib/isolated_verify.py" <<'PY'
import os, sys
if sys.argv[1] == 'prepare':
    os.makedirs(sys.argv[3], exist_ok=True)
PY
printf 'import sys\n' > "$ROOT/scripts/lib/test_report.py"
printf 'print("fixed-fingerprint")\n' > "$ROOT/scripts/lib/tree_fingerprint.py"
printf 'import sys\n' > "$ROOT/scripts/lib/install_command.py"

PROJECT="$TMP/project"; mkdir -p "$PROJECT/.uncle/docs" "$PROJECT/.uncle/workflow/logs"
cd "$PROJECT"
STATE_DIR="$PWD/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"
GREEN_CMDS="$STATE_DIR/green-check.commands"; GREEN_CUR="$STATE_DIR/green-check.current.tsv"
GREEN_CLASS="$STATE_DIR/green-check.tsv"; GREEN_MD="$STATE_DIR/green-check.md"; GREEN_OVERRIDE_FILE="$STATE_DIR/green.override"
GREEN_CHECK=1; UNATTENDED=1; export ROOT STATE_DIR LOG_DIR
printf 'plan\n' > .uncle/docs/UPDATED_PROJECT_PLAN.md

. "$REAL_ROOT/scripts/lib/green-check.sh"
. "$REAL_ROOT/scripts/lib/background-verify.sh"

# The plan's commands: two ordinary ones, and a defect-injection runner that takes a while.
verify_commands() { printf '%s\n' 'true # build' 'true # unit' 'sleep 3; true # tests/mutations/run.mjs'; }
record_nonblocking_failure() { :; }
record_test_failure_disposition() { :; }
green_report() { { echo '## Green check'; echo; awk -F'\t' '{ printf "| %s | `%s` |\n", $1, $2 }' "$1"; } > "$2"; }
# run_green_check stands in for the real one: it honours GREEN_COMMAND_FILTER and GREEN_LOG like the real one does.
run_green_check() {
    local log="${GREEN_LOG:-$LOG_DIR/green-check.log}" cmd status
    verify_commands > "$GREEN_CMDS"
    [[ -z "${GREEN_COMMAND_FILTER:-}" ]] || python3 -B "$ROOT/scripts/lib/filter_commands.py" "$GREEN_CMDS" "$STATE_DIR/green-check.groups" "$GREEN_COMMAND_FILTER" > /dev/null
    : > "$GREEN_CUR"; : > "$log"
    while IFS= read -r cmd; do
        printf '\n$ %s\n' "$cmd" >> "$log"
        status=0; bash -c "$cmd" >> "$log" 2>&1 || status=$?
        printf '%s\t%s\n' "$status" "$cmd" >> "$GREEN_CUR"
    done < "$GREEN_CMDS"
    green_classify "$STATE_DIR/green-check.no-baseline" "$GREEN_CUR" > "$GREEN_CLASS"
    green_report "$GREEN_CLASS" "$GREEN_MD"
}

printf 'npx vitest run\nnode tests/mutations/run.mjs\n' > "$TMP/both"; printf 'npx vitest run\n' > "$TMP/ordinary"; printf 'node tests/mutations/run.mjs\n' > "$TMP/runner"
expect "a plan with ordinary and defect-injection commands defers the latter" 'green_defer_mutation "$TMP/both"'
expect "a plan with only ordinary commands does not defer" '! green_defer_mutation "$TMP/ordinary"'
expect "a plan with only the runner does not defer" '! green_defer_mutation "$TMP/runner"'
expect "WORKFLOW_DEFER_MUTATION=0 turns it off" '! WORKFLOW_DEFER_MUTATION=0 green_defer_mutation "$TMP/both"'

green_check_background_start > "$TMP/start.out" 2>&1
expect "start announces the deferral" 'grep -q "defect-injection check runs after" "$TMP/start.out"'

# Wait for the interim publish; the runner (3 s) must still be going.
for _ in $(seq 1 60); do [[ -e "$STATE_DIR/green-background.main-done" ]] && break; sleep 0.1; done
expect "the ordinary commands publish before the defect-injection command ends" '[[ -e "$STATE_DIR/green-background.main-done" ]] && green_pending'
expect "the interim record has the ordinary rows" 'grep -q "build" "$GREEN_CLASS" && grep -q "unit" "$GREEN_CLASS"'
expect "the interim record does not yet claim the runner passed" '! grep -q "mutations/run.mjs" "$GREEN_CLASS"'
expect "the interim report says the check is still running" 'grep -q "still running" "$GREEN_MD"'
expect "the checklist gate opens at once" 't0=$SECONDS; green_wait_main; (( SECONDS - t0 <= 1 ))'
expect "the full gate is still closed" 'green_pending && ! [[ ! -e "$STATE_DIR/green-background.pending" ]]'

# The test review and final audit wait for everything.
t0=$SECONDS; green_wait_final > /dev/null 2>&1; waited=$((SECONDS - t0))
expect "the full wait covers the defect-injection command" '(( waited >= 1 ))'
expect "pending is cleared at the end" '[[ ! -e "$STATE_DIR/green-background.pending" && ! -e "$STATE_DIR/green-background.main-done" ]]'
expect "the final record has every command" 'grep -q "build" "$GREEN_CLASS" && grep -q "unit" "$GREEN_CLASS" && grep -q "mutations/run.mjs" "$GREEN_CLASS"'
expect "the final report no longer says the check is running" '! grep -q "still running" "$GREEN_MD"'
expect "both logs end up in one" 'grep -q "# build" "$LOG_DIR/green-check.log" && grep -q "mutations/run.mjs" "$LOG_DIR/green-check.log" && [[ ! -e "$LOG_DIR/green-check.mutation.log" ]]'
expect "the fingerprint is recorded for the full list" '[[ -s "$STATE_DIR/green-check.fingerprint" ]]'

# A failing defect-injection command is a MUTATION row, never a regression.
verify_commands() { printf '%s\n' 'true # build' 'sleep 1; false # tests/mutations/run.mjs'; }
green_check_background_start > /dev/null 2>&1
green_wait_final > /dev/null 2>&1
expect "a failing runner is recorded as MUTATION, not as a regression" 'grep -q "^MUTATION" "$GREEN_CLASS" && [[ "$(green_regressions "$GREEN_CLASS")" == 0 ]]'

# Without deferral the old single combined result is unchanged.
verify_commands() { printf '%s\n' 'true # build' 'sleep 1; true # tests/mutations/run.mjs'; }
WORKFLOW_DEFER_MUTATION=0 green_check_background_start > /dev/null 2>&1
sleep 0.3
expect "without deferral nothing is published early" '[[ ! -e "$STATE_DIR/green-background.main-done" ]]'
green_wait_final > /dev/null 2>&1
expect "without deferral the combined result is complete" 'grep -q "mutations/run.mjs" "$GREEN_CLASS"'

echo "green-defer-mutation-test: $COUNT checks, $FAILED failures"
[[ "$FAILED" == 0 ]]

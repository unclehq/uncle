#!/usr/bin/env bash
# A report gets a fresh runner session after implementation is checkpointed.
# This prevents a runner's per-session iteration cap from discarding completed
# code merely because report reconciliation needs more actions.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
grep -q 'at most 12 tool actions' "$ROOT/scripts/change-workflow.sh"
grep -q 'recover_missing_implementation_reports' "$ROOT/scripts/change-workflow.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"

mkdir -p state .uncle/docs
STATE_DIR="$work/state"
MODEL_IMPLEMENT=fake
BUDGET_IMPLEMENT=1

plan_steps() { printf '%s\n' 'one' 'two'; }
run_supervised_parallel_implementation() { return 2; }
compose_implementation_prompt() { : > "$2"; }
plan_assess() { :; }
check_document_budget() { test -s "$1"; }
require_file() { [[ -s "$1" ]] || { echo "missing: $1" >&2; return 1; }; }
supervision_validation_failed() { :; }
run_claude() {
    local _prompt="$1" stage="$2"
    printf '%s\n' "$stage" >> calls
    case "$stage" in
        implementation-step-1|implementation-step-2)
            local n="${stage##*-}"
            printf '{"schema":"uncle.artifact/v1","kind":"implementation-notes","changed_files":[{"path":"file%s.py"}]}\n' \
                "$n" > "$STATE_DIR/implement-step-$n-notes.json" ;;
        implementation-step-report)
            printf 'reconciled notes\n' > .uncle/docs/IMPLEMENTATION_NOTES.md
            printf 'authoritative report\n' > .uncle/docs/CHANGE_TEST_REPORT.md ;;
        *) exit 99 ;;
    esac
}

eval "$(sed -n '/^run_stepwise_implementation() {/,/^# Count checks as they stream/p' \
    "$ROOT/scripts/change-workflow.sh" | sed '$d')"

run_stepwise_implementation base
expected=$'implementation-step-1\nimplementation-step-2'
[[ "$(cat calls)" == "$expected" ]] || { cat calls >&2; exit 1; }
[[ ! -e "$STATE_DIR/implement-step-done" ]]
[[ ! -e "$STATE_DIR/implement-report-done" ]]

# A single-agent implementation that omitted both reports receives the same
# report-only recovery, without repeating either code step.
rm -f .uncle/docs/IMPLEMENTATION_NOTES.md .uncle/docs/CHANGE_TEST_REPORT.md
: > calls
recover_missing_implementation_reports
[[ "$(cat calls)" == 'implementation-step-report' ]]
[[ -s .uncle/docs/IMPLEMENTATION_NOTES.md ]]
[[ -s .uncle/docs/CHANGE_TEST_REPORT.md ]]

# A report failure is retryable without rerunning either checkpointed code step.
: > calls
printf '2\n' > "$STATE_DIR/implement-step-done"
run_claude() {
    local _prompt="$1" stage="$2"
    printf '%s\n' "$stage" >> calls
    [[ "$stage" == implementation-step-report ]] && return 1
    exit 99
}
set +e
( set -e; run_stepwise_implementation base )
status=$?
set -e
[[ "$status" -ne 0 ]]
[[ "$(cat calls)" == 'implementation-step-report' ]]
[[ "$(cat "$STATE_DIR/implement-step-done")" == 2 ]]

echo 'stepwise-implementation-report-test: code checkpoint and report retry are isolated'

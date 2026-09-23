#!/usr/bin/env bash
set -euo pipefail

# A failed later parallel group must not replay groups the driver has already
# merged.  This is deliberately a direct extraction of the production
# function: marker behavior is a recovery contract, not an implementation
# detail a copied test helper may reinterpret.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
STATE_DIR="$WORK/.uncle/workflow"
LOG_DIR="$STATE_DIR/logs"
mkdir -p "$LOG_DIR" .uncle/docs
touch .uncle/docs/UPDATED_PROJECT_PLAN.md
FUNCTION="$(awk '/^run_parallel_application_implementation\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/stagegate.sh")"
[[ -n "$FUNCTION" ]] || { echo 'FAIL: implementation fan-out function missing' >&2; exit 1; }

parallel_groups() { printf '1\n2\n'; }
uncle_resolve_stage_runner() { :; }
stage_agent_cmd() { printf fake; }
stage_model() { :; }
stage_effort() { printf low; }
stage_tools() { printf Read; }
plan_steps() { printf 'one\ntwo\n'; }
supervision_validation_failed() { :; }
parallel_run_group() {
    local _lib="$1" _logs="$2" _plan="$3" group="$4"
    printf '%s\n' "$group" >> "$WORK/calls"
    if [[ "$group" == 2 && "${FAIL_SECOND:-0}" == 1 ]]; then return 1; fi
    mkdir -p "$STATE_DIR/parallel/notes"
    printf '{"schema":"uncle.artifact/v1","kind":"implementation-notes","changed_files":[{"path":"handoff-%s.py"}]}\n' \
        "$group" > "$STATE_DIR/parallel/notes/step-$group.json"
    printf '{"elapsed_seconds":0}'
}
eval "$FUNCTION"

set +e
FAIL_SECOND=1 run_parallel_application_implementation
status=$?
set -e
[[ "$status" -ne 0 ]] || { echo 'FAIL: injected second-group failure passed' >&2; exit 1; }
[[ -e "$STATE_DIR/parallel-implementation-groups/group-1" ]] || { echo 'FAIL: first group was not checkpointed' >&2; exit 1; }
[[ "$(cat calls)" == $'1\n2' ]] || { echo 'FAIL: unexpected first scheduling' >&2; exit 1; }

: > calls
run_parallel_application_implementation
[[ "$(cat calls)" == 2 ]] || { echo 'FAIL: resume replayed an already merged group' >&2; exit 1; }
[[ -e "$STATE_DIR/parallel-implementation-complete" ]] || { echo 'FAIL: complete marker missing' >&2; exit 1; }
echo 'parallel-implementation-checkpoint-test.sh: resumes at the first unmerged group'

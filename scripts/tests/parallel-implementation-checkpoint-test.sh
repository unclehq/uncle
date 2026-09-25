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
grep -Fq '## Isolated ownership boundary (binding)' "$ROOT/scripts/stagegate.sh" || { echo 'FAIL: isolated workers may scaffold outside ownership' >&2; exit 1; }
grep -Fq 'Do not invoke a framework generator or' "$ROOT/scripts/stagegate.sh" || { echo 'FAIL: scaffold generator ban missing' >&2; exit 1; }
grep -Fq 'Implementation fan-out ownership mismatch; no worker changes were merged.' "$ROOT/scripts/stagegate.sh" || { echo 'FAIL: application fan-out does not fall back after a safe ownership rejection' >&2; exit 1; }
grep -Fq 'Implementation fan-out ownership mismatch; no worker changes were merged.' "$ROOT/scripts/change-workflow.sh" || { echo 'FAIL: change fan-out does not fall back after a safe ownership rejection' >&2; exit 1; }

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

# An ownership violation is distinct from a worker failure: the executor has
# not merged anything, so the application driver must return its normal
# serial-fallback sentinel rather than strand the workflow in IMPLEMENT.
STATE_DIR="$WORK/fallback-state"
LOG_DIR="$STATE_DIR/logs"
mkdir -p "$LOG_DIR" "$STATE_DIR/parallel/prompts" .uncle/docs
parallel_groups() { printf '1 2\n'; }
parallel_run_group() { return 3; }
set +e
run_parallel_application_implementation
status=$?
set -e
[[ "$status" == 2 ]] || { echo "FAIL: ownership rejection returned $status, not serial fallback" >&2; exit 1; }
[[ ! -e "$STATE_DIR/parallel-implementation-complete" ]] || { echo 'FAIL: rejected parallel work was marked complete' >&2; exit 1; }
[[ -e "$STATE_DIR/parallel-implementation-serial-fallback" ]] || { echo 'FAIL: serial fallback was not persisted for resume' >&2; exit 1; }
parallel_run_group() { echo 'FAIL: rejected parallel work was retried' >&2; return 99; }
run_parallel_application_implementation
[[ $? == 2 ]] || { echo 'FAIL: persisted serial fallback was not reused' >&2; exit 1; }
echo 'parallel-implementation-checkpoint-test.sh: resumes at the first unmerged group'

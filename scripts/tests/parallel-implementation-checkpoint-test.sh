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
# uncle consolidation phase (b): the fan-out + merge loop moved into the
# shared parallel_implement_run_groups (scripts/lib/parallel-implement.sh),
# used by both stagegate.sh and change-workflow.sh. The driver-specific
# wrapper (run_parallel_application_implementation) and its prompt/checkpoint
# callbacks still live in stagegate.sh and are extracted the same way as
# before; the shared merge loop is extracted from its own file so this test
# keeps full control of every stub (parallel_groups, parallel_run_group,
# derive_module_interfaces, supervision_validation_failed) without the real
# implementations in parallel-implement.sh overriding them.
FUNCTION="$(awk '/^run_parallel_application_implementation\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/stagegate.sh")"
[[ -n "$FUNCTION" ]] || { echo 'FAIL: implementation fan-out function missing' >&2; exit 1; }
for helper in _stagegate_parallel_build_step_prompt _stagegate_parallel_group_already_merged _stagegate_parallel_mark_group_done; do
    block="$(awk -v fn="$helper() {" '$0 == fn {p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/stagegate.sh")"
    [[ -n "$block" ]] || { echo "FAIL: $helper missing from stagegate.sh" >&2; exit 1; }
    eval "$block"
done
SHARED_FUNCTION="$(awk '/^parallel_implement_run_groups\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/lib/parallel-implement.sh")"
[[ -n "$SHARED_FUNCTION" ]] || { echo 'FAIL: shared parallel_implement_run_groups is missing' >&2; exit 1; }
grep -Fq '## Isolated ownership boundary (binding)' "$ROOT/scripts/stagegate.sh" || { echo 'FAIL: isolated workers may scaffold outside ownership' >&2; exit 1; }
grep -Fq 'Do not invoke a framework generator or' "$ROOT/scripts/stagegate.sh" || { echo 'FAIL: scaffold generator ban missing' >&2; exit 1; }
grep -Fq 'Implementation fan-out ownership mismatch; no worker changes were merged.' "$ROOT/scripts/lib/parallel-implement.sh" || { echo 'FAIL: shared fan-out does not fall back after a safe ownership rejection' >&2; exit 1; }
grep -Fq 'parallel_implement_run_groups' "$ROOT/scripts/stagegate.sh" || { echo 'FAIL: stagegate.sh does not call the shared fan-out function' >&2; exit 1; }
grep -Fq 'parallel_implement_run_groups' "$ROOT/scripts/change-workflow.sh" || { echo 'FAIL: change-workflow.sh does not call the shared fan-out function' >&2; exit 1; }

parallel_groups() { printf '1\n2\n'; }
parallel_prewarm_wait() { :; }
uncle_resolve_stage_runner() { :; }
stage_agent_cmd() { printf fake; }
stage_model() { :; }
stage_effort() { printf low; }
stage_tools() { printf Read; }
plan_steps() { printf 'one\ntwo\n'; }
plan_step_owns() { printf '1\thandoff-1.py\n2\thandoff-2.py\n'; }
supervision_validation_failed() { :; }
require_file() { [[ -s "$1" ]] || { supervision_validation_failed require_file "$1" "missing"; exit 1; }; }
derive_module_interfaces() { return 1; }  # not under test here; an optional, non-fatal extra
parallel_run_group() {
    local _lib="$1" _logs="$2" _plan="$3" group="$4"
    printf '%s\n' "$group" >> "$WORK/calls"
    if [[ "$group" == 2 && "${FAIL_SECOND:-0}" == 1 ]]; then return 1; fi
    mkdir -p "$STATE_DIR/parallel/notes"
    printf '{"schema":"uncle.artifact/v1","kind":"implementation-notes","changed_files":[{"path":"handoff-%s.py"}]}\n' \
        "$group" > "$STATE_DIR/parallel/notes/step-$group.json"
    printf '{"elapsed_seconds":0}'
}
eval "$SHARED_FUNCTION"
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
set +e
run_parallel_application_implementation
status=$?
set -e
[[ "$status" == 2 ]] || { echo 'FAIL: persisted serial fallback was not reused' >&2; exit 1; }
echo 'parallel-implementation-checkpoint-test.sh: resumes at the first unmerged group'

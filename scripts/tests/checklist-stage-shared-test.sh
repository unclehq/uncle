#!/usr/bin/env bash
# uncle consolidation phase (c): scripts/lib/checklist-stage.sh extracts the
# genuinely identical pieces of VALIDATE_MANUAL_CHECKLIST and EXECUTE_CHECKLIST
# that stagegate.sh and change-workflow.sh had each implemented independently.
# This exercises both shared functions directly, with stubs standing in for
# everything each driver would normally provide, so a behavior change in the
# shared code is caught here rather than only by a slower full-driver test.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
STATE_DIR="$WORK/.uncle/workflow"
mkdir -p "$STATE_DIR/documents" .uncle/docs

. "$ROOT/scripts/lib/checklist-stage.sh"

# --- checklist_validate_manual_checklist ------------------------------------

set_state() { printf '%s' "$1" > "$STATE_DIR/state-under-test"; }
supervision_validation_failed() { printf '%s\n' "$*" >> "$STATE_DIR/supervision-calls"; }

checklist_driver_scope_calls=0
_fake_checklist_driver_scope() { checklist_driver_scope_calls=$((checklist_driver_scope_calls + 1)); }

# A first pass: checklist_document.py --validate-json will reject this
# (missing required fields), exercising the one-shot retry path.
printf '{}' > "$STATE_DIR/documents/MANUAL_CHECKLIST.json"

python3() {
    case "$*" in
        *checklist_driver_scope.py*) _fake_checklist_driver_scope; return 0 ;;
        *checklist_document.py\ --validate-json*)
            # First call fails (triggers the retry); a second call (post-retry
            # resume) succeeds, so the test can also exercise the success path.
            if [[ -e "$STATE_DIR/validate-attempted" ]]; then
                return 0
            fi
            : > "$STATE_DIR/validate-attempted"
            echo "missing required field: exact_action" >&2
            return 1
            ;;
        *checklist_document.py\ --render-json*) : > .uncle/docs/MANUAL_CHECKLIST.md; return 0 ;;
        *) command python3 "$@" ;;
    esac
}

status=0
checklist_validate_manual_checklist MANUAL_CHECKLIST 1 "retry message one" || status=$?
[[ "$status" == 2 ]] || { echo "FAIL: first (failing) validation did not signal retry (got $status)" >&2; exit 1; }
[[ "$(cat "$STATE_DIR/state-under-test")" == MANUAL_CHECKLIST ]] || { echo 'FAIL: did not reopen the given generation state' >&2; exit 1; }
[[ -s "$STATE_DIR/manual-checklist-format-retry.md" ]] || { echo 'FAIL: retry marker was not written' >&2; exit 1; }
grep -q 'retry message one' "$STATE_DIR/manual-checklist-format-retry.md" || { echo 'FAIL: retry marker does not carry the caller-supplied message' >&2; exit 1; }
[[ ! -s "$STATE_DIR/documents/MANUAL_CHECKLIST.json" ]] || { echo 'FAIL: clear_worker_json=1 did not clear the stale checklist JSON' >&2; exit 1; }
[[ -s "$STATE_DIR/supervision-calls" ]] || { echo 'FAIL: a validation failure must call supervision_validation_failed' >&2; exit 1; }
[[ "$checklist_driver_scope_calls" -ge 1 ]] || { echo 'FAIL: checklist_driver_scope.py was never invoked' >&2; exit 1; }

# Resume: checklist JSON exists again (as if regenerated) and now validates.
printf '{"checks": []}' > "$STATE_DIR/documents/MANUAL_CHECKLIST.json"
status=0
checklist_validate_manual_checklist MANUAL_CHECKLIST 1 "retry message one" || status=$?
[[ "$status" == 0 ]] || { echo "FAIL: a passing validation must return 0 (got $status)" >&2; exit 1; }
[[ -e .uncle/docs/MANUAL_CHECKLIST.md ]] || { echo 'FAIL: MANUAL_CHECKLIST.md was not rendered on success' >&2; exit 1; }

# clear_worker_json=0 must leave a stale checklist JSON alone (change-workflow.sh's behavior).
rm -f "$STATE_DIR/manual-checklist-format-retry.md" "$STATE_DIR/validate-attempted" "$STATE_DIR/supervision-calls"
printf '{}' > "$STATE_DIR/documents/MANUAL_CHECKLIST.json"
status=0
checklist_validate_manual_checklist CHECKLIST 0 "retry message two" || status=$?
[[ "$status" == 2 ]] || { echo "FAIL: clear_worker_json=0 case did not signal retry (got $status)" >&2; exit 1; }
[[ "$(cat "$STATE_DIR/state-under-test")" == CHECKLIST ]] || { echo 'FAIL: clear_worker_json=0 case reopened the wrong state name' >&2; exit 1; }
[[ -s "$STATE_DIR/documents/MANUAL_CHECKLIST.json" ]] || { echo 'FAIL: clear_worker_json=0 must not clear the stale checklist JSON' >&2; exit 1; }
grep -q 'retry message two' "$STATE_DIR/manual-checklist-format-retry.md" || { echo 'FAIL: second retry marker lost the caller message' >&2; exit 1; }

unset -f python3 set_state supervision_validation_failed

echo 'checklist_validate_manual_checklist: resume, both clear_worker_json modes, and retry-message passthrough all hold'

# --- checklist_execute_worker_fastpath --------------------------------------

STATE_DIR="$WORK/fastpath/.uncle/workflow"
mkdir -p "$STATE_DIR/documents"

fastpath_workers_calls=0
run_parallel_checklist_workers() { fastpath_workers_calls=$((fastpath_workers_calls + 1)); }

python3() {
    case "$*" in
        *checklist_coverage.py*) printf '%s' "${COVERAGE_RESULT:-}"; return 0 ;;
        *execute_checklist_reports.py*) printf '{}' > "$STATE_DIR/documents/EXECUTE_CHECKLIST.json"; return 0 ;;
        *) command python3 "$@" ;;
    esac
}

# No worker packet at all: fast path must not apply (caller falls through to
# its own synthesis call).
rm -f "$STATE_DIR/documents/EXECUTE_CHECKLIST_WORKERS.json"
status=0
checklist_execute_worker_fastpath || status=$?
[[ "$status" == 2 ]] || { echo "FAIL: no worker packet must return 2 (got $status)" >&2; exit 1; }
[[ "$fastpath_workers_calls" == 1 ]] || { echo 'FAIL: run_parallel_checklist_workers was not called' >&2; exit 1; }
[[ ! -s "$STATE_DIR/execute-checklist-uncovered.md" ]] || { echo 'FAIL: no uncovered-checks file should exist with no worker packet' >&2; exit 1; }

# Worker packet exists but leaves checks uncovered: still return 2, with the
# uncovered-checks section written for the caller to append.
printf '{"checks": []}' > "$STATE_DIR/documents/EXECUTE_CHECKLIST_WORKERS.json"
COVERAGE_RESULT='CHK-9: no worker covered this check'
status=0
checklist_execute_worker_fastpath || status=$?
[[ "$status" == 2 ]] || { echo "FAIL: incomplete coverage must return 2 (got $status)" >&2; exit 1; }
[[ -s "$STATE_DIR/execute-checklist-uncovered.md" ]] || { echo 'FAIL: incomplete coverage must write the uncovered-checks file' >&2; exit 1; }
grep -q 'CHK-9' "$STATE_DIR/execute-checklist-uncovered.md" || { echo 'FAIL: uncovered-checks file lost the coverage report text' >&2; exit 1; }

# Full coverage: fast path applies, reports are rendered, no agent call needed.
COVERAGE_RESULT=''
rm -f "$STATE_DIR/documents/EXECUTE_CHECKLIST.json"
status=0
checklist_execute_worker_fastpath || status=$?
[[ "$status" == 0 ]] || { echo "FAIL: full coverage must return 0 (got $status)" >&2; exit 1; }
[[ -s "$STATE_DIR/documents/EXECUTE_CHECKLIST.json" ]] || { echo 'FAIL: full coverage must render the authoritative execute-checklist report' >&2; exit 1; }
[[ ! -s "$STATE_DIR/execute-checklist-uncovered.md" ]] || { echo 'FAIL: full coverage must not leave a stale uncovered-checks file' >&2; exit 1; }

# post_workers_fn, when given, runs after the workers and before the coverage
# check (stagegate.sh stops its app dev-server there).
hook_order=""
_hook() { hook_order="${hook_order}hook,"; }
run_parallel_checklist_workers() { hook_order="${hook_order}workers,"; }
status=0
checklist_execute_worker_fastpath _hook || status=$?
[[ "$hook_order" == "workers,hook," ]] || { echo "FAIL: post_workers_fn did not run immediately after the workers (got '$hook_order')" >&2; exit 1; }

echo 'checklist_execute_worker_fastpath: no-packet, partial-coverage, full-coverage, and post_workers_fn ordering all hold'

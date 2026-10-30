#!/usr/bin/env bash
# Short reviews use one sealed compiler call.  Long hosted reviews use
# bounded, file-backed JSON patch writers with no advisor/reconciler round.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fail=0
check() { local message="$1"; shift; if "$@"; then :; else echo "FAIL: $message"; fail=$((fail + 1)); fi; }

awk '/^run_updated_plan_compact\(\) \{/,/^run_test_review_panel\(\) \{/' "$ROOT/scripts/stagegate.sh" | sed '$d' > "$TMP/function.sh"
check "compact function extracted" grep -q '^run_updated_plan_compact()' "$TMP/function.sh"

mkdir -p "$TMP/.uncle/workflow/documents" "$TMP/.uncle/workflow/logs" "$TMP/.uncle/docs"
python3 - "$TMP" <<'PY'
import json, sys
root = sys.argv[1]
documents = root + '/.uncle/workflow/documents/'
json.dump({'schema':'uncle.artifact/v1', 'kind':'plan', 'narrative':'# Project plan\n\n## 1. Scope\n\nBase.\n',
           'verification_commands':'npm test\n# Frozen verification paths: tests/a.test.js'},
          open(documents + 'PROJECT_PLAN.json', 'w'))
json.dump({'schema':'uncle.artifact/v1', 'kind':'adversarial-review',
           'findings':[{'id':'AR-001', 'severity':'High', 'references':'B-1', 'fix':'Add a test', 'verify':'npm test'}]},
          open(documents + 'ADVERSARIAL_REVIEW.json', 'w'))
PY

(
    cd "$TMP"
    ROOT="$ROOT"; STATE_DIR=.uncle/workflow; LOG_DIR=.uncle/workflow/logs
    ensure_project_plan_json() { :; }
    require_file() { [[ -s "$1" ]]; }
    stage_supports_structured_output() { return 0; }
    run_codex_review() { echo 'unexpected reviewer' >&2; return 99; }
    run_claude() {
        [[ "$2" == updated-plan ]] || return 91
        cat "$1" > "$STATE_DIR/compiler-prompt"
        printf '%s\n' "$PWD/$UNCLE_OUTPUT_SCHEMA_FILE" > "$STATE_DIR/schema-path"
        printf '{"schema":"uncle.artifact/v1","kind":"plan"}\n' > "$UNCLE_STRUCTURED_OUTPUT_PATH"
    }
    . "$TMP/function.sh"
    run_updated_plan_compact
)

check "exactly one compiler call" test -s "$TMP/.uncle/workflow/compiler-prompt"
check "compiler receives no worker packet section" bash -c '! grep -q "Collated specialist corrections" "$1"' _ "$TMP/.uncle/workflow/compiler-prompt"
check "compiler prompt is sealed" grep -q 'sealed synthesis' "$TMP/.uncle/workflow/compiler-prompt"
check "compiler has synthesis schema" test -s "$(cat "$TMP/.uncle/workflow/schema-path")"
check "structured response target selected" test -s "$TMP/.uncle/workflow/artifact-delivery/updated-plan.json"

# A long hosted review uses a few concurrent patch writers.  It must not
# revive the advisory/reconcile committee that made the stage unpredictable.
awk '/^run_updated_plan_adaptive\(\) \{/,/^run_test_review_panel\(\) \{/' "$ROOT/scripts/stagegate.sh" | sed '$d' > "$TMP/adaptive.sh"
python3 - "$TMP/.uncle/workflow/documents/ADVERSARIAL_REVIEW.json" <<'PY'
import json, sys
json.dump({'schema':'uncle.artifact/v1', 'kind':'adversarial-review',
           'findings':[{'id':'AR-%03d' % n} for n in range(1, 10)]}, open(sys.argv[1], 'w'))
PY
(
    cd "$TMP"
    ROOT="$ROOT"; STATE_DIR=.uncle/workflow; LOG_DIR=.uncle/workflow/logs
    ensure_project_plan_json() { :; }
    require_file() { [[ -s "$1" ]]; }
    stage_uses_self_hosted() { return 1; }
    UPDATED_PLAN_ADVISOR_PIDS=()
    run_updated_plan_edit_writers() {
        printf 'slice=%s delivery=%s fast_merge=%s driver_contract=%s warm=%s advisors=%s\n' "${WORKFLOW_UPDATED_PLAN_EDIT_SLICE:-}" "${WORKFLOW_UPDATED_PLAN_WRITER_DELIVERY:-}" "${WORKFLOW_UPDATED_PLAN_FAST_MERGE:-}" "${WORKFLOW_UPDATED_PLAN_DRIVER_CONTRACT:-}" "${WORKFLOW_PREFIX_WARM_SECONDS:-}" "${#UPDATED_PLAN_ADVISOR_PIDS[@]}" > "$STATE_DIR/adaptive"
    }
    run_updated_plan_compact() { echo 'unexpected single compiler' >&2; return 99; }
    . "$TMP/adaptive.sh"
    WORKFLOW_UPDATED_PLAN_PARALLEL_THRESHOLD=5 run_updated_plan_adaptive
)
check "long hosted review uses bounded file-backed deterministic patch batches" grep -qx 'slice=2 delivery=file fast_merge=1 driver_contract=1 warm=0 advisors=0' "$TMP/.uncle/workflow/adaptive"

# Self-hosted long reviews use the same packets with bounded scheduling and
# the conflict resolver retained. One worker restores the compact path.
(
    cd "$TMP"
    ROOT="$ROOT"; STATE_DIR=.uncle/workflow; LOG_DIR=.uncle/workflow/logs
    stage_uses_self_hosted() { return 0; }
    ensure_project_plan_json() { :; }
    require_file() { [[ -s "$1" ]]; }
    run_updated_plan_edit_writers() {
        printf 'jobs=%s merge=%s slice=%s\n' "$(workflow_model_jobs updated-plan)" "$WORKFLOW_UPDATED_PLAN_FAST_MERGE" "$WORKFLOW_UPDATED_PLAN_EDIT_SLICE" > "$STATE_DIR/local-adaptive"
    }
    run_updated_plan_compact() { touch "$STATE_DIR/local-compact"; }
    . "$TMP/adaptive.sh"
    WORKFLOW_SELF_HOSTED_STAGE_JOBS=2 run_updated_plan_adaptive
    WORKFLOW_SELF_HOSTED_STAGE_JOBS=1 run_updated_plan_adaptive
    WORKFLOW_UPDATED_PLAN_PARALLEL_THRESHOLD=99 run_updated_plan_adaptive
    rm -f "$STATE_DIR/local-compact"
    run_updated_plan_edit_writers() { return 9; }
    WORKFLOW_SELF_HOSTED_STAGE_JOBS=2 run_updated_plan_adaptive
    [[ -e "$STATE_DIR/local-compact" ]]
)
check "self-hosted batches retain conflict resolution" grep -qx 'jobs=2 merge=0 slice=2' "$TMP/.uncle/workflow/local-adaptive"
check "one slot or short review keeps compact path" test -e "$TMP/.uncle/workflow/local-compact"

state_block="$(awk '/^        UPDATED_PLAN\)/,/^        IMPLEMENT\)/' "$ROOT/scripts/stagegate.sh")"
check "adaptive path runs before legacy committee" bash -c 'a=$(grep -n "run_updated_plan_adaptive" <<< "$1" | head -1 | cut -d: -f1); b=$(grep -n "run_updated_plan_decide" <<< "$1" | head -1 | cut -d: -f1); [[ -n "$a" && -n "$b" && "$a" -lt "$b" ]]' _ "$state_block"
check "compact failure does not enter committee" bash -c 'a=$(grep -n "run_updated_plan_adaptive" <<< "$1" | head -1 | cut -d: -f1); r=$(grep -n "return \$?" <<< "$1" | head -1 | cut -d: -f1); b=$(grep -n "run_updated_plan_decide" <<< "$1" | head -1 | cut -d: -f1); [[ -n "$a" && -n "$r" && -n "$b" && "$a" -lt "$r" && "$r" -lt "$b" ]]' _ "$state_block"

[[ "$fail" == 0 ]] && echo 'updated-plan-compact-driver-test.sh: all checks passed' || exit 1

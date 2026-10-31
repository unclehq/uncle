#!/usr/bin/env bash
# The CLASSIFY stage library: which runner and model it uses (the supervisor's by default, any runner as a fallback), that a
# model's answer is read whether it arrives as a file or only as the runner's final text, that a failing runner never stops
# the build, and the operator's switches.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
unset UNCLE_STATUS_FILE WORKFLOW_CLASSIFY WORKFLOW_CHANGE_CLASS WORKFLOW_ADVERSARIAL_LENSES WORKFLOW_MODEL_CLASSIFY_CHANGE WORKFLOW_EFFORT_CLASSIFY_CHANGE

. "$ROOT/scripts/lib/stage-config.sh"
export UNCLE_CONFIG="$TMP/config"

# --- which stage's runner/model/effort the classifier uses ----------------------------------------------------------------
bin="$TMP/bin"; mkdir -p "$bin"
for runner in claude codex kimi; do printf '#!/bin/sh\n' > "$bin/$runner"; chmod +x "$bin/$runner"; done
stage_for() { PATH="$1:/usr/bin:/bin" UNCLE_CLASSIFY_FALLBACK_STAGE=change-plan uncle_config_stage classify-change; }
printf 'supervision.runner claude\nsupervision.model claude-sonnet-5-5\nsupervision.effort low\nchange-plan.runner codex\n' > "$UNCLE_CONFIG"
check "the supervisor's settings are the default" test "$(stage_for "$bin")" == supervision
check "the supervisor's model is what the stage reads" test "$(uncle_stage_model supervision)" == claude-sonnet-5-5
check "the supervisor's effort is what the stage reads" test "$(uncle_stage_effort supervision)" == low
printf 'classify-change.runner kimi\nsupervision.model sonnet\n' > "$UNCLE_CONFIG"
check "a classify-change setting wins over the supervisor" test "$(stage_for "$bin")" == classify-change
check "...and routes to that runner" test "$(uncle_stage_runner classify-change)" == kimi
# A Codex-only (or Kimi-only, Cline, self-hosted) machine has no claude: the stage that planned the build is used instead.
printf 'supervision.model sonnet\nchange-plan.runner codex\nchange-plan.model gpt-6\n' > "$UNCLE_CONFIG"
empty="$TMP/empty"; mkdir -p "$empty"
check "no supervisor runner installed falls back to the planning stage" test "$(stage_for "$empty")" == change-plan
check "...whose runner is then used" test "$(uncle_stage_runner change-plan)" == codex
printf 'supervision.runner kimi\nsupervision.model k3\n' > "$UNCLE_CONFIG"
check "a non-claude supervisor runner is honoured when installed" test "$(stage_for "$bin")" == supervision
check "...and used" test "$(uncle_stage_runner supervision)" == kimi

# --- the stage itself, with a stub runner ---------------------------------------------------------------------------------
ROOT_FOR_LIB="$ROOT"
make_project() {
    local p="$TMP/$1"; rm -rf "$p"; mkdir -p "$p/.uncle/docs" "$p/.uncle/workflow/documents" "$p/.uncle/workflow/logs"
    printf '# Change request\n\nFix the greeting text.\n' > "$p/CHANGE_REQUEST.md"
    printf '# Change plan\n\n## Implementation sequence\n\n1. Fix \xe2\x80\x94 Owns: `src/app.py` \xe2\x80\x94 Depends on: 0\n' > "$p/.uncle/docs/CHANGE_PLAN.md"
    printf '{"acceptance_criteria":[{"id":"AC-1"}]}' > "$p/.uncle/workflow/documents/CHANGE_SPEC.json"
    echo "$p"
}
run_stage() {  # <project> <runner-behaviour> -- prints the stage's output; runner behaviours: file | log | garbage | fail | none
    local p="$1" mode="$2"
    (
        cd "$p" || exit 1
        ROOT="$ROOT_FOR_LIB"; STATE_DIR=.uncle/workflow; LOG_DIR=.uncle/workflow/logs; export ROOT STATE_DIR LOG_DIR
        PACKET='{"schema":"uncle.artifact/v1","kind":"change-class","class":"small","adversarial_lenses":["requirements"],"edit_slice":5,"rationale":"one string"}'
        run_claude() {
            printf '%s\n' "$2 model=${WORKFLOW_MODEL_CLASSIFY_CHANGE:-} effort=${WORKFLOW_EFFORT_CLASSIFY_CHANGE:-}" >> .uncle/workflow/runs
            case "$mode" in
                file) printf '%s' "$PACKET" > "$UNCLE_WORKER_PACKET_PATH" ;;
                log)  python3 -c 'import json,sys; print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":sys.argv[1]}}))' "$PACKET" > .uncle/workflow/logs/classify-change.jsonl ;;
                garbage) echo 'I think this is a small change.' > .uncle/workflow/logs/classify-change.jsonl ;;
                fail) return 1 ;;
                crash) exit 7 ;;
            esac
        }
        . "$ROOT/scripts/lib/stage-config.sh"
        . "$ROOT/scripts/lib/change-class-stage.sh"
        classify_change_stage change .uncle/docs/CHANGE_PLAN.md
    ) 2>&1
}
get() { python3 -B "$ROOT/scripts/lib/change_class.py" get "$1" "$2"; }

P="$(make_project file)"; rm -f "$UNCLE_CONFIG"
out="$(run_stage "$P" file)"
check "file delivery: model class is used" test "$(get "$P" source)" == model
check "file delivery: the lens trim is clamped to the floor" test "$(get "$P" lenses)" == "requirements regression testability"
check "file delivery: the slice is kept" test "$(get "$P" edit_slice)" == 4   # bounded by the small class (4)
check "file delivery: the stage announces the class" grep -q '^Build class: small (model)' <<< "$out"
check "the supervisor defaults reach the runner when nothing is configured" grep -q 'classify-change model=sonnet effort=low' "$P/.uncle/workflow/runs"

P="$(make_project log)"
run_stage "$P" log > /dev/null
check "a runner that only prints its answer (no file) still classifies" test "$(get "$P" source)" == model

for mode in garbage fail crash; do
    P="$(make_project "$mode")"
    out="$(run_stage "$P" "$mode")"; rc=$?
    check "$mode: the stage returns and the build goes on" test "$rc" == 0
    check "$mode: the deterministic profile is written" test "$(get "$P" source)" == fallback
    check "$mode: it still has a usable lens list" test -n "$(get "$P" lenses)"
done

P="$(make_project off)"
out="$(WORKFLOW_CLASSIFY=0 run_stage "$P" file)"
check "WORKFLOW_CLASSIFY=0 writes nothing and does not call the runner" test ! -e "$P/.uncle/workflow/change-class.json" -a ! -e "$P/.uncle/workflow/runs"

P="$(make_project forced)"
WORKFLOW_CHANGE_CLASS=large run_stage "$P" file > /dev/null
check "WORKFLOW_CHANGE_CLASS forces a class without calling the runner" test "$(get "$P" class)" == large -a "$(get "$P" source)" == forced -a ! -e "$P/.uncle/workflow/runs"

P="$(make_project again)"
run_stage "$P" file > /dev/null; run_stage "$P" file > /dev/null
check "an unchanged plan is classified once" test "$(wc -l < "$P/.uncle/workflow/runs" | tr -d ' ')" == 1
printf '\n2. Add \xe2\x80\x94 Owns: `src/b.py` \xe2\x80\x94 Depends on: 1\n' >> "$P/.uncle/docs/CHANGE_PLAN.md"
run_stage "$P" file > /dev/null
check "a changed plan is classified again" test "$(wc -l < "$P/.uncle/workflow/runs" | tr -d ' ')" == 2

# --- consumers --------------------------------------------------------------------------------------------------------------
. "$ROOT/scripts/lib/change-class-stage.sh"
P="$(make_project consumers)"; run_stage "$P" file > /dev/null
check "lens list: the classified set" test "$(cd "$P" && change_class_lenses 'a b c')" == "requirements regression testability"
check "lens list: the operator's list wins" test "$(cd "$P" && WORKFLOW_ADVERSARIAL_LENSES='security' change_class_lenses 'a b c')" == security
check "lens list: no classification means the default" test "$(cd "$TMP" && change_class_lenses 'a b c')" == "a b c"
check "edit slice: the classified value" test "$(cd "$P" && change_class_edit_slice 9)" == 4
check "edit slice: an explicit value wins" test "$(cd "$P" && change_class_edit_slice 9 7)" == 7
check "edit slice: no classification means the default" test "$(cd "$TMP" && change_class_edit_slice 9)" == 9

[[ "$fails" == 0 ]] && echo "change-class-stage-test.sh: all checks passed" || { echo "change-class-stage-test.sh: $fails failure(s)"; exit 1; }

#!/usr/bin/env bash
# The CHANGE_PLAN_DUTIES stage: no model for a consistent plan, one targeted patch for an inconsistent one (from a file or only from the
# runner's text), the draft key that keeps PLAN from planning twice, and fail-open on every way the model can let us down.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
unset WORKFLOW_PLAN_DUTIES UNCLE_STATUS_FILE

PLAN=$'# Change plan\n\n## 1. Implementation sequence\n\n1. Style the page \xe2\x80\x94 Owns: `src/styles.css`, `src/App.jsx` \xe2\x80\x94 Depends on: 0\n\n## 2. Notes\n\nThe theme lives in `src/theme.css`; `App.jsx` renders it.\n'
PLAN_NN="${PLAN%$'\n'}"; FIXED_NN="${PLAN_NN//src\/theme.css/src/styles.css}"
GOOD='{"schema":"uncle.artifact/v1","kind":"change-plan-duties","patch":{"replace_text":[{"heading":"## 2. Notes","old":"src/theme.css","new":"src/styles.css"}]}}'

new_project() {  # name [plan]
    local d="$TMP/$1"; rm -rf "$d"; mkdir -p "$d/.uncle/docs" "$d/.uncle/workflow/documents" "$d/.uncle/workflow/logs" "$d/src"
    printf 'x' > "$d/src/styles.css"
    printf '%s' "${2:-$PLAN}" > "$d/.uncle/docs/CHANGE_PLAN.md"
    python3 -c 'import json,sys; print(json.dumps({"schema":"uncle.artifact/v1","kind":"change-plan","narrative":sys.argv[1]}))' "${2:-$PLAN}" > "$d/.uncle/workflow/documents/CHANGE_PLAN.json"
    ( cd "$d" && git init -q )
    echo "$d"
}
# stage <dir> <runner mode> [env...] : run the stage with a stub run_claude; prints its output
stage() {
    local d="$1" mode="$2"; shift 2
    (
        cd "$d" || exit 1
        for assignment in "$@"; do export "$assignment"; done
        ROOT="$ROOT"; STATE_DIR=.uncle/workflow; LOG_DIR=.uncle/workflow/logs; export ROOT STATE_DIR LOG_DIR
        run_claude() {
            printf '%s\n' "$2" >> .uncle/workflow/runs
            case "$mode" in
                file) printf '%s' "$GOOD" > "$UNCLE_WORKER_PACKET_PATH" ;;
                log) python3 -c 'import json,sys; print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":sys.argv[1]}}))' "$GOOD" > .uncle/workflow/logs/change-plan-stage-duties.jsonl ;;
                garbage) echo 'I looked and it seems fine.' > .uncle/workflow/logs/change-plan-stage-duties.jsonl ;;
                badpatch) printf '%s' '{"kind":"change-plan-duties","patch":{"replace_text":[{"heading":"## 9. Nope","old":"a","new":"b"}]}}' > "$UNCLE_WORKER_PACKET_PATH" ;;
                fail) return 1 ;;
                crash) exit 7 ;;
            esac
        }
        change_plan_draft_key() { cksum < .uncle/workflow/documents/CHANGE_PLAN.json | cut -d' ' -f1; }
        . "$ROOT/scripts/lib/change-plan-duties-stage.sh"
        change_plan_duties_stage; echo "rc=$?"
    ) 2>&1
}
plan_text() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["narrative"], end="")' "$1/.uncle/workflow/documents/CHANGE_PLAN.json"; }
record() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["before"], d["after"], str(d["model_called"]).lower())' "$1/.uncle/workflow/change-plan-duties.json"; }

d="$(new_project clean "${PLAN//src\/theme.css/src/styles.css}")"; out="$(stage "$d" file)"
check "a consistent plan makes no model call" test ! -e "$d/.uncle/workflow/runs"
check "...and says so" grep -q 'the plan is consistent' <<< "$out"
check "...and records 0 0 false" test "$(record "$d")" == "0 0 false"

d="$(new_project fixfile)"; echo "before" > /dev/null; ( cd "$d"; echo "99999" > .uncle/workflow/change-plan.draft-key )
out="$(stage "$d" file)"
check "an inconsistency asks the model once, under the stage's own name" test "$(cat "$d/.uncle/workflow/runs")" == change-plan-stage-duties
check "the finding is shown" grep -q 'src/theme.css' <<< "$out"
check "a patch delivered as a file fixes the canonical plan" test "$(plan_text "$d")" == "$FIXED_NN"
check "...and the rendered view" bash -c '! grep -q "theme.css" "$1"' _ "$d/.uncle/docs/CHANGE_PLAN.md"
check "the stage reports it fixed it" grep -q 'fixed; the plan is consistent' <<< "$out"
check "the record says 1 0 true" test "$(record "$d")" == "1 0 true"
check "the draft key follows the patched plan (PLAN must not plan a second time)" test "$(cat "$d/.uncle/workflow/change-plan.draft-key")" == "$(cksum < "$d/.uncle/workflow/documents/CHANGE_PLAN.json" | cut -d' ' -f1)"
check "the stage returns 0" grep -q '^rc=0$' <<< "$out"

d="$(new_project fixlog)"; stage "$d" log > /dev/null
check "a runner that only prints its answer is still applied" test "$(plan_text "$d")" == "$FIXED_NN"

for mode in garbage badpatch fail crash; do
    d="$(new_project "m-$mode")"; out="$(stage "$d" "$mode")"
    check "$mode: the stage still returns 0" grep -q '^rc=0$' <<< "$out"
    check "$mode: the plan is unchanged" test "$(plan_text "$d")" == "$PLAN_NN"
    check "$mode: it says the plan goes to review as it stands" grep -q 'goes to review as it stands' <<< "$out"
    check "$mode: the record keeps the findings" test "$(record "$d")" == "1 1 true"
done

d="$(new_project off)"; out="$(stage "$d" file WORKFLOW_PLAN_DUTIES=0)"
check "WORKFLOW_PLAN_DUTIES=0: no check, no model, plan unchanged" test ! -e "$d/.uncle/workflow/runs" -a "$(plan_text "$d")" == "$PLAN_NN"
check "...and says it is off" grep -q 'are off' <<< "$out"

d="$(new_project noplan)"; rm -f "$d/.uncle/docs/CHANGE_PLAN.md"; out="$(stage "$d" file)"
check "no plan on disk: nothing to do, returns 0" grep -q '^rc=0$' <<< "$out"

[[ "$fails" == 0 ]] && echo "change-plan-duties-stage-test.sh: all checks passed" || { echo "change-plan-duties-stage-test.sh: $fails failure(s)"; exit 1; }

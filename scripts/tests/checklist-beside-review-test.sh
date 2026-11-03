#!/usr/bin/env bash
# The drafted checklist rows run beside the test review, not inside IMPLEMENT. The real functions are used; only the worker pool and the
# app server are stubbed. What matters: it starts only after a clean verification, only once, records what it covered against the
# application as it was when it STARTED (a repair that edits the application afterwards must make the results unreusable), waits for
# the rows before the real stage uses them, and gives up on a run that never ends.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FIXTURE="$REPO/scripts/tests/fixtures/manual-checklist-valid.json"
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

make_project() {   # name tsv-body
    local project="$TMP/$1"
    mkdir -p "$project/src" "$project/.uncle/workflow/logs" "$project/.uncle/workflow/documents"
    printf 'export const a = 1;\n' > "$project/src/app.js"
    printf '{}\n' > "$project/package.json"
    cp "$FIXTURE" "$project/.uncle/workflow/documents/MANUAL_CHECKLIST_DRAFT.json"
    cp "$FIXTURE" "$project/.uncle/workflow/documents/MANUAL_CHECKLIST.json"
    printf 'fp1\n' > "$project/.uncle/workflow/manual-checklist-draft.done"
    printf '%b' "$2" > "$project/.uncle/workflow/green-check.current.tsv"
    printf '%s' "$project"
}

# Runs `body` inside the project with the real early-checklist functions loaded.
in_project() {   # project body
    (
        cd "$1" || exit 1
        ROOT="$REPO"; STATE_DIR="$1/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"
        export STATE_DIR LOG_DIR ROOT
        for fn in early_checklist_enabled early_checklist_execute early_checklist_record early_checklist_beside_review_start \
                  early_checklist_beside_review_finish early_checklist_reuse_prepare early_checklist_changed_start; do
            eval "$(awk -v f="$fn" '$0 == f "() {" {p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/lib/parallel-implement.sh")"
        done
        eval "$(awk '$0 == "checklist_execute_worker_fastpath() {" {p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/lib/checklist-stage.sh")"
        EARLY_CHECKLIST_PID=""; EARLY_CHECKLIST_CHANGED_PID=""
        early_checklist_stop_server() { printf 'stop\n' >> "$STATE_DIR/server-calls"; printf 'stop\n' >> "$STATE_DIR/events"; }
        manual_checklist_draft_fingerprint() { printf 'fp1\n'; }
        run_parallel_checklist_workers() {   # checklist out: every row passes, unless told to hang
            printf 'run\n' >> "$STATE_DIR/runs"
            local kind=other; case "$1" in */early-checklist/checklist.json) kind=early ;; */changed.json) kind=changed ;; */reduced.json) kind=reduced ;; esac
            printf 'start %s %s\n' "$kind" "$(python3 -c 'import json,sys; print(",".join(r["id"] for r in json.load(open(sys.argv[1]))["checks"]))' "$1")" >> "$STATE_DIR/events"
            [[ -z "${HANG:-}" ]] || sleep 30
            [[ "$kind" != early || -z "${EARLY_SECONDS:-}" ]] || sleep "$EARLY_SECONDS"
            [[ "$kind" != changed || -z "${CHANGED_SECONDS:-}" ]] || sleep "$CHANGED_SECONDS"
            python3 - "$1" "$2" <<'PY'
import json, sys
rows = json.load(open(sys.argv[1]))['checks']
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'checklist-execution-worker-packets', 'workers': [{'source': 'w', 'status': 'ok'}],
           'results': [{'id': r['id'], 'status': 'PASS', 'action': 'a', 'expected_result': 'e', 'actual_result': 'ok', 'evidence': 'x'} for r in rows]},
          open(sys.argv[2], 'w'))
PY
            printf 'end %s\n' "$kind" >> "$STATE_DIR/events"
        }
        eval "$2"
    )
}
runs() { [[ -f "$TMP/$1/.uncle/workflow/runs" ]] && wc -l < "$TMP/$1/.uncle/workflow/runs" | tr -d ' ' || echo 0; }
fp_of() { python3 -B "$REPO/scripts/lib/tree_fingerprint.py" --app "$TMP/$1"; }

CLEAN='0\tnpm ls\n0\tnpx vitest run\n0\tnpx playwright test\n125\tnode tests/mutations/run.mjs\n'
# 1. Clean verification (the mutation runner failing does not count): the rows run, and are recorded and reusable.
P="$(make_project clean "$CLEAN")"
in_project "$P" 'early_checklist_beside_review_start; early_checklist_beside_review_finish; early_checklist_reuse_prepare > "$STATE_DIR/reuse.out"; echo $? > "$STATE_DIR/reuse.rc"' > /dev/null 2>&1
check "clean: the rows ran once" test "$(runs clean)" == 1
check "clean: the manifest was recorded" test -s "$P/.uncle/workflow/early-checklist/manifest.json"
check "clean: everything is reusable" test "$(cat "$P/.uncle/workflow/reuse.rc")" == 0
check "clean: and the stage says how many" grep -q "reusing" "$P/.uncle/workflow/reuse.out"

# 2. The application changes after the rows started (a repair): the results are recorded against the old application and not reused.
P="$(make_project repaired "$CLEAN")"
in_project "$P" 'early_checklist_beside_review_start; printf "export const a = 2;\n" > src/app.js; early_checklist_beside_review_finish; early_checklist_reuse_prepare > "$STATE_DIR/reuse.out"; echo $? > "$STATE_DIR/reuse.rc"' > /dev/null 2>&1
check "repaired: the rows still ran" test "$(runs repaired)" == 1
check "repaired: results were recorded" test -s "$P/.uncle/workflow/early-checklist/manifest.json"
check "repaired: nothing is reusable after the application changed" test "$(cat "$P/.uncle/workflow/reuse.rc")" == 3
check "repaired: the recorded fingerprint is the one from the start" bash -c \
    'python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[\"app_fingerprint\"])" "$1" | grep -qx "$2"' _ \
    "$P/.uncle/workflow/early-checklist/manifest.json" "$(cat "$P/.uncle/workflow/early-checklist/start.fingerprint")"
check "repaired: and it is not today's" bash -c '! grep -q "$1" "$2"' _ "$(fp_of repaired)" "$P/.uncle/workflow/early-checklist/manifest.json"

# 3. A failing verification command other than the mutation runner: the rows wait for the real stage.
P="$(make_project failing '0\tnpm ls\n1\tnpx playwright test\n')"
# `finish` waits for anything started, so a run that should not have happened would have been counted.
in_project "$P" 'early_checklist_beside_review_start; early_checklist_beside_review_finish' > /dev/null 2>&1
check "failing verification: the rows did not run" test "$(runs failing)" == 0
check "failing verification: no fingerprint was taken" test ! -e "$P/.uncle/workflow/early-checklist/start.fingerprint"

# 4. Once per run: a second entry (the test review after a repair) does not start another.
P="$(make_project once "$CLEAN")"
in_project "$P" 'early_checklist_beside_review_start; early_checklist_beside_review_finish; early_checklist_beside_review_start; early_checklist_beside_review_finish' > /dev/null 2>&1
check "once: the rows ran a single time" test "$(runs once)" == 1

# 5. The switch.
P="$(make_project off "$CLEAN")"
WORKFLOW_CHECKLIST_BESIDE_REVIEW=0 in_project "$P" 'early_checklist_beside_review_start; early_checklist_beside_review_finish' > /dev/null 2>&1
check "off: the rows did not run" test "$(runs off)" == 0

# 6. A run that never ends is stopped, the app server is stopped, and the manifest is left empty so the real stage runs every row.
P="$(make_project slow "$CLEAN")"
HANG=1 WORKFLOW_EARLY_CHECKLIST_SECONDS=2 in_project "$P" 'early_checklist_beside_review_start; early_checklist_beside_review_finish; early_checklist_reuse_prepare > /dev/null 2>&1; echo $? > "$STATE_DIR/reuse.rc"' > /dev/null 2>&1
check "slow: the app server was stopped" test -s "$P/.uncle/workflow/server-calls"
check "slow: the manifest is empty" test ! -s "$P/.uncle/workflow/early-checklist/manifest.json"
check "slow: nothing is reusable" test "$(cat "$P/.uncle/workflow/reuse.rc")" == 1

# 7. Finishing with nothing started is a no-op.
P="$(make_project none "$CLEAN")"
in_project "$P" 'early_checklist_beside_review_finish; echo ok > "$STATE_DIR/finished"' > /dev/null 2>&1
check "nothing started: finish does nothing and returns" test -s "$P/.uncle/workflow/finished"

# 9. The rows the reconciliation changed start at once, beside the early rows still running, and are not run twice (run 27: a reworded
#    row waited 45 s for the early rows and then ran for 99 s, the two added together).
reword() { python3 - "$1/.uncle/workflow/documents/MANUAL_CHECKLIST.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d['checks'][0]['exact_action'] = 'reworded by the reconciliation'
json.dump(d, open(sys.argv[1], 'w'))
PY
}
events() { tr '\n' '|' < "$TMP/$1/.uncle/workflow/events"; }
FIRST_ID="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['checks'][0]['id'])" "$FIXTURE")"
ROWS="$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))['checks']))" "$FIXTURE")"
P="$(make_project changedfirst "$CLEAN")"; reword "$P"
# The early rows run in the background; the real stage begins while they are still going (a second in, the draft copy exists).
EARLY_SECONDS=3 CHANGED_SECONDS=4 in_project "$P" 'early_checklist_beside_review_start; sleep 1; checklist_execute_worker_fastpath; echo done > "$STATE_DIR/fastpath.done"' > /dev/null 2>&1
EV="$(events changedfirst)"
check "changed first: the early rows started" bash -c 'grep -q "^start early|\|start early " <<< "$1"' _ "$EV"
check "changed first: the changed row started before the early rows ended" bash -c '[[ "$1" =~ start\ early.*start\ changed.*end\ early ]]' _ "$EV"
check "changed first: only the changed row was run for it" bash -c '[[ "$1" == *"start changed $2|"* ]]' _ "$EV" "$FIRST_ID"
check "changed first: that row was not run a second time" bash -c '[[ "$(grep -c "start reduced" "$1/.uncle/workflow/events")" == 0 ]]' _ "$P"
check "changed first: the document holds every row" bash -c 'python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if len(d[\"results\"])==int(sys.argv[2]) else 1)" "$1/.uncle/workflow/documents/EXECUTE_CHECKLIST_WORKERS.json" "$2"' _ "$P" "$ROWS"
check "changed first: the changed row's result is the fresh one" bash -c 'python3 -c "import json,sys; d={r[\"id\"]:r for r in json.load(open(sys.argv[1]))[\"results\"]}; sys.exit(0 if d[sys.argv[2]].get(\"source\")!=\"early-checklist\" else 1)" "$1/.uncle/workflow/documents/EXECUTE_CHECKLIST_WORKERS.json" "$2"' _ "$P" "$FIRST_ID"
check "changed first: the others were reused from the early rows" bash -c 'python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if sum(1 for r in d[\"results\"] if r.get(\"source\")==\"early-checklist\")==int(sys.argv[2])-1 else 1)" "$1/.uncle/workflow/documents/EXECUTE_CHECKLIST_WORKERS.json" "$2"' _ "$P" "$ROWS"
check "changed first: the server was stopped" bash -c '[[ "$1" == *stop* ]]' _ "$EV"
check "changed first: and not until both runs had ended (the changed run outlasts the early one here)" bash -c 'p="${1%%stop*}"; [[ "$p" == *"end early"* && "$p" == *"end changed"* ]]' _ "$EV"

# The switch: off, the changed row runs after the early rows (through the ordinary reduced list).
P="$(make_project changedoff "$CLEAN")"; reword "$P"
WORKFLOW_CHECKLIST_CHANGED_FIRST=0 EARLY_SECONDS=4 in_project "$P" 'early_checklist_beside_review_start; sleep 1; checklist_execute_worker_fastpath' > /dev/null 2>&1
EV="$(events changedoff)"
check "changed first off: no changed run" bash -c '[[ "$1" != *"start changed"* ]]' _ "$EV"
check "changed first off: the row ran after the early rows ended" bash -c '[[ "$1" =~ end\ early.*start\ reduced ]]' _ "$EV"

# Nothing changed: no changed run, and nothing fresh at all.
P="$(make_project nochange "$CLEAN")"
EARLY_SECONDS=2 in_project "$P" 'early_checklist_beside_review_start; checklist_execute_worker_fastpath' > /dev/null 2>&1
EV="$(events nochange)"
check "nothing changed: no changed run" bash -c '[[ "$1" != *"start changed"* ]]' _ "$EV"
check "nothing changed: no row was run after the early rows" bash -c '[[ "$1" != *"start reduced"* ]]' _ "$EV"

# Early rows already over when the stage starts: nothing to overlap, the ordinary path.
P="$(make_project early_done "$CLEAN")"; reword "$P"
in_project "$P" 'early_checklist_beside_review_start; early_checklist_beside_review_finish; checklist_execute_worker_fastpath' > /dev/null 2>&1
EV="$(events early_done)"
check "early rows already finished: no changed run" bash -c '[[ "$1" != *"start changed"* ]]' _ "$EV"
check "early rows already finished: the changed row ran through the reduced list" bash -c '[[ "$1" == *"start reduced"* ]]' _ "$EV"

# 8. The stage calls both ends.
check "TEST_REVIEW starts the rows before the review runs" python3 - "$REPO/scripts/stagegate.sh" <<'PY'
import sys
t = open(sys.argv[1]).read()
a = t.index('early_checklist_beside_review_start; fi')
assert a < t.index('run_stage TEST_REVIEW', a) and t.index('run_stage TEST_REVIEW', a) - a < 200
PY
check "the real checklist stage waits for them before reusing" grep -q "early_checklist_beside_review_finish" "$REPO/scripts/lib/checklist-stage.sh"

if [[ "$fails" -ne 0 ]]; then echo "checklist-beside-review-test.sh: $fails failed"; exit 1; fi
echo "checklist-beside-review-test.sh: all checks passed"

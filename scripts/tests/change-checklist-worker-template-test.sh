#!/usr/bin/env bash
set -uo pipefail
# Every checklist worker has to be told where the application is running and which file holds the rows. The change workflow had its own
# copy of run_parallel_checklist_workers that handed the lane runner the bare worker prompt, so each worker was named an id and nothing
# else: all nine required rows came back BLOCKED-SETUP ("gives no checklist JSON path and no application URL") in twelve seconds, and a
# change request was audited without anything having been run (found changing a calculator's background). Both drivers now share
# checklist_bind_worker_template. The real helper and the change workflow's real function run, with a stub application server.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

# A scratch ROOT: the real prompts, and an app_server.py that answers like the real one (a URL, or nothing).
mkdir -p "$TMP/root/scripts/lib" "$TMP/root/prompts/change" "$TMP/state/documents" "$TMP/proj"
cp "$REPO/prompts/change/execute-checklist-worker.md" "$TMP/root/prompts/change/"
cat > "$TMP/root/scripts/lib/app_server.py" <<'PY'
import os, sys
if sys.argv[1:2] == ['start']:
    with open(os.environ['STUB_LOG'], 'a') as log:
        log.write('start %s\n' % ' '.join(sys.argv[2:]))
    if os.environ.get('STUB_SERVER') == 'down':
        sys.exit(1)
    print('http://127.0.0.1:5199/')
elif sys.argv[1:2] == ['stop']:
    with open(os.environ['STUB_LOG'], 'a') as log:
        log.write('stop %s\n' % ' '.join(sys.argv[2:]))
PY
export STUB_LOG="$TMP/server.log"

in_project() {   # body... runs with the helper loaded, in the project directory
    ( cd "$TMP/proj" && ROOT="$TMP/root" STATE_DIR="$TMP/state" bash -c ". '$REPO/scripts/lib/checklist-stage.sh'; $*" )
}

# 1. The helper: the running application and the checklist input are both bound into the template.
: > "$STUB_LOG"
OUT="$(in_project 'checklist_bind_worker_template "$STATE_DIR/documents/MANUAL_CHECKLIST.json" EXECUTE_CHECKLIST_WORKERS.json; echo "TEMPLATE=$CHECKLIST_WORKER_TEMPLATE"')"
T="$(printf '%s\n' "$OUT" | sed -n 's/^TEMPLATE=//p')"
check "it sets the template" test -s "$T"
check "it is named for the workers document" test "$(basename "$T")" == "execute-checklist-worker-EXECUTE_CHECKLIST_WORKERS.json.md"
check "it carries the worker prompt itself" bash -c 'head -c 200 "$1" | grep -q "." && grep -qF "$(head -n 1 "$2")" "$1"' _ "$T" "$TMP/root/prompts/change/execute-checklist-worker.md"
check "it says the application is already running" grep -qF "## The application is already running (binding)" "$T"
check "and where" grep -qF "http://127.0.0.1:5199/" "$T"
check "it names the checklist input" grep -qF "## Checklist input (binding)" "$T"
check "with the exact path" grep -qF "$TMP/state/documents/MANUAL_CHECKLIST.json" "$T"
check "it started the server in the project directory with the state directory" bash -c '[[ "$(sed "s#^start ##" "$1" | head -n 1)" == "$(cd "$2" && pwd) $3" || "$(sed "s#^start ##" "$1" | head -n 1)" == "$(cd "$2" && pwd -P) $3" ]]' _ "$STUB_LOG" "$TMP/proj" "$TMP/state"
check "and told the user" grep -q "Checklist: the application is running at http://127.0.0.1:5199/" <<< "$OUT"

# 2. A server that will not start: the checklist input is still bound, the 'running' section is not, and it says so.
: > "$STUB_LOG"
OUT="$(STUB_SERVER=down in_project 'checklist_bind_worker_template "$STATE_DIR/documents/MANUAL_CHECKLIST.json" down.json; echo "TEMPLATE=$CHECKLIST_WORKER_TEMPLATE"')"
T="$(printf '%s\n' "$OUT" | sed -n 's/^TEMPLATE=//p')"
check "server down: a template is still made" test -s "$T"
check "server down: no claim the application is running" bash -c '! grep -qF "already running" "$1"' _ "$T"
check "server down: the checklist input is still bound" grep -qF "## Checklist input (binding)" "$T"
check "server down: the user is told" grep -q "could not be started by the driver" <<< "$OUT"

# 3. The switch: no server is started at all.
: > "$STUB_LOG"
OUT="$(WORKFLOW_CHECKLIST_APP_SERVER=0 in_project 'checklist_bind_worker_template "$STATE_DIR/documents/MANUAL_CHECKLIST.json" off.json; echo "TEMPLATE=$CHECKLIST_WORKER_TEMPLATE"')"
T="$(printf '%s\n' "$OUT" | sed -n 's/^TEMPLATE=//p')"
check "switch off: no server was started" test ! -s "$STUB_LOG"
check "switch off: the checklist input is bound" grep -qF "## Checklist input (binding)" "$T"
check "switch off: nothing claims the application is running" bash -c '! grep -qF "already running" "$1"' _ "$T"

# 4. Two lane sets do not overwrite each other's template.
OUT="$(in_project 'checklist_bind_worker_template "$STATE_DIR/documents/A.json" a.json; A="$CHECKLIST_WORKER_TEMPLATE"; checklist_bind_worker_template "$STATE_DIR/documents/B.json" b.json; echo "A=$A"; echo "B=$CHECKLIST_WORKER_TEMPLATE"')"
A="$(printf '%s\n' "$OUT" | sed -n 's/^A=//p')"; B="$(printf '%s\n' "$OUT" | sed -n 's/^B=//p')"
check "separate templates per output" test "$A" != "$B"
check "A still names A" grep -qF "documents/A.json" "$A"
check "B names B and not A" bash -c 'grep -qF documents/B.json "$1" && ! grep -qF documents/A.json "$1"' _ "$B"

# 5. The change workflow's own function hands the lane runner that bound template, not the bare prompt.
mkdir -p "$TMP/state/checklist-groups"
printf 'MC-101 MC-102\n' > "$TMP/state/checklist-groups/groups.txt"
printf '{}' > "$TMP/state/documents/MANUAL_CHECKLIST.json"
: > "$STUB_LOG"; : > "$TMP/seen-template"; : > "$TMP/seen-path"
OUT="$(cd "$TMP/proj" && ROOT="$TMP/root" STATE_DIR="$TMP/state" PROJECT_ROOT="$TMP/proj" PARALLEL_CHECKLIST_WORKERS=1 bash -c "
    . '$REPO/scripts/lib/checklist-stage.sh'
    eval \"\$(awk '\$0 == \"run_parallel_checklist_workers() {\" {p=1} p{print} p&&/^}\$/{exit}' '$REPO/scripts/change-workflow.sh')\"
    checklist_lane_batches() { printf 'MC-101 MC-102\n' > \"\$2\"; echo 1; }
    checklist_run_lanes() { printf '%s' \"\$3\" > '$TMP/seen-path'; cp \"\$3\" '$TMP/seen-template'; }
    run_parallel_checklist_workers
" 2>&1)"
SEEN="$(cat "$TMP/seen-path")"
check "the lane runner was given a template" test -s "$TMP/seen-template"
check "not the bare worker prompt" test "$SEEN" != "$TMP/root/prompts/change/execute-checklist-worker.md"
check "it tells the workers where the application is" grep -qF "http://127.0.0.1:5199/" "$TMP/seen-template"
check "and which file holds the rows: the change workflow's own checklist" grep -qF "$TMP/state/documents/MANUAL_CHECKLIST.json" "$TMP/seen-template"

# 6. Both drivers use the one helper, and the change workflow stops the application it started.
check "stagegate.sh uses the shared helper" grep -q 'checklist_bind_worker_template "\$checklist_input"' "$REPO/scripts/stagegate.sh"
check "change-workflow.sh uses the shared helper" grep -q 'checklist_bind_worker_template "\$STATE_DIR/documents/MANUAL_CHECKLIST.json"' "$REPO/scripts/change-workflow.sh"
check "neither driver still hands out the bare prompt to the lane runner" bash -c '! grep -q "checklist_run_lanes .*execute-checklist-worker.md" "$1/scripts/stagegate.sh" "$1/scripts/change-workflow.sh"' _ "$REPO"
check "the change workflow's one-lane-per-group fallback copies the bound template too, never the bare prompt" bash -c 'grep -q "cp \"\$CHECKLIST_WORKER_TEMPLATE\" \"\$prompt\"" "$1/scripts/change-workflow.sh" && ! grep -q "cp \"\$ROOT/prompts/change/execute-checklist-worker.md\"" "$1/scripts/change-workflow.sh"' _ "$REPO"
check "the change workflow stops the application after its workers" grep -q 'checklist_execute_worker_fastpath _change_execute_checklist_stop_app_server' "$REPO/scripts/change-workflow.sh"
check "and when it exits" bash -c 'sed -n "/^on_exit() {/,/^}/p" "$1/scripts/change-workflow.sh" | grep -q "app_server.py\" stop"' _ "$REPO"
: > "$STUB_LOG"
in_project '_change_stop() { python3 -B "$ROOT/scripts/lib/app_server.py" stop "$STATE_DIR" > /dev/null 2>&1 || true; }; eval "$(awk "\$0 == \"_change_execute_checklist_stop_app_server() {\" {p=1} p{print} p&&/^}\$/{exit}" "'"$REPO"'/scripts/change-workflow.sh")"; _change_execute_checklist_stop_app_server' > /dev/null 2>&1
check "the stop function really stops the server" grep -q "^stop $TMP/state$" "$STUB_LOG"

if [[ "$fails" -ne 0 ]]; then echo "change-checklist-worker-template-test.sh: $fails failed"; exit 1; fi
echo "change-checklist-worker-template-test.sh: all checks passed"

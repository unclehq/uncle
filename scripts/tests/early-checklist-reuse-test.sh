#!/usr/bin/env bash
# The real checklist stage reusing early results: checklist_execute_worker_fastpath and early_checklist_reuse_prepare as they are in the
# driver, the real coverage check, and the real merge. Only the model workers and the report renderer are stood in.
# What must hold: a row is reused only when the early run passed it, on the same row, on the same application files; every other row
# runs; and when anything is wrong the stage runs every row exactly as it did before there was an early run.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

mkdir -p "$TMP/root"
cp -R "$REPO/scripts" "$REPO/prompts" "$TMP/root/"
# The report renderer is stood in: the fast path calls it once the workers cover every required check.
cat > "$TMP/root/scripts/lib/execute_checklist_reports.py" <<'PY'
import os
open(os.path.join(os.environ['HARNESS'], 'reports-rendered'), 'w').write('1')
PY
FIXTURE="$REPO/scripts/tests/fixtures/manual-checklist-valid.json"
IDS="$(python3 -c 'import json,sys; print(" ".join(c["id"] for c in json.load(open(sys.argv[1]))["checks"]))' "$FIXTURE")"
FIRST="${IDS%% *}"; LAST="${IDS##* }"
ROWS="$(wc -w <<< "$IDS" | tr -d ' ')"

# Writes a workers document for the rows of a checklist; rows in $2 (comma separated) FAIL.
cat > "$TMP/make_workers.py" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1])); fails = set(filter(None, sys.argv[3].split(',')))
results = [{'id': c['id'], 'action': c['exact_action'], 'expected_result': c['expected_result'],
            'actual_result': 'broken' if c['id'] in fails else 'fine', 'evidence': 'EV-%s' % c['id'],
            'status': 'FAIL' if c['id'] in fails else 'PASS', 'defect_reference': '', 'source': 'group-1-batch-1'} for c in doc['checks']]
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'checklist-execution-worker-packets',
           'workers': [{'source': 'group-1-batch-1', 'status': 'ok', 'result_count': len(results)}],
           'results': sorted(results, key=lambda r: r['id'])}, open(sys.argv[2], 'w'))
PY

# case NAME [early failing ids] — a project that has had an early run; env knobs below change the situation before the stage runs.
run_case() {
    local name="$1" failing="${2:-}" project="$TMP/$1"
    local state="$project/.uncle/workflow" early="$project/.uncle/workflow/early-checklist"
    mkdir -p "$project/src" "$state/documents" "$early" "$project/.uncle/harness"
    echo 'export const a = 1' > "$project/src/a.js"
    cp "$FIXTURE" "$state/documents/MANUAL_CHECKLIST.json"
    if [[ -z "${NO_EARLY:-}" ]]; then
        cp "$FIXTURE" "$early/checklist.json"
        python3 "$TMP/make_workers.py" "$early/checklist.json" "$early/workers.json" "$failing"
        python3 -B "$TMP/root/scripts/lib/early_checklist.py" manifest "$early/checklist.json" "$early/workers.json" \
            "$(python3 -B "$TMP/root/scripts/lib/tree_fingerprint.py" --app "$project")" "$early/manifest.json"
    fi
    (
        cd "$project" || exit 1
        ROOT="$TMP/root"; STATE_DIR="$state"; LOG_DIR="$state/logs"; export HARNESS="$project/.uncle/harness"
        for assignment in "$@"; do :; done
        eval "$(awk '$0 == "checklist_execute_worker_fastpath() {" {p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/lib/checklist-stage.sh")"
        eval "$(awk '$0 == "early_checklist_reuse_prepare() {" {p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/lib/parallel-implement.sh")"
        # The workers: record what they were asked to run, and execute exactly those rows (all PASS).
        run_parallel_checklist_workers() {
            local input="${1:-$STATE_DIR/documents/MANUAL_CHECKLIST.json}" output="${2:-$STATE_DIR/documents/EXECUTE_CHECKLIST_WORKERS.json}"
            printf 'args=%s ids=%s\n' "${1:-none}" "$(python3 -c 'import json,sys; print(",".join(c["id"] for c in json.load(open(sys.argv[1]))["checks"]))' "$input")" >> "$HARNESS/worker-calls.log"
            [[ -z "${WORKERS_WRITE_NOTHING:-}" ]] || return 0
            python3 "$TMP/make_workers.py" "$input" "$output" ""
            python3 - "$output" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for r in d['results']: r['evidence'] = 'FRESH-' + r['id']; r['source'] = 'fresh-worker'
json.dump(d, open(sys.argv[1], 'w'))
PY
        }
        # Something happens between the early run and the stage.
        [[ -z "${CHANGE_APP:-}" ]] || echo 'export const a = 2' > src/a.js
        [[ -z "${CHANGE_TESTS:-}" ]] || { mkdir -p tests; echo x > tests/new.test.js; }
        [[ -z "${RECONCILE_CHANGES_ROW:-}" ]] || python3 - "$STATE_DIR/documents/MANUAL_CHECKLIST.json" "$RECONCILE_CHANGES_ROW" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for c in d['checks']:
    if c['id'] == sys.argv[2]: c['exact_action'] += ' and then press Enter'
json.dump(d, open(sys.argv[1], 'w'))
PY
        [[ -z "${RECONCILE_ADDS_ROW:-}" ]] || python3 - "$STATE_DIR/documents/MANUAL_CHECKLIST.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
d['checks'].append({'id': 'MC-999', 'exact_action': 'a brand new check', 'expected_result': 'it works', 'exclusive_resources': []})
json.dump(d, open(sys.argv[1], 'w'))
PY
        [[ -z "${CORRUPT_REUSED:-}" ]] || true
        checklist_execute_worker_fastpath > "$HARNESS/out.txt" 2>&1
        echo $? > "$HARNESS/rc"
    )
}
H() { echo "$TMP/$1/.uncle/harness"; }
calls() { [[ -e "$(H "$1")/worker-calls.log" ]] && wc -l < "$(H "$1")/worker-calls.log" | tr -d ' ' || echo 0; }
workers_doc() { echo "$TMP/$1/.uncle/workflow/documents/EXECUTE_CHECKLIST_WORKERS.json"; }
status_of() { python3 -c 'import json,sys; d={r["id"]:r for r in json.load(open(sys.argv[1]))["results"]}; print(d[sys.argv[2]]["status"])' "$(workers_doc "$1")" "$2" 2> /dev/null; }
source_of() { python3 -c 'import json,sys; d={r["id"]:r for r in json.load(open(sys.argv[1]))["results"]}; print(d[sys.argv[2]]["source"])' "$(workers_doc "$1")" "$2" 2> /dev/null; }
evidence_of() { python3 -c 'import json,sys; d={r["id"]:r for r in json.load(open(sys.argv[1]))["results"]}; print(d[sys.argv[2]]["evidence"])' "$(workers_doc "$1")" "$2" 2> /dev/null; }
result_count() { python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["results"]))' "$(workers_doc "$1")" 2> /dev/null || echo 0; }

# 1. Every early row passed on this exact application: no worker runs at all, and the stage is satisfied.
run_case allreuse
check "all reused: the stage succeeds" test "$(cat "$(H allreuse)/rc")" == 0
check "all reused: no worker was started" test "$(calls allreuse)" == 0
check "all reused: every row is recorded" test "$(result_count allreuse)" == "$ROWS"
check "all reused: each came from the early run" test "$(source_of allreuse "$FIRST")" == early-checklist
check "all reused: with the early evidence" test "$(evidence_of allreuse "$FIRST")" == "EV-$FIRST"
check "all reused: the reports were rendered" test -e "$(H allreuse)/reports-rendered"
check "all reused: it said how many were reused" grep -q "$ROWS row(s) already passed in the early run" "$(H allreuse)/out.txt"

# 2. One row failed early: only that row runs; the others are reused.
run_case onefailed "$FIRST"
check "one failed: the stage succeeds" test "$(cat "$(H onefailed)/rc")" == 0
check "one failed: workers ran once" test "$(calls onefailed)" == 1
check "one failed: for only the failed row" grep -q "ids=$FIRST\$" "$(H onefailed)/worker-calls.log"
check "one failed: through the reduced checklist, not the default" grep -q "args=.*reduced.json" "$(H onefailed)/worker-calls.log"
check "one failed: the failed row has fresh evidence" test "$(evidence_of onefailed "$FIRST")" == "FRESH-$FIRST"
check "one failed: its result came from a worker, not the early run" test "$(source_of onefailed "$FIRST")" == fresh-worker
check "one failed: another row is reused" test "$(source_of onefailed "$LAST")" == early-checklist
check "one failed: every row is recorded" test "$(result_count onefailed)" == "$ROWS"

# 3. The application changed since the early run: nothing is reused and everything runs as it always did.
CHANGE_APP=1 run_case appchanged
check "app changed: the stage succeeds" test "$(cat "$(H appchanged)/rc")" == 0
check "app changed: workers ran once" test "$(calls appchanged)" == 1
check "app changed: with the default call, no early checklist involved" grep -q "args=none" "$(H appchanged)/worker-calls.log"
check "app changed: for every row" grep -q "ids=${IDS// /,}\$" "$(H appchanged)/worker-calls.log"
check "app changed: no row is marked as early" test "$(source_of appchanged "$FIRST")" == fresh-worker

# 4. A test file added after the early run does not matter.
CHANGE_TESTS=1 run_case testsadded
check "tests added: every row is still reused" test "$(calls testsadded)" == 0
check "tests added: all recorded" test "$(result_count testsadded)" == "$ROWS"

# 5. There was no early run (or it left nothing): the stage is exactly what it was.
NO_EARLY=1 run_case noearly
check "no early run: the stage succeeds" test "$(cat "$(H noearly)/rc")" == 0
check "no early run: the default call, for every row" grep -q "args=none ids=${IDS// /,}\$" "$(H noearly)/worker-calls.log"
check "no early run: nothing is marked as early" test "$(source_of noearly "$FIRST")" == fresh-worker

# 6. The reconciliation changed a row after the draft: that row runs, the others are reused.
RECONCILE_CHANGES_ROW="$FIRST" run_case rowchanged
check "row changed: only the changed row runs" grep -q "ids=$FIRST\$" "$(H rowchanged)/worker-calls.log"
check "row changed: one worker call" test "$(calls rowchanged)" == 1
check "row changed: the others are reused" test "$(source_of rowchanged "$LAST")" == early-checklist

# 7. The reconciliation added a row: it runs, and everything else is reused.
RECONCILE_ADDS_ROW=1 run_case rowadded
check "row added: only the new row runs" grep -q "ids=MC-999\$" "$(H rowadded)/worker-calls.log"
check "row added: the old rows are reused" test "$(source_of rowadded "$FIRST")" == early-checklist
check "row added: all recorded" test "$(result_count rowadded)" == "$((ROWS + 1))"

# 8. The workers for the remaining rows produce nothing: the stage says what is uncovered instead of claiming success.
WORKERS_WRITE_NOTHING=1 run_case writesnothing "$FIRST"
check "workers wrote nothing: the stage does not claim success" test "$(cat "$(H writesnothing)/rc")" == 2
check "workers wrote nothing: the uncovered row is named" grep -q "$FIRST" "$TMP/writesnothing/.uncle/workflow/execute-checklist-uncovered.md"
check "workers wrote nothing: the reports were not rendered" test ! -e "$(H writesnothing)/reports-rendered"

if [[ "$fails" -ne 0 ]]; then echo "early-checklist-reuse-test.sh: $fails failed"; exit 1; fi
echo "early-checklist-reuse-test.sh: all checks passed"

#!/usr/bin/env bash
# The checklist, run early: the real functions from parallel-implement.sh and checklist-stage.sh, with the model workers, the app server and
# the executor stood in for. It checks the sequence (early run after the source wave built; fix pass for failures; only failed rows run
# again; manifest; reuse at the real stage) and, above all, that every problem falls back to the real stage running every row.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

mkdir -p "$TMP/root" "$TMP/bin"
cp -R "$REPO/scripts" "$REPO/prompts" "$TMP/root/"
# The executor records each group and, for a fix prompt, applies the "fix" when told to.
cat > "$TMP/root/scripts/lib/parallel_steps.py" <<'PY'
import json, os, sys
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text())
project = Path(request['project'])
first = str(request['steps'][0]['number'])
owned = ';'.join(sorted(request['owned'].get(first, [])))
with open(os.environ['GROUP_LOG'], 'a') as log:
    log.write('group=%s link=%s owned=%s\n' % (' '.join(str(s['number']) for s in request['steps']), os.environ.get('UNCLE_LINK_DEPENDENCIES', ''), owned))
prompt = project / '.uncle/workflow/parallel/prompts' / ('step-%s.md' % first)
text = prompt.read_text() if prompt.exists() else ''
if 'Checklist failures to fix' in text and os.environ.get('FIX_WORKS') == '1':
    (project / '.uncle/harness/fixed').write_text('1')
if 'Build failure to fix' in text and os.environ.get('FIX_WORKS') == '1':
    (project / '.uncle/harness/fixed').write_text('1')
for step in request['steps']:
    note = project / step['note']
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes',
                                'changed_files': [{'path': 'file-%s.js' % step['number']}]}))
print(json.dumps({'elapsed_seconds': 0, 'step_seconds': {}, 'files': []}))
PY
cat > "$TMP/root/scripts/lib/app_server.py" <<'PY'
import os, sys
open(os.path.join(os.environ['FAKE_PROJECT'], '.uncle/harness/server-calls.log'), 'a').write(' '.join(sys.argv[1:2]) + '\n')
PY
cat > "$TMP/bin/npm" <<'SH'
#!/usr/bin/env bash
echo "npm $*" >> "$NPM_LOG"
if [[ "${1:-}" == run && "${2:-}" == build ]]; then
    if [[ "${BUILD_FAIL:-0}" == 1 && ! -e "$FAKE_PROJECT/.uncle/harness/fixed" ]]; then echo 'Error: failed to resolve import' >&2; exit 1; fi
    exit 0
fi
mkdir -p node_modules/.bin
SH
chmod +x "$TMP/bin/npm"
cat > "$TMP/plan.md" <<'PLAN'
# Updated plan

## 12. Implementation steps

1. Scaffold. Owns: `package.json`, `.gitignore`
2. Core logic: reduce(state, action). Owns: `src/calc.js`
3. View: renders the keypad div. Owns: `src/App.jsx`, `src/main.jsx`, `index.html`
4. Theme: styles the keypad. Owns: `src/styles.css`
5. Unit tests. Owns: `tests/calc.test.js`
6. Browser tests. Owns: `e2e/theme.spec.js`
7. Mutation list. Owns: `tests/mutations/list.mjs`
PLAN
DRAFT_FIXTURE="$REPO/scripts/tests/fixtures/manual-checklist-valid.json"
IDS="$(python3 -c 'import json,sys; print(" ".join(c["id"] for c in json.load(open(sys.argv[1]))["checks"]))' "$DRAFT_FIXTURE")"
FIRST="${IDS%% *}"
ROWS="$(wc -w <<< "$IDS" | tr -d ' ')"

run_case() {   # name [env assignments...]
    local name="$1"; shift
    local project="$TMP/$name"
    mkdir -p "$project/.uncle/docs" "$project/.uncle/workflow/logs" "$project/.uncle/workflow/documents"
    cp "$TMP/plan.md" "$project/.uncle/docs/UPDATED_PROJECT_PLAN.md"
    printf '{"scripts":{"build":"vite build"}}\n' > "$project/package.json"
    [[ -n "${NO_LAUNCH:-}" ]] || printf '{"url":"http://127.0.0.1:5173/"}\n' > "$project/.uncle/launch.json"
    cp "$DRAFT_FIXTURE" "$project/.uncle/workflow/documents/MANUAL_CHECKLIST.json"
    if [[ -z "${NO_DRAFT:-}" ]]; then
        cp "$DRAFT_FIXTURE" "$project/.uncle/workflow/documents/MANUAL_CHECKLIST_DRAFT.json"
        printf 'fp1\n' > "$project/.uncle/workflow/manual-checklist-draft.done"
    fi
    (
        cd "$project" || exit 1
        ROOT="$TMP/root"; STATE_DIR="$project/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"
        mkdir -p "$project/.uncle/harness"
        export GROUP_LOG="$project/.uncle/harness/groups.log" NPM_LOG="$project/.uncle/harness/npm.log" FAKE_PROJECT="$project" PATH="$TMP/bin:$PATH"
        # These cases test the run inside IMPLEMENT, which is off by default now: turn it on unless a case asks for the default.
        [[ -n "${DEFAULT_ENV:-}" ]] || export WORKFLOW_EARLY_CHECKLIST=1
        for assignment in "$@"; do export "$assignment"; done
        . "$ROOT/scripts/lib/plan-scope.sh"
        for fn in parallel_group_wave parallel_module_steps parallel_group_writes_source parallel_fix_pass parallel_wave_build_gate \
                  early_checklist_enabled early_checklist_stop_server early_checklist_execute early_checklist_start early_checklist_record \
                  early_checklist_fix early_checklist_finish early_checklist_reuse_prepare \
                  parallel_install_dependencies parallel_merge_map parallel_run_group parallel_implement_run_groups; do
            eval "$(awk -v f="$fn" '$0 == f "() {" {p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/lib/parallel-implement.sh")"
        done
        eval "$(grep -E '^early_checklist_stop_server\(\)' "$ROOT/scripts/lib/parallel-implement.sh")"
        eval "$(awk '$0 == "_stagegate_parallel_build_step_prompt() {" {p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/stagegate.sh")"
        EARLY_CHECKLIST_PID=""; EARLY_CHECKLIST_GROUP=""
        manual_checklist_draft_fingerprint() { echo fp1; }
        # The workers: one result per row, PASS unless the row is listed in FAIL_IDS and the fix has not been applied.
        run_parallel_checklist_workers() {
            [[ -z "${SLOW:-}" ]] || sleep 30
            local input="${1:-$STATE_DIR/documents/MANUAL_CHECKLIST.json}" output="${2:-$STATE_DIR/documents/EXECUTE_CHECKLIST_WORKERS.json}"
            printf 'input=%s ids=%s\n' "${1:-default}" "$(python3 -c 'import json,sys; print(",".join(c["id"] for c in json.load(open(sys.argv[1]))["checks"]))' "$input")" \
                >> "$FAKE_PROJECT/.uncle/harness/checklist-calls.log"
            python3 - "$input" "$output" "$FAKE_PROJECT" <<'PY'
import json, os, sys
doc = json.load(open(sys.argv[1])); fixed = os.path.exists(os.path.join(sys.argv[3], '.uncle/harness/fixed'))
fails = set(filter(None, os.environ.get('FAIL_IDS', '').split(',')))
results = []
for c in doc['checks']:
    bad = c['id'] in fails and not fixed
    results.append({'id': c['id'], 'action': c['exact_action'], 'expected_result': c['expected_result'],
                    'actual_result': 'it was broken' if bad else 'it was fine', 'evidence': 'EVIDENCE-%s' % c['id'],
                    'status': 'FAIL' if bad else 'PASS', 'defect_reference': '', 'source': 'group-1-batch-1'})
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'checklist-execution-worker-packets',
           'workers': [{'source': 'group-1-batch-1', 'status': 'ok', 'result_count': len(results)}],
           'results': sorted(results, key=lambda r: r['id'])}, open(sys.argv[2], 'w'))
PY
        }
        supervision_validation_failed() { :; }
        require_file() { [[ -s "$1" ]] || { echo "missing $1" >&2; exit 1; }; }
        runtime_repair_marker="$project/none"
        plan_steps .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/implement-steps.txt"
        plan_step_owns .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/implement-owns.tsv"
        python3 "$ROOT/scripts/lib/implementation_notes.py" reset . > /dev/null 2>&1 || true
        parallel_groups() { printf '%b' "${TEST_GROUPS:-1 2 3 4\n5 6\n7\n}"; }
        parallel_implement_run_groups .uncle/docs/UPDATED_PROJECT_PLAN.md _stagegate_parallel_build_step_prompt "Isolated step" > "$project/.uncle/harness/out.txt" 2>&1
        echo $? > "$project/.uncle/harness/rc"
        # Something happens to the tree between the early run and the real stage.
        [[ -z "${CHANGE_APP:-}" ]] || { mkdir -p src; echo changed > src/changed.js; }
        [[ -z "${CHANGE_TESTS:-}" ]] || { mkdir -p tests; echo extra > tests/extra.test.js; mkdir -p e2e; echo extra > e2e/extra.spec.js; }
        # What the real stage would be offered, in the same shell that ran the implementation.
        early_checklist_reuse_prepare > "$project/.uncle/harness/reuse.out" 2>&1 && echo 0 > "$project/.uncle/harness/reuse.rc" || echo 1 > "$project/.uncle/harness/reuse.rc"
    )
}
calls() { cat "$TMP/$1/.uncle/harness/checklist-calls.log" 2> /dev/null | wc -l | tr -d ' '; }
call_ids() { sed -n "${2}p" "$TMP/$1/.uncle/harness/checklist-calls.log" | sed 's/.*ids=//'; }
manifest_passed() { python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["passed"]))' "$TMP/$1/.uncle/workflow/early-checklist/manifest.json"; }
exists() { [[ -s "$TMP/$1/.uncle/workflow/early-checklist/$2" ]]; }

# 1. Every drafted row passes: one early run, a manifest, and everything reusable.
run_case allpass
check "all pass: the implementation completes" test "$(cat "$TMP/allpass/.uncle/harness/rc")" == 0
check "all pass: the early run executed the draft once" test "$(calls allpass)" == 1
check "all pass: with every draft row" test "$(call_ids allpass 1)" == "${IDS// /,}"
check "all pass: it said so" grep -q "every drafted row passed" "$TMP/allpass/.uncle/harness/out.txt"
check "all pass: no fix pass ran" test "$(grep -c '^group=1 link=1' "$TMP/allpass/.uncle/harness/groups.log" || true)" == 0
check "all pass: the manifest lists every row as passed" test "$(manifest_passed allpass)" == "$IDS"
check "all pass: the app server was stopped" grep -q stop "$TMP/allpass/.uncle/harness/server-calls.log"
check "all pass: the real stage may reuse every row" test "$(cat "$TMP/allpass/.uncle/harness/reuse.rc")" == 0
check "all pass: reusing all of them" grep -q "reusing $ROWS of $ROWS" "$TMP/allpass/.uncle/harness/reuse.out"
check "all pass: nothing is left to run" test "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["checks"]))' "$TMP/allpass/.uncle/workflow/early-checklist/reduced.json")" == 0

# 2. One row fails and the fix works: a fix pass with the evidence, only that row again, then all reusable.
run_case fixed "FAIL_IDS=$FIRST" FIX_WORKS=1
check "fixed: the implementation completes" test "$(cat "$TMP/fixed/.uncle/harness/rc")" == 0
check "fixed: two executions, all rows then only the failed one" test "$(calls fixed)" == 2
check "fixed: the second run is only the failed row" test "$(call_ids fixed 2)" == "$FIRST"
check "fixed: a fix pass ran, linked to the dependencies" grep -q "^group=1 link=1 " "$TMP/fixed/.uncle/harness/groups.log"
check "fixed: its worker owns the files of every step in the source wave" grep -q "^group=1 link=1 .*owned=.*src/App.jsx.*src/calc.js\|^group=1 link=1 .*owned=.*src/calc.js.*src/App.jsx" "$TMP/fixed/.uncle/harness/groups.log"
check "fixed: its prompt names the failing row and carries the evidence" grep -q "EVIDENCE-$FIRST" "$TMP/fixed/.uncle/workflow/parallel/prompts/step-1.md"
check "fixed: its prompt says what was observed" grep -q "it was broken" "$TMP/fixed/.uncle/workflow/parallel/prompts/step-1.md"
check "fixed: its prompt has the heading" grep -q "Checklist failures to fix (binding)" "$TMP/fixed/.uncle/workflow/parallel/prompts/step-1.md"
check "fixed: the fix is limited to the worker's own files" grep -q "editing only the files you own" "$TMP/fixed/.uncle/workflow/parallel/prompts/step-1.md"
check "fixed: its prompt tells the worker to keep its own tests in step with the change" grep -q "change that test in the same pass" "$TMP/fixed/.uncle/workflow/parallel/prompts/step-1.md"
check "fixed: the manifest now lists every row as passed" test "$(manifest_passed fixed)" == "$IDS"
check "fixed: every row is reusable" grep -q "reusing $ROWS of $ROWS" "$TMP/fixed/.uncle/harness/reuse.out"

# 3. The fix does not work: one pass only, the row stays failed, the rest are reusable.
run_case stuck "FAIL_IDS=$FIRST" FIX_WORKS=0
check "stuck: the implementation still completes" test "$(cat "$TMP/stuck/.uncle/harness/rc")" == 0
check "stuck: exactly one fix pass" test "$(grep -c '^group=1 link=1' "$TMP/stuck/.uncle/harness/groups.log")" == 1
check "stuck: the failed row ran again, once" test "$(calls stuck)" == 2
check "stuck: the failed row is not in the manifest's passes" bash -c '! grep -qw "$1" <<< "$2"' _ "$FIRST" "$(manifest_passed stuck)"
check "stuck: the other rows are reusable" grep -q "reusing $((ROWS - 1)) of $ROWS" "$TMP/stuck/.uncle/harness/reuse.out"
check "stuck: the failed row is left for the real stage" python3 -c 'import json,sys; sys.exit(0 if [c["id"] for c in json.load(open(sys.argv[1]))["checks"]]==[sys.argv[2]] else 1)' "$TMP/stuck/.uncle/workflow/early-checklist/reduced.json" "$FIRST"

# 3b. The application changes after the early run (a later wave, the lead agent, a repair): nothing is reused. Tests added do not matter.
CHANGE_APP=1 run_case changedapp
check "changed application: the early run happened" test "$(calls changedapp)" == 1
check "changed application: nothing is reusable" test "$(cat "$TMP/changedapp/.uncle/harness/reuse.rc")" == 1
check "changed application: every row would run" grep -q "reusing 0 of $ROWS" "$TMP/changedapp/.uncle/harness/reuse.out"
CHANGE_TESTS=1 run_case changedtests
check "tests added after the early run: still reusable" test "$(cat "$TMP/changedtests/.uncle/harness/reuse.rc")" == 0
check "tests added after the early run: every row reused" grep -q "reusing $ROWS of $ROWS" "$TMP/changedtests/.uncle/harness/reuse.out"

# 4. The fix pass can be turned off on its own.
run_case nofix "FAIL_IDS=$FIRST" FIX_WORKS=1 WORKFLOW_EARLY_CHECKLIST_FIX=0
check "no fix: only the early run executed" test "$(calls nofix)" == 1
check "no fix: no fix group ran" test "$(grep -c '^group=1 link=1' "$TMP/nofix/.uncle/harness/groups.log" || true)" == 0
check "no fix: the failing row is not reusable" grep -q "reusing $((ROWS - 1)) of $ROWS" "$TMP/nofix/.uncle/harness/reuse.out"

# 5. Anything that is not right means no early run at all, and nothing to reuse.
run_case off WORKFLOW_EARLY_CHECKLIST=0
check "off: nothing ran early" test "$(calls off)" == 0
check "off: nothing is reusable" test "$(cat "$TMP/off/.uncle/harness/reuse.rc")" == 1
DEFAULT_ENV=1 run_case default
check "default: the run inside IMPLEMENT is off" test "$(calls default)" == 0
check "default: nothing is reusable from it" test "$(cat "$TMP/default/.uncle/harness/reuse.rc")" == 1
run_case wavesoff WORKFLOW_IMPLEMENT_TEST_WAVES=0 'TEST_GROUPS=1 2 3 4 5 6 7\n'
check "waves off: nothing ran early" test "$(calls wavesoff)" == 0
NO_LAUNCH=1 run_case nolaunch
check "no launch file (missing from most builds): the early run still happens" test "$(calls nolaunch)" == 1
check "no launch file: its results are recorded and reusable" test "$(cat "$TMP/nolaunch/.uncle/harness/reuse.rc")" == 0
NO_DRAFT=1 run_case nodraft WORKFLOW_EARLY_CHECKLIST_DRAFT_WAIT=2
check "no draft: the implementation still completes" test "$(cat "$TMP/nodraft/.uncle/harness/rc")" == 0
check "no draft: nothing ran early" test "$(calls nodraft)" == 0
check "no draft: no manifest was written" test ! -s "$TMP/nodraft/.uncle/workflow/early-checklist/manifest.json"
check "no draft: nothing is reusable" test "$(cat "$TMP/nodraft/.uncle/harness/reuse.rc")" == 1
check "no draft: it said why" grep -q "no finished draft" "$TMP/nodraft/.uncle/harness/out.txt" "$TMP/nodraft/.uncle/workflow/logs/early-checklist.log"
run_case brokenbuild BUILD_FAIL=1 FIX_WORKS=0
check "a build that fails: the rows never run against a broken application" test "$(calls brokenbuild)" == 0
check "a build that fails: the implementation still completes" test "$(cat "$TMP/brokenbuild/.uncle/harness/rc")" == 0
run_case scaffoldonly 'TEST_GROUPS=1\n5 6\n7\n'
check "no source wave: nothing ran early" test "$(calls scaffoldonly)" == 0

# 6. A run that takes too long is stopped, the implementation does not wait for it, and the real stage runs every row.
started=$SECONDS
run_case slow SLOW=1 WORKFLOW_EARLY_CHECKLIST_SECONDS=2
elapsed=$((SECONDS - started))
check "slow: the implementation still completes" test "$(cat "$TMP/slow/.uncle/harness/rc")" == 0
check "slow: it did not wait for the stuck run (took ${elapsed}s)" test "$elapsed" -lt 25
check "slow: it said it gave up" grep -q "still running after 2 seconds" "$TMP/slow/.uncle/harness/out.txt"
check "slow: the app server was stopped" grep -q stop "$TMP/slow/.uncle/harness/server-calls.log"
check "slow: no manifest, so nothing is reusable" test "$(cat "$TMP/slow/.uncle/harness/reuse.rc")" == 1

if [[ "$fails" -ne 0 ]]; then echo "early-checklist-flow-test.sh: $fails failed"; exit 1; fi
echo "early-checklist-flow-test.sh: all checks passed"

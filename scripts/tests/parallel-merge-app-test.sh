#!/usr/bin/env bash
# WORKFLOW_IMPLEMENT_MERGE_APP=1: the application steps of a parallel group are written by one worker -- their text and files
# reach that worker's prompt, their files are owned by it alone, they run no worker of their own -- while scaffold and test steps
# stay separate. Off, and for a builder that cannot carry the extra text, nothing changes. Real fan-out loop, prompt builder
# and request builder; only the executor is stubbed, to record what it was asked to run.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

# A private copy of the repo's scripts with the executor replaced by a recorder.
mkdir -p "$TMP/root"
cp -R "$REPO/scripts" "$REPO/prompts" "$TMP/root/"
[[ ! -d "$REPO/lib" ]] || cp -R "$REPO/lib" "$TMP/root/lib"
cat > "$TMP/root/scripts/lib/parallel_steps.py" <<'PY'
import json, os, sys
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text())
Path(os.environ['REQUEST_COPY']).write_text(json.dumps(request))
for step in request['steps']:
    note = Path(request['project']) / step['note']
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes',
                                'changed_files': [{'path': 'file-%s.js' % step['number']}]}))
print(json.dumps({'elapsed_seconds': 0, 'step_seconds': {}, 'files': []}))
PY
cat > "$TMP/plan.md" <<'PLAN'
# Updated plan

## 12. Implementation steps

1. Scaffold. Owns: `package.json`, `index.html`, `.gitignore`
2. Core logic: reduce(state, action). Owns: `src/calc.js`
3. View: renders the keypad div. Owns: `src/App.jsx`, `src/main.jsx`
4. Theme: styles the keypad. Owns: `src/styles.css`
5. Unit tests. Owns: `tests/calc.test.js`
6. Browser tests. Owns: `e2e/theme.spec.js`
PLAN

run_case() {   # name [env assignments...]
    local name="$1"; shift
    local project="$TMP/$name"
    mkdir -p "$project/.uncle/docs" "$project/.uncle/workflow/logs"
    cp "$TMP/plan.md" "$project/.uncle/docs/UPDATED_PROJECT_PLAN.md"
    (
        cd "$project" || exit 1
        ROOT="$TMP/root"; STATE_DIR="$project/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"
        export REQUEST_COPY="$project/request.json"
        for assignment in "$@"; do export "$assignment"; done
        . "$ROOT/scripts/lib/plan-scope.sh"
        eval "$(awk '/^parallel_merge_map\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/lib/parallel-implement.sh")"
        eval "$(awk '/^parallel_run_group\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/lib/parallel-implement.sh")"
        eval "$(awk '/^parallel_implement_run_groups\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/lib/parallel-implement.sh")"
        eval "$(awk '$0 == "_stagegate_parallel_build_step_prompt() {" {p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/stagegate.sh")"
        parallel_groups() { printf '1 2 3 4 5 6\n'; }
        supervision_validation_failed() { :; }
        require_file() { [[ -s "$1" ]] || { echo "missing $1" >&2; exit 1; }; }
        runtime_repair_marker="$project/none"
        plan_steps .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/implement-steps.txt"
        plan_step_owns .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/implement-owns.tsv"
        python3 "$ROOT/scripts/lib/implementation_notes.py" reset . > /dev/null 2>&1 || true
        parallel_implement_run_groups .uncle/docs/UPDATED_PROJECT_PLAN.md _stagegate_parallel_build_step_prompt "Isolated step" > "$project/out.txt" 2>&1
        echo $? > "$project/rc"
    )
}
steps_run() { python3 -c 'import json,sys; print(" ".join(str(s["number"]) for s in json.load(open(sys.argv[1]))["steps"]))' "$1/request.json"; }
owned_of() { python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["owned"].get(sys.argv[2], [])))' "$1/request.json" "$2"; }
has_owner() { python3 -c 'import json,sys; sys.exit(0 if sys.argv[2] in json.load(open(sys.argv[1]))["owned"] else 1)' "$1/request.json" "$2"; }

# Mode 0: the old fan-out, six workers, nothing merged, the prompts are the ones they always were.
run_case off PARALLEL_BUILDER_SUPPORTS_MERGE=1 WORKFLOW_IMPLEMENT_MERGE_APP=0
check "mode 0: the group runs" test "$(cat "$TMP/off/rc")" == 0
check "mode 0: all six steps run" test "$(steps_run "$TMP/off")" == "1 2 3 4 5 6"
check "mode 0: no step is told it has another" bash -c '! grep -q "Also assigned" "$1"/.uncle/workflow/parallel/prompts/*.md' _ "$TMP/off"

# Mode 1: the application steps (2, 3, 4) are one worker; scaffold and tests stay apart.
run_case app PARALLEL_BUILDER_SUPPORTS_MERGE=1 WORKFLOW_IMPLEMENT_MERGE_APP=1
check "mode 1: scaffold, one application worker and the test steps run" test "$(steps_run "$TMP/app")" == "1 2 5 6"
check "mode 1: the application worker owns every application file" test "$(owned_of "$TMP/app" 2)" == "src/calc.js src/App.jsx src/main.jsx src/styles.css"

# Default keeps separate unit and browser-test workers alongside implementation.
run_case default PARALLEL_BUILDER_SUPPORTS_MERGE=1
check "default: independent test workers run alongside scaffold and app" test "$(steps_run "$TMP/default")" == "1 2 5 6"
check "default: unit tests own only their declared file" test "$(owned_of "$TMP/default" 5)" == "tests/calc.test.js"
check "default: browser tests own only their declared file" test "$(owned_of "$TMP/default" 6)" == "e2e/theme.spec.js"
check "default: test workers receive shared contract guidance" grep -q 'targeted contract read' "$TMP/default/.uncle/workflow/parallel/prompts/step-5.md"

# Explicit mode 2: two workers -- the application, and everything that builds and verifies it.
run_case on PARALLEL_BUILDER_SUPPORTS_MERGE=1 WORKFLOW_IMPLEMENT_MERGE_APP=2
p="$TMP/on/.uncle/workflow/parallel/prompts"
check "default: the group runs" test "$(cat "$TMP/on/rc")" == 0
check "default: two workers run" test "$(steps_run "$TMP/on")" == "1 2"
check "default: the application worker owns every source file" test "$(owned_of "$TMP/on" 2)" == "src/calc.js src/App.jsx src/main.jsx src/styles.css"
check "default: the harness worker owns the scaffold and every test" test "$(owned_of "$TMP/on" 1)" == "package.json index.html .gitignore tests/calc.test.js e2e/theme.spec.js"
for absorbed in 3 4 5 6; do
    if has_owner "$TMP/on" "$absorbed"; then echo "FAIL: absorbed step $absorbed is still an owner (its files would be claimed twice)"; fails=$((fails + 1)); fi
done
check "default: the application worker's prompt carries steps 3 and 4" bash -c 'grep -q "Also assigned step 3" "$1" && grep -q "Also assigned step 4" "$1"' _ "$p/step-2.md"
check "default: ... including what they say and own" bash -c 'grep -q "styles the keypad" "$1" && grep -q "src/styles.css" "$1"' _ "$p/step-2.md"
check "default: the harness worker's prompt carries steps 5 and 6" bash -c 'grep -q "Also assigned step 5" "$1" && grep -q "Also assigned step 6" "$1"' _ "$p/step-1.md"
check "default: ... and their files are in its binding list" bash -c 'grep -q "tests/calc.test.js" "$1" && grep -q "e2e/theme.spec.js" "$1"' _ "$p/step-1.md"
check "default: the worker that owns package.json is told what it must declare" grep -q 'Dependencies (binding)' "$p/step-1.md"
check "default: a worker that does not own package.json is not" bash -c '! grep -q "Dependencies (binding)" "$1"' _ "$p/step-2.md"
check "default: the two workers' files do not overlap" bash -c '! grep -q "src/calc.js" "$1"' _ "$p/step-1.md"
check "default: no prompt is built for an absorbed step" bash -c 'for n in 3 4 5 6; do test ! -e "$1/step-$n.md" || exit 1; done' _ "$p"
check "default: the driver says what it merged" grep -q 'written together with their first' "$TMP/on/out.txt"
check "default: notes were recorded for the two workers only" bash -c 'grep -q "Isolated step 1" "$1/.uncle/docs/IMPLEMENTATION_NOTES.md" && grep -q "Isolated step 2" "$1/.uncle/docs/IMPLEMENTATION_NOTES.md" && ! grep -q "Isolated step 3" "$1/.uncle/docs/IMPLEMENTATION_NOTES.md"' _ "$TMP/on"

# A builder that cannot carry the extra text must never be handed a merge: its absorbed steps would silently vanish.
run_case nobuilder WORKFLOW_IMPLEMENT_MERGE_APP=1
check "unsupported builder: nothing merges" test "$(steps_run "$TMP/nobuilder")" == "1 2 3 4 5 6"

[[ "$fails" == 0 ]] && echo "parallel-merge-app-test.sh: all checks passed" || { echo "parallel-merge-app-test.sh: $fails failure(s)"; exit 1; }

#!/usr/bin/env bash
# Waves: tests and the defect-injection list run after the source, so their workers read that source and check their own work.
# A first-wave worker keeps the rules it always had. Real fan-out loop, prompt builder and request builder; only the executor is
# stubbed, to record what it was asked to run, whether dependencies were linked, and what had been installed by then.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

mkdir -p "$TMP/root" "$TMP/bin"
cp -R "$REPO/scripts" "$REPO/prompts" "$TMP/root/"
cat > "$TMP/root/scripts/lib/parallel_steps.py" <<'PY'
import json, os, sys
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_text())
project = Path(request['project'])
numbers = ' '.join(str(s['number']) for s in request['steps'])
installed = (project / 'node_modules').exists()
first = str(request['steps'][0]['number'])
owned = ';'.join(sorted(request['owned'].get(first, [])))
with open(os.environ['GROUP_LOG'], 'a') as log:
    log.write('group=%s link=%s node_modules=%s owned=%s\n' % (numbers, os.environ.get('UNCLE_LINK_DEPENDENCIES', ''), installed, owned))
prompt = project / '.uncle/workflow/parallel/prompts' / ('step-%s.md' % first)
if prompt.exists() and 'Build failure to fix' in prompt.read_text() and os.environ.get('FIX_WORKS') == '1':
    (project / '.fixed').write_text('1')
for step in request['steps']:
    note = project / step['note']
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes',
                                'changed_files': [{'path': 'file-%s.js' % step['number']}]}))
print(json.dumps({'elapsed_seconds': 0, 'step_seconds': {}, 'files': []}))
PY
# A stand-in npm that records the call and installs, or fails when told to.
cat > "$TMP/bin/npm" <<'SH'
#!/usr/bin/env bash
echo "npm $*" >> "$NPM_LOG"
if [[ "${1:-}" == run && "${2:-}" == build ]]; then
    if [[ "${BUILD_FAIL:-0}" == 1 && ! -e "$FAKE_PROJECT/.fixed" ]]; then
        echo 'Error: Rolldown failed to resolve import "react-dom/client" from "src/main.jsx".' >&2; exit 1
    fi
    exit 0
fi
[[ "${NPM_FAIL:-0}" != 1 ]] || { echo "registry unreachable" >&2; exit 1; }
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

run_case() {   # name [env assignments...]
    local name="$1"; shift
    local project="$TMP/$name"
    mkdir -p "$project/.uncle/docs" "$project/.uncle/workflow/logs"
    cp "${PLAN_OVERRIDE:-$TMP/plan.md}" "$project/.uncle/docs/UPDATED_PROJECT_PLAN.md"
    if [[ -n "${PREVIEW_HTML:-}" ]]; then mkdir -p "$project/.uncle/workflow/preview"; printf '%s\n' "$PREVIEW_HTML" > "$project/.uncle/workflow/preview/index.html"; fi
    printf '%s\n' "${PKG_JSON:-{\}}" > "$project/package.json"
    (
        cd "$project" || exit 1
        ROOT="$TMP/root"; STATE_DIR="$project/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"
        export GROUP_LOG="$project/groups.log" NPM_LOG="$project/npm.log" FAKE_PROJECT="$project" PATH="$TMP/bin:$PATH"
        for assignment in "$@"; do export "$assignment"; done
        . "$ROOT/scripts/lib/plan-scope.sh"
        for fn in parallel_group_wave parallel_module_steps parallel_group_writes_source parallel_fix_pass parallel_wave_build_gate parallel_install_dependencies parallel_merge_map parallel_run_group parallel_implement_run_groups; do
            [[ "$fn" != parallel_module_steps || -z "${OMIT_MODULE_FN:-}" ]] || continue
            eval "$(awk -v f="$fn" '$0 == f "() {" {p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/lib/parallel-implement.sh")"
        done
        # Every `_step_*` prompt helper the driver defines, so a section added by any of them shows up in the prompts tested here.
        for helper in $(grep -oE '^_step_[a-z_]+\(\) \{' "$ROOT/scripts/stagegate.sh" | sed 's/() {//'); do
            eval "$(awk -v f="$helper" '$0 == f "() {" {p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/stagegate.sh")"
        done
        eval "$(awk '$0 == "_stagegate_parallel_build_step_prompt() {" {p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/stagegate.sh")"
        parallel_groups() { printf '%b' "${TEST_GROUPS:-1 2 3 4\\n5 6\\n7\\n}"; }
        supervision_validation_failed() { :; }
        require_file() { [[ -s "$1" ]] || { echo "missing $1" >&2; exit 1; }; }
        runtime_repair_marker="$project/none"
        plan_steps .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/implement-steps.txt"
        plan_step_owns .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/implement-owns.tsv"
        # The real driver keeps ownership in implement-owns.tsv and leaves it out of the step text (run 19): do the same when asked.
        if [[ -n "${STEP_TEXT_WITHOUT_OWNS:-}" ]]; then sed -E 's/[[:space:]]*Owns:.*$//' "$STATE_DIR/implement-steps.txt" > "$STATE_DIR/steps.stripped" && mv "$STATE_DIR/steps.stripped" "$STATE_DIR/implement-steps.txt"; fi
        python3 "$ROOT/scripts/lib/implementation_notes.py" reset . > /dev/null 2>&1 || true
        parallel_implement_run_groups .uncle/docs/UPDATED_PROJECT_PLAN.md _stagegate_parallel_build_step_prompt "Isolated step" > "$project/out.txt" 2>&1
        echo $? > "$project/rc"
    )
}
prompt() { cat "$TMP/$1/.uncle/workflow/parallel/prompts/step-$2.md"; }
has() { grep -q -F -- "$2" <<< "$(prompt "$1" "$3")"; }
lacks() { ! grep -q -F -- "$2" <<< "$(prompt "$1" "$3")"; }
# The base prompt (implement.md) carries one copy of the acceptance-handoff section and the shared contract adds a second, so the
# heading alone cannot show the contract kept it: count it.
handoffs() { prompt "$1" "$2" | grep -c -F -- "## Prepare the acceptance handoff now"; }

run_case waves
check "the groups run" test "$(cat "$TMP/waves/rc")" == 0

# First wave: unchanged rules.
check "wave 0: told not to read sibling files" has waves "may not exist yet" 2
check "wave 0: told not to run tests" has waves "Do not run tests, builds or checks" 2
check "wave 0: no self-check section" lacks waves "Speed and self-check" 2
check "wave 0: the blind contract stands" has waves "targeted contract read" 2

# Tests (wave 1) and the mutation list (wave 2): read the source, check your own work.
for step in 5 6 7; do
    check "step $step: self-check section" has waves "Speed and self-check" $step
    check "step $step: no longer told siblings may not exist" lacks waves "may not exist yet" $step
    check "step $step: no longer told to run nothing" lacks waves "Do not run tests, builds or checks. The driver" $step
    check "step $step: told the source is already merged" has waves "already merged into the project" $step
    check "step $step: runs only its own vitest file" has waves "npx vitest run <your file>" $step
    check "step $step: checks mutation find strings by count" has waves "grep -c" $step
    check "step $step: runs its own browser spec on a port of its own" has waves "E2E_PORT=$((43000 + step)) npx playwright test <your spec>" $step
    check "step $step: browser output goes outside the project" has waves "--output=/tmp/uncle-pw-step-$step" $step
    check "step $step: the browser run is capped" has waves "--global-timeout=60000" $step
    check "step $step: builds before it runs the spec" has waves "Run the project's build first" $step
    check "step $step: a failed build means no spec run" has waves "If the build fails, do not run the spec" $step
    check "step $step: the build error is recorded, not edited around" has waves "record the build error as an unresolved concern" $step
    check "step $step: never installs a browser" has waves "install anything and do not run it" $step
    check "step $step: no placeholder is left in the prompt" lacks waves "__PORT__" $step
    check "step $step: told not to edit the source" has waves "do not edit it" $step
    check "step $step: keeps both copies of the acceptance handoff section" test "$(handoffs waves $step)" == 2
    check "step $step: the blind contract is gone" lacks waves "targeted contract read" $step
done
check "wave 0 keeps both copies of the acceptance handoff section" test "$(handoffs waves 2)" == 2

# No two workers are given the same port or output directory.
check "workers 5 and 6 get different ports" bash -c '! diff <(grep -o "E2E_PORT=[0-9]*" "$1") <(grep -o "E2E_PORT=[0-9]*" "$2") > /dev/null' _ "$TMP/waves/.uncle/workflow/parallel/prompts/step-5.md" "$TMP/waves/.uncle/workflow/parallel/prompts/step-6.md"
check "worker 5 is not given worker 6's port" lacks waves "E2E_PORT=$((43000 + 6))" 5

# Every worker, in every wave, is told its exact sandbox and that the project root is not its own.
check "a non-module worker is not given the module plan-read rule" lacks waves "one targeted read" 2
for step in 2 5 6 7; do
    check "step $step: told its exact sandbox" has waves "$TMP/waves/.uncle/workflow/parallel/step-$step" $step
    check "step $step: told the project root is not its own" has waves "never write there" $step
done

# The early preview is NOT offered to any worker (run 27): it was built from the brief before the plan was reviewed, its palette and
# fonts (#ffd166, Courier New) were copied into the stylesheet over the plan's, and a repair followed. Even with a page present, no step
# prompt carries it, markup and style steps included.
STEP_TEXT_WITHOUT_OWNS=1 PREVIEW_HTML='<style>body{background:#ffd166;font-family:"Courier New"}</style><!-- PREVIEW-MARKER -->' run_case preview
check "preview: the groups run" test "$(cat "$TMP/preview/rc")" == 0
for step in 1 2 3 4 5 6 7; do
    check "step $step: not shown the early preview" lacks preview "PREVIEW-MARKER" $step
    check "step $step: no visual-reference section" lacks preview "Visual reference from the early preview" $step
    check "step $step: not told to take palette or fonts from a preview" lacks preview "Take its look from it" $step
done
check "the markup and style steps still get the layout rule" has preview "Layout rule for variable text (binding)" 4
check "the driver no longer has a preview-reference helper" bash -c '! grep -q "_step_preview_reference" "$1/scripts/stagegate.sh"' _ "$REPO"
check "and does not read the preview page into a prompt" bash -c '! grep -q "preview/index.html" "$1/scripts/stagegate.sh" || ! sed -n "/^_stagegate_parallel_build_step_prompt() {/,/^}/p" "$1/scripts/stagegate.sh" | grep -q "preview/index.html"' _ "$REPO"

# Steps that write markup or styles are given the plan's own rows that fix exact theme values; no other step is, and nothing is invented when
# the plan fixes none (run 27: a palette and a Courier font of the worker's own; run 29: a font stack without Fredoka).
{ cat "$TMP/plan.md"; cat <<'ROWS'

## 6. Behaviors

| B-12 | Page load | Body chocolate #4B2E1E, buttons rotate #CC5500/#E1AD01, font stack Righteous, Fredoka, Arial Rounded MT Bold, sans-serif | None |
| I-10 | Theme colors are CSS custom properties with exact values #CC5500, #E1AD01 and #568203. | theme |
| I-11 | The font stack is 'Righteous','Fredoka','Arial Rounded MT Bold',sans-serif. | theme |
| I-4 | Backspace in Error is ignored. | engine |
| I-14 | Body font-family lists Cooper Black, Pacifico, Baloo 2, ui-rounded, system-ui, sans-serif; buttons are rounded. | theme |
| I-15 | The page uses a Typeface of Georgia for the title only. | theme |
| I-16 | Two font families are bundled with the app. | theme |
| I-13 | The display font stack is 'Nunito','Arial Rounded MT Bold',sans-serif with no network fetch. | theme |
| DI-7 | Background changed from #4B2E1E to a stock purple | tests/e2e/theme.spec.js | Rejected |
| T-4 | Theme test: colors #CC5500 compared | tests/e2e/theme.spec.js |
ROWS
} > "$TMP/plan-theme.md"
STEP_TEXT_WITHOUT_OWNS=1 PLAN_OVERRIDE="$TMP/plan-theme.md" run_case theme
check "theme: the groups run" test "$(cat "$TMP/theme/rc")" == 0
for step in 3 4; do
    check "step $step (markup or styles): given the plan's theme values" has theme "Theme values the plan fixes (binding)" $step
    check "step $step: given the hex row verbatim" has theme "Body chocolate #4B2E1E, buttons rotate #CC5500/#E1AD01" $step
    check "step $step: given the font stack row verbatim" has theme "font stack Righteous, Fredoka, Arial Rounded MT Bold, sans-serif" $step
    check "step $step: given the invariant rows too" has theme "exact values #CC5500, #E1AD01 and #568203" $step
    check "step $step: a row that fixes only a font stack is included" has theme "'Nunito','Arial Rounded MT Bold',sans-serif" $step
    check "step $step: a font-family row with no hex code or font-stack wording is included (run 31)" has theme "font-family lists Cooper Black, Pacifico, Baloo 2" $step
    check "step $step: a typeface row is included" has theme "Typeface of Georgia" $step
    check "step $step: a font families row is included" has theme "Two font families are bundled" $step
    check "step $step: told to use them verbatim" has theme "Use those values verbatim" $step
    check "step $step: told not to add a font ahead of the plan's" has theme "add a font ahead of the plan's" $step
    check "step $step: a row about something else is not included" lacks theme "Backspace in Error is ignored" $step
    check "step $step: a mutation row is not included" lacks theme "stock purple" $step
    check "step $step: a test row is not included" lacks theme "Theme test: colors" $step
done
for step in 1 2 5 6 7; do
    check "step $step (no markup or styles): not given theme values" lacks theme "Theme values the plan fixes" $step
done
check "a plan that fixes no theme values adds no section" lacks waves "Theme values the plan fixes" 3

# Test steps read the plan's test rows once and write one test per row (run 26: a browser spec skipped T-4, T-5 and T-9).
for step in 5 6; do
    check "step $step: told to make one targeted read of the plan" has waves "makes one targeted read of" $step
    check "step $step: and told which document and rows" has waves "the test (T-n) rows that live in your files" $step
    check "step $step: told a test per T-n row, none skipped" has waves "Write one test for every such T-n row, none skipped" $step
    check "step $step: still told not to read the other documents" has waves "Do not read the full requirements, preflight report, or rendered" $step
done
check "wave 0 source step is not given the test-row rule" lacks waves "Write one test for every such T-n row" 2

# Steps that write markup or styles are given the layout rule; no other step is (run 26: a fixed font size with an ellipsis clipped the result).
for step in 3 4; do
    check "step $step (markup or styles): given the layout rule" has waves "Layout rule for variable text (binding)" $step
    check "step $step: told not to rely on clipping or an ellipsis" has waves "do not give such text a fixed font size with \`overflow: hidden\` or an ellipsis" $step
    check "step $step: told every required character stays visible" has waves "keep every required character visible" $step
done
for step in 1 2 5 6 7; do
    check "step $step (no markup or styles): not given the layout rule" lacks waves "Layout rule for variable text" $step
done

# Dependencies are linked only for the later waves, and are installed before the first of them.
check "wave 0 group is not linked" grep -q "group=1 2 3 4 link= " "$TMP/waves/groups.log"
check "wave 1 group is linked" grep -q "group=5 6 link=1 " "$TMP/waves/groups.log"
check "wave 2 group is linked" grep -q "group=7 link=1 " "$TMP/waves/groups.log"
check "nothing is installed when the source wave runs" grep -q "group=1 2 3 4 link= node_modules=False" "$TMP/waves/groups.log"
check "dependencies exist when the test wave runs" grep -q "group=5 6 link=1 node_modules=True" "$TMP/waves/groups.log"
check "npm installed exactly once" test "$(wc -l < "$TMP/waves/npm.log" | tr -d ' ')" == 1
check "the install is the quiet one" grep -q "npm install --no-audit --no-fund --loglevel=error" "$TMP/waves/npm.log"

# A group that mixes source and tests (waves off) is a first wave: its source is not written yet, so nobody in it may be told
# to read it, to run tests, or to expect installed dependencies.
run_case mixed 'TEST_GROUPS=1 2 3 4 5 6 7\n'
check "mixed group: runs" test "$(cat "$TMP/mixed/rc")" == 0
check "mixed group: not linked" grep -q "group=1 2 3 4 5 6 7 link= " "$TMP/mixed/groups.log"
check "mixed group: nothing installed" test ! -e "$TMP/mixed/npm.log"
for step in 2 5 7; do
    check "mixed group, step $step: the first-wave rules" has mixed "Do not run tests, builds or checks" $step
    check "mixed group, step $step: no self-check section" lacks mixed "Speed and self-check" $step
done

# Vertical modules: each owns its source and its own tests behind a contract.
cat > "$TMP/modules.md" <<'PLAN'
# Updated plan

## 12. Implementation steps

1. Scaffold. Owns: `package.json`, `.gitignore`
2. Engine module. Owns: `src/engine/engine.js`, `src/engine/engine.test.js`, `src/engine/CONTRACT.md`
3. Keyboard module. Owns: `src/keyboard/keyboard.js`, `src/keyboard/keyboard.test.js`
4. Shell. Owns: `src/App.jsx`, `src/main.jsx`, `index.html`
5. Browser specs. Owns: `e2e/calc.spec.js`
6. Mutation list. Owns: `tests/mutations/list.mjs`
PLAN
PLAN_OVERRIDE="$TMP/modules.md" run_case modules 'TEST_GROUPS=1\n2 3 4\n5\n6\n'
check "modules: the groups run" test "$(cat "$TMP/modules/rc")" == 0
for step in 2 3; do
    check "module $step: told its files are one module" has modules "Your owned files are one module" $step
    check "module $step: runs only its own unit test file" has modules "npx vitest run <your test file>" $step
    check "module $step: not told to run nothing" lacks modules "Do not run tests, builds or checks. The driver" $step
    check "module $step: told to stub other modules" has modules "Stub it in your tests" $step
    check "module $step: told its neighbours may not exist" has modules "may not exist yet" $step
    check "module $step: has the module contract" has modules "Other modules and the shell are written at the same time" $step
    check "module $step: not given the later-wave contract" lacks modules "already merged into the project" $step
    check "module $step: told to read the plan's rows once" has modules "one targeted read of \`.uncle/docs/UPDATED_PROJECT_PLAN.md\`" $step
    check "module $step: told a test per row, do-nothing cases included" has modules "Write a test case for every such row, including each case where an input does nothing" $step
    check "module $step: still told not to read the other documents" has modules "Do not read the full requirements, preflight report" $step
    check "module $step: browser specs are not its to run" has modules "A browser spec is not for you to run" $step
    check "module $step: keeps both copies of the acceptance handoff section" test "$(handoffs modules $step)" == 2
done
for step in 1 4; do
    check "step $step (not a module): the first-wave rules" has modules "Do not run tests, builds or checks" $step
    check "step $step (not a module): no module text" lacks modules "Your owned files are one module" $step
done
check "the scaffold wave is not linked" grep -q "group=1 link= node_modules=False" "$TMP/modules/groups.log"
check "modules and shell are linked" grep -q "group=2 3 4 link=1 node_modules=True" "$TMP/modules/groups.log"
check "nothing is installed before the scaffold has landed" grep -q "group=1 link= node_modules=False" "$TMP/modules/groups.log"
check "npm installed once, before the modules" test "$(wc -l < "$TMP/modules/npm.log" | tr -d ' ')" == 1
check "the browser spec wave is a later wave" has modules "Speed and self-check" 5

# A detector that is missing or fails must not turn install and link on: nothing is a module until a step number says so.
PLAN_OVERRIDE="$TMP/modules.md" OMIT_MODULE_FN=1 run_case nodetector 'TEST_GROUPS=1\n2 3 4\n'
check "no detector: the groups still run" test "$(cat "$TMP/nodetector/rc")" == 0
check "no detector: modules are not linked" grep -q "group=2 3 4 link= " "$TMP/nodetector/groups.log"
check "no detector: nothing is installed" test ! -e "$TMP/nodetector/npm.log"
check "no detector: the first-wave rules apply" has nodetector "Do not run tests, builds or checks" 2

# With waves off a module is just a step: no module prompt, no install, no link.
PLAN_OVERRIDE="$TMP/modules.md" run_case waves_off 'TEST_GROUPS=1 2 3 4 5 6\n' WORKFLOW_IMPLEMENT_TEST_WAVES=0
check "waves off: runs" test "$(cat "$TMP/waves_off/rc")" == 0
check "waves off: no module prompt" lacks waves_off "Your owned files are one module" 2
check "waves off: not linked" grep -q "link= " "$TMP/waves_off/groups.log"
check "waves off: nothing installed" test ! -e "$TMP/waves_off/npm.log"

# The build gate after a wave that wrote source: build in a copy; if it fails, one fix pass by the worker that owns the wave's files.
BUILD='{"scripts":{"build":"vite build"}}'
builds() { if [[ -e "$TMP/$1/npm.log" ]]; then grep -c "^npm run build" "$TMP/$1/npm.log" || true; else echo 0; fi; }
PKG_JSON="$BUILD" run_case gate_ok
check "gate, build passes: the groups run" test "$(cat "$TMP/gate_ok/rc")" == 0
check "gate, build passes: built once, after the source wave only" test "$(builds gate_ok)" == 1
check "gate, build passes: reported" grep -q "Wave build check passed" "$TMP/gate_ok/out.txt"
check "gate, build passes: no fix group" test "$(grep -c "group=1 link=1" "$TMP/gate_ok/groups.log" || true)" == 0

PKG_JSON="$BUILD" BUILD_FAIL=1 FIX_WORKS=1 run_case gate_fix
check "gate, fixable: the groups run" test "$(cat "$TMP/gate_fix/rc")" == 0
check "gate, fixable: built twice, failing then fixed" test "$(builds gate_fix)" == 2
check "gate, fixable: failure announced" grep -q "Wave build check failed" "$TMP/gate_fix/out.txt"
check "gate, fixable: fix announced" grep -q "the build is fixed" "$TMP/gate_fix/out.txt"
check "gate, fixable: one fix group ran, linked to the dependencies" grep -q "group=1 link=1 node_modules=True" "$TMP/gate_fix/groups.log"
check "gate, fixable: the fix worker owns the files of every step in the wave" grep -q "group=1 link=1 .*owned=.*package.json.*src/App.jsx.*src/calc.js\|group=1 link=1 .*owned=.*src/App.jsx" "$TMP/gate_fix/groups.log"
check "gate, fixable: its prompt carries the build error" grep -q 'Rolldown failed to resolve import "react-dom/client"' "$TMP/gate_fix/.uncle/workflow/parallel/prompts/step-1.md"
check "gate, fixable: its prompt says to fix only its own files" grep -q "editing only the files you own" "$TMP/gate_fix/.uncle/workflow/parallel/prompts/step-1.md"
check "gate, fixable: the later groups still ran" grep -q "group=5 6 " "$TMP/gate_fix/groups.log"

PKG_JSON="$BUILD" BUILD_FAIL=1 FIX_WORKS=0 run_case gate_stuck
check "gate, unfixable: the build still carries on" test "$(cat "$TMP/gate_stuck/rc")" == 0
check "gate, unfixable: exactly one fix pass, not a loop" test "$(grep -c "group=1 link=1" "$TMP/gate_stuck/groups.log")" == 1
check "gate, unfixable: built twice and no more" test "$(builds gate_stuck)" == 2
check "gate, unfixable: says it still fails" grep -q "the build still fails" "$TMP/gate_stuck/out.txt"
check "gate, unfixable: the later groups still ran" grep -q "group=7 " "$TMP/gate_stuck/groups.log"

run_case gate_nobuild BUILD_FAIL=1
check "no build script: nothing is built" test "$(builds gate_nobuild)" == 0
check "no build script: no fix group" test "$(grep -c "group=1 link=1" "$TMP/gate_nobuild/groups.log" || true)" == 0

PKG_JSON="$BUILD" run_case gate_off WORKFLOW_WAVE_BUILD_GATE=0 BUILD_FAIL=1
check "gate off: nothing is built" test "$(builds gate_off)" == 0

PKG_JSON="$BUILD" run_case gate_waves_off WORKFLOW_IMPLEMENT_TEST_WAVES=0 BUILD_FAIL=1 'TEST_GROUPS=1 2 3 4 5 6 7\n'
check "waves off: nothing is built" test "$(builds gate_waves_off)" == 0

# Only a wave that wrote source is built: the scaffold alone and the test waves are not.
PKG_JSON="$BUILD" run_case gate_scaffold_only 'TEST_GROUPS=1\n5 6\n7\n'
check "scaffold and test waves only: nothing is built" test "$(builds gate_scaffold_only)" == 0

# Off switch, up-to-date dependencies, and a failing install.
run_case off WORKFLOW_WAVE_INSTALL=0
check "install off: the groups still run" test "$(cat "$TMP/off/rc")" == 0
check "install off: npm is never called" test ! -e "$TMP/off/npm.log"
check "install off: the test wave still gets the link flag" grep -q "group=5 6 link=1 node_modules=False" "$TMP/off/groups.log"

run_case failing NPM_FAIL=1
check "failing install: the build goes on" test "$(cat "$TMP/failing/rc")" == 0
check "failing install: all three groups ran" test "$(wc -l < "$TMP/failing/groups.log" | tr -d ' ')" == 3
check "failing install: the failure is reported" grep -q "Dependency install before the next wave failed" "$TMP/failing/out.txt"

# The change workflow keeps its groups whole by default (regression-first plans write tests that fail before the fix); the new-application
# driver splits them. The line is taken from change-workflow.sh itself, so this cannot drift from it.
line="$(grep -E '^export WORKFLOW_IMPLEMENT_TEST_WAVES=' "$REPO/scripts/change-workflow.sh")"
default_value() { env -u WORKFLOW_IMPLEMENT_TEST_WAVES "$@" bash -c "$line; printf %s \"\$WORKFLOW_IMPLEMENT_TEST_WAVES\""; }
check "the change workflow has the line" test -n "$line"
check "change workflow: waves off by default" test "$(default_value)" == 0
check "change workflow: an explicit 1 is kept" test "$(WORKFLOW_IMPLEMENT_TEST_WAVES=1 bash -c "$line; printf %s \"\$WORKFLOW_IMPLEMENT_TEST_WAVES\"")" == 1
check "the new-application driver sets no such default" bash -c '! grep -q "^export WORKFLOW_IMPLEMENT_TEST_WAVES" "$1"' _ "$REPO/scripts/stagegate.sh"

if [[ "$fails" -ne 0 ]]; then echo "wave-prompts-test.sh: $fails failed"; exit 1; fi
echo "wave-prompts-test.sh: all checks passed"

#!/usr/bin/env bash
set -euo pipefail

# Tests lane runner (scripts/lib/tests-stage.sh). Hermetic: a stub stands in for the agent.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"      # the scratch project (a git repo the stage inspects)
SCR="$(mktemp -d)"      # test scratch files, kept out of that repo so they are not mistaken for changes
trap 'rm -rf "$TMP" "$SCR"' EXIT
FAILED=0 COUNT=0
ok() { COUNT=$((COUNT + 1)); }
bad() { COUNT=$((COUNT + 1)); FAILED=$((FAILED + 1)); echo "FAIL: $1"; }
expect() { if eval "$2"; then ok; else bad "$1"; fi; }

cd "$TMP"
git init -q . && git config user.email t@t && git config user.name t
echo seed > README.md && git add . && git commit -qm seed
mkdir -p .uncle/workflow tests
STATE_DIR="$PWD/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"; mkdir -p "$LOG_DIR"
PLAN_DOC=plan.md
cat > plan.md <<'PLAN'
Browser tests with playwright. Defect injection is required.
PLAN
printf 'tests/\nvitest.config.js\n' > "$STATE_DIR/tests.paths.fixture"

. "$ROOT/scripts/lib/sha256.sh"
. "$ROOT/scripts/lib/verification-integrity.sh"
. "$ROOT/scripts/lib/tests-stage.sh"
set_state() { printf '%s\n' "$1" > "$STATE_DIR/state"; }
gate_prompt() { printf '%s' "$1"; }
verify_commands() { printf '%s\n' "${FAKE_COMMANDS:-npx vitest run}"; }
verification_paths() { cat "$STATE_DIR/tests.paths.fixture"; }
export UNATTENDED=1 WORKFLOW_TESTS=1
# The driver's python3 is a shell function (scripts/lib/pyhost.sh) that does `command python3 ...; return`. Under macOS bash 3.2 an
# async function that calls one dies silently, so the stub agent calls it the way run_claude does.
python3() { local dir="${UNCLE_PY_HOST_DIR:-}"; if [[ -z "$dir" ]]; then command python3 "$@"; return; fi; }

# Stub agent: each lane writes files; the harness must finish before the others begin.
run_claude() {
    local lane="${2#tests-}" dir="$STATE_DIR/tests"
    python3 -c 'pass'
    echo "$lane reuse=${UNCLE_RUNNER_REUSE:-unset}" >> "$STATE_DIR/reuse.log"
    echo "$lane start $(date +%s%N)" >> "$STATE_DIR/order.log"
    case "$lane" in
        complete) if [[ -n "${COMPLETE_BAD_ONCE:-}" && ! -e "$STATE_DIR/complete.bad.done" ]]; then
                      touch "$STATE_DIR/complete.bad.done"; complete_list
                      sed -i.bak "s/find: 'beta'/find: 'a'/" tests/mutations/list.mjs; rm -f tests/mutations/list.mjs.bak     # 'a' occurs many times
                  elif [[ -n "${COMPLETE_DROPS_INTENT:-}" ]]; then
                      complete_list; sed -i.bak "s/expected_failing_tests: \['T-2'\]/expected_failing_tests: ['T-99']/" tests/mutations/list.mjs; rm -f tests/mutations/list.mjs.bak
                  else complete_list; fi ;;
        harness) echo cfg > vitest.config.js; mkdir -p helpers; echo h > helpers/dom.js; printf 'vitest.config.js\nhelpers/dom.js\n' > "$dir/lane-harness.files" ;;
        unit)    sleep "${UNIT_SLEEP:-0}"; [[ -f vitest.config.js ]] || { echo "unit began before harness finished" >> "$STATE_DIR/errors.log"; }
                 echo u > tests/unit.test.js; printf 'tests/unit.test.js\n' > "$dir/lane-unit.files" ;;
        e2e)     mkdir -p tests/e2e; echo e > tests/e2e/a.spec.js; printf 'tests/e2e/a.spec.js\n%s\n' "${E2E_EXTRA:-}" | sed '/^$/d' > "$dir/lane-e2e.files" ;;
        mutation) mkdir -p tests/mutations
                  cat > tests/mutations/list.mjs <<'JS'
export const defects = [
  { id: 'DI-1', breaks: ['I-1'], target: 'src/engine.js', spec: 'tests/unit.test.js', expected_failing_tests: ['T-1'] },
  { id: 'DI-2', breaks: ['I-2'], target: 'src/engine.js', spec: 'tests/unit.test.js', expected_failing_tests: ['T-2'] },
];
export default defects;
JS
                  printf 'tests/mutations/list.mjs\n' > "$dir/lane-mutation.files"; printf 'tests/mutations/list.mjs\n' > "$dir/lane-mutation.mutable" ;;
    esac
    echo "notes for $lane" > "$dir/lane-$lane.md"
    sleep 1
    echo "$lane end $(date +%s%N)" >> "$STATE_DIR/order.log"
}

complete_list() {
    mkdir -p src
    [[ -f src/engine.js ]] || : > src/engine.js
    grep -q alpha src/engine.js || echo alpha >> src/engine.js
    grep -q beta src/engine.js || echo beta >> src/engine.js
    cat > tests/mutations/list.mjs <<'JS'
export const defects = [
  { id: 'DI-1', breaks: ['I-1'], target: 'src/engine.js', file: 'src/engine.js', find: 'alpha', replace: 'omega', spec: 'tests/unit.test.js', expected_failing_tests: ['T-1'] },
  { id: 'DI-2', breaks: ['I-2'], target: 'src/engine.js', file: 'src/engine.js', find: 'beta', replace: 'gamma', spec: 'tests/unit.test.js', expected_failing_tests: ['T-2'] },
];
export default defects;
JS
}
expect "lane selection picks e2e and mutation from the plan" \
    '[[ "$(tests_lanes | tr "\n" " ")" == "harness unit e2e mutation " ]]'
expect "explicit lane override still puts harness first" \
    '[[ "$(WORKFLOW_TESTS_LANES="unit" tests_lanes | tr "\n" " ")" == "harness unit " ]]'
expect "a stray flag value is not silently on" \
    '! (WORKFLOW_TESTS="1." tests_enabled 2>/dev/null)'

# Red check: a vacuous suite (every test command passes) is refused.
FAKE_COMMANDS='true # vitest'
expect "all-pass suite is vacuous" '! tests_red_check "$SCR/red.md" && grep -q vacuous "$SCR/red.md"'
FAKE_COMMANDS='false # vitest'
expect "failing suite is red" 'tests_red_check "$SCR/red.md" && grep -q "failed as expected" "$SCR/red.md"'
FAKE_COMMANDS='make build'
expect "non-test commands are not run" 'tests_red_check "$SCR/red.md" && grep -q "No test commands" "$SCR/red.md"'

# Full stage, lanes concurrent after the harness.
FAKE_COMMANDS='false # vitest'
rm -rf "$STATE_DIR/tests"
( tests_stage ) > "$SCR/stage.out" 2>&1 || { cat "$SCR/stage.out"; bad "stage failed on a clean run"; }
cp tests/mutations/list.mjs "$SCR/list.unfinished.mjs"   # the lane's version: intent only
complete_list                                                # what the implementation step does once the source exists
expect "stage freezes and advances to IMPLEMENT" '[[ "$(cat "$STATE_DIR/state")" == IMPLEMENT && -s "$(tests_lock)" ]]'
expect "a helper the plan did not list is claimed, allowed and frozen" 'grep -q "helpers/dom.js" "$(tests_lock)"'
expect "harness finished before unit started" '[[ ! -s "$STATE_DIR/errors.log" ]]'
expect "assembled notes name every lane" 'grep -q "Lane: e2e" .uncle/docs/TESTS_NOTES.md && grep -q "Lane: mutation" .uncle/docs/TESTS_NOTES.md'
s() { awk -v l="$1" '$1 == l && $2 == "start" { print $3 }' "$STATE_DIR/order.log"; }
e() { awk -v l="$1" '$1 == l && $2 == "end" { print $3 }' "$STATE_DIR/order.log"; }
expect "unit, e2e and mutation overlap in time" '(( $(s e2e) < $(e unit) && $(s mutation) < $(e unit) && $(s unit) < $(e e2e) ))'

# Freeze: edit, delete, add.
expect "unchanged tests pass the frozen check" 'tests_check_frozen 2>/dev/null'
echo changed > tests/unit.test.js
expect "edited frozen test is rejected" '! tests_check_frozen 2>/dev/null'
echo u > tests/unit.test.js; echo n > tests/extra.test.js
expect "new test files are allowed" 'tests_check_frozen 2>/dev/null'
echo changed > helpers/dom.js
expect "an edited unlisted helper is rejected" '! tests_check_frozen 2>/dev/null'
echo h > helpers/dom.js
rm tests/unit.test.js
expect "deleted frozen test is rejected" '! tests_check_frozen 2>/dev/null'

# Ownership: a file listed by two lanes, and a production file nobody claimed.
reset() { rm -rf "$STATE_DIR/tests" "$STATE_DIR/tests.lock" tests src .uncle/docs; git checkout -q . ; git clean -fdq -e .uncle; mkdir -p tests; echo "Browser tests with playwright. Defect injection is required." > plan.md; printf "tests/\\nvitest.config.js\\n" > "$STATE_DIR/tests.paths.fixture"; }
reset
E2E_EXTRA='tests/unit.test.js'
( tests_stage ) > "$SCR/dup.out" 2>&1 && dup_status=0 || dup_status=$?
expect "a file claimed by two lanes is rejected" '[[ "$dup_status" != 0 ]] && grep -q "listed by lanes" "$SCR/dup.out"'
E2E_EXTRA=''
reset
run_claude_orig="$(declare -f run_claude)"
run_claude() { eval "$run_claude_orig"; :; }
eval "${run_claude_orig/run_claude/stub_agent}"
run_claude() { stub_agent "$@"; [[ "${2#tests-}" != unit ]] || { mkdir -p src; echo prod > src/engine.js; }; }
expect "production code written during authoring is rejected" '! ( tests_stage ) > "$SCR/stray.out" 2>&1 && grep -q "src/engine.js changed during test authoring" "$SCR/stray.out"'

# Ownership handed to implementation steps: frozen tests are removed from every step, and steps left with nothing are skipped.
reset
run_claude() { stub_agent "$@"; }   # the previous test left the stray-production stub installed
( tests_stage ) > "$SCR/own.out" 2>&1 || true
cp tests/mutations/list.mjs "$SCR/list.unfinished.mjs"; complete_list
printf '1\tpackage.json\n1\tvitest.config.js\n2\tsrc/engine.js\n2\ttests/unit.test.js\n3\ttests/e2e/a.spec.js\n4\ttests/mutations/list.mjs\n5\ttests/mutations/run.mjs\n' > "$SCR/owns.tsv"
expect "filter drops frozen paths from every step" '[[ "$(tests_filter_owns < "$SCR/owns.tsv" | tr "\t\n" ": ")" == "1:package.json 2:src/engine.js 4:tests/mutations/list.mjs 5:tests/mutations/run.mjs " ]]'
expect "steps whose every path is frozen are skipped" '[[ "$(tests_frozen_only_steps < "$SCR/owns.tsv" | sort | tr "\n" " ")" == "3 " ]]'
expect "a step is told which of its files are frozen" '[[ "$(tests_frozen_for_step 2 < "$SCR/owns.tsv")" == "- \`tests/unit.test.js\`" ]]'
# A protected path that was absent at freeze time (e.g. the driver-supplied runner) may appear later without tripping the check.
printf 'ABSENT\ttests/mutations/run.mjs\n' >> "$(tests_lock)"
mkdir -p tests/mutations; echo r > tests/mutations/run.mjs
expect "an ABSENT-at-freeze path appearing later is not a violation" 'tests_check_frozen 2>/dev/null'

# Completable files: the defect list is not hash-frozen, but its intent is.
rm -f tests/mutations/run.mjs
expect "the completable list is not in the freeze set" '! grep -q "list.mjs" "$(tests_lock)" && [[ -s "$STATE_DIR/tests/intent.tsv" ]]'
expect "the step that owns the list is told it is completable" '[[ "$(tests_mutable_for_step 4 < "$SCR/owns.tsv")" == "- \`tests/mutations/list.mjs\`" ]]'
cp "$SCR/list.unfinished.mjs" tests/mutations/list.mjs
expect "an unfinished list (no file/find) is rejected" '! tests_check_frozen 2>"$SCR/intent.err" && grep -q "no exact .file. + .find." "$SCR/intent.err"'
complete_list
expect "a completed list with the same intent passes" 'tests_check_frozen 2>/dev/null'
sed -i.bak "s/expected_failing_tests: \['T-2'\]/expected_failing_tests: ['T-9']/" tests/mutations/list.mjs; rm -f tests/mutations/list.mjs.bak
expect "changing a defect's expected tests is rejected" '! tests_check_frozen 2>/dev/null'
grep -v "DI-2" tests/mutations/list.mjs | sed 's/^  {\(.*\)},$/  {\1},/' > tests/mutations/list2.mjs; mv tests/mutations/list2.mjs tests/mutations/list.mjs
expect "dropping a defect is rejected" '! tests_check_frozen 2>/dev/null'

# Amendments: a wrong frozen test can be changed, with a reason; without one it cannot.
echo amended > tests/unit.test.js
complete_list
printf 'tests/unit.test.js\t\n' > "$(tests_amendments_file)"
expect "an amendment with no reason is not accepted" '! tests_check_frozen 2>/dev/null'
printf 'tests/unit.test.js\tR-3 says rounding is to 12 digits, the test asserted 10\n' > "$(tests_amendments_file)"
expect "an amendment with a reason is accepted and logged" 'tests_check_frozen >/dev/null 2>&1 && grep -q "rounding" "$STATE_DIR/tests/amendments.log"'
expect "the lock is refreshed to the amended content" 'tests_check_frozen 2>/dev/null'


# ---------------------------------------------------------------------------------------------------------------------------------
# Concurrent mode: the lanes run in the background while the implementation steps run; join is the barrier.
reset
run_claude() { stub_agent "$@"; }
unset E2E_EXTRA
export WORKFLOW_TESTS_CONCURRENT=1
printf 'tests/\nvitest.config.js\ntests/mutations/run.mjs\n' > "$STATE_DIR/tests.paths.fixture"
: > "$STATE_DIR/order.log"
t0=$SECONDS
tests_background_start > "$SCR/bg.out" 2>&1
expect "background start returns at once (it does not wait for the lanes)" '(( SECONDS - t0 <= 1 )) && tests_authoring_running'
# Before the freeze, the plan's protected scopes are reserved so no implementation step is told it owns a test file, but the
# driver-supplied runner path is not reserved (it must still be installed by its step).
printf '1\tpackage.json\n1\tvitest.config.js\n2\tsrc/engine.js\n2\ttests/unit.test.js\n3\ttests/mutations/run.mjs\n4\ttests/e2e/a.spec.js\n' > "$SCR/owns2.tsv"
expect "reserved scopes drop test files from every step before the freeze" \
    '[[ "$(tests_filter_owns < "$SCR/owns2.tsv" | tr "\t\n" ": ")" == "1:package.json 2:src/engine.js 3:tests/mutations/run.mjs " ]]'
expect "steps whose files are all reserved are skipped before the freeze" '[[ "$(tests_frozen_only_steps < "$SCR/owns2.tsv" | tr "\n" " ")" == "4 " ]]'
# The implementation runs meanwhile and writes source it owns (the stray-file check must not mistake it for a lane's work).
cp "$SCR/owns2.tsv" "$STATE_DIR/implement-owns.all.tsv"
sleep 0.2; mkdir -p src; echo impl > src/engine.js
tests_join > "$SCR/join.out" 2>&1 && join_rc=0 || join_rc=$?
expect "join waits for the authors and freezes (rc=0)" '[[ "$join_rc" == 0 ]] && tests_locked && grep -q "implementation finished; waiting" "$SCR/join.out"'
expect "concurrent mode skips the red check and says so" 'grep -q "Skipped" "$STATE_DIR/tests/red-check.md"'
expect "source the implementation owns is not flagged as a stray" '! grep -q "src/engine.js changed during test authoring" "$SCR/join.out"'
expect "the join froze the lane files" 'grep -q "tests/unit.test.js" "$(tests_lock)" && grep -q "tests/e2e/a.spec.js" "$(tests_lock)"'
expect "the lanes really overlapped the join (unit started before the join returned)" '[[ -s "$STATE_DIR/order.log" ]] && grep -q "^unit start" "$STATE_DIR/order.log"'

# A production file nobody owns is still a stray in concurrent mode.
reset
printf 'tests/\nvitest.config.js\n' > "$STATE_DIR/tests.paths.fixture"
tests_background_start > /dev/null 2>&1
mkdir -p src; echo rogue > src/rogue.js
( tests_join ) > "$SCR/join2.out" 2>&1 && join2_rc=0 || join2_rc=$?
expect "an unowned stray is still rejected at the join" '[[ "$join2_rc" != 0 ]] && grep -q "src/rogue.js changed during test authoring" "$SCR/join2.out"'

# A lane that fails once in the background is retried at the join (finished lanes are kept); one that keeps failing fails the join.
reset
printf 'tests/\nvitest.config.js\n' > "$SCR/../tests.paths.fixture" 2>/dev/null || printf 'tests/\nvitest.config.js\n' > "$STATE_DIR/tests.paths.fixture"
run_claude() { if [[ "${2#tests-}" == unit && ! -e "$SCR/unit.failed.once" ]]; then touch "$SCR/unit.failed.once"; return 1; fi; stub_agent "$@"; }
tests_background_start > /dev/null 2>&1
( tests_join ) > "$SCR/join3.out" 2>&1 && join3_rc=0 || join3_rc=$?
expect "a lane that failed once in the background is retried at the join" '[[ "$join3_rc" == 0 ]] && grep -q "finishing the unfinished lanes now" "$SCR/join3.out" && tests_locked'
reset
printf 'tests/\nvitest.config.js\n' > "$STATE_DIR/tests.paths.fixture"
run_claude() { if [[ "${2#tests-}" == unit ]]; then return 1; fi; stub_agent "$@"; }
tests_background_start > /dev/null 2>&1
( tests_join ) > "$SCR/join4.out" 2>&1 && join4_rc=0 || join4_rc=$?
expect "a lane that keeps failing fails the join and freezes nothing" '[[ "$join4_rc" != 0 ]] && ! tests_locked'
expect "finished lanes are kept for the next try" '[[ -e "$STATE_DIR/tests/lane-harness.done" && ! -e "$STATE_DIR/tests/lane-unit.done" ]]'
run_claude() { stub_agent "$@"; }
( tests_join ) > "$SCR/join5.out" 2>&1 && join5_rc=0 || join5_rc=$?
expect "the next try finishes only the failed lane and freezes" '[[ "$join5_rc" == 0 ]] && tests_locked'
unset WORKFLOW_TESTS_CONCURRENT

# Runner reuse: lanes share warm runners by default and can be switched back to cold per-lane CLIs.
reset
printf 'tests/\nvitest.config.js\n' > "$STATE_DIR/tests.paths.fixture"
: > "$STATE_DIR/reuse.log"
( tests_stage ) > /dev/null 2>&1 || true
expect "lanes run with runner reuse on by default" 'grep -q "^unit reuse=1" "$STATE_DIR/reuse.log" && grep -q "^harness reuse=1" "$STATE_DIR/reuse.log"'
reset
printf 'tests/\nvitest.config.js\n' > "$STATE_DIR/tests.paths.fixture"
: > "$STATE_DIR/reuse.log"
( WORKFLOW_TESTS_RUNNER_REUSE=0 tests_stage ) > /dev/null 2>&1 || true
expect "WORKFLOW_TESTS_RUNNER_REUSE=0 gives every lane a cold CLI" '! grep -q "reuse=1" "$STATE_DIR/reuse.log" && grep -q "^unit reuse=0" "$STATE_DIR/reuse.log"'


# ---------------------------------------------------------------------------------------------------------------------------------
# Completing the defect list early, cheaply, and checked by the driver.
reset
run_claude() { stub_agent "$@"; }
export WORKFLOW_TESTS_CONCURRENT=1
printf 'tests/\nvitest.config.js\n' > "$STATE_DIR/tests.paths.fixture"
: > "$STATE_DIR/order.log"
UNIT_SLEEP=5; export UNIT_SLEEP
tests_background_start > /dev/null 2>&1
sleep 2                                   # the harness and the fast authors are done; the unit author is still working
mkdir -p src; echo "impl" > src/engine.js
( tests_join ) > "$SCR/early.out" 2>&1 && early_rc=0 || early_rc=$?
unset UNIT_SLEEP
unit_end="$(awk '$1 == "unit" && $2 == "end" { print $3 }' "$STATE_DIR/order.log")"
complete_start="$(awk '$1 == "complete" && $2 == "start" { print $3 }' "$STATE_DIR/order.log")"
expect "the join succeeds with an early completion" '[[ "$early_rc" == 0 ]] && tests_locked'
expect "the completion started before the slowest author finished" '[[ -n "$complete_start" && -n "$unit_end" ]] && (( complete_start < unit_end ))'
expect "the join announces the early start" 'grep -q "completing the defect list now, beside the remaining authors" "$SCR/early.out"'
expect "the agent is given the list and the source inline" 'grep -q "Source .src/engine.js." "$STATE_DIR/tests/prompt-complete.md" && grep -q "Current contents of .tests/mutations/list.mjs." "$STATE_DIR/tests/prompt-complete.md"'
expect "the completed list passes the driver's own uniqueness check" '[[ -z "$(tests_verify_list tests/mutations/list.mjs)" ]]'
expect "the intent snapshot predates the completion (it has no find yet)" 'grep -q "\"find\":false" "$STATE_DIR/tests/intent.tsv"'

# A find that is not unique is caught by the driver, and the agent is asked once more with the exact problem.
reset
printf 'tests/\nvitest.config.js\n' > "$STATE_DIR/tests.paths.fixture"
rm -f "$STATE_DIR/complete.bad.done"
COMPLETE_BAD_ONCE=1; export COMPLETE_BAD_ONCE
tests_background_start > /dev/null 2>&1
mkdir -p src; echo "alpha beta" > src/engine.js
( tests_join ) > "$SCR/retry.out" 2>&1 && retry_rc=0 || retry_rc=$?
unset COMPLETE_BAD_ONCE
expect "a non-unique find is rejected by the driver and fixed on the retry" '[[ "$retry_rc" == 0 ]] && grep -q "occurs .* times in src/engine.js" "$SCR/retry.out" && grep -q "asking once more" "$SCR/retry.out"'
expect "the retry prompt names the failures" 'grep -q "driver rejected your previous list" "$STATE_DIR/tests/prompt-complete.md"'

# An agent that changes the frozen intent while completing is still caught.
reset
printf 'tests/\nvitest.config.js\n' > "$STATE_DIR/tests.paths.fixture"
COMPLETE_DROPS_INTENT=1; export COMPLETE_DROPS_INTENT
tests_background_start > /dev/null 2>&1
mkdir -p src; echo "impl" > src/engine.js
( tests_join ) > "$SCR/intent.out" 2>&1 && intent_rc=0 || intent_rc=$?
unset COMPLETE_DROPS_INTENT
expect "a completion that changes the authored intent fails the join" '[[ "$intent_rc" != 0 ]] && grep -q "changed its breaks/expected_failing_tests" "$SCR/intent.out"'
unset WORKFLOW_TESTS_CONCURRENT

# A lane marked done whose file list vanished is a reported problem, not a bash error.
reset
mkdir -p "$STATE_DIR/tests"; touch "$STATE_DIR/tests/lane-harness.done"
( tests_stage ) > "$SCR/missing.out" 2>&1 && missing_status=0 || missing_status=$?
expect "a done lane without a file list is reported clearly" '[[ "$missing_status" != 0 ]] && grep -q "has no .*lane-harness.files" "$SCR/missing.out"'

echo "tests-stage-test: $COUNT checks, $FAILED failures"
[[ "$FAILED" == 0 ]]

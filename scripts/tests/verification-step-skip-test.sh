#!/usr/bin/env bash
# A plan step that only runs the test suites is not implementation work: the driver runs the approved verification commands
# itself, so the serial loop and the parallel grouping both skip it, and the last step that actually runs is the final code step.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
VERIFY='Verification only: run `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` \xe2\x80\x94 Owns: none \xe2\x80\x94 Depends on: 2'

# --- the serial loop -----------------------------------------------------------------------------------------------------
mkdir -p "$work/serial/state" "$work/serial/.uncle/docs"
(
    cd "$work/serial"
    STATE_DIR="$work/serial/state"; MODEL_IMPLEMENT=fake; BUDGET_IMPLEMENT=1
    plan_steps() { printf 'One \xe2\x80\x94 Owns: `a.py` \xe2\x80\x94 Depends on: 0\n'; printf 'Two \xe2\x80\x94 Owns: `b.py` \xe2\x80\x94 Depends on: 1\n'; printf "$VERIFY\n"; }
    run_supervised_parallel_implementation() { return 2; }
    compose_implementation_prompt() { : > "$2"; }
    plan_assess() { :; }
    check_document_budget() { test -s "$1"; }
    require_file() { [[ -s "$1" ]] || { echo "missing: $1" >&2; return 1; }; }
    supervision_validation_failed() { :; }
    run_claude() {
        printf '%s\n' "$2" >> calls
        n="${2##*-}"
        printf '{"schema":"uncle.artifact/v1","kind":"implementation-notes","changed_files":[{"path":"f%s.py"}]}\n' "$n" > "$STATE_DIR/implement-step-$n-notes.json"
        cp "$1" "prompt-$n.md"
        [[ "$2" == implementation-step-[12] ]] || exit 99
    }
    eval "$(sed -n '/^run_stepwise_implementation() {/,/^# Count checks as they stream/p' "$ROOT/scripts/change-workflow.sh" | sed '$d')"
    run_stepwise_implementation base > out.txt 2>&1
) || { echo "FAIL: the serial loop stopped"; cat "$work/serial/out.txt" >&2; fails=$((fails + 1)); }
check "the verification-only step starts no model session" test "$(cat "$work/serial/calls")" == $'implementation-step-1\nimplementation-step-2'
check "the skip is announced" grep -q 'Implementation step 3/3 skipped: it only runs the test suites' "$work/serial/out.txt"
check "the last step that runs is the final code step" grep -q 'This is the final code step' "$work/serial/prompt-2.md"
check "an earlier step is not the final code step" grep -q 'Do not run the full suite; the final step does that once' "$work/serial/prompt-1.md"
check "the skipped step does not leave a resume marker behind" test ! -e "$work/serial/state/implement-step-done"

# --- resuming after the last real step does not run the skipped one --------------------------------------------------------
rm -f "$work/serial/calls"; printf '2\n' > "$work/serial/state/implement-step-done"
(
    cd "$work/serial"
    STATE_DIR="$work/serial/state"; MODEL_IMPLEMENT=fake; BUDGET_IMPLEMENT=1
    plan_steps() { printf 'One \xe2\x80\x94 Owns: `a.py` \xe2\x80\x94 Depends on: 0\n'; printf 'Two \xe2\x80\x94 Owns: `b.py` \xe2\x80\x94 Depends on: 1\n'; printf "$VERIFY\n"; }
    run_supervised_parallel_implementation() { return 2; }
    compose_implementation_prompt() { : > "$2"; }
    plan_assess() { :; }
    check_document_budget() { test -s "$1"; }
    require_file() { return 0; }
    supervision_validation_failed() { :; }
    run_claude() { printf '%s\n' "$2" >> calls; exit 99; }
    eval "$(sed -n '/^run_stepwise_implementation() {/,/^# Count checks as they stream/p' "$ROOT/scripts/change-workflow.sh" | sed '$d')"
    run_stepwise_implementation base > out2.txt 2>&1
) || { echo "FAIL: resuming ran a model session"; cat "$work/serial/out2.txt" >&2; fails=$((fails + 1)); }
check "a resume after the last real step runs nothing" test ! -e "$work/serial/calls"

# --- the parallel grouping -----------------------------------------------------------------------------------------------
mkdir -p "$work/par/.uncle/docs"
printf '# Change plan\n\n## Implementation sequence\n\n1. One \xe2\x80\x94 Owns: `a.py` \xe2\x80\x94 Depends on: 0\n2. Two \xe2\x80\x94 Owns: `b.py` \xe2\x80\x94 Depends on: 0\n3. Three \xe2\x80\x94 Owns: `c.py` \xe2\x80\x94 Depends on: 0\n4. %b\n' "$VERIFY" > "$work/par/.uncle/docs/CHANGE_PLAN.md"
groups="$(cd "$work/par" && . "$ROOT/scripts/lib/plan-scope.sh" && . "$ROOT/scripts/lib/parallel-implement.sh" \
    && parallel_implement_enabled() { return 0; } && parallel_groups .uncle/docs/CHANGE_PLAN.md "$ROOT/scripts/lib")"
check "the parallel groups hold only the real steps" test "$groups" == "1 2 3"

[[ "$fails" == 0 ]] && echo "verification-step-skip-test.sh: all checks passed" || { echo "verification-step-skip-test.sh: $fails failure(s)"; exit 1; }

#!/usr/bin/env bash
# change-workflow.sh's own parallel implementation fan-out (the same
# parallel_groups/parallel_run_group mechanism the new-application driver
# uses, against CHANGE_PLAN.md) has exactly the same cross-file-interface-
# guessing risk module-interfaces was built to close for the app driver, but
# never called it. This checks the wiring exists: the shared lib is sourced,
# derive_module_interfaces is called against CHANGE_PLAN.md before the
# per-step prompts are built, and the rendered section reaches those prompts.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }

grep -q '^\. "\$ROOT/scripts/lib/module-interfaces-stage\.sh"$' "$ROOT/scripts/change-workflow.sh" \
    && ok || bad "sources-shared-lib" "change-workflow.sh does not source module-interfaces-stage.sh"

block="$(sed -n '/^run_supervised_parallel_implementation() {/,/^}/p' "$ROOT/scripts/change-workflow.sh")"
[[ -n "$block" ]] || { echo 'FATAL: could not extract run_supervised_parallel_implementation'; exit 2; }

if printf '%s' "$block" | grep -q 'derive_module_interfaces .uncle/docs/CHANGE_PLAN.md'; then ok
else bad "derives-against-change-plan" "does not call derive_module_interfaces against CHANGE_PLAN.md"; fi

if printf '%s' "$block" | grep -q 'module_interfaces_section='; then ok
else bad "renders-section" "does not render the module-interfaces section"; fi

if printf '%s' "$block" | grep -q 'module_interfaces_section'; then
    inject_count="$(printf '%s' "$block" | grep -c 'module_interfaces_section')"
    # Declaration + derive-assignment + at least one use in the per-step prompt.
    [[ "$inject_count" -ge 3 ]] && ok || bad "injects-into-prompt" "module_interfaces_section is declared but never used in a step prompt"
else
    bad "injects-into-prompt" "module_interfaces_section never referenced"
fi

# The derive call must happen before the per-step prompt loop, or the
# section would always be empty for every step's prompt.
derive_line="$(printf '%s' "$block" | grep -n 'derive_module_interfaces .uncle/docs/CHANGE_PLAN.md' | head -1 | cut -d: -f1)"
loop_line="$(printf '%s' "$block" | grep -n 'while IFS= read -r group' | head -1 | cut -d: -f1)"
if [[ -n "$derive_line" && -n "$loop_line" && "$derive_line" -lt "$loop_line" ]]; then ok
else bad "runs-before-loop" "derive_module_interfaces (line $derive_line) does not precede the step-prompt loop (line $loop_line)"; fi

bash -n "$ROOT/scripts/change-workflow.sh" && ok || bad "syntax" "change-workflow.sh fails bash -n"
bash -n "$ROOT/scripts/lib/module-interfaces-stage.sh" && ok || bad "syntax-lib" "module-interfaces-stage.sh fails bash -n"

# run_supervised_parallel_implementation returns before deriving module
# interfaces on every serial trigger (no ownership partitions, a resume, or
# the ownership-mismatch fallback marker), so the serial per-step loop in
# run_stepwise_implementation must derive and inject its own copy instead of
# relying on the parallel function's local variable.
serial_block="$(sed -n '/^run_stepwise_implementation() {/,/^}/p' "$ROOT/scripts/change-workflow.sh")"
[[ -n "$serial_block" ]] || { echo 'FATAL: could not extract run_stepwise_implementation'; exit 2; }

if printf '%s' "$serial_block" | grep -q 'derive_module_interfaces .uncle/docs/CHANGE_PLAN.md'; then ok
else bad "serial-derives" "run_stepwise_implementation does not call derive_module_interfaces"; fi

derive_line2="$(printf '%s' "$serial_block" | grep -n 'derive_module_interfaces .uncle/docs/CHANGE_PLAN.md' | head -1 | cut -d: -f1)"
single_stage_line="$(printf '%s' "$serial_block" | grep -n 'running implementation as a single stage' | head -1 | cut -d: -f1)"
loop_line2="$(printf '%s' "$serial_block" | grep -n 'while IFS= read -r step' | head -1 | cut -d: -f1)"
if [[ -n "$derive_line2" && -n "$single_stage_line" && "$derive_line2" -lt "$single_stage_line" ]]; then ok
else bad "serial-derives-before-single-stage" "derive_module_interfaces (line $derive_line2) does not precede the single-stage path (line $single_stage_line)"; fi
if [[ -n "$derive_line2" && -n "$loop_line2" && "$derive_line2" -lt "$loop_line2" ]]; then ok
else bad "serial-derives-before-loop" "derive_module_interfaces (line $derive_line2) does not precede the per-step loop (line $loop_line2)"; fi

single_stage_block="$(printf '%s' "$serial_block" | sed -n "/running implementation as a single stage/,/return 0/p")"
if printf '%s' "$single_stage_block" | grep -q 'module_interfaces_section'; then ok
else bad "serial-single-stage-injects" "the single-stage prompt path never references module_interfaces_section"; fi

per_step_block="$(printf '%s' "$serial_block" | sed -n '/while IFS= read -r step/,/^    done < "\$steps_file"/p')"
if printf '%s' "$per_step_block" | grep -q 'module_interfaces_section'; then ok
else bad "serial-per-step-injects" "the per-step prompt loop never references module_interfaces_section"; fi

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "change-workflow-module-interfaces-wiring-test.sh: $FAIL of $((PASS + FAIL)) checks failed"
    exit 1
fi
echo "change-workflow-module-interfaces-wiring-test.sh: $PASS checks passed"

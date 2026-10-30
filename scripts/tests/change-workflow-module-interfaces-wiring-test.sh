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

# uncle consolidation phase (b): the derive+inject logic that used to live
# directly in run_supervised_parallel_implementation moved into the shared
# parallel_implement_run_groups (scripts/lib/parallel-implement.sh), used by
# both stagegate.sh and change-workflow.sh, so it is checked once there
# instead of once per driver. What remains driver-specific is: (1) that
# change-workflow.sh's wrapper actually calls the shared function against
# CHANGE_PLAN.md, and (2) that its own per-step prompt-builder callback
# references the module-interfaces section the shared function hands it.
wrapper_block="$(sed -n '/^run_supervised_parallel_implementation() {/,/^}/p' "$ROOT/scripts/change-workflow.sh")"
[[ -n "$wrapper_block" ]] || { echo 'FATAL: could not extract run_supervised_parallel_implementation'; exit 2; }

if printf '%s' "$wrapper_block" | grep -q 'parallel_implement_run_groups \\$' \
   && printf '%s' "$wrapper_block" | grep -A1 'parallel_implement_run_groups \\$' | grep -q '.uncle/docs/CHANGE_PLAN.md'; then
    ok
else
    bad "derives-against-change-plan" "run_supervised_parallel_implementation does not call the shared fan-out against CHANGE_PLAN.md"
fi

prompt_fn="$(printf '%s' "$wrapper_block" | grep -o '_changeworkflow_parallel_build_step_prompt' | head -1)"
[[ -n "$prompt_fn" ]] || bad "names-prompt-callback" "run_supervised_parallel_implementation does not pass its own prompt-builder callback"
[[ -z "$prompt_fn" ]] || ok

block="$(sed -n "/^${prompt_fn:-_no_such_fn_}() {/,/^}/p" "$ROOT/scripts/change-workflow.sh")"
[[ -n "$block" ]] || { echo 'FATAL: could not extract the change-workflow.sh prompt-builder callback'; exit 2; }

if printf '%s' "$block" | grep -q 'module_interfaces_section'; then ok
else bad "injects-into-prompt" "the change-workflow.sh prompt-builder callback never references module_interfaces_section"; fi

# The shared function itself must still derive against whatever plan_doc its
# caller passed (not a hardcoded UPDATED_PROJECT_PLAN.md default), and must do
# so before the per-group loop that calls the prompt-builder callback -- or
# the section handed to every family's callback would always be empty.
shared_block="$(sed -n '/^parallel_implement_run_groups() {/,/^}/p' "$ROOT/scripts/lib/parallel-implement.sh")"
[[ -n "$shared_block" ]] || { echo 'FATAL: could not extract the shared parallel_implement_run_groups'; exit 2; }

if printf '%s' "$shared_block" | grep -q 'derive_module_interfaces "\$plan_doc"'; then ok
else bad "shared-derives-against-plan-doc" "parallel_implement_run_groups does not derive module interfaces against its plan_doc argument"; fi

if printf '%s' "$shared_block" | grep -q 'module_interfaces_section='; then ok
else bad "shared-renders-section" "parallel_implement_run_groups does not render the module-interfaces section"; fi

derive_line="$(printf '%s' "$shared_block" | grep -n 'derive_module_interfaces "\$plan_doc"' | head -1 | cut -d: -f1)"
loop_line="$(printf '%s' "$shared_block" | grep -n 'while IFS= read -r group' | head -1 | cut -d: -f1)"
if [[ -n "$derive_line" && -n "$loop_line" && "$derive_line" -lt "$loop_line" ]]; then ok
else bad "runs-before-loop" "derive_module_interfaces (line $derive_line) does not precede the group loop (line $loop_line)"; fi

callback_line="$(printf '%s' "$shared_block" | grep -n '"\$prompt_builder_fn"' | head -1 | cut -d: -f1)"
if [[ -n "$derive_line" && -n "$callback_line" && "$derive_line" -lt "$callback_line" ]]; then ok
else bad "callback-after-derive" "the prompt-builder callback (line $callback_line) is invoked before derive_module_interfaces (line $derive_line)"; fi

bash -n "$ROOT/scripts/lib/parallel-implement.sh" && ok || bad "syntax-shared" "parallel-implement.sh fails bash -n"
grep -Fq '. "$ROOT/scripts/lib/parallel-implement.sh"' "$ROOT/scripts/stagegate.sh" \
    && ok || bad "stagegate-sources-shared" "stagegate.sh does not source parallel-implement.sh"
grep -Fq '. "$ROOT/scripts/lib/parallel-implement.sh"' "$ROOT/scripts/change-workflow.sh" \
    && ok || bad "change-workflow-sources-shared" "change-workflow.sh does not source parallel-implement.sh"

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

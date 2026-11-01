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

if grep -q 'parallel_implement_run_groups \\$' <<<"$wrapper_block" \
   && grep -A1 'parallel_implement_run_groups \\$' <<<"$wrapper_block" | grep -q '.uncle/docs/CHANGE_PLAN.md'; then
    ok
else
    bad "derives-against-change-plan" "run_supervised_parallel_implementation does not call the shared fan-out against CHANGE_PLAN.md"
fi

prompt_fn="$(grep -o '_changeworkflow_parallel_build_step_prompt' <<<"$wrapper_block" | head -1)"
[[ -n "$prompt_fn" ]] || bad "names-prompt-callback" "run_supervised_parallel_implementation does not pass its own prompt-builder callback"
[[ -z "$prompt_fn" ]] || ok

block="$(sed -n "/^${prompt_fn:-_no_such_fn_}() {/,/^}/p" "$ROOT/scripts/change-workflow.sh")"
[[ -n "$block" ]] || { echo 'FATAL: could not extract the change-workflow.sh prompt-builder callback'; exit 2; }

if grep -q 'module_interfaces_section' <<<"$block"; then ok
else bad "injects-into-prompt" "the change-workflow.sh prompt-builder callback never references module_interfaces_section"; fi

# uncle consolidation phase (d): derivation itself moved out of this function
# entirely, into the dedicated MODULE_INTERFACES state both drivers now visit
# once, before IMPLEMENT -- see module-interfaces-stage-test.sh for that. This
# function only renders whatever MODULE_INTERFACES.json that state already
# produced (if any), and must still do so before the per-group loop that
# calls the prompt-builder callback -- or the section handed to every
# family's callback would always be empty.
shared_block="$(sed -n '/^parallel_implement_run_groups() {/,/^}/p' "$ROOT/scripts/lib/parallel-implement.sh")"
[[ -n "$shared_block" ]] || { echo 'FATAL: could not extract the shared parallel_implement_run_groups'; exit 2; }

if grep -q 'derive_module_interfaces' <<<"$shared_block"; then
    bad "no-redundant-derive" "parallel_implement_run_groups still calls derive_module_interfaces directly; it should only render from the MODULE_INTERFACES state's own output"
else
    ok
fi

if grep -q '\[\[ -s "\$STATE_DIR/documents/MODULE_INTERFACES\.json" \]\]' <<<"$shared_block"; then ok
else bad "shared-checks-existing-json" "parallel_implement_run_groups does not check for an already-derived MODULE_INTERFACES.json"; fi

if grep -q 'module_interfaces_section=' <<<"$shared_block"; then ok
else bad "shared-renders-section" "parallel_implement_run_groups does not render the module-interfaces section"; fi

render_line="$(grep -n '\[\[ -s "\$STATE_DIR/documents/MODULE_INTERFACES\.json" \]\]' <<<"$shared_block" | head -1 | cut -d: -f1)"
loop_line="$(grep -n 'while IFS= read -r group' <<<"$shared_block" | head -1 | cut -d: -f1)"
if [[ -n "$render_line" && -n "$loop_line" && "$render_line" -lt "$loop_line" ]]; then ok
else bad "runs-before-loop" "the MODULE_INTERFACES.json check (line $render_line) does not precede the group loop (line $loop_line)"; fi

callback_line="$(grep -n '"\$prompt_builder_fn"' <<<"$shared_block" | head -1 | cut -d: -f1)"
if [[ -n "$render_line" && -n "$callback_line" && "$render_line" -lt "$callback_line" ]]; then ok
else bad "callback-after-render" "the prompt-builder callback (line $callback_line) is invoked before the MODULE_INTERFACES.json check (line $render_line)"; fi

bash -n "$ROOT/scripts/lib/parallel-implement.sh" && ok || bad "syntax-shared" "parallel-implement.sh fails bash -n"
grep -Fq '. "$ROOT/scripts/lib/parallel-implement.sh"' "$ROOT/scripts/stagegate.sh" \
    && ok || bad "stagegate-sources-shared" "stagegate.sh does not source parallel-implement.sh"
grep -Fq '. "$ROOT/scripts/lib/parallel-implement.sh"' "$ROOT/scripts/change-workflow.sh" \
    && ok || bad "change-workflow-sources-shared" "change-workflow.sh does not source parallel-implement.sh"

bash -n "$ROOT/scripts/change-workflow.sh" && ok || bad "syntax" "change-workflow.sh fails bash -n"
bash -n "$ROOT/scripts/lib/module-interfaces-stage.sh" && ok || bad "syntax-lib" "module-interfaces-stage.sh fails bash -n"

# uncle consolidation phase (d): run_stepwise_implementation no longer derives
# either -- it renders from whatever MODULE_INTERFACES.json the dedicated
# MODULE_INTERFACES state already produced, same as parallel_implement_run_groups.
serial_block="$(sed -n '/^run_stepwise_implementation() {/,/^}/p' "$ROOT/scripts/change-workflow.sh")"
[[ -n "$serial_block" ]] || { echo 'FATAL: could not extract run_stepwise_implementation'; exit 2; }

if grep -q 'derive_module_interfaces' <<<"$serial_block"; then
    bad "no-redundant-serial-derive" "run_stepwise_implementation still calls derive_module_interfaces directly; it should only render from the MODULE_INTERFACES state's own output"
else
    ok
fi

derive_line2="$(grep -n '\[\[ -s "\$STATE_DIR/documents/MODULE_INTERFACES\.json" \]\]' <<<"$serial_block" | head -1 | cut -d: -f1)"
single_stage_line="$(grep -n 'running implementation as a single stage' <<<"$serial_block" | head -1 | cut -d: -f1)"
loop_line2="$(grep -n 'while IFS= read -r step' <<<"$serial_block" | head -1 | cut -d: -f1)"
if [[ -n "$derive_line2" && -n "$single_stage_line" && "$derive_line2" -lt "$single_stage_line" ]]; then ok
else bad "serial-renders-before-single-stage" "the MODULE_INTERFACES.json check (line $derive_line2) does not precede the single-stage path (line $single_stage_line)"; fi
if [[ -n "$derive_line2" && -n "$loop_line2" && "$derive_line2" -lt "$loop_line2" ]]; then ok
else bad "serial-renders-before-loop" "the MODULE_INTERFACES.json check (line $derive_line2) does not precede the per-step loop (line $loop_line2)"; fi

single_stage_block="$(printf '%s' "$serial_block" | sed -n "/running implementation as a single stage/,/return 0/p")"
if grep -q 'module_interfaces_section' <<<"$single_stage_block"; then ok
else bad "serial-single-stage-injects" "the single-stage prompt path never references module_interfaces_section"; fi

per_step_block="$(printf '%s' "$serial_block" | sed -n '/while IFS= read -r step/,/^    done < "\$steps_file"/p')"
if grep -q 'module_interfaces_section' <<<"$per_step_block"; then ok
else bad "serial-per-step-injects" "the per-step prompt loop never references module_interfaces_section"; fi

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "change-workflow-module-interfaces-wiring-test.sh: $FAIL of $((PASS + FAIL)) checks failed"
    exit 1
fi
echo "change-workflow-module-interfaces-wiring-test.sh: $PASS checks passed"

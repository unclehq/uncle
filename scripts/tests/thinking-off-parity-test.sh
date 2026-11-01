#!/usr/bin/env bash
# The stages that run without thinking are one list for every runner: the bash predicate (claude, codex, kimi) and the self-hosted
# default (Python) must agree on every stage name, with and without the operator's overrides.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
STAGES_RAW="requirements requirements-investigate project-plan project-plan-investigate project-plan-section-steps project-plan-stage-duties
updated-plan updated-plan-worker-edits-3 updated-plan-review-worker-scope updated-change-plan updated-change-plan-worker-edits-1
preflight preflight-worker-a preview-build module-interfaces classify-change execute-checklist execute-checklist-worker-group-1-batch-1
test-review test-review-worker-oracle test-review-worker-coverage-investigate final-audit final-audit-review-worker-verification
adversarial-review adversarial-review-worker-regression manual-checklist manual-checklist-review-worker-coverage implementation
implementation-step-3 repair derive-brief supervision triage final-auditor test-reviews execute-checklists"
STAGES="$(printf '%s' "$STAGES_RAW" | tr '\n' ' ')"

bash_answers() {   # env...
    env -i PATH="$PATH" HOME="$HOME" "$@" bash --norc --noprofile -c "
        . '$ROOT/scripts/lib/thinking-off.sh'
        for s in $STAGES; do uncle_stage_thinking_off \"\$s\" && echo \"\$s off\" || echo \"\$s on\"; done"
}
python_answers() {   # env...
    env -i PATH="$PATH" HOME="$HOME" "$@" python3 -B -c "
import sys; sys.path.insert(0, '$ROOT/scripts/lib')
import self_hosted_http as h
for s in '''$STAGES'''.split(): print(s, 'off' if h.thinking_off_stage(s) else 'on')"
}

for env in "X=1" "WORKFLOW_THINKING=on" "WORKFLOW_THINKING_OFF_EXTRA=adversarial-review-* implementation*" "WORKFLOW_THINKING_OFF_EXTRA=nothing-*"; do
    a="$(bash_answers "$env")"; b="$(python_answers "$env")"
    [[ "$a" == "$b" ]] || { bad "the runners disagree under '$env':"; diff <(echo "$a") <(echo "$b") >&2; }
done
[[ "$(bash_answers X=1 | grep -c ' off$')" -ge 15 ]] || bad "the shared list unexpectedly shrank"
bash_answers X=1 | grep -qx 'test-review off' || bad "test-review is not on the shared list"
bash_answers X=1 | grep -qx 'final-audit off' || bad "final-audit is not on the shared list"
bash_answers X=1 | grep -qx 'adversarial-review on' || bad "adversarial-review must keep thinking"
[[ $fail == 0 ]] && echo "thinking-off-parity-test.sh: ok"
exit $fail

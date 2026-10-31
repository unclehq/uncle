#!/usr/bin/env bash
# thinking-off.sh: which stages run without thinking, the opt-outs, and the Codex/Kimi probe that
# keeps an unsupported value from failing a stage.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
nocheck() { local what="$1"; shift; if "$@"; then echo "FAIL: $what"; fails=$((fails + 1)); fi; }
. "$ROOT/scripts/lib/thinking-off.sh"

# Stages that transcribe decided inputs are off; judgment stages are not.
for stage in requirements project-plan project-plan-section-invariants updated-plan updated-plan-worker-edits-3 \
             updated-plan-worker-resolve-g1-retry preflight-worker-browser preview-build-part-a module-interfaces \
             execute-checklist-worker-group-1-batch-2; do
    check "$stage runs without thinking" uncle_stage_thinking_off "$stage"
done
for stage in implementation implementation-step-2 repair adversarial-review adversarial-review-worker-security \
             test-review final-audit manual-checklist derive-brief project-plan-stage-duties; do
    nocheck "$stage keeps thinking" uncle_stage_thinking_off "$stage"
done

# Opt-outs.
nocheck "WORKFLOW_THINKING=on restores thinking" env WORKFLOW_THINKING=on bash -c ". '$ROOT/scripts/lib/thinking-off.sh'; uncle_stage_thinking_off updated-plan"
check "extra glob switches a stage off" env WORKFLOW_THINKING_OFF_EXTRA='repair* foo' bash -c ". '$ROOT/scripts/lib/thinking-off.sh'; uncle_stage_thinking_off repair-investigate"
# An extra glob must not expand against the working directory: with a file named `implementation`
# in it, an expanded `*` would become that one word and stop matching other stages. The shell's
# noglob state must also be restored afterward.
mkdir "$TMP/glob" && : > "$TMP/glob/implementation"
check "extra glob is matched as a pattern, not expanded" env WORKFLOW_THINKING_OFF_EXTRA='*' bash -c "cd '$TMP/glob'; . '$ROOT/scripts/lib/thinking-off.sh'; uncle_stage_thinking_off adversarial-review"
check "noglob is restored afterward" bash -c "cd '$TMP/glob'; . '$ROOT/scripts/lib/thinking-off.sh'; WORKFLOW_THINKING_OFF_EXTRA='x' uncle_stage_thinking_off adversarial-review; [[ \$- != *f* ]]"

# Probes: a runner that takes `none` says yes, one that rejects it says no, and the answer is cached.
cat > "$TMP/codex-ok" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "$STUB_CALLS"
echo '{"type":"turn.completed","usage":{}}'
STUB
cat > "$TMP/codex-no" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "$STUB_CALLS"
echo '{"type":"error","message":"Unsupported value: none"}'
echo '{"type":"turn.failed"}'
STUB
cat > "$TMP/kimi-ok" <<'STUB'
#!/usr/bin/env bash
echo "$KIMI_MODEL_THINKING_EFFORT $*" >> "$STUB_CALLS"
echo '{"role":"assistant","content":"ok"}'
STUB
cat > "$TMP/kimi-no" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "$STUB_CALLS"
echo "error: unsupported thinking effort"
STUB
chmod +x "$TMP"/codex-* "$TMP"/kimi-*
export STUB_CALLS="$TMP/calls"
export STATE_DIR="$TMP/state"

WORKFLOW_CODEX_CMD="$TMP/codex-ok" check "codex that takes none is accepted" uncle_runner_accepts_no_thinking codex gpt-x
grep -q 'model_reasoning_effort=none' "$STUB_CALLS" || { echo "FAIL: probe asked codex for effort none"; fails=$((fails + 1)); }
grep -q -- '-m gpt-x' "$STUB_CALLS" || { echo "FAIL: probe used the stage's model"; fails=$((fails + 1)); }
before="$(wc -l < "$STUB_CALLS")"
WORKFLOW_CODEX_CMD="$TMP/codex-no" check "a cached answer is not probed again" uncle_runner_accepts_no_thinking codex gpt-x
[[ "$(wc -l < "$STUB_CALLS")" == "$before" ]] || { echo "FAIL: cached probe called codex again"; fails=$((fails + 1)); }
WORKFLOW_CODEX_CMD="$TMP/codex-no" nocheck "codex that rejects none keeps its effort" uncle_runner_accepts_no_thinking codex other-model

WORKFLOW_KIMI_CMD="$TMP/kimi-ok" check "kimi that takes off is accepted" uncle_runner_accepts_no_thinking kimi kimi:moonshot-ai/kimi-k3
grep -q '^off .*-m moonshot-ai/kimi-k3' "$STUB_CALLS" || { echo "FAIL: kimi probe sets KIMI_MODEL_THINKING_EFFORT=off and strips the kimi: prefix"; fails=$((fails + 1)); }
WORKFLOW_KIMI_CMD="$TMP/kimi-no" nocheck "kimi that errors keeps its effort" uncle_runner_accepts_no_thinking kimi moonshot-ai/kimi-k2.6

[[ "$fails" == 0 ]] && echo "thinking-off-test.sh: all checks passed" || { echo "thinking-off-test.sh: $fails failure(s)"; exit 1; }

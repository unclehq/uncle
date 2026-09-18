#!/usr/bin/env bash
# Model selection for claude, codex, and kimi stages via config and env vars.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/stage-config.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
UNCLE_CONFIG="$work/config"

eq() { [ "$2" = "$3" ] || { echo "FAIL $1: expected '$3', got '$2'" >&2; exit 1; }; }

# ============================================================================
# AC-1: Claude config model selection
# ============================================================================
printf 'change-plan.runner claude\nchange-plan.model claude-opus-5\n' > "$UNCLE_CONFIG"
eq "AC-1: claude config model" "$(uncle_stage_model change-plan claude)" "claude-opus-5"

# ============================================================================
# AC-2: Codex config model selection
# ============================================================================
printf 'change-plan.runner codex\nchange-plan.model deepseek-v4-flash\n' > "$UNCLE_CONFIG"
eq "AC-2: codex config model" "$(uncle_stage_model change-plan codex)" "deepseek-v4-flash"

# ============================================================================
# AC-3: Kimi config model selection
# ============================================================================
printf 'change-plan.runner kimi\nchange-plan.model moonshot-ai/kimi-k2.7-code-highspeed\n' > "$UNCLE_CONFIG"
# When kimi has config, it should return "kimi" and set WORKFLOW_KIMI_MODEL
# Call without subshell to capture the export
unset WORKFLOW_KIMI_MODEL
kimi_out=$(uncle_stage_model change-plan kimi)
eq "AC-3: kimi returns dispatch key" "$kimi_out" "kimi"
# Export test: call again without capturing output in subshell
uncle_stage_model change-plan kimi > /dev/null
[[ "${WORKFLOW_KIMI_MODEL:-}" == "moonshot-ai/kimi-k2.7-code-highspeed" ]] || {
    echo "FAIL AC-3: expected WORKFLOW_KIMI_MODEL='moonshot-ai/kimi-k2.7-code-highspeed', got '${WORKFLOW_KIMI_MODEL:-}'" >&2
    exit 1
}

# ============================================================================
# AC-4: Claude env var fallback
# ============================================================================
printf 'change-plan.runner claude\n' > "$UNCLE_CONFIG"
export WORKFLOW_REVIEWER_CLAUDE_MODEL=claude-sonnet-5
eq "AC-4: claude env fallback" "$(uncle_stage_model change-plan claude)" "claude-sonnet-5"
unset WORKFLOW_REVIEWER_CLAUDE_MODEL

# ============================================================================
# AC-5: Codex env var fallback
# ============================================================================
printf 'change-plan.runner codex\n' > "$UNCLE_CONFIG"
export UNCLE_CODEX_MODEL=gpt-5.1
eq "AC-5: codex env fallback" "$(uncle_stage_model change-plan codex)" "gpt-5.1"
unset UNCLE_CODEX_MODEL

# ============================================================================
# AC-6: Kimi env var fallback
# ============================================================================
printf 'change-plan.runner kimi\n' > "$UNCLE_CONFIG"
output=$(uncle_stage_model change-plan kimi)
eq "AC-6: kimi env fallback returns dispatch key" "$output" "kimi"
# Without config, WORKFLOW_KIMI_MODEL should not be exported by our code
unset WORKFLOW_KIMI_MODEL

# ============================================================================
# AC-7: Non-existent config keys return empty
# ============================================================================
printf 'change-plan.runner codex\n' > "$UNCLE_CONFIG"
eq "AC-7: missing config key returns empty" "$(uncle_stage_model change-plan codex)" ""

# ============================================================================
# AC-8: Config takes precedence over env vars
# ============================================================================
printf 'change-plan.runner claude\nchange-plan.model claude-opus-5\n' > "$UNCLE_CONFIG"
export WORKFLOW_REVIEWER_CLAUDE_MODEL=claude-sonnet-5
eq "AC-8: claude config beats env" "$(uncle_stage_model change-plan claude)" "claude-opus-5"
unset WORKFLOW_REVIEWER_CLAUDE_MODEL

printf 'change-plan.runner codex\nchange-plan.model deepseek-v4-pro\n' > "$UNCLE_CONFIG"
export UNCLE_CODEX_MODEL=gpt-5.1
eq "AC-8: codex config beats env" "$(uncle_stage_model change-plan codex)" "deepseek-v4-pro"
unset UNCLE_CODEX_MODEL

printf 'change-plan.runner kimi\nchange-plan.model moonshot-ai/kimi-k3\n' > "$UNCLE_CONFIG"
# Test that config value wins over pre-existing env var
export WORKFLOW_KIMI_MODEL=moonshot-ai/kimi-k2.7-code-highspeed
# Call directly without output redirection to capture the export in parent shell
uncle_stage_model change-plan kimi > /dev/null
eq "AC-8: kimi config with env exports new value" "${WORKFLOW_KIMI_MODEL:-}" "moonshot-ai/kimi-k3"
unset WORKFLOW_KIMI_MODEL

echo 'stage-config-test.sh: AC-1 through AC-8 passed'

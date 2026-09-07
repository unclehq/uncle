#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export KIMI_ARGS="$tmp/args"
cat > "$tmp/kimi" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$KIMI_ARGS"
for arg in "$@"; do
    case "$arg" in --print|--mcp-config-file|*.yaml) exit 2 ;; esac
done
case "${TEST_MODE:-ok}" in
    fail) exit 7 ;;
    empty) exit 0 ;;
esac
printf '%s\n' '{"role":"assistant","content":"intermediate"}'
printf '%s\n' '{"role":"assistant","tool_calls":[{"function":{"name":"ReadFile"}}]}'
printf '%s\n' '{"role":"assistant","content":"final review"}'
STUB
chmod +x "$tmp/kimi"
export WORKFLOW_KIMI_CMD="$tmp/kimi"
bash "$ROOT/scripts/reviewer-kimi.sh" exec --sandbox read-only --ephemeral \
    -c model_reasoning_effort=high --output-last-message "$tmp/review" 'Review files' > "$tmp/log"
[[ $(cat "$tmp/review") == 'final review' ]]
grep -Fx -- '-p' "$KIMI_ARGS"
grep -Fx -- '--agent-file' "$KIMI_ARGS"
grep -Fx -- "$ROOT/lib/kimi/reviewer.md" "$KIMI_ARGS"
python3 - "$ROOT/lib/kimi/reviewer.md" <<'PY'
import sys
from pathlib import Path
header = Path(sys.argv[1]).read_text().split('---')[1]
assert 'subagents: []' in header
assert [line.strip() for line in header.splitlines() if line.startswith('  - ')] == ['- Read', '- Glob', '- Grep']
PY
for mode in fail empty; do
    printf "stale review" > "$tmp/$mode"
    if TEST_MODE="$mode" bash "$ROOT/scripts/reviewer-kimi.sh" exec \
        --output-last-message "$tmp/$mode" 'Review files' > "$tmp/log" 2>&1; then exit 1; fi
    [[ ! -e "$tmp/$mode" ]]
done
# A Kimi selection without a stage model must invoke Kimi, never Claude.
printf 'prompt' | WORKFLOW_CLAUDE_CMD=/nonexistent bash "$ROOT/scripts/agent-kimi.sh" -p > "$tmp/log"
grep -Fx -- 'moonshot-ai/kimi-k2.7-code-highspeed' "$KIMI_ARGS"
. "$ROOT/scripts/lib/stage-config.sh"
[[ $(uncle_runner_cmd kimi reviewer) == "$ROOT/scripts/reviewer-kimi.sh" ]]
echo 'reviewer-kimi-test: passed'

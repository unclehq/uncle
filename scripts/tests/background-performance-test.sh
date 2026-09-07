#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
BG_PID=""
trap 'if [[ -n "$BG_PID" ]]; then kill "$BG_PID" 2>/dev/null || true; wait "$BG_PID" 2>/dev/null || true; fi; rm -rf "$TMP"' EXIT
LOG_DIR="$TMP/logs"
STATE_DIR="$TMP/state"
mkdir -p "$LOG_DIR" "$STATE_DIR"
printf 'review\n' > "$TMP/prompt"
export FAKE_PID="$TMP/child.pid"
cat > "$TMP/reviewer" <<'EOF'
#!/usr/bin/env bash
echo $$ > "$FAKE_PID"
exec sleep 30
EOF
chmod +x "$TMP/reviewer"
# Exercise the actual background launch function with a temporary runner.
awk '/^start_codex_bg\(\)/ { copy=1 } /^wait_codex_bg\(\)/ { exit } copy' \
    "$ROOT/scripts/change-workflow.sh" > "$TMP/function.sh"
resolve_prompt() { printf '%s' "$1"; }
stage_reviewer_cmd() { printf '%s' "$TMP/reviewer"; }
stage_effort_for() { printf low; }
stage_model_for() { :; }
require_file() { [[ -s "$1" ]]; }
gated_prompt() { printf '%s' "$1"; }
status_stage_context() { :; }
. "$ROOT/scripts/lib/performance.sh"
. "$TMP/function.sh"
start_codex_bg "$TMP/prompt" "$TMP/review" test-review > /dev/null
for i in {1..100}; do [[ ! -s "$FAKE_PID" ]] || break; sleep .02; done
[[ -s "$FAKE_PID" ]]
child_pid="$(cat "$FAKE_PID")"
kill "$BG_PID"
status=0
wait "$BG_PID" || status=$?
BG_PID=""
[[ "$status" == 130 ]]
if kill -0 "$child_pid" 2>/dev/null; then
    echo 'FAIL: instrumentation orphaned the background reviewer'
    exit 1
fi
echo 'background-performance-test.sh: cancellation stops the wrapped reviewer'

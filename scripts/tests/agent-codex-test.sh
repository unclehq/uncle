#!/usr/bin/env bash
set -euo pipefail

# Fixture tests for scripts/agent-codex.sh.
# Hermetic: a stub codex under a temp directory, no network, no real calls.
#
# The shim translates the drivers' `claude -p` flag set onto `codex exec`, then
# rewrites codex's `--json` JSONL (thread.started / turn.started /
# item.completed / turn.completed) into the stream-json schema the drivers'
# format_claude_stream renders and record_cost reads. The properties that
# matter: exactly one terminal `result` event lands last, a run that produced
# no turn fails the stage instead of parking it, the sandbox is
# workspace-write and never a bypass flag, and a tier name from the driver's
# defaults is not forwarded as a codex model id.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SHIM="$ROOT/scripts/agent-codex.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
COUNT=0

fail() {
    echo "FAIL: $1"
    FAILED=$((FAILED + 1))
}

check_eq() {
    local name="$1" expected="$2" actual="$3"
    COUNT=$((COUNT + 1))
    if [[ "$actual" != "$expected" ]]; then
        fail "$name — expected '$expected', got '$actual'"
    fi
}

check_contains() {
    local name="$1" needle="$2" hay="$3"
    COUNT=$((COUNT + 1))
    case "$hay" in
        *"$needle"*) ;;
        *) fail "$name — '$needle' not in: $hay" ;;
    esac
}

check_absent() {
    local name="$1" needle="$2" hay="$3"
    COUNT=$((COUNT + 1))
    case "$hay" in
        *"$needle"*) fail "$name — '$needle' should not be in: $hay" ;;
    esac
}

# --- stubs ------------------------------------------------------------------

# Speaks codex's `--json` JSONL. Argv and stdin are recorded so the flag
# translation stays verifiable; the event stream is controlled by env vars.
cat > "$TMP/fake-codex" <<'EOF'
#!/usr/bin/env bash
# The adapter retains its channel, but the CLI and its child tests must not.
for name in UNCLE_STATUS_FILE UNCLE_PROJECT_ROOT UNCLE_CONFIG STAGEGATE_RUN_ID STAGEGATE_ORIGIN_REPO STAGEGATE_ORIGIN_ISSUE; do
    [[ -z "${!name:-}" ]] || { echo "Leaked workflow setting: $name" >&2; exit 88; }
done
if [[ -n "${ARGV_FILE:-}" ]]; then
    printf '%s\n' "$*" > "$ARGV_FILE"
fi
if [[ -n "${STDIN_FILE:-}" ]]; then
    cat > "$STDIN_FILE"
else
    cat > /dev/null
fi
echo '{"type":"thread.started","thread_id":"t-1"}'
if [[ "${EMIT_TURN:-1}" == "1" ]]; then
    echo '{"type":"turn.started"}'
fi
if [[ "${EMIT_MESSAGE:-1}" == "1" ]]; then
    echo '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Hello from codex"}}'
fi
if [[ "${EMIT_COMMAND:-0}" == "1" ]]; then
    echo '{"type":"item.completed","item":{"id":"item_1","type":"command_execution","command":"ls"}}'
fi
if [[ "${EMIT_REASONING:-0}" == "1" ]]; then
    echo '{"type":"item.completed","item":{"id":"item_2","type":"reasoning","text":"thinking"}}'
fi
if [[ -n "${EMIT_TEXT:-}" ]]; then
    printf '%s\n' "$EMIT_TEXT"
fi
if [[ "${EMIT_COMPLETED:-1}" == "1" ]]; then
    echo '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":20,"cache_write_input_tokens":10,"output_tokens":50,"reasoning_output_tokens":5}}'
fi
exit "${FAKE_EXIT:-0}"
EOF
chmod +x "$TMP/fake-codex"

run_shim() {
    WORKFLOW_CODEX_CMD="$TMP/fake-codex" "$SHIM" "$@"
}

driver_result() {
    jq -R -c 'fromjson? | select(.type == "result")' < "$1" | tail -n 1
}

# --- a completed turn is a successful stage --------------------------------

status=0
run_shim -p --model opus --effort high --max-turns 120 --output-format stream-json \
    --verbose --allowedTools Read,Write <<< "the prompt" > "$TMP/out.jsonl" || status=$?
check_eq "success: shim exit status" "0" "$status"

result="$(driver_result "$TMP/out.jsonl")"
if [[ -z "$result" ]]; then
    fail "success: no result event — the driver would treat the stage as failed"
    COUNT=$((COUNT + 1))
else
    check_eq "success: is_error" "false" "$(jq -r '.is_error' <<< "$result")"
    check_eq "success: subtype" "success" "$(jq -r '.subtype' <<< "$result")"
    check_eq "success: num_turns" "1" "$(jq -r '.num_turns' <<< "$result")"
    check_eq "success: input tokens" "100" "$(jq -r '.usage.input_tokens' <<< "$result")"
    check_eq "success: output tokens" "50" "$(jq -r '.usage.output_tokens' <<< "$result")"
    check_eq "success: cache read" "20" "$(jq -r '.usage.cache_read_input_tokens' <<< "$result")"
    check_eq "success: cache write" "10" "$(jq -r '.usage.cache_creation_input_tokens' <<< "$result")"
fi
check_eq "success: exactly one result event" "1" \
    "$(jq -R -r 'fromjson? | select(.type == "result") | .type' < "$TMP/out.jsonl" | wc -l | tr -d ' ')"
check_eq "success: result is last" "result" \
    "$(jq -R -r 'fromjson? | .type' < "$TMP/out.jsonl" | tail -n 1)"

# --- an agent message is text; other items are tool lines ------------------

EMIT_COMMAND=1 EMIT_REASONING=1 run_shim -p <<< "the prompt" > "$TMP/items.jsonl"
rendered="$(jq -R -r '
    (fromjson? // empty) as $e
    | if $e.type == "assistant" then
          ($e.message.content[]?
           | if .type == "text" then .text
             elif .type == "tool_use" then "[tool] \(.name)"
             else empty end)
      else empty end' < "$TMP/items.jsonl")"
check_contains "items: an agent message becomes text" "Hello from codex" "$rendered"
check_contains "items: a command becomes a tool line" "[tool] command_execution" "$rendered"
check_absent "items: reasoning is not shown" "thinking" "$rendered"

# --- a run with no completed turn is a failure, whatever the exit status ----

status=0
EMIT_TURN=0 EMIT_COMPLETED=0 run_shim -p <<< "the prompt" > "$TMP/noturn.jsonl" || status=$?
check_eq "no turn: shim exit status" "1" "$status"
result="$(driver_result "$TMP/noturn.jsonl")"
check_eq "no turn: is_error" "true" "$(jq -r '.is_error' <<< "$result")"
check_eq "no turn: subtype" "error_during_execution" "$(jq -r '.subtype' <<< "$result")"

# --- codex's own failure propagates ---------------------------------------

status=0
FAKE_EXIT=7 run_shim -p <<< "the prompt" > /dev/null 2>&1 || status=$?
check_eq "codex failure: exit status propagates" "7" "$status"

# --- context exhaustion is its own recoverable subtype ---------------------

status=0
EMIT_TURN=0 EMIT_COMPLETED=0 EMIT_TEXT="error: maximum context length exceeded" \
    run_shim -p <<< "the prompt" > "$TMP/ctx.jsonl" || status=$?
check_eq "context: subtype" "context_length_exceeded" \
    "$(jq -r '.subtype' <<< "$(driver_result "$TMP/ctx.jsonl")")"

# --- flag translation ------------------------------------------------------

ARGV_FILE="$TMP/argv" STDIN_FILE="$TMP/stdin" run_shim -p --model gpt-5-codex \
    --effort high --max-turns 120 --max-budget-usd 5 --output-format stream-json \
    --verbose --strict-mcp-config --allowedTools Read,Write <<< "the prompt" > /dev/null
argv="$(cat "$TMP/argv")"
for flag in "exec" "--json" "--ephemeral" "--skip-git-repo-check" \
            "--sandbox workspace-write" "-m gpt-5-codex" \
            "-c model_reasoning_effort=high"; do
    check_contains "flags: $flag" "$flag" "$argv"
done
for dropped in "-p" "--max-turns" "--max-budget-usd" "--allowedTools" \
               "--output-format" "--verbose" "--strict-mcp-config"; do
    check_absent "flags: $dropped is not forwarded" "$dropped" "$argv"
done
# An implementing stage writes, but never outside the sandbox.
check_absent "flags: no approval/sandbox bypass" "--dangerously-bypass" "$argv"
check_absent "flags: not read-only" "read-only" "$argv"

# --- sandbox network ---------------------------------------------------------
# workspace-write denies loopback binds unless codex is told otherwise, which
# is what stops a checklist stage from serving the product it is verifying.
# Opt-in only: the default must stay closed.
check_absent "network: closed by default" "network_access" "$argv"

ARGV_FILE="$TMP/argv-net" UNCLE_STAGE_NETWORK=true run_shim -p <<< "p" > /dev/null
check_contains "network: opt-in opens it" \
    "-c sandbox_workspace_write.network_access=true" "$(cat "$TMP/argv-net")"
check_contains "network: still sandboxed when open" \
    "--sandbox workspace-write" "$(cat "$TMP/argv-net")"
check_absent "network: opening it is not a bypass" \
    "--dangerously-bypass" "$(cat "$TMP/argv-net")"

for value in false "" 1 yes garbage; do
    ARGV_FILE="$TMP/argv-net-off" UNCLE_STAGE_NETWORK="$value" run_shim -p <<< "p" > /dev/null
    check_absent "network: '$value' does not open it" \
        "network_access" "$(cat "$TMP/argv-net-off")"
done
check_eq "the prompt reaches codex on stdin" "the prompt" "$(cat "$TMP/stdin")"

# --- a tier name is not a codex model id ----------------------------------

for tier in opus sonnet kimi; do
    ARGV_FILE="$TMP/argv-$tier" run_shim -p --model "$tier" <<< "p" > /dev/null
    check_absent "model: tier '$tier' is not forwarded" "-m " "$(cat "$TMP/argv-$tier")"
done

ARGV_FILE="$TMP/argv-real" run_shim -p --model o3 <<< "p" > /dev/null
check_contains "model: a real id is forwarded" "-m o3" "$(cat "$TMP/argv-real")"

UNCLE_CODEX_MODEL=gpt-5.1 ARGV_FILE="$TMP/argv-env" run_shim -p --model o3 <<< "p" > /dev/null
check_contains "model: UNCLE_CODEX_MODEL wins" "-m gpt-5.1" "$(cat "$TMP/argv-env")"

failure=$(EMIT_COMPLETED=0 EMIT_TEXT='{"type":"turn.failed","error":{"message":"Model unavailable"}}' run_shim -p <<< "p" || true)
check_contains "model error is retained" 'Model unavailable' "$failure"

# --- missing prompt fails fast --------------------------------------------

status=0
run_shim -p --model o3 < /dev/null > /dev/null 2>&1 || status=$?
check_eq "missing prompt: exit 2" "2" "$status"

# --- the status channel, when the TUI asked for one -----------------------

: > "$TMP/status.jsonl"
UNCLE_PROJECT_ROOT="$TMP/live-project" UNCLE_CONFIG="$TMP/live-config" STAGEGATE_RUN_ID=outer STAGEGATE_ORIGIN_REPO=real/project STAGEGATE_ORIGIN_ISSUE=6 \
UNCLE_STATUS_FILE="$TMP/status.jsonl" UNCLE_STATUS_STAGE=implementation \
    run_shim -p --model o3 <<< "the prompt" > /dev/null
check_eq "status: a start event names the stage" "implementation" \
    "$(jq -R -r 'fromjson? | select(.event == "start") | .stage' < "$TMP/status.jsonl" | head -1)"
check_eq "status: usage totals the turn without double-counting cache" "150" \
    "$(jq -R -r 'fromjson? | select(.event == "usage") | .total_tokens' < "$TMP/status.jsonl" | tail -1)"

# --- report ---------------------------------------------------------------

if [[ "$FAILED" -ne 0 ]]; then
    echo "agent-codex-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "agent-codex-test.sh: $COUNT checks passed"

#!/usr/bin/env bash
set -euo pipefail

# Fixture tests for scripts/agent-kimi.sh.
# Hermetic: stub CLIs under a temp directory, no network, no real agent calls.
#
# The regression these guard: kimi emits no `result` event, and run_claude in
# the drivers treats a stream without one as a failed stage. Every kimi-backed
# stage therefore failed no matter how it went — the baseline stage wrote
# BASELINE_REPORT.md four times and was discarded four times.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SHIM="$ROOT/scripts/agent-kimi.sh"

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

# --- stubs ------------------------------------------------------------------

# Speaks kimi's OpenAI-shaped dialect, including a non-JSON startup line.
cat > "$TMP/fake-kimi" <<'EOF'
#!/usr/bin/env bash
for arg in "$@"; do
    if [[ "$arg" == --print ]]; then echo "unknown option --print" >&2; exit 2; fi
done
echo 'startup notice, not json'
echo '{"role":"assistant","content":"Working."}'
echo '{"role":"assistant","tool_calls":[{"function":{"name":"Bash"}}]}'
echo '{"role":"meta","content":"dropped"}'
exit "${FAKE_KIMI_EXIT:-0}"
EOF

# Records the argv and stdin it was handed, so passthrough stays verifiable.
cat > "$TMP/fake-claude" <<'EOF'
#!/usr/bin/env bash
printf 'args: %s\n' "$*"
printf 'stdin: %s\n' "$(cat)"
exit "${FAKE_CLAUDE_EXIT:-0}"
EOF

chmod +x "$TMP/fake-kimi" "$TMP/fake-claude"

run_shim() {
    WORKFLOW_KIMI_CMD="$TMP/fake-kimi" \
    WORKFLOW_CLAUDE_CMD="$TMP/fake-claude" \
        "$SHIM" "$@"
}

# The drivers' own extraction (change-workflow.sh) and nothing more.
driver_result() {
    jq -R -c 'fromjson? | select(.type == "result")' < "$1" | tail -n 1
}

# --- the kimi path emits a terminal result event ----------------------------

status=0
run_shim -p --model kimi --max-turns 120 --output-format stream-json \
    --verbose --allowedTools "Bash Read" < /dev/null > "$TMP/out.jsonl" || status=$?

check_eq "kimi success: shim exit status" "0" "$status"

result="$(driver_result "$TMP/out.jsonl")"
COUNT=$((COUNT + 1))
if [[ -z "$result" ]]; then
    fail "kimi success: no result event — the driver would treat the stage as failed"
fi

check_eq "kimi success: is_error"  "false"   "$(printf '%s' "$result" | jq -r '.is_error')"
check_eq "kimi success: subtype"   "success" "$(printf '%s' "$result" | jq -r '.subtype')"

# record_cost reads these with `// 0`; they must be present and numeric.
check_eq "kimi success: unknown cost is null" "null" "$(printf '%s' "$result" | jq -r '.total_cost_usd | type')"
check_eq "kimi success: turns is numeric"    "number" "$(printf '%s' "$result" | jq -r '.num_turns | type')"
check_eq "kimi success: duration is numeric" "number" "$(printf '%s' "$result" | jq -r '.duration_ms | type')"

# Exactly one, and last: `tail -n 1` must not pick up a stale event.
check_eq "kimi success: one result event" "1" \
    "$(grep -c '"type":"result"' "$TMP/out.jsonl")"
check_eq "kimi success: result is the last line" "1" \
    "$(tail -n 1 "$TMP/out.jsonl" | grep -c '"type":"result"')"

# --- the translation the drivers render is unchanged ------------------------

check_eq "kimi: assistant text translated" "1" \
    "$(grep -c '{"type":"assistant","message":{"content":\[{"type":"text","text":"Working."}\]}}' "$TMP/out.jsonl")"
check_eq "kimi: tool_use translated" "1" \
    "$(grep -c '{"type":"tool_use","name":"Bash"}' "$TMP/out.jsonl")"
check_eq "kimi: non-JSON passed through" "1" \
    "$(grep -c '^startup notice, not json$' "$TMP/out.jsonl")"
check_eq "kimi: meta event dropped" "0" \
    "$(grep -c 'dropped' "$TMP/out.jsonl")"

# --- a kimi failure is reported, not swallowed ------------------------------

status=0
FAKE_KIMI_EXIT=3 run_shim -p --model kimi < /dev/null > "$TMP/fail.jsonl" || status=$?

check_eq "kimi failure: shim propagates exit status" "3" "$status"

result="$(driver_result "$TMP/fail.jsonl")"
COUNT=$((COUNT + 1))
if [[ -z "$result" ]]; then
    fail "kimi failure: no result event"
fi
check_eq "kimi failure: is_error" "true" "$(printf '%s' "$result" | jq -r '.is_error')"
check_eq "kimi failure: subtype"  "error_during_execution" \
    "$(printf '%s' "$result" | jq -r '.subtype')"

# --- kimi:<alias> selects the alias, still on the kimi path -----------------

status=0
run_shim -p --model kimi:some-alias < /dev/null > "$TMP/alias.jsonl" || status=$?
check_eq "kimi alias: shim exit status" "0" "$status"
COUNT=$((COUNT + 1))
if [[ -z "$(driver_result "$TMP/alias.jsonl")" ]]; then
    fail "kimi alias: no result event"
fi

# --- every other model is handed to claude untouched ------------------------

out="$(printf 'the prompt body' | run_shim -p --model opus --max-turns 120 \
    --verbose --allowedTools "Bash Read")"

check_eq "passthrough: argv preserved" \
    "args: -p --model opus --max-turns 120 --verbose --allowedTools Bash Read" \
    "$(printf '%s\n' "$out" | sed -n '1p')"
check_eq "passthrough: stdin preserved" \
    "stdin: the prompt body" \
    "$(printf '%s\n' "$out" | sed -n '2p')"

# claude speaks the schema itself; the shim must not add a second result event.
check_eq "passthrough: shim adds no result event" "0" \
    "$(grep -c '"type":"result"' <<<"$out")"

status=0
FAKE_CLAUDE_EXIT=7 run_shim -p --model opus < /dev/null > /dev/null || status=$?
check_eq "passthrough: claude exit status propagates" "7" "$status"

# --- --effort reaches kimi via KIMI_MODEL_THINKING_EFFORT -------------------
#
# The regression this guards: `kimi -p` has no --effort/--thinking flag (kimi
# --help lists none), so the shim used to capture the driver's --effort and
# then discard it in the claude-only-flags filter. Every prompt-mode stage
# then ran at whatever [thinking].effort happens to be set in the operator's
# ~/.kimi-code/config.toml, regardless of what stage-config.sh resolved for
# that stage. The CLI's one per-invocation override is the
# KIMI_MODEL_THINKING_EFFORT environment variable.

cat > "$TMP/fake-kimi-effort" <<'EOF'
#!/usr/bin/env bash
printf 'effort: %s\n' "${KIMI_MODEL_THINKING_EFFORT-<unset>}"
echo '{"role":"assistant","content":"done"}'
EOF
chmod +x "$TMP/fake-kimi-effort"

run_effort() {
    WORKFLOW_KIMI_CMD="$TMP/fake-kimi-effort" \
        "$SHIM" -p --model kimi --effort "$1" < /dev/null
}

check_eq "effort passthrough: low stays low" \
    "effort: low" "$(run_effort low | sed -n '1p')"
check_eq "effort passthrough: high stays high" \
    "effort: high" "$(run_effort high | sed -n '1p')"
check_eq "effort passthrough: max stays max" \
    "effort: max" "$(run_effort max | sed -n '1p')"

# Uncle's effort scale does not match every kimi model's declared
# support_efforts (kimi-k3 only accepts low/high/max); these are the same
# aliases native_kimi.py applies for its REST /profile call.
check_eq "effort passthrough: none maps to off" \
    "effort: off" "$(run_effort none | sed -n '1p')"
check_eq "effort passthrough: medium maps to high" \
    "effort: high" "$(run_effort medium | sed -n '1p')"
check_eq "effort passthrough: xhigh maps to max" \
    "effort: max" "$(run_effort xhigh | sed -n '1p')"

# No --effort at all: leave the override unset so kimi's own config/model
# default (whatever the operator configured) applies, rather than forcing a
# fixed level on every stage.
WORKFLOW_KIMI_CMD="$TMP/fake-kimi-effort"
check_eq "effort passthrough: absent leaves override unset" \
    "effort: <unset>" \
    "$(WORKFLOW_KIMI_CMD="$TMP/fake-kimi-effort" "$SHIM" -p --model kimi < /dev/null | sed -n '1p')"

# --- report -----------------------------------------------------------------

# --- a stalled kimi fails the stage instead of parking it ------------------
#
# kimi talks to a remote API; a socket can go established but silent and the
# process then sits in a read at 0% CPU. The shim strips --max-turns and
# --max-budget-usd because kimi does not accept them, so nothing else in the
# pipeline can bound that.

cat > "$TMP/stall" <<'EOF'
#!/usr/bin/env bash
echo '{"role":"assistant","content":"working"}'
sleep 300
EOF
chmod +x "$TMP/stall"

started="$SECONDS"
status=0
ARGV_FILE="$TMP/argv" WORKFLOW_KIMI_IDLE_TIMEOUT=5 WORKFLOW_KIMI_CMD="$TMP/stall" \
    "$SHIM" -p --model kimi --max-turns 200 < /dev/null > "$TMP/stall.out" 2>/dev/null || status=$?
elapsed=$(( SECONDS - started ))

COUNT=$((COUNT + 1))
if [[ "$elapsed" -gt 60 ]]; then
    fail "stall: shim ran ${elapsed}s; the idle guard should have stopped it"
fi

check_eq "stall: exit status is non-zero" "1" "$([[ "$status" -ne 0 ]] && echo 1 || echo 0)"

result="$(driver_result "$TMP/stall.out")"
COUNT=$((COUNT + 1))
if [[ -z "$result" ]]; then
    fail "stall: no result event — the driver would hang rather than fail the stage"
fi
check_eq "stall: is_error" "true" "$(printf '%s' "$result" | jq -r '.is_error')"

# The output produced before the stall is still rendered, so the log shows how
# far the stage got.
check_eq "stall: pre-stall output preserved" "1" \
    "$(grep -c '"text":"working"' "$TMP/stall.out")"

# Killing only kimi would leave its children holding the fifo open.
COUNT=$((COUNT + 1))
if pgrep -f "$TMP/stall" > /dev/null 2>&1; then
    fail "stall: descendants survived the guard"
    pkill -f "$TMP/stall" 2>/dev/null
fi

if [[ "$FAILED" -ne 0 ]]; then
    echo "agent-kimi-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "agent-kimi-test.sh: $COUNT checks passed"

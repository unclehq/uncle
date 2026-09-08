#!/usr/bin/env bash
set -euo pipefail

# Fixture tests for scripts/agent-cline.sh.
# Hermetic: a stub cline under a temp directory, no network, no real calls.
#
# The shim translates the drivers' `claude -p` flag set onto `cline`, then
# rewrites cline's `--json` NDJSON (agent_event / content_end / usage /
# run_result) into the stream-json schema the drivers' `format_claude_stream`
# renders and `record_cost` reads. The properties that matter: exactly one
# terminal `result` event lands last, a non-`completed` finishReason or a
# missing result fails the stage instead of parking it, and the model/effort
# pickers (UNCLE_CLINE_MODEL / UNCLE_CLINE_EFFORT) win over the driver flags.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SHIM="$ROOT/scripts/agent-cline.sh"

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

# Speaks cline's `--json` NDJSON. Argv is recorded so flag translation stays
# verifiable; the event stream is controlled by env vars.
cat > "$TMP/fake-cline" <<'EOF'
#!/usr/bin/env bash
if [[ -n "${ARGV_FILE:-}" ]]; then
    printf '%s\n' "$*" > "$ARGV_FILE"
fi
if [[ "${EMIT_CONTENT:-1}" == "1" ]]; then
    echo '{"type":"agent_event","event":{"type":"content_end","contentType":"text","text":"Hello from cline"}}'
fi
if [[ "${EMIT_USAGE:-0}" == "1" ]]; then
    echo '{"type":"agent_event","event":{"type":"usage","inputTokens":10,"outputTokens":5,"cacheReadTokens":2,"cacheWriteTokens":1,"cost":0.01,"totalInputTokens":100,"totalOutputTokens":50,"totalCacheReadTokens":20,"totalCacheWriteTokens":10,"totalCost":0.5}}'
fi
if [[ "${EMIT_RESULT:-1}" == "1" ]]; then
    echo '{"type":"run_result","finishReason":"'"${FINISH_REASON:-completed}"'","iterations":3,"usage":{"inputTokens":100,"outputTokens":50,"cacheReadTokens":20,"cacheWriteTokens":10,"totalCost":0.5},"durationMs":1234,"text":"'"${RESULT_TEXT:-Final answer}"'","model":"test-model","models":{"catalogue":{"description":"'"${CATALOGUE_TEXT:-Frontier reasoning and coding with 1M context window}"'"}}}'
fi
exit "${FAKE_EXIT:-0}"
EOF
chmod +x "$TMP/fake-cline"

run_shim() {
    WORKFLOW_CLINE_CMD="$TMP/fake-cline" "$SHIM" "$@"
}

# The drivers' own extraction (change-workflow.sh) and nothing more.
driver_result() {
    jq -R -c 'fromjson? | select(.type == "result")' < "$1" | tail -n 1
}

# --- the cline path emits a terminal result event ---------------------------

status=0
run_shim -p --model vendor/some-model --max-turns 120 --output-format stream-json \
    --verbose --allowedTools "Bash Read" <<< "the prompt" > "$TMP/out.jsonl" || status=$?

check_eq "success: shim exit status" "0" "$status"

result="$(driver_result "$TMP/out.jsonl")"
COUNT=$((COUNT + 1))
if [[ -z "$result" ]]; then
    fail "success: no result event — the driver would treat the stage as failed"
fi

check_eq "success: is_error"  "false"   "$(printf '%s' "$result" | jq -r '.is_error')"
check_eq "success: subtype"   "success" "$(printf '%s' "$result" | jq -r '.subtype')"

# record_cost reads these with `// 0`; they must be present and numeric.
check_eq "success: cost is numeric"     "number" "$(printf '%s' "$result" | jq -r '.total_cost_usd | type')"
check_eq "success: turns is numeric"    "number" "$(printf '%s' "$result" | jq -r '.num_turns | type')"
check_eq "success: duration is numeric" "number" "$(printf '%s' "$result" | jq -r '.duration_ms | type')"
check_eq "success: turns value"    "3"    "$(printf '%s' "$result" | jq -r '.num_turns')"
check_eq "success: cost value"     "0.5"  "$(printf '%s' "$result" | jq -r '.total_cost_usd')"
check_eq "success: duration value" "1234" "$(printf '%s' "$result" | jq -r '.duration_ms')"

# The snake_case usage keys are what record_cost reads.
check_eq "success: input_tokens"               "100" "$(printf '%s' "$result" | jq -r '.usage.input_tokens')"
check_eq "success: output_tokens"              "50"  "$(printf '%s' "$result" | jq -r '.usage.output_tokens')"
check_eq "success: cache_read_input_tokens"    "20"  "$(printf '%s' "$result" | jq -r '.usage.cache_read_input_tokens')"
check_eq "success: cache_creation_input_tokens" "10" "$(printf '%s' "$result" | jq -r '.usage.cache_creation_input_tokens')"

# Exactly one, and last: `tail -n 1` must not pick up a stale event.
check_eq "success: one result event" "1" \
    "$(grep -c '"type":"result"' "$TMP/out.jsonl")"
check_eq "success: result is the last line" "1" \
    "$(tail -n 1 "$TMP/out.jsonl" | grep -c '"type":"result"')"

# --- the translation the drivers render is unchanged ------------------------

check_eq "success: assistant text translated" "1" \
    "$(grep -c '{"type":"assistant","message":{"content":\[{"type":"text","text":"Hello from cline"}\]}}' "$TMP/out.jsonl")"

# --- a non-completed finishReason is a failed stage, not a parked one -------

status=0
FINISH_REASON=max_iterations run_shim -p --model vendor/some-model <<< "the prompt" \
    > "$TMP/fail.jsonl" || status=$?

check_eq "non-completed: shim exit status" "1" "$status"

result="$(driver_result "$TMP/fail.jsonl")"
COUNT=$((COUNT + 1))
if [[ -z "$result" ]]; then
    fail "non-completed: no result event"
fi
check_eq "non-completed: is_error" "true" "$(printf '%s' "$result" | jq -r '.is_error')"
check_eq "non-completed: subtype"  "error_during_execution" \
    "$(printf '%s' "$result" | jq -r '.subtype')"

# --- context exhaustion is read from the failure, not from the transcript ----
# cline's run_result carries a catalogue of models, and those descriptions say
# things like "1M context window". Scanning the whole stream therefore labelled
# every cline failure as context exhaustion -- a weekly billing limit included
# -- which sends the operator to change models when the real fix is to change
# providers or wait. Observed against cline 3.0.61.
result="$(FINISH_REASON=error FAKE_EXIT=1 \
    RESULT_TEXT="You have reached your weekly Clinepass limit. The limit resets in 5d 14h." \
    run_shim -p <<< "prompt" | grep '"type":"result"' || true)"
check_eq "a quota limit is not context exhaustion" "error_during_execution" \
    "$(printf '%s' "$result" | jq -r '.subtype')"

# The real thing still classifies, from the same field.
result="$(FINISH_REASON=error FAKE_EXIT=1 \
    RESULT_TEXT="Request failed: maximum context length exceeded" \
    run_shim -p <<< "prompt" | grep '"type":"result"' || true)"
check_eq "real context exhaustion is named" "context_length_exceeded" \
    "$(printf '%s' "$result" | jq -r '.subtype')"

# And a success is never relabelled, catalogue or no catalogue.
result="$(run_shim -p <<< "prompt" | grep '"type":"result"' || true)"
check_eq "a successful run keeps its subtype" "success" \
    "$(printf '%s' "$result" | jq -r '.subtype')"

# --- a missing run_result is a failed stage, not a hung one -----------------
# cline that exits 0 but emits no run_result (e.g. interrupted before the final
# event) must still surface a terminal result so the driver fails fast.

status=0
EMIT_RESULT=0 run_shim -p --model vendor/some-model <<< "the prompt" \
    > "$TMP/noresult.jsonl" || status=$?

check_eq "no run_result: shim exit status" "1" "$status"

result="$(driver_result "$TMP/noresult.jsonl")"
COUNT=$((COUNT + 1))
if [[ -z "$result" ]]; then
    fail "no run_result: no result event"
fi
check_eq "no run_result: is_error" "true" "$(printf '%s' "$result" | jq -r '.is_error')"
check_eq "no run_result: subtype"  "error_during_execution" \
    "$(printf '%s' "$result" | jq -r '.subtype')"

# --- a non-zero cline exit propagates ---------------------------------------

status=0
FAKE_EXIT=7 run_shim -p --model vendor/some-model <<< "the prompt" > /dev/null || status=$?
check_eq "cline failure: exit status propagates" "7" "$status"

# --- flag translation --------------------------------------------------------
# The drivers pass `claude -p` flags. cline keeps --json/--auto-approve/-m/
# --thinking; the rest are dropped.

ARGV_FILE="$TMP/argv" run_shim -p --model vendor/some-model --max-turns 120 \
    --output-format stream-json --verbose --strict-mcp-config \
    --exclude-dynamic-system-prompt-sections --allowedTools "Bash Read" \
    --max-budget-usd 12 --effort medium <<< "the prompt" > /dev/null

argv="$(cat "$TMP/argv")"

# An omitted mode inherits Cline's saved planActMode, which may be plan.
# Document-producing stages must explicitly select act even in that case.
for flag in --act --json --auto-approve "-m vendor/some-model" "--thinking medium"; do
    COUNT=$((COUNT + 1))
    case " $argv " in
        *" $flag "*) ;;
        *) fail "flags: expected '$flag' in argv, got '$argv'" ;;
    esac
done

for flag in -p --max-turns --output-format --verbose --strict-mcp-config \
    --exclude-dynamic-system-prompt-sections --allowedTools --max-budget-usd \
    --effort 120 12 "Bash Read" stream-json; do
    COUNT=$((COUNT + 1))
    case " $argv " in
        *" $flag "*) fail "flags: claude-only '$flag' leaked through to cline" ;;
    esac
done

# --- the prompt moves from stdin to a positional arg -------------------------

ARGV_FILE="$TMP/prompt-argv" run_shim -p --model vendor/some-model \
    <<< "promptbody" > /dev/null

check_eq "prompt: moved to a positional arg" \
    "promptbody" "$(sed -n '1p' "$TMP/prompt-argv" | awk '{print $NF}')"

# --- model / effort pickers win over driver flags ---------------------------
# A cline model id carried by the driver wins; a tier name falls back to the
# global pick, then to cline's own default (no -m).

UNCLE_CLINE_MODEL=vendor/global-model ARGV_FILE="$TMP/argv1" \
    run_shim -p --model opus <<< "the prompt" > /dev/null
COUNT=$((COUNT + 1))
case " $(cat "$TMP/argv1") " in
    *" -m vendor/global-model "*) ;;
    *) fail "model: tier 'opus' did not fall back to UNCLE_CLINE_MODEL" ;;
esac

ARGV_FILE="$TMP/argv2" run_shim -p --model opus <<< "the prompt" > /dev/null
COUNT=$((COUNT + 1))
case " $(cat "$TMP/argv2") " in
    *" -m "*) fail "model: with no global pick a tier must emit no -m flag" ;;
esac

ARGV_FILE="$TMP/argv3" run_shim -p --model vendor/specific-model-id \
    <<< "the prompt" > /dev/null
COUNT=$((COUNT + 1))
case " $(cat "$TMP/argv3") " in
    *" -m vendor/specific-model-id "*) ;;
    *) fail "model: a real cline model id was rewritten instead of passed through" ;;
esac

UNCLE_CLINE_EFFORT=high ARGV_FILE="$TMP/argv4" \
    run_shim -p --model vendor/some-model --effort low <<< "the prompt" > /dev/null
COUNT=$((COUNT + 1))
case " $(cat "$TMP/argv4") " in
    *" --thinking high "*) ;;
    *) fail "effort: UNCLE_CLINE_EFFORT did not override --effort" ;;
esac

# --- missing prompt fails fast ----------------------------------------------

status=0
run_shim -p --model vendor/some-model < /dev/null > /dev/null 2>&1 || status=$?
check_eq "missing prompt: exit 2" "2" "$status"

# --- a model id cline cannot parse is refused before cline runs -------------

# cline needs modelType/model. A display name ("Laguna S 2.1", or the
# space-stripped "LagunaS2.1" a stale config produces) is otherwise only
# rejected by cline itself, one turn into the stage.

status=0
err="$TMP/badmodel.err"
argv="$TMP/badmodel.argv"
rm -f "$argv"
ARGV_FILE="$argv" run_shim -p --model "LagunaS2.1" <<< "the prompt" \
    > /dev/null 2>"$err" || status=$?
check_eq "invalid model: exit 2" "2" "$status"
check_eq "invalid model: cline was not invoked" "absent" \
    "$([[ -e "$argv" ]] && echo present || echo absent)"
case "$(cat "$err")" in
    *"LagunaS2.1"*) ;;
    *) fail "invalid model: error does not name the offending value" ;;
esac
COUNT=$((COUNT + 1))

# The global pick is validated too, not just the driver flag.
status=0
UNCLE_CLINE_MODEL="Laguna S 2.1" run_shim -p --model opus <<< "the prompt" \
    > /dev/null 2>&1 || status=$?
check_eq "invalid global pick: exit 2" "2" "$status"

# A well-formed id and an empty pick both still run.
status=0
UNCLE_CLINE_MODEL="" run_shim -p --model opus <<< "the prompt" > /dev/null 2>&1 || status=$?
check_eq "no model at all: still runs" "0" "$status"

# --- report -----------------------------------------------------------------

if [[ "$FAILED" -ne 0 ]]; then
    echo "agent-cline-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "agent-cline-test.sh: $COUNT checks passed"

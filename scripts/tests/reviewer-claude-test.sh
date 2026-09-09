#!/usr/bin/env bash
set -euo pipefail

# Fixture tests for scripts/reviewer-claude.sh.
# Hermetic: a stub claude under a temp directory, no network, no real calls.
#
# The shim translates the drivers' `codex exec` flag set onto `claude -p`. The
# properties that matter: the review artifact is written only on success, the
# reviewer gets no tool that can write or execute, and a failed review is not
# reported as a passing one.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SHIM="$ROOT/scripts/reviewer-claude.sh"

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

check_absent() {
    local name="$1" file="$2"
    COUNT=$((COUNT + 1))
    if [[ -e "$file" ]]; then
        fail "$name — $file was written"
    fi
}

# Records argv and stdin on fd 3, then speaks claude's stream-json.
cat > "$TMP/fake-claude" <<'EOF'
#!/usr/bin/env bash
printf 'ARGV: %s\n' "$*" > "$ARGV_FILE"
printf 'STDIN: %s\n' "$(cat)" >> "$ARGV_FILE"
echo '{"type":"assistant","message":{"content":[{"type":"text","text":"Reading."}]}}'
echo '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read"}]}}'
printf '123\nnull\n[]\n'
echo '{"type":"result","subtype":"success","is_error":false,"total_cost_usd":0.02,"result":"## AR-001: Finding\n\nNOT READY","usage":{"input_tokens":100,"output_tokens":200,"cache_read_input_tokens":50,"cache_creation_input_tokens":25}}'
exit "${FAKE_EXIT:-0}"
EOF

cat > "$TMP/no-result" <<'EOF'
#!/usr/bin/env bash
cat > /dev/null
echo '{"type":"assistant","message":{"content":[{"type":"text","text":"partial"}]}}'
EOF

cat > "$TMP/errored" <<'EOF'
#!/usr/bin/env bash
cat > /dev/null
echo '{"type":"result","subtype":"error_max_turns","is_error":true,"result":""}'
EOF

chmod +x "$TMP/fake-claude" "$TMP/no-result" "$TMP/errored"

run_shim() {
    local cli="$1"; shift
    ARGV_FILE="$TMP/argv" WORKFLOW_REVIEWER_CLAUDE_CMD="$TMP/$cli" "$SHIM" "$@"
}

# --- the codex flag set is translated -------------------------------------

out="$TMP/review.md"
status=0
run_shim fake-claude exec --ephemeral --sandbox read-only \
    --output-last-message "$out" -c model_reasoning_effort=high \
    "REVIEW THE PLAN" > "$TMP/stdout" 2>&1 || status=$?

check_eq "success: shim exit status" "0" "$status"

argv="$(sed -n '1p' "$TMP/argv")"
COUNT=$((COUNT + 1))
case "$argv" in
    *"--effort high"*) ;;
    *) fail "effort: -c model_reasoning_effort=high did not become --effort high — got '$argv'" ;;
esac

check_eq "prompt moved to stdin" "STDIN: REVIEW THE PLAN" "$(sed -n '2p' "$TMP/argv")"

# The codex-only flags must not reach claude.
for flag in exec --ephemeral --sandbox read-only --output-last-message; do
    COUNT=$((COUNT + 1))
    case " $argv " in
        *" $flag "*) fail "codex flag '$flag' leaked through to claude" ;;
    esac
done

# --- read-only is the property the workflow depends on ---------------------

COUNT=$((COUNT + 1))
case "$argv" in
    *"--allowedTools Read,Glob,Grep"*) ;;
    *) fail "tools: expected a read-only allowlist, got '$argv'" ;;
esac

for tool in Write Edit Bash NotebookEdit; do
    COUNT=$((COUNT + 1))
    case "$argv" in
        *"$tool"*) fail "tools: '$tool' is reachable by the reviewer" ;;
    esac
done

# --- the artifact is the review, and record_codex_cost can read the log ----

check_eq "artifact content" "## AR-001: Finding

NOT READY" "$(cat "$out")"

check_eq "native review cost preserved" "0.02" "$(jq -R -r 'fromjson? | select(type == "object") | select(.type == "result") | .total_cost_usd' "$TMP/stdout")"

check_eq "token line parses" "375" \
    "$(awk '/tokens used/ {getline; gsub(/[^0-9]/, "", $0); if ($0 != "") t = $0} END {print (t == "" ? "-" : t)}' "$TMP/stdout")"

# --- a failed review must not leave an artifact behind ---------------------
# The drivers `require_file` the output afterwards; a stale or partial file
# would be accepted as this stage's review.

out="$TMP/fail-exit.md"
status=0
FAKE_EXIT=4 run_shim fake-claude exec --output-last-message "$out" "P" \
    > /dev/null 2>&1 || status=$?
check_eq "claude failure: exit status propagates" "4" "$status"
check_absent "claude failure: no artifact" "$out"

out="$TMP/fail-noresult.md"
status=0
run_shim no-result exec --output-last-message "$out" "P" > /dev/null 2>&1 || status=$?
check_eq "no result event: exit 1" "1" "$status"
check_absent "no result event: no artifact" "$out"

out="$TMP/fail-error.md"
status=0
run_shim errored exec --output-last-message "$out" "P" > /dev/null 2>&1 || status=$?
check_eq "is_error result: exit 1" "1" "$status"
check_absent "is_error result: no artifact" "$out"

status=0
run_shim fake-claude exec --output-last-message "$TMP/none.md" > /dev/null 2>&1 || status=$?
check_eq "missing prompt: exit 2" "2" "$status"
check_absent "missing prompt: no artifact" "$TMP/none.md"

# --- stagegate passes -m, sometimes with a codex model name ----------------

run_shim fake-claude exec --sandbox read-only -m sonnet \
    --output-last-message "$TMP/m.md" "P" > /dev/null 2>&1
COUNT=$((COUNT + 1))
case "$(sed -n '1p' "$TMP/argv")" in
    *"--model sonnet"*) ;;
    *) fail "-m sonnet did not become --model sonnet" ;;
esac

# Allowlist, not denylist: anything that is not a Claude tier falls back.
for bad in gpt-5.6-sol o3-mini codex-1 gemini-2.5-pro some-future-model; do
    run_shim fake-claude exec -m "$bad" --output-last-message "$TMP/g.md" "P" \
        > /dev/null 2>&1
    COUNT=$((COUNT + 1))
    case "$(sed -n '1p' "$TMP/argv")" in
        *"--model opus"*) ;;
        *) fail "non-Claude model '$bad' was passed to claude instead of falling back" ;;
    esac
done

# Claude tiers and full model ids must survive untouched.
for good in opus sonnet haiku claude-opus-5 sonnet-5; do
    run_shim fake-claude exec -m "$good" --output-last-message "$TMP/g.md" "P" \
        > /dev/null 2>&1
    COUNT=$((COUNT + 1))
    case "$(sed -n '1p' "$TMP/argv")" in
        *"--model $good"*) ;;
        *) fail "Claude tier '$good' was rewritten instead of passed through" ;;
    esac
done

if [[ "$FAILED" -ne 0 ]]; then
    echo "reviewer-claude-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "reviewer-claude-test.sh: $COUNT checks passed"

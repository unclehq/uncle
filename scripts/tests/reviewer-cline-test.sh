#!/usr/bin/env bash
set -euo pipefail

# Fixture tests for scripts/reviewer-cline.sh.
# Hermetic: a stub cline under a temp directory, no network, no real calls.
#
# The shim translates the drivers' `codex exec` flag set onto `cline -p`
# (plan mode enforces read-only), then extracts the final review text and
# token totals from cline's `--json` NDJSON. The properties that matter: the
# artifact is written only on success, the reviewer gets no tool that can
# write or execute, and a failed review is never reported as a passing one.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SHIM="$ROOT/scripts/reviewer-cline.sh"

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

# --- stubs ------------------------------------------------------------------

# Speaks cline's `--json` NDJSON. Argv is recorded; events are env-controlled.
cat > "$TMP/fake-cline" <<'EOF'
#!/usr/bin/env bash
if [[ -n "${ARGV_FILE:-}" ]]; then
    printf '%s\n' "$*" > "$ARGV_FILE"
fi
if [[ "${EMIT_RESULT:-1}" == "1" ]]; then
    echo '{"type":"run_result","finishReason":"completed","iterations":1,"usage":{"inputTokens":10,"outputTokens":5,"cacheReadTokens":2,"cacheWriteTokens":1,"totalCost":0.01},"durationMs":99,"text":"REVIEW TEXT","model":"m"}'
elif [[ "${EMIT_DONE:-0}" == "1" ]]; then
    echo '{"type":"agent_event","event":{"type":"done","reason":"completed","text":"DONE TEXT","iterations":1}}'
fi
exit "${FAKE_EXIT:-0}"
EOF
chmod +x "$TMP/fake-cline"

run_shim() {
    WORKFLOW_CLINE_CMD="$TMP/fake-cline" "$SHIM" "$@"
}

# The drivers' record_codex_cost extraction and nothing more.
tokens_from() {
    awk '/tokens used/ {getline; gsub(/[^0-9]/, "", $0); if ($0 != "") t = $0} END {print (t == "" ? "-" : t)}' "$1"
}

# --- the codex flag set is translated ---------------------------------------

out="$TMP/review.md"
status=0
run_shim exec --ephemeral --sandbox read-only \
    --output-last-message "$out" -c model_reasoning_effort=high \
    "REVIEW THE PLAN" > "$TMP/stdout" 2>&1 || status=$?

check_eq "success: shim exit status" "0" "$status"
check_eq "artifact content" "REVIEW TEXT" "$(cat "$out")"
check_eq "review printed to stdout" "1" "$(grep -c '^REVIEW TEXT$' "$TMP/stdout")"
check_eq "token line parses" "18" "$(tokens_from "$TMP/stdout")"

# --- the codex-only flags must not reach cline ------------------------------

ARGV_FILE="$TMP/argv" run_shim exec --ephemeral --sandbox read-only \
    --output-last-message "$TMP/x.md" -m cline-pass/kimi-k3 -c model_reasoning_effort=high \
    "REVIEW THE PLAN" > /dev/null

argv="$(cat "$TMP/argv")"

for flag in --json -p "-m cline-pass/kimi-k3" "--thinking high"; do
    COUNT=$((COUNT + 1))
    case " $argv " in
        *" $flag "*) ;;
        *) fail "flags: expected '$flag' in argv, got '$argv'" ;;
    esac
done

for flag in exec --ephemeral --sandbox --output-last-message -c \
    read-only model_reasoning_effort=high; do
    COUNT=$((COUNT + 1))
    case " $argv " in
        *" $flag "*) fail "flags: codex-only '$flag' leaked through to cline" ;;
    esac
done

COUNT=$((COUNT + 1))
case " $argv " in
    *" REVIEW THE PLAN "*) ;;
    *) fail "flags: prompt was not passed as the trailing positional arg" ;;
esac

# --- read-only is the property the workflow depends on ----------------------
# Plan mode (-p) enforces read-only; the shim must not pass an editable tool
# allowlist or an act-mode invocation.

COUNT=$((COUNT + 1))
case " $argv " in
    *" -p "*) ;;
    *) fail "plan mode: expected -p in argv, got '$argv'" ;;
esac

for flag in --auto-approve --allowedTools Write Edit Bash; do
    COUNT=$((COUNT + 1))
    case " $argv " in
        *" $flag "*) fail "read-only: '$flag' is reachable by the reviewer" ;;
    esac
done

# --- model precedence -------------------------------------------------------
# Dedicated reviewer model > global pick > driver -m.

UNCLE_CLINE_REVIEWER_MODEL=vendor/reviewer-model ARGV_FILE="$TMP/argv1" \
    run_shim exec -m vendor/driver-model "P" > /dev/null
COUNT=$((COUNT + 1))
case " $(cat "$TMP/argv1") " in
    *" -m vendor/reviewer-model "*) ;;
    *) fail "model: UNCLE_CLINE_REVIEWER_MODEL did not win over -m" ;;
esac

UNCLE_CLINE_MODEL=vendor/global-model ARGV_FILE="$TMP/argv2" \
    run_shim exec -m vendor/driver-model "P" > /dev/null
COUNT=$((COUNT + 1))
case " $(cat "$TMP/argv2") " in
    *" -m vendor/global-model "*) ;;
    *) fail "model: UNCLE_CLINE_MODEL did not win over -m when no reviewer model set" ;;
esac

ARGV_FILE="$TMP/argv3" run_shim exec -m vendor/driver-model "P" > /dev/null
COUNT=$((COUNT + 1))
case " $(cat "$TMP/argv3") " in
    *" -m vendor/driver-model "*) ;;
    *) fail "model: driver -m was not passed through when no override set" ;;
esac

UNCLE_CLINE_EFFORT=low ARGV_FILE="$TMP/argv4" \
    run_shim exec -c model_reasoning_effort=high "P" > /dev/null
COUNT=$((COUNT + 1))
case " $(cat "$TMP/argv4") " in
    *" --thinking low "*) ;;
    *) fail "effort: UNCLE_CLINE_EFFORT did not override -c model_reasoning_effort" ;;
esac

# --- a done event is an acceptable final text fallback ----------------------

out="$TMP/done.md"
status=0
EMIT_RESULT=0 EMIT_DONE=1 run_shim exec --output-last-message "$out" "P" \
    > "$TMP/done-out" 2>&1 || status=$?
check_eq "done fallback: exit 0" "0" "$status"
check_eq "done fallback: review text" "DONE TEXT" "$(cat "$out")"
check_eq "done fallback: tokens zero" "0" "$(tokens_from "$TMP/done-out")"

# --- a failed review must not leave an artifact behind ----------------------

out="$TMP/noresult.md"
status=0
EMIT_RESULT=0 run_shim exec --output-last-message "$out" "P" \
    > /dev/null 2>&1 || status=$?
check_eq "no final text: exit 1" "1" "$status"
check_absent "no final text: no artifact" "$out"

out="$TMP/fail-exit.md"
status=0
FAKE_EXIT=4 run_shim exec --output-last-message "$out" "P" \
    > /dev/null 2>&1 || status=$?
check_eq "cline failure: exit status propagates" "4" "$status"
check_absent "cline failure: no artifact" "$out"

status=0
run_shim exec --output-last-message "$TMP/none.md" > /dev/null 2>&1 || status=$?
check_eq "missing prompt: exit 2" "2" "$status"
check_absent "missing prompt: no artifact" "$TMP/none.md"

# --- reviewer tier names and unparseable ids --------------------------------

# The drivers default the reviewer model to CODEX_MODEL, so a codex tier name
# can reach this shim. It is not a cline id: fall back to the configured cline
# model, and emit no -m when there is none.

UNCLE_CLINE_MODEL=vendor/global-model ARGV_FILE="$TMP/argv-tier1" \
    run_shim exec -m sonnet "P" > /dev/null
COUNT=$((COUNT + 1))
case " $(cat "$TMP/argv-tier1") " in
    *" -m vendor/global-model "*) ;;
    *) fail "tier: 'sonnet' did not fall back to the configured cline model" ;;
esac

ARGV_FILE="$TMP/argv-tier2" run_shim exec -m sonnet "P" > /dev/null
COUNT=$((COUNT + 1))
case " $(cat "$TMP/argv-tier2") " in
    *" -m "*) fail "tier: with no configured model a tier must emit no -m flag" ;;
esac

status=0
err="$TMP/badmodel.err"
run_shim exec -m "LagunaS2.1" "P" > /dev/null 2>"$err" || status=$?
check_eq "invalid model: exit 2" "2" "$status"
case "$(cat "$err")" in
    *"LagunaS2.1"*) ;;
    *) fail "invalid model: error does not name the offending value" ;;
esac
COUNT=$((COUNT + 1))

# --- report -----------------------------------------------------------------

if [[ "$FAILED" -ne 0 ]]; then
    echo "reviewer-cline-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "reviewer-cline-test.sh: $COUNT checks passed"

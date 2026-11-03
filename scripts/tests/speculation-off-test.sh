#!/usr/bin/env bash
set -euo pipefail

# Speculative stages are off by default, attended or not. An unattended gate is open for 0.0 seconds, so there is nothing for a
# background stage to overlap, and the speculative PROJECT_PLAN / UPDATED_PLAN stages ended with "produced no artifact": the real stage
# waited for them and ran again, and the spend was wasted. The real functions are run, so this cannot drift from the driver.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DRIVER="$ROOT/scripts/stagegate.sh"
FAILED=0
COUNT=0
check_eq() {
    COUNT=$((COUNT + 1))
    [[ "$3" == "$2" ]] || { echo "FAIL: $1 — expected '$2', got '$3'"; FAILED=$((FAILED + 1)); }
}

LINE="$(grep -E '^WORKFLOW_SPECULATE=' "$DRIVER")"
check_eq "the driver sets the default on one line" 1 "$(printf '%s\n' "$LINE" | grep -c .)"
default_value() { env "$@" bash -c "$LINE; printf %s \"\$WORKFLOW_SPECULATE\""; }
check_eq "default: off" 0 "$(default_value -u WORKFLOW_SPECULATE)"
check_eq "an explicit 1 turns it on" 1 "$(default_value WORKFLOW_SPECULATE=1)"
check_eq "an explicit 0 keeps it off" 0 "$(default_value WORKFLOW_SPECULATE=0)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/root/scripts/lib" "$TMP/spec" "$TMP/logs" "$TMP/state"
cat > "$TMP/root/scripts/lib/model-jobs.sh" <<'SH'
workflow_terminal_failure() { return 1; }
workflow_archive_attempt() { return 0; }
SH
printf 'gate\n' > "$TMP/gate.json"

extract() { awk -v f="$1" '$0 == f "() {" {p=1} p{print} p&&/^}/{exit}' "$DRIVER"; }
eval "$(extract speculate)"
eval "$(extract adopt_speculation)"
canonical_artifact_path() { printf '%s\n' "$TMP/gate.json"; }
hash_file() { sha256sum "$1" 2> /dev/null | cut -d' ' -f1 || shasum -a 256 "$1" | cut -d' ' -f1; }
run_stage() { printf '%s\n' "$1" >> "$TMP/stages-run"; }
ROOT_REAL="$ROOT"; ROOT="$TMP/root"; SPEC_DIR="$TMP/spec"; LOG_DIR="$TMP/logs"; STATE_DIR="$TMP/state"
spec_pid=""; spec_stage=""

# With the default, the function starts nothing.
WORKFLOW_SPECULATE=0
speculate PROJECT_PLAN .uncle/docs/REQUIREMENTS_INTERPRETATION.md > "$TMP/off.out" 2>&1 || true
check_eq "off: no background pid" "" "$spec_pid"
check_eq "off: no speculative stage recorded" "" "$spec_stage"
check_eq "off: nothing was run" 0 "$([[ -e "$TMP/stages-run" ]] && wc -l < "$TMP/stages-run" | tr -d ' ' || echo 0)"
check_eq "off: nothing was announced" 0 "$(grep -c 'in the background' "$TMP/off.out" || true)"
check_eq "off: no speculative input file" 0 "$(ls "$TMP/spec" | wc -l | tr -d ' ')"
check_eq "off: no speculative log" 0 "$(ls "$TMP/logs" | wc -l | tr -d ' ')"

# With nothing started, adoption declines at once, so the foreground stage runs straight away and never waits.
adopt_status=0
adopt_speculation PROJECT_PLAN .uncle/docs/REQUIREMENTS_INTERPRETATION.md .uncle/docs/PROJECT_PLAN.md > "$TMP/adopt.out" 2>&1 || adopt_status=$?
check_eq "off: adoption declines (the stage runs in the foreground)" 1 "$adopt_status"
check_eq "off: and prints nothing about waiting" 0 "$(grep -c 'Waiting for the speculative' "$TMP/adopt.out" || true)"

# The switch still works when someone asks for it.
WORKFLOW_SPECULATE=1
speculate PROJECT_PLAN .uncle/docs/REQUIREMENTS_INTERPRETATION.md > "$TMP/on.out" 2>&1
check_eq "on: a background job was started" 1 "$([[ -n "$spec_pid" ]] && echo 1 || echo 0)"
check_eq "on: the stage is recorded" PROJECT_PLAN "$spec_stage"
wait "$spec_pid" 2> /dev/null || true
check_eq "on: the stage ran" PROJECT_PLAN "$(cat "$TMP/stages-run")"
check_eq "on: it was announced" 1 "$(grep -c 'in the background' "$TMP/on.out")"

ROOT="$ROOT_REAL"
# The docs say what the code does.
COUNT=$((COUNT + 1))
grep -q 'off by default' "$ROOT/AGENTIC.md" || { echo "FAIL: AGENTIC.md does not say speculation is off by default"; FAILED=$((FAILED + 1)); }
COUNT=$((COUNT + 1))
if grep -q 'can be disabled' "$ROOT/AGENTIC.md"; then echo "FAIL: AGENTIC.md still describes it as on"; FAILED=$((FAILED + 1)); fi

if [[ "$FAILED" -ne 0 ]]; then
    echo "speculation-off-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi
echo "speculation-off-test.sh: $COUNT checks passed"

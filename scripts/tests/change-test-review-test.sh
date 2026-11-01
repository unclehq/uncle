#!/usr/bin/env bash
# uncle consolidation item 1: change-workflow.sh gained a TEST_REVIEW/
# VALIDATE_TEST_REVIEW pair modeled on stagegate.sh's (CLAUDE.md Stage 6:
# coverage, integrity, assertions, oracle provenance, defect-injection
# evidence, results), reviewing CHANGE_TEST_REPORT.md instead of
# AUTOMATED_TEST_REPORT.md, positioned the same place relative to FINAL_AUDIT
# (before checklist generation). This proves: (a) the state machine actually
# visits TEST_REVIEW between WAIT_IMPLEMENT_APPROVAL and CHECKLIST; (b) the
# validation step uses the shared acceptance-gate framework
# (scripts/lib/acceptance-gate.sh), not a reimplementation; (c) a FAIL finding
# routes to IMPLEMENT, not to a REPAIR state change-workflow.sh does not have
# (confirmed: zero `set_state REPAIR` anywhere in it) -- a deliberate choice,
# not an oversight, documented at the acceptance_transition call site.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }

# --- (a) the state machine actually transitions through TEST_REVIEW --------

n="$(grep -c '^        TEST_REVIEW)$' "$ROOT/scripts/change-workflow.sh" || true)"
[[ "$n" == 1 ]] && ok || bad "one-case-label" "change-workflow.sh has $n TEST_REVIEW) case labels, expected exactly 1"

wia_line="$(grep -n '^        WAIT_IMPLEMENT_APPROVAL)$' "$ROOT/scripts/change-workflow.sh" | head -1 | cut -d: -f1)"
tr_line="$(grep -n '^        TEST_REVIEW)$' "$ROOT/scripts/change-workflow.sh" | head -1 | cut -d: -f1)"
wia_block="$(sed -n "${wia_line},${tr_line}p" "$ROOT/scripts/change-workflow.sh")"
if printf '%s' "$wia_block" | grep -q 'set_state CHECKLIST'; then
    bad "wia-skips-test-review" "WAIT_IMPLEMENT_APPROVAL still transitions directly to CHECKLIST instead of through TEST_REVIEW"
else
    ok
fi
set_tr_count="$(printf '%s' "$wia_block" | grep -c 'set_state TEST_REVIEW' || true)"
[[ "$set_tr_count" -ge 2 ]] && ok || bad "wia-routes-test-review" "WAIT_IMPLEMENT_APPROVAL has $set_tr_count set_state TEST_REVIEW call site(s), expected at least 2 (diff-gate-disabled and normal approve paths)"

vtr_line="$(grep -n '^        VALIDATE_TEST_REVIEW)$' "$ROOT/scripts/change-workflow.sh" | head -1 | cut -d: -f1)"
checklist_line="$(grep -n '^        CHECKLIST)$' "$ROOT/scripts/change-workflow.sh" | head -1 | cut -d: -f1)"
[[ -n "$vtr_line" ]] && ok || bad "has-validate-state" "VALIDATE_TEST_REVIEW) case label missing"
[[ -n "$checklist_line" && "$vtr_line" -lt "$checklist_line" ]] && ok || bad "validate-before-checklist" "VALIDATE_TEST_REVIEW does not precede CHECKLIST"

# --- (b) uses the shared acceptance-gate framework --------------------------

vtr_block="$(sed -n "${vtr_line},${checklist_line}p" "$ROOT/scripts/change-workflow.sh")"
if printf '%s' "$vtr_block" | grep -q 'acceptance_transition .uncle/docs/TEST_REVIEW.md'; then ok
else bad "uses-shared-acceptance-transition" "VALIDATE_TEST_REVIEW does not call the shared acceptance_transition"; fi

grep -Fq '. "$ROOT/scripts/lib/acceptance-gate.sh"' "$ROOT/scripts/change-workflow.sh" \
    && ok || bad "sources-shared-lib" "change-workflow.sh does not source acceptance-gate.sh"
grep -Fq '. "$ROOT/scripts/lib/acceptance-gate.sh"' "$ROOT/scripts/stagegate.sh" \
    && ok || bad "stagegate-sources-shared-lib" "stagegate.sh does not source acceptance-gate.sh (should still, after the move)"

# --- (c) FAIL routes to IMPLEMENT, not a nonexistent REPAIR state -----------

if printf '%s' "$vtr_block" | tr '\n' ' ' | grep -q "acceptance_transition .uncle/docs/TEST_REVIEW.md CHECKLIST.*IMPLEMENT"; then ok
else bad "fail-routes-to-implement" "VALIDATE_TEST_REVIEW does not pass IMPLEMENT as acceptance_transition's repair_target"; fi

repair_count="$(grep -v '^\s*#' "$ROOT/scripts/change-workflow.sh" | grep -c 'set_state REPAIR' || true)"
[[ "$repair_count" == 0 ]] && ok || bad "no-repair-state-invented" "change-workflow.sh now has $repair_count set_state REPAIR call site(s) -- it has no REPAIR state to receive them"

[[ -s "$ROOT/prompts/change/test-review.md" ]] && ok || bad "prompt-exists" "prompts/change/test-review.md is missing"
grep -Fq 'CHANGE_TEST_REPORT.md' "$ROOT/prompts/change/test-review.md" \
    && ok || bad "prompt-targets-change-report" "prompts/change/test-review.md does not reference CHANGE_TEST_REPORT.md"
grep -Fq 'NOT RUN is for evidence that cannot be obtained' "$ROOT/prompts/change/test-review.md" \
    && ok || bad "prompt-forbids-unread-not-run" "prompts/change/test-review.md lets a reviewer leave a row NOT RUN because it did not open a readable file"
grep -Fq 'AUTOMATED_TEST_REPORT.md' "$ROOT/prompts/change/test-review.md" \
    && bad "prompt-leaked-app-doc" "prompts/change/test-review.md still references the app-family AUTOMATED_TEST_REPORT.md" \
    || ok

bash -n "$ROOT/scripts/change-workflow.sh" && ok || bad "syntax" "change-workflow.sh fails bash -n"
bash -n "$ROOT/scripts/stagegate.sh" && ok || bad "syntax-stagegate" "stagegate.sh fails bash -n"
bash -n "$ROOT/scripts/lib/acceptance-gate.sh" && ok || bad "syntax-shared" "acceptance-gate.sh fails bash -n"

# --- functional: acceptance_transition's repair_target parameter -----------
# Direct functional check, not just a structural grep: a FAIL verdict with
# repair_target="IMPLEMENT" must set_state IMPLEMENT and must NOT write
# $STATE_DIR/repair-source (that file is read only by stagegate.sh's REPAIR
# state; writing it for a driver with no REPAIR state is dead, misleading
# state).
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
(
    cd "$temp"
    STATE_DIR="$temp/state"
    mkdir -p "$STATE_DIR/documents" .uncle/docs
    set_state() { printf '%s' "$1" > "$STATE_DIR/current-state"; }
    supervision_validation_failed() { :; }
    hash_file() { printf 'deadbeef'; }
    printf '{"schema":"uncle.artifact/v1","kind":"acceptance-report","rows":[{"id":"ASSERTIONS","required":true,"status":"FAIL","evidence":"weak"}]}' \
        > "$STATE_DIR/documents/TEST_REVIEW.json"
    : > .uncle/docs/TEST_REVIEW.md
    # shellcheck disable=SC1090
    . "$ROOT/scripts/lib/acceptance-gate.sh"
    set -e
    acceptance_transition .uncle/docs/TEST_REVIEW.md CHECKLIST '' IMPLEMENT
    [[ "$(cat "$STATE_DIR/current-state")" == IMPLEMENT ]] || { echo 'FAIL: did not route to IMPLEMENT' >&2; exit 1; }
    [[ ! -e "$STATE_DIR/repair-source" ]] || { echo 'FAIL: wrote repair-source for a driver with no REPAIR state' >&2; exit 1; }
)
functional_status=$?
[[ "$functional_status" == 0 ]] && ok || bad "functional-repair-target" "acceptance_transition's repair_target routing did not behave as expected (exit $functional_status)"

# And the default (no 4th argument) still goes to REPAIR, for stagegate.sh.
(
    cd "$temp"
    STATE_DIR="$temp/state2"
    mkdir -p "$STATE_DIR/documents" .uncle/docs
    set_state() { printf '%s' "$1" > "$STATE_DIR/current-state"; }
    supervision_validation_failed() { :; }
    hash_file() { printf 'deadbeef'; }
    printf '{"schema":"uncle.artifact/v1","kind":"acceptance-report","rows":[{"id":"ASSERTIONS","required":true,"status":"FAIL","evidence":"weak"}]}' \
        > "$STATE_DIR/documents/TEST_REVIEW.json"
    : > .uncle/docs/TEST_REVIEW.md
    # shellcheck disable=SC1090
    . "$ROOT/scripts/lib/acceptance-gate.sh"
    set -e
    acceptance_transition .uncle/docs/TEST_REVIEW.md MANUAL_CHECKLIST
    [[ "$(cat "$STATE_DIR/current-state")" == REPAIR ]] || { echo 'FAIL: default repair_target did not route to REPAIR' >&2; exit 1; }
    [[ "$(cat "$STATE_DIR/repair-source")" == .uncle/docs/TEST_REVIEW.md ]] || { echo 'FAIL: default repair_target did not write repair-source' >&2; exit 1; }
)
default_status=$?
[[ "$default_status" == 0 ]] && ok || bad "functional-default-repair-target" "acceptance_transition's default repair_target broke stagegate.sh's existing REPAIR routing (exit $default_status)"

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "change-test-review-test.sh: $FAIL of $((PASS + FAIL)) checks failed"
    exit 1
fi
echo "change-test-review-test.sh: $PASS checks passed"

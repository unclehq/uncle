#!/usr/bin/env bash
set -uo pipefail

# Hermetic coverage of the close decision in from-issue.sh and of the lock and
# origin preflight in change-workflow.sh. No network, no real gh, no agent
# calls: every case runs against a scratch copy of the scripts with a stubbed
# gh and a stubbed driver on PATH.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/sha256.sh"   # hash_file, portable across platforms

TMP="$(mktemp -d)"
trap 'if [[ "${UNCLE_KEEP_TEST_TMP:-0}" == 1 ]]; then echo "Kept close-flow fixtures: $TMP"; else rm -rf "$TMP"; fi' EXIT

# Exercise timeout coverage even on hosts without coreutils.
if ! command -v timeout >/dev/null 2>&1 && ! command -v gtimeout >/dev/null 2>&1; then
    mkdir "$TMP/timeout-bin"
    cat > "$TMP/timeout-bin/timeout" <<'TIMEOUT'
#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
p = subprocess.Popen(sys.argv[2:], start_new_session=True)
try:
    raise SystemExit(p.wait(timeout=float(sys.argv[1])))
except subprocess.TimeoutExpired:
    os.killpg(p.pid, signal.SIGKILL)
    p.wait()
    raise SystemExit(124)
TIMEOUT
    chmod +x "$TMP/timeout-bin/timeout"
    export PATH="$TMP/timeout-bin:$PATH"
fi

FAILED=0
COUNT=0
CASE_NAME=""
CASE=""
REPO=""
OUT=""
GH_LOG=""
RC=0

fail() {
    echo "FAIL [$CASE_NAME] $1"
    FAILED=$((FAILED + 1))
}

expect_status() {
    COUNT=$((COUNT + 1))
    if [[ "$RC" != "$1" ]]; then
        fail "expected exit $1, got $RC"
        sed 's/^/    /' < "$OUT"
    fi
}

expect_out() {
    COUNT=$((COUNT + 1))
    if ! grep -qF "$1" "$OUT"; then
        fail "expected output to contain: $1"
        sed 's/^/    /' < "$OUT"
    fi
}

expect_not_out() {
    COUNT=$((COUNT + 1))
    if grep -qF "$1" "$OUT"; then
        fail "expected output NOT to contain: $1"
    fi
}

expect_not_closed() {
    COUNT=$((COUNT + 1))
    if grep -qF "issue close" "$GH_LOG"; then
        fail "expected no gh issue close call, got: $(cat "$GH_LOG")"
    fi
}

expect_driver_ran() {
    COUNT=$((COUNT + 1))
    if [[ ! -s "$REPO/.uncle/workflow/driver.log" ]]; then
        fail "expected the driver to have run"
    fi
}

# ---------------------------------------------------------------------------
# Scratch fixture
# ---------------------------------------------------------------------------

new_case() {
    CASE_NAME="$1"
    CASE="$TMP/$1"
    REPO="$CASE/repo"
    OUT="$CASE/out.txt"
    GH_LOG="$CASE/gh.log"

    mkdir -p "$REPO/scripts/lib" "$REPO/.uncle/workflow" "$CASE/bin"
    cp "$ROOT/scripts/from-issue.sh" "$REPO/scripts/from-issue.sh"
    cp "$ROOT"/scripts/lib/*.sh "$REPO/scripts/lib/"
    cp "$ROOT"/scripts/lib/*.py "$REPO/scripts/lib/"
    : > "$GH_LOG"
    : > "$OUT"

    cat > "$CASE/bin/gh" <<'GH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GH_LOG_FILE"
if [[ "${1:-}" == "auth" ]]; then
    exit "${FAKE_GH_AUTH_RC:-0}"
fi
if [[ "${1:-}" == "issue" && "${2:-}" == "close" ]]; then
    if [[ -n "${FAKE_GH_CLOSE_SLEEP:-}" ]]; then
        sleep "$FAKE_GH_CLOSE_SLEEP"
    fi
    if [[ "${FAKE_GH_CLOSE_RC:-0}" == "0" ]]; then
        echo "stub: closed"
        exit 0
    fi
    echo "stub: close failed" >&2
    exit "${FAKE_GH_CLOSE_RC}"
fi
exit 0
GH
    chmod +x "$CASE/bin/gh"

    cat > "$REPO/scripts/change-workflow.sh" <<'DRV'
#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p .uncle/workflow
echo "ran" >> .uncle/workflow/driver.log
if [[ -n "${FAKE_DRIVER_VERDICT_TEXT:-}" ]]; then
    printf '%s\n' "$FAKE_DRIVER_VERDICT_TEXT" > FINAL_AUDIT.md
    . "$ROOT/scripts/lib/audit-verdict.sh"
    . "$ROOT/scripts/lib/sha256.sh"
    class="$(classify_audit_verdict FINAL_AUDIT.md)"
    hash="$(hash_file FINAL_AUDIT.md)"
    printf '%s\t%s\t%s\n' \
        "${STAGEGATE_RUN_ID:--}" "$class" "$hash" \
        > .uncle/workflow/audit-verdict
fi
if [[ "${FAKE_DRIVER_CLOSED_MARKER:-0}" == "1" ]]; then
    printf '%s\t%s\t%s\n' "${STAGEGATE_RUN_ID:--}" \
        "${STAGEGATE_ORIGIN_REPO:-}" "${STAGEGATE_ORIGIN_ISSUE:-}" \
        > .uncle/workflow/issue-closed
elif [[ -n "${FAKE_DRIVER_MARKER_TEXT:-}" ]]; then
    printf '%s\n' "$FAKE_DRIVER_MARKER_TEXT" > .uncle/workflow/issue-closed
fi
exit "${FAKE_DRIVER_EXIT:-0}"
DRV
    chmod +x "$REPO/scripts/change-workflow.sh"

    cat > "$REPO/runner.sh" <<'RUN'
#!/usr/bin/env bash
set -uo pipefail
export STAGEGATE_FROM_ISSUE_SOURCE_ONLY=1
. "$(dirname "$0")/scripts/from-issue.sh"
OWNER="${T_OWNER:-owner}"
REPO="${T_REPO:-repo}"
ISSUE_NUM="${T_ISSUE:-42}"
USED_GH="${T_USED_GH:-1}"
case "$1" in
    confirm) run_issue_workflow ;;
    seed_gate)
        check_origin_or_refuse
        if seed_is_current; then echo "SEED_SKIPPED"; else echo "SEED_WRITE"; fi
        ;;
    *) echo "unknown runner action: $1"; exit 2 ;;
esac
RUN
    chmod +x "$REPO/runner.sh"
}

# run_confirm <stdin text> [VAR=VAL ...]
run_runner() {
    local action="$1" input="$2"
    shift 2
    printf '%b' "$input" | env \
        PATH="$CASE/bin:$PATH" \
        GH_LOG_FILE="$GH_LOG" \
        "$@" \
        bash "$REPO/runner.sh" "$action" > "$OUT" 2>&1
    RC=$?
}

# run_driver [VAR=VAL ...] — runs the real change-workflow.sh in the scratch repo.
# STAGEGATE_ORIGIN_*/STAGEGATE_RUN_ID are stripped from the ambient environment:
# running this suite from inside a live stagegate session otherwise leaks them
# into every case and trips the origin preflight.
run_driver() {
    run_driver_stdin /dev/null "$@"
}

# The driver now has gates that can be reached from a state this suite sets up,
# so stdin is always given explicitly: inherited stdin would block a developer
# running the suite from a terminal, and silently decline everywhere else.
run_driver_stdin() {
    local stdin_file="$1"
    shift

    cp "$ROOT/scripts/change-workflow.sh" "$REPO/scripts/change-workflow.sh"
    env -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u STAGEGATE_RUN_ID \
        PATH="$CASE/bin:$PATH" GH_LOG_FILE="$GH_LOG" "$@" \
        bash "$REPO/scripts/change-workflow.sh" \
        < "$stdin_file" > "$OUT" 2>&1
    RC=$?
}

# gate_input <line>... — a file holding the keystrokes one human_gate consumes,
# one Y/N answer per gate reached.
gate_input() {
    local f="$CASE/gate-input"
    printf '%s\n' "$@" > "$f"
    printf '%s' "$f"
}

# Prepares the scratch repo to run the real driver's FINAL_AUDIT stage with a
# reviewer stub that writes <verdict text> into FINAL_AUDIT.md.
setup_audit_stage() {
    local verdict="$1" finding=""
    if [[ "$verdict" == "NOT READY" ]]; then
        finding='| F-1 | Fixture blocker | Review fixture | YES |'
    fi
    mkdir -p "$REPO/prompts/change"
    mkdir -p "$REPO/.uncle/workflow/approvals"
    printf 'Approved fixture plan\n' > "$REPO/CHANGE_PLAN.md"
    cat > "$REPO/CHANGE_SPEC.md" <<'SPEC'
## Acceptance criteria
| ID | Criterion | Verification |
|---|---|---|
| AC-1 | Fixture behavior | Fixture check |
SPEC
    cat > "$REPO/IMPLEMENTATION_NOTES.md" <<'NOTES'
## Acceptance delivery
| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | Fixture code | Fixture check PASS |
NOTES
    hash_file "$REPO/CHANGE_SPEC.md" > "$REPO/.uncle/workflow/approvals/CHANGE_SPEC.sha256"
    hash_file "$REPO/CHANGE_PLAN.md" > "$REPO/.uncle/workflow/approvals/CHANGE_PLAN.sha256"
    cp "$ROOT/prompts/change/final-audit.md" "$REPO/prompts/change/final-audit.md"
    cat > "$CASE/bin/fake-reviewer" <<REV
#!/usr/bin/env bash
out=""
while [[ \$# -gt 0 ]]; do
    if [[ "\$1" == "--output-last-message" ]]; then out="\$2"; shift; fi
    shift
done
printf '%s\n' '## Findings' '' '| ID | Evidence | Required correction | Blocks |' '|---|---|---|---|' '$finding' '' '$verdict' > "\$out"
REV
    chmod +x "$CASE/bin/fake-reviewer"
}

expect_state() {
    COUNT=$((COUNT + 1))
    if [[ "$(cat "$REPO/.uncle/workflow/state" 2>/dev/null)" != "$1" ]]; then
        fail "expected state '$1', got '$(cat "$REPO/.uncle/workflow/state" 2>/dev/null)'"
    fi
}

expect_no_marker() {
    COUNT=$((COUNT + 1))
    if [[ -e "$REPO/.uncle/workflow/issue-closed" ]]; then
        fail "expected no close marker, got: $(cat "$REPO/.uncle/workflow/issue-closed")"
    fi
}

# How many `gh issue close` calls the stub logged.
close_calls() {
    grep -cF "issue close" "$GH_LOG" 2>/dev/null || true
}

expect_close_count() {
    COUNT=$((COUNT + 1))
    if [[ "$(close_calls)" != "$1" ]]; then
        fail "expected $1 gh issue close call(s), got $(close_calls)"
    fi
}

# ---------------------------------------------------------------------------
# Issue launch starts directly, including with closed stdin.
# ---------------------------------------------------------------------------
new_case direct-launch-eof
run_runner confirm "" FAKE_DRIVER_VERDICT_TEXT="READY"
expect_status 0
expect_out "Starting the change workflow from this issue."
expect_driver_ran
expect_not_closed

# ---------------------------------------------------------------------------
# The runner never closes the issue itself: a READY audit with gh
# authenticated is the one case that used to, and it must not (B-04, B-05,
# I-08). Closing follows the PR merge; the verdict guards that used to sit
# here are attestation-test's T2 rows now.
# ---------------------------------------------------------------------------

new_case ready-never-closes
run_runner confirm "" FAKE_DRIVER_VERDICT_TEXT="READY"
expect_status 0
expect_out "Issues remain open until their PR is merged."
expect_not_closed

new_case not-ready-stays-open
run_runner confirm "" FAKE_DRIVER_VERDICT_TEXT="NOT READY"
expect_status 0
expect_not_closed

# ---------------------------------------------------------------------------
# Driver exit status (AR-008, B-06)
# ---------------------------------------------------------------------------

for rc in 1 7 130; do
    new_case "driver-exit-$rc"
    run_runner confirm "" FAKE_DRIVER_EXIT="$rc" FAKE_DRIVER_VERDICT_TEXT="READY"
    expect_status "$rc"
    expect_out "change-workflow.sh exited $rc; owner/repo#42 remains open."
    expect_not_closed
done

# ---------------------------------------------------------------------------
# Seed gate in from-issue.sh (AR-001, AR-004)
# ---------------------------------------------------------------------------

new_case seed-gate-foreign-origin
printf 'IMPLEMENT\n' > "$REPO/.uncle/workflow/state"
printf 'other/repo\t99\n' > "$REPO/.uncle/workflow/origin"
run_runner seed_gate ""
expect_status 1
expect_out "Refusing to seed owner/repo#42"
expect_out "other/repo"

new_case seed-gate-unowned-state
printf 'IMPLEMENT\n' > "$REPO/.uncle/workflow/state"
run_runner seed_gate ""
expect_status 1
expect_out "absent — the in-flight state has no provable owner"

new_case seed-gate-same-origin-resumes
printf 'IMPLEMENT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\n' > "$REPO/.uncle/workflow/origin"
run_runner seed_gate ""
expect_status 0
expect_out "SEED_SKIPPED"

new_case seed-gate-complete-state-reseeds
printf 'COMPLETE\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\n' > "$REPO/.uncle/workflow/origin"
run_runner seed_gate ""
expect_status 0
expect_out "SEED_WRITE"

new_case seed-gate-fresh-checkout
run_runner seed_gate ""
expect_status 0
expect_out "SEED_WRITE"

# ---------------------------------------------------------------------------
# Driver lock and origin preflight (AR-003, AR-001)
# ---------------------------------------------------------------------------

new_case lock-held-by-live-pid
mkdir -p "$REPO/.uncle/workflow/lock"
printf '%s\n' "$$" > "$REPO/.uncle/workflow/lock/pid"
printf 'COMPLETE\n' > "$REPO/.uncle/workflow/state"
run_driver
expect_status 1
expect_out "another change-workflow.sh run (pid $$) holds this checkout"
COUNT=$((COUNT + 1))
if [[ ! -f "$REPO/.uncle/workflow/lock/pid" ]]; then
    fail "the live holder's lock must not be removed"
fi

new_case lock-stale-pid-cleared
DEAD_PID=""
( exit 0 ) &
DEAD_PID=$!
wait "$DEAD_PID" 2>/dev/null
mkdir -p "$REPO/.uncle/workflow/lock"
printf '%s\n' "$DEAD_PID" > "$REPO/.uncle/workflow/lock/pid"
printf 'COMPLETE\n' > "$REPO/.uncle/workflow/state"
run_driver
expect_status 0
expect_out "Clearing stale lock"
expect_out "Change workflow complete."
COUNT=$((COUNT + 1))
if [[ -d "$REPO/.uncle/workflow/lock" ]]; then
    fail "lock must be released on exit"
fi

new_case preflight-origin-mismatch
printf 'IMPLEMENT\n' > "$REPO/.uncle/workflow/state"
printf 'other/repo\t99\n' > "$REPO/.uncle/workflow/origin"
run_driver STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 1
expect_out "Refusing to resume: this checkout is mid-run"
COUNT=$((COUNT + 1))
if [[ "$(cat "$REPO/.uncle/workflow/state")" != "IMPLEMENT" ]]; then
    fail "a refused preflight must not touch the state file"
fi

new_case preflight-origin-absent
printf 'IMPLEMENT\n' > "$REPO/.uncle/workflow/state"
run_driver STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 1
expect_out "cannot be proven to belong to owner/repo#42"

new_case preflight-standalone-unaffected
printf 'IMPLEMENT\n' > "$REPO/.uncle/workflow/state"
printf 'other/repo\t99\n' > "$REPO/.uncle/workflow/origin"
run_driver
# No STAGEGATE_ORIGIN_*: the preflight is skipped entirely, so the run reaches
# the state machine and fails on its own missing-approval check instead of
# refusing to resume.
expect_status 1
expect_not_out "Refusing to resume"

new_case preflight-complete-state-passes
printf 'COMPLETE\n' > "$REPO/.uncle/workflow/state"
printf 'other/repo\t99\n' > "$REPO/.uncle/workflow/origin"
run_driver STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 0
expect_out "Change workflow complete."
# The support prompt belongs to the TUI only; a non-TUI completion must never
# print it (B-7).
expect_not_out "github.com/unclehq/uncle"
expect_not_out "support Uncle"

# ---------------------------------------------------------------------------
# FINAL_AUDIT freshness and verdict record (AR-002)
# ---------------------------------------------------------------------------

# A reviewer invocation that exits 0 without writing must not leave a stale
# audit readable as this run's verdict.
new_case stale-audit-rejected
setup_audit_stage READY
mkdir -p "$REPO/prompts/change"
cp "$ROOT/prompts/change/final-audit.md" "$REPO/prompts/change/final-audit.md"
printf 'READY\n' > "$REPO/FINAL_AUDIT.md"
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
run_driver WORKFLOW_REVIEWER_CMD=/usr/bin/true STAGEGATE_RUN_ID=run-1
expect_status 1
expect_out "Required file missing or empty: FINAL_AUDIT.md"
COUNT=$((COUNT + 1))
if [[ -e "$REPO/.uncle/workflow/audit-verdict" ]]; then
    fail "no verdict may be recorded when the audit was not produced"
fi
COUNT=$((COUNT + 1))
if [[ "$(cat "$REPO/.uncle/workflow/state")" != "FINAL_AUDIT" ]]; then
    fail "state must not advance past a failed audit"
fi

new_case verdict-record-written
setup_audit_stage READY
mkdir -p "$REPO/prompts/change" "$CASE/bin"
cp "$ROOT/prompts/change/final-audit.md" "$REPO/prompts/change/final-audit.md"
cat > "$CASE/bin/fake-reviewer" <<'REV'
#!/usr/bin/env bash
out=""
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--output-last-message" ]]; then out="$2"; shift; fi
    shift
done
printf '%s\n' '## Findings' '' '| ID | Evidence | Required correction | Blocks |' '|---|---|---|---|' '' 'READY' > "$out"
REV
chmod +x "$CASE/bin/fake-reviewer"
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1
expect_status 0
expect_out "Audit verdict: READY"
COUNT=$((COUNT + 1))
expected_record="$(printf 'run-1\tREADY\t%s' "$(hash_file "$REPO/FINAL_AUDIT.md")")"
if [[ "$(cat "$REPO/.uncle/workflow/audit-verdict")" != "$expected_record" ]]; then
    fail "verdict record mismatch: $(cat "$REPO/.uncle/workflow/audit-verdict")"
fi

# ---------------------------------------------------------------------------
# State-token grammar (BEH-B)
# ---------------------------------------------------------------------------

# A two-field origin is used here on purpose: this case is about the state
# format, and no fetch provenance keeps the close gate out of it.
new_case state-prefix-written
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1
expect_status 0
expect_state "42:COMPLETE"

new_case state-bare-still-read
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1
expect_status 0
expect_out "Audit verdict: READY"

new_case state-no-origin-stays-bare
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1
expect_status 0
expect_state "COMPLETE"

new_case state-unknown-prefix-refused
printf 'abc:IMPLEMENT\n' > "$REPO/.uncle/workflow/state"
run_driver
expect_status 1
expect_out "Unknown workflow state: abc:IMPLEMENT"

# --- Regression tests for R-1: a prefixed COMPLETE must still read as done ---

new_case seed-gate-prefixed-complete-reseeds
printf '42:COMPLETE\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_runner seed_gate ""
expect_status 0
expect_out "SEED_WRITE"

new_case seed-gate-prefixed-inflight-refuses
printf '99:IMPLEMENT\n' > "$REPO/.uncle/workflow/state"
printf 'other/repo\t99\tgh\n' > "$REPO/.uncle/workflow/origin"
run_runner seed_gate ""
expect_status 1
expect_out "Refusing to seed owner/repo#42"

# The origin here is foreign by repo, not by issue: a foreign *issue* number
# beside a prefixed state is the AR-004 corruption case, covered separately.
new_case preflight-prefixed-complete-passes
printf '42:COMPLETE\n' > "$REPO/.uncle/workflow/state"
printf 'other/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 0
expect_out "Change workflow complete."

# ---------------------------------------------------------------------------
# Manual-clear guidance on refusal (BEH-C)
# ---------------------------------------------------------------------------

new_case seed-gate-mismatch-prints-guidance
printf 'IMPLEMENT\n' > "$REPO/.uncle/workflow/state"
printf 'other/repo\t99\tgh\n' > "$REPO/.uncle/workflow/origin"
run_runner seed_gate ""
expect_status 1
expect_out "rm -f .uncle/workflow/state .uncle/workflow/origin"

# ---------------------------------------------------------------------------
# State-prefix / origin-issue corruption (AR-004)
# ---------------------------------------------------------------------------

new_case state-origin-issue-mismatch-refused
printf '99:IMPLEMENT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_runner seed_gate ""
expect_status 1
expect_out "Refusing to act on corrupt workflow state"
expect_out "99 but .uncle/workflow/origin names issue 42."
expect_not_out "Refusing to seed"
run_driver STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 1
expect_out "Refusing to act on corrupt workflow state"
expect_not_out "Refusing to resume"
expect_state "99:IMPLEMENT"

# ---------------------------------------------------------------------------
# Driver-side close (BEH-D)
# ---------------------------------------------------------------------------

# T-1: a Git checkout must never close the issue at COMPLETE.
new_case git-completion-defers-close
setup_audit_stage READY
git -C "$REPO" init -q
git -C "$REPO" add -A
git -C "$REPO" -c commit.gpgsign=false -c tag.gpgsign=false -c user.name=Fixture -c user.email=fixture@example.test commit --no-gpg-sign -qm initial
printf '42:FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1
expect_status 0
expect_state "42:COMPLETE"
expect_not_closed
expect_no_marker

for setting in WORKFLOW_CLOSE_ISSUE=0 UNATTENDED=1; do
    new_case "git-disabled-$setting"
    setup_audit_stage READY
    git -C "$REPO" init -q
    git -C "$REPO" add -A
    git -C "$REPO" -c commit.gpgsign=false -c tag.gpgsign=false -c user.name=Fixture -c user.email=fixture@example.test commit --no-gpg-sign -qm initial
    printf '42:FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
    printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
    run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" "$setting"
    expect_status 0
    expect_state "42:COMPLETE"
    expect_not_out "PR title [default:"
    expect_not_closed
    expect_no_marker
done

new_case git-wrapper-never-closes
mkdir "$REPO/.git"
run_runner confirm "" FAKE_DRIVER_VERDICT_TEXT=READY
expect_status 0
expect_not_closed
expect_no_marker

new_case direct-run-closes
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 0
expect_not_closed
expect_no_marker

# A NOT READY audit no longer completes the run. It stops at the override
# gate, and declining there leaves the state — and the issue — where they are.
new_case direct-run-not-ready-stops-at-gate
setup_audit_stage "NOT READY"
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 1
expect_out "Audit verdict: NOT_READY"
expect_out "AUDIT REVIEW REQUIRED:"
expect_out "No decision received; audit remains pending."
expect_not_out "Change workflow complete."
expect_state "42:WAIT_AUDIT_OVERRIDE"
expect_not_closed
expect_no_marker

# An audit whose last line is not one of the three verdict phrases is rejected
# by deterministic validation before it can reach the audit gate.
new_case direct-run-unknown-verdict-stops-at-gate
setup_audit_stage "probably fine, ship it"
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 1
expect_out "Audit format invalid: Missing final audit verdict"
expect_state "42:VALIDATE_AUDIT"
expect_not_closed

# Per-finding acceptance produces effective READY; retained blockers deny close.
new_case direct-run-not-ready-accepted-completes
setup_audit_stage "NOT READY"
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver_stdin "$(gate_input r)" \
    WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 0
expect_out "Change workflow complete."
expect_out "Build verdict: READY"
expect_state "42:COMPLETE"
expect_not_closed
expect_no_marker

new_case direct-run-not-ready-retained-blocker
setup_audit_stage "NOT READY"
printf '42:FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver_stdin "$(gate_input n)" \
    WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1
expect_status 1
expect_out "still blocking: F-1"
expect_state "42:WAIT_AUDIT_OVERRIDE"
expect_not_closed
expect_no_marker

# The kill switch restores the old behavior, and says so.
new_case direct-run-audit-gate-disabled
setup_audit_stage "NOT READY"
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_AUDIT_GATE=0 \
    WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 0
expect_out "Audit gate disabled (WORKFLOW_AUDIT_GATE=0); completing on a NOT_READY verdict."
expect_state "42:COMPLETE"
expect_not_closed
expect_no_marker

new_case direct-run-no-origin-skips-close
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1
expect_status 0
expect_out "Change workflow complete."
expect_not_closed
expect_no_marker

new_case direct-run-gh-unauth-skips-close
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42 FAKE_GH_AUTH_RC=1
expect_status 0
expect_not_closed
expect_no_marker

new_case direct-run-close-flag-off
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42 WORKFLOW_CLOSE_ISSUE=0
expect_status 0
expect_not_closed
expect_no_marker

new_case direct-run-close-fails-still-completes
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42 FAKE_GH_CLOSE_RC=1
expect_status 0
expect_no_marker

# ---------------------------------------------------------------------------
# Driver / from-issue.sh double-close protection (BEH-D)
# ---------------------------------------------------------------------------

new_case no-double-close-after-driver
run_runner confirm "" FAKE_DRIVER_VERDICT_TEXT="READY" FAKE_DRIVER_CLOSED_MARKER=1
expect_status 0
expect_not_closed

new_case stale-marker-ignored
run_runner confirm "" FAKE_DRIVER_VERDICT_TEXT="READY" \
    FAKE_DRIVER_MARKER_TEXT="other-run	other/repo	99"
expect_status 0
expect_not_closed

# ---------------------------------------------------------------------------
# Origin freshness (AR-001)
# ---------------------------------------------------------------------------

new_case direct-run-stale-origin-fresh-state-skips-close
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'other/repo\t99\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1
expect_status 0
expect_not_closed
expect_no_marker

new_case direct-run-explicit-origin-env-closes
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 0
expect_not_closed

# ---------------------------------------------------------------------------
# Close retry on a later run (AR-002)
# ---------------------------------------------------------------------------

new_case direct-run-close-retries-on-rerun
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42 FAKE_GH_CLOSE_RC=1
expect_status 0
expect_no_marker
run_driver STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 0
expect_no_marker
expect_close_count 0

new_case direct-run-stale-sentinel-run-id-no-retry
printf 'READY\n' > "$REPO/FINAL_AUDIT.md"
printf '42:COMPLETE\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
printf -- '-\tREADY\t%s\n' \
    "$(hash_file "$REPO/FINAL_AUDIT.md")" \
    > "$REPO/.uncle/workflow/audit-verdict"
run_driver
expect_status 0
expect_not_closed
expect_no_marker

# ---------------------------------------------------------------------------
# Fetch provenance (AR-003)
# ---------------------------------------------------------------------------

new_case curl-fallback-driver-side-skips-close
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\tcurl\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 0
expect_not_closed
expect_no_marker

new_case legacy-two-field-origin-skips-close
setup_audit_stage READY
printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
printf 'owner/repo\t42\n' > "$REPO/.uncle/workflow/origin"
run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
    STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42
expect_status 0
expect_not_closed
expect_no_marker

# ---------------------------------------------------------------------------
# Bounded close call (AR-008)
# ---------------------------------------------------------------------------

new_case direct-run-close-timeout-treated-as-failure
if ! command -v timeout >/dev/null 2>&1 && ! command -v gtimeout >/dev/null 2>&1; then
    echo "NOTE [$CASE_NAME] skipped: neither timeout nor gtimeout is available"
else
    setup_audit_stage READY
    printf 'FINAL_AUDIT\n' > "$REPO/.uncle/workflow/state"
    printf 'owner/repo\t42\tgh\n' > "$REPO/.uncle/workflow/origin"
    run_driver WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" STAGEGATE_RUN_ID=run-1 \
        STAGEGATE_ORIGIN_REPO=owner/repo STAGEGATE_ORIGIN_ISSUE=42 \
        STAGEGATE_CLOSE_TIMEOUT=1 FAKE_GH_CLOSE_SLEEP=5
    expect_status 0
    expect_no_marker
    COUNT=$((COUNT + 1))
    if [[ -d "$REPO/.uncle/workflow/lock" ]]; then
        fail "lock must be released after a timed-out close"
    fi
fi

# --- state/origin agreement across a completed run -------------------------
#
# Seeding a new issue writes .uncle/workflow/origin and leaves the finished run's
# .uncle/workflow/state behind. Treating that as corruption made a checkout
# single-use: the second issue could not start without deleting files by hand.

CASE_NAME="state_origin_agree"
SOTMP="$TMP/state-origin"
mkdir -p "$SOTMP"
( . "$ROOT/scripts/lib/state.sh"; . "$ROOT/scripts/lib/issue-close.sh"
  printf 'o/r\t6\tgh\n' > "$SOTMP/origin"

  agree() { state_origin_agree "$SOTMP/state" "$SOTMP/origin" >/dev/null 2>&1; }

  printf '5:COMPLETE\n' > "$SOTMP/state"
  agree || echo "FAILCASE a finished run of another issue must not block a new one"

  printf '5:IMPLEMENT\n' > "$SOTMP/state"
  agree && echo "FAILCASE an unfinished run of another issue must still refuse"

  printf '6:IMPLEMENT\n' > "$SOTMP/state"
  agree || echo "FAILCASE the same issue in flight must be allowed"

  printf '6:COMPLETE\n' > "$SOTMP/state"
  agree || echo "FAILCASE the same issue complete must be allowed"

  printf 'COMPLETE\n' > "$SOTMP/state"
  agree || echo "FAILCASE a legacy unprefixed token has no issue to disagree with"

  : > "$SOTMP/state"
  agree || echo "FAILCASE an empty state file must be allowed"
) > "$SOTMP/out" 2>&1

while IFS= read -r line; do
    case "$line" in
        FAILCASE*) COUNT=$((COUNT + 1)); fail "${line#FAILCASE }" ;;
    esac
done < "$SOTMP/out"
COUNT=$((COUNT + 6))

# T-5–8: local Git publication with a persistent fake GitHub server.
# The Git shim changes only identity discovery; commits/pushes use real bare repos.
CASE_NAME=pr-handoff
python3 /dev/fd/3 "$ROOT" 3<<'PY'
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(sys.argv.pop())
LIB = ROOT / 'scripts/lib/change-pr.sh'
REAL_GIT = shutil.which('git')


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        REAL_GIT=REAL_GIT, SERVER=str(self.root / 'server.json'),
                        GH_CALLS=str(self.root / 'gh.jsonl'), GIT_CONFIG_GLOBAL='/dev/null',
                        GIT_CONFIG_NOSYSTEM='1')
        for key in ('STAGEGATE_RUN_ID', 'STAGEGATE_ORIGIN_REPO', 'STAGEGATE_ORIGIN_ISSUE', 'UNCLE_PROJECT_ROOT'):
            self.env.pop(key, None)
        self.exe('git', '#!/usr/bin/env bash\nif [[ "$1" == remote && "${2:-}" == get-url ]]; then\n    if [[ -n "${FORK:-}" && "${@: -1}" == origin ]]; then\n        echo \'https://github.com/forker/repo.git\'\n    else\n        echo \'https://github.com/owner/repo.git\'\n    fi\n    exit 0\nfi\nif [[ "${CRASH_GIT:-}" == "$1" ]]; then\n    "$REAL_GIT" "$@"\n    exit 70\nfi\nexec "$REAL_GIT" "$@"\n')
        self.exe('gh', '''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
args = sys.argv[1:]
with open(os.environ['GH_CALLS'], 'a') as f: f.write(json.dumps(args) + '\\n')
server = pathlib.Path(os.environ['SERVER'])
if args[:2] == ['auth', 'status']: sys.exit(int(os.environ.get('AUTH_RC', '0')))
if args[:2] == ['repo', 'view']:
    print(json.dumps({'nameWithOwner': args[2], 'defaultBranchRef': {'name': 'main'}}))
elif args[:2] == ['issue', 'view']:
    if os.environ.get('LABELS_HANG'):
        import time
        time.sleep(5)
    if os.environ.get('LABELS_FAIL'): sys.exit(1)
    if os.environ.get('LABELS_BAD'):
        print('{broken')
    else:
        print(json.dumps({'labels': [{'name': name} for name in os.environ.get('ISSUE_LABELS', '').split(',') if name]}))
elif args[0] == 'api':
    print(json.dumps({'fork': True, 'parent': {'full_name': 'owner/repo'}, 'owner': {'type': 'User'}}))
elif args[:2] == ['pr', 'list']:
    if os.environ.get('LOOKUP_FAIL'): sys.exit(1)
    rows = json.loads(server.read_text()) if server.exists() else []
    if os.environ.get('DUPLICATE'): rows = rows * 2
    print(json.dumps(rows))
elif args[:2] == ['pr', 'view']:
    row = json.loads(server.read_text())[0]
    if os.environ.get('WRONG_PR_SHA'): row['headRefOid'] = '0' * 40
    print(json.dumps(row))
elif args[:2] == ['pr', 'create']:
    if os.environ.get('CREATE_FAIL'): sys.exit(1)
    identity = 'forker' if os.environ.get('FORK') else 'owner'
    branch = subprocess.check_output(['git', 'branch', '--show-current']).decode().strip()
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
    body = pathlib.Path(args[args.index('--body-file') + 1]).read_text()
    server.with_suffix('.body').write_text(body)
    server.with_suffix('.bodypath').write_text(args[args.index('--body-file') + 1])
    server.write_text(json.dumps([dict(number=7, url='https://github.com/owner/repo/pull/7',
        headRefName=branch, headRefOid=sha, headRepository={'name': 'repo'},
        headRepositoryOwner={'login': identity}, baseRefName='main')]))
    print('https://github.com/owner/repo/pull/7')
    if os.environ.get('CREATE_TIMEOUT'): sys.exit(124)
''')
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.test')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'tag.gpgsign', 'false')
        (self.repo / '.gitignore').write_text('.uncle/workflow/\n')
        (self.repo / 'source.txt').write_text('before\n')
        (self.repo / 'CHANGE_REQUEST.md').write_text('## Summary\n\nFix café 日本語\n')
        self.git('add', '.')
        self.git('commit', '--no-gpg-sign', '-qm', 'initial')
        self.original = self.git('rev-parse', 'HEAD')
        self.bare = self.root / 'remote.git'
        subprocess.run([REAL_GIT, 'init', '--bare', '-q', str(self.bare)], check=True, env=self.env)
        self.git('remote', 'add', 'origin', str(self.bare))
        self.git('push', '-q', 'origin', 'main')
        self.state = self.repo / '.uncle/workflow'
        self.state.mkdir(parents=True)
        (self.state / 'origin').write_text('owner/repo\t42\tgh\n')
        (self.repo / 'source.txt').write_text('audited\n')
        self.freeze()

    def exe(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)

    def git(self, *args):
        return subprocess.check_output([REAL_GIT, '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', *args], cwd=self.repo, env=self.env, stderr=subprocess.PIPE).decode().strip()

    def engine(self, action, text='', **env):
        result = subprocess.run(['bash', '-c', '. "$1"; change_pr_engine "$2"', 'test', str(LIB), action],
                              cwd=self.repo, env=dict(self.env, **env), input=text, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        # With signing off the engine commits itself; only the signed cases
        # (signed_pending) may ask the person, and they ask for a signature.
        self.assertNotIn('Commit needs your help.', result.stdout)
        return result

    def ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)

    def freeze(self):
        self.ok(self.engine('freeze'))
        (self.repo / 'FINAL_AUDIT.md').write_text('READY\n')
        sha = hashlib.sha256((self.repo / 'FINAL_AUDIT.md').read_bytes()).hexdigest()
        (self.state / 'audit-verdict').write_text('-\tREADY\t' + sha + '\n')
        self.ok(self.engine('bind'))

    def journal(self):
        return json.loads((self.state / 'pr/journal.json').read_text())

    def calls(self):
        path = self.root / 'gh.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def creates(self):
        return [a for a in self.calls() if a[:2] == ['pr', 'create']]

    def publish(self, **env):
        return self.engine('handoff', '\nImplemented audited fix\nRun smoke test\ny\n', **env)

    def signed_pending(self):
        key = self.root / 'signing-key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
        allowed = self.root / 'allowed-signers'
        allowed.write_text('fixture@example.test ' + key.with_suffix('.pub').read_text())
        self.git('config', 'gpg.format', 'ssh')
        self.git('config', 'user.signingkey', str(key))
        self.git('config', 'gpg.ssh.allowedSignersFile', str(allowed))
        self.git('config', 'commit.gpgsign', 'true')
        (self.repo / '.gitignore').write_text('FINAL_AUDIT.md\n')
        (self.state / 'tracked').write_text('tracked state\n')
        self.git('add', '-f', '.uncle/workflow/tracked')
        self.git('commit', '--no-gpg-sign', '-qm', 'tracked workflow state')
        self.original = self.git('rev-parse', 'HEAD')
        self.freeze()
        result = self.publish()
        self.assertIn('No answer received', result.stdout)
        self.assertTrue(self.journal()['manual_signing'])
        command = result.stdout.split('Commit signing needs your help.', 1)[1].split('\n', 1)[1].split('\nReturn here', 1)[0]
        self.ok(subprocess.run(['sh', '-c', command], cwd=self.repo, env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}'), self.journal()['commit_tree'])
        self.assertNotIn('.uncle/workflow/', self.git('ls-tree', '-r', '--name-only', 'HEAD'))

    def complete(self, close='0', unattended='0', file=False, **extra):
        (self.state / 'state').write_text('42:COMPLETE\n')
        unattended_path = self.state / 'unattended-gates'
        if file:
            unattended_path.write_text('1\n')
        elif unattended_path.exists():
            unattended_path.unlink()
        return subprocess.run(['bash', str(ROOT / 'scripts/change-workflow.sh')], cwd=self.repo,
            env=dict(self.env, UNCLE_PROJECT_ROOT=str(self.repo), WORKFLOW_CLOSE_ISSUE=close, UNATTENDED=unattended, **extra),
            input='\n', text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)

    def test_signed_complete_skip_inputs_and_markerless_phases(self):
        self.signed_pending()
        pending = self.journal()
        for close, unattended, file in [('0', '0', False), ('1', '1', False), ('1', '0', True), ('0', '1', True)]:
            (self.state / 'pr/journal.json').write_text(json.dumps(pending))
            result = self.complete(close, unattended, file)
            self.ok(result)
            self.assertEqual(self.journal()['phase'], 'created', result.stdout)
            self.assertEqual(self.journal()['manual_signed_head'], self.git('rev-parse', 'HEAD'))
            self.assertEqual(len(self.creates()), 1)
        created = self.journal()
        for phase in ('prepared', 'published', 'creating', 'unknown'):
            for marker in (True, False):
                j = dict(created, phase=phase)
                if not marker: j.pop('manual_signed_head')
                (self.state / 'pr/journal.json').write_text(json.dumps(j))
                result = self.complete()
                self.ok(result)
                self.assertEqual(self.journal()['phase'], 'created', result.stdout)
                self.assertEqual(len(self.creates()), 1)
        self.assertFalse((self.state / 'issue-closed').exists())

    def test_signed_unknown_never_recreates_and_invalid_skips(self):
        self.signed_pending()
        self.ok(self.complete(CREATE_FAIL='1'))
        self.assertEqual(self.journal()['phase'], 'unknown')
        for lookup in ('', '1'):
            self.ok(self.complete(LOOKUP_FAIL=lookup))
            self.assertEqual(len(self.creates()), 1)
        j = self.journal()
        j['manual_signed_head'] = '0' * 40
        (self.state / 'pr/journal.json').write_text(json.dumps(j))
        result = self.complete()
        self.assertIn('handoff disabled', result.stdout)
        self.assertEqual(len(self.creates()), 1)

    def test_signed_published_retry_and_unsigned_intended_skip(self):
        self.signed_pending()
        self.ok(self.complete(LOOKUP_FAIL='1'))
        self.assertEqual(self.journal()['phase'], 'published')
        self.assertEqual(len(self.creates()), 0)
        self.ok(self.complete())
        self.assertEqual(self.journal()['phase'], 'created')
        self.assertEqual(len(self.creates()), 1)
        j = self.journal()
        unsigned = self.git('-c', 'commit.gpgsign=false', 'commit-tree', '--no-gpg-sign', j['commit_tree'], '-p', j['original_head'], '-m', 'unsigned')
        self.git('update-ref', 'HEAD', unsigned)
        j.update(phase='prepared', intended_head=unsigned)
        j.pop('manual_signed_head')
        (self.state / 'pr/journal.json').write_text(json.dumps(j))
        result = self.complete()
        self.assertIn('handoff disabled', result.stdout)
        self.assertEqual(len(self.creates()), 1)

    def test_unsigned_complete_still_skips(self):
        result = self.complete()
        self.assertIn('handoff disabled', result.stdout)
        self.assertEqual(len(self.creates()), 0)

    def test_driver_audit_to_pr_and_rerun(self):
        (self.repo / 'CHANGE_SPEC.md').write_text('## Acceptance criteria\n| ID | Criterion | Verification |\n|---|---|---|\n| AC-1 | Fixture behavior | Fixture check |\n')
        (self.repo / 'CHANGE_PLAN.md').write_text('Approved fixture plan\n')
        (self.repo / 'IMPLEMENTATION_NOTES.md').write_text('## Acceptance delivery\n| ID | Status | Changed code | Observed targeted verification |\n|---|---|---|---|\n| AC-1 | IMPLEMENTED | source.txt | Fixture check PASS |\n')
        approvals = self.state / 'approvals'
        approvals.mkdir(exist_ok=True)
        for artifact in ('CHANGE_SPEC', 'CHANGE_PLAN'):
            digest = hashlib.sha256((self.repo / (artifact + '.md')).read_bytes()).hexdigest()
            (approvals / (artifact + '.sha256')).write_text(digest + '\n')
        self.exe('reviewer', """#!/usr/bin/env python3
from pathlib import Path
import sys
Path(sys.argv[sys.argv.index('--output-last-message') + 1]).write_text(
    '## Findings\\n\\n| ID | Evidence | Required correction | Blocks |\\n'
    '|---|---|---|---|\\n\\nREADY\\n')
""")
        (self.state / 'state').write_text('42:FINAL_AUDIT\n')
        env = dict(self.env, UNCLE_PROJECT_ROOT=str(self.repo),
                   WORKFLOW_REVIEWER_CMD=str(self.bin / 'reviewer'), WORKFLOW_CLOSE_ISSUE='1', UNATTENDED='0')
        command = ['bash', str(ROOT / 'scripts/change-workflow.sh')]
        result = subprocess.run(command, cwd=self.repo, env=env, input='\nSummary\nManual\ny\n',
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        self.ok(result)
        self.assertEqual((self.state / 'state').read_text().strip(), '42:COMPLETE')
        self.assertNotIn('needs your help', result.stdout)
        self.assertIn('PR: https://github.com/owner/repo/pull/7', result.stdout)
        self.assertEqual(len(self.creates()), 1, result.stdout)
        self.assertFalse((self.state / 'issue-closed').exists())
        result = subprocess.run(command, cwd=self.repo, env=env, input='', text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        self.ok(result)
        self.assertIn('https://github.com/owner/repo/pull/7', result.stdout)
        self.assertEqual(len(self.creates()), 1)

    def assert_named(self, prefix, slug='fix-cafe'):
        j = self.journal()
        self.assertEqual(j['head_branch'], prefix + '/' + slug + '-' + j['owner'][:12])
        self.assertEqual(self.git('check-ref-format', '--branch', j['head_branch']), j['head_branch'])
        self.assertEqual(j['phase'], 'created')
        create = self.creates()[0]
        self.assertEqual(create[create.index('--head') + 1], 'owner:' + j['head_branch'])

    def test_naming_labels(self):
        # Rebind between cases so every case exercises fresh resolution.
        for labels, prefix in [('enhancement', 'feat'), ('bug', 'bug'),
                               ('documentation', 'doc'), ('', 'uncle'),
                               ('question', 'uncle'), ('BuG', 'bug'),
                               ('documentation,bug,enhancement', 'feat'),
                               ('enhancement,bug,documentation', 'feat'),
                               ('documentation,bug', 'bug')]:
            with self.subTest(labels=labels):
                self.setUp()
                self.ok(self.publish(ISSUE_LABELS=labels))
                self.assert_named(prefix)
                queries = [a for a in self.calls() if a[:2] == ['issue', 'view']]
                self.assertEqual(queries, [['issue', 'view', '42', '--repo', 'owner/repo', '--json', 'labels']])

    def test_naming_failures(self):
        for flag in ('LABELS_FAIL', 'LABELS_BAD', 'LABELS_HANG'):
            with self.subTest(flag=flag):
                self.setUp()
                result = self.publish(**{flag: '1', 'STAGEGATE_CLOSE_TIMEOUT': '1'})
                self.ok(result)
                self.assertEqual(result.stdout.count('Label lookup failed; using uncle/ prefix'), 1)
                self.assert_named('uncle')

    def test_naming_lookup_deadline(self):
        import ast
        import time
        source = LIB.read_text().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]
        tree = ast.parse(source)
        parts = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
                 or isinstance(node, ast.FunctionDef) and node.name == 'label_prefix']
        code = ast.unparse(ast.Module(body=parts, type_ignores=[]))
        code += "\nprint(label_prefix('owner/repo\\t42\\tgh'))"
        # Execute the real helper with a hard outer bound, independent of timeout(1).
        self.exe('timeout', '#!/bin/sh\nexit 99\n')
        self.exe('gtimeout', '#!/bin/sh\nexit 99\n')
        start = time.monotonic()
        result = subprocess.run([sys.executable, '-c', code], cwd=self.repo,
                                env=dict(self.env, LABELS_HANG='1', STAGEGATE_CLOSE_TIMEOUT='1'),
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3)
        self.ok(result)
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(result.stdout, 'Label lookup failed; using uncle/ prefix\nuncle/\n')

    def test_naming_slug_sources(self):
        for filename, content, slug, title in [
            ('CHANGE_REQUEST.md', '## Summary\n\nFix café 日本語\n', 'fix-cafe', 'Fix café 日本語'),
            ('CHANGE_REQUEST.md', '## Summary\n\n', 'change', 'Completed change'),
            ('CHANGE_REQUEST.md', '# Header fallback\n', 'header-fallback', 'Completed change'),
            ('REQUIREMENTS.md', '## Summary\nRequirements only\n', 'requirements-only', 'Completed change'),
            ('REQUIREMENTS.md', '# Build widgets\n', 'build-widgets', 'Completed change'),
            ('CHANGE_REQUEST.md', '## Summary\n' + 'A' * 39 + ' ! tail', 'a' * 39, 'A' * 39 + ' ! tail'),
            ('CHANGE_REQUEST.md', '## Summary\n日本語 !!!\n', 'change', '日本語 !!!'),
        ]:
            with self.subTest(content=content):
                self.setUp()
                (self.repo / 'CHANGE_REQUEST.md').unlink()
                (self.repo / filename).write_text(content)
                self.freeze()
                self.ok(self.publish())
                self.assert_named('uncle', slug)
                create = self.creates()[0]
                self.assertEqual(create[create.index('--title') + 1], title)

    def test_naming_nondefault(self):
        self.git('checkout', '-qb', 'existing-feature')
        self.freeze()
        self.ok(self.publish(ISSUE_LABELS='bug'))
        self.assertEqual(self.journal()['head_branch'], 'existing-feature')
        self.assertFalse([a for a in self.calls() if a[:2] == ['issue', 'view']])

    def test_naming_curl_rejected(self):
        (self.state / 'origin').write_text('owner/repo\t42\tcurl\n')
        self.freeze()
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Only a gh-fetched origin', result.stdout)
        self.assertFalse([a for a in self.calls() if a[:2] == ['issue', 'view']])
        self.assertEqual(len(self.creates()), 0)

    def test_publish_and_resume_without_run_id(self):
        # A persisted legacy identity must bypass naming on resume.
        self.assertNotEqual(self.engine('handoff').returncode, 0)
        legacy = self.journal()
        legacy['head_branch'] = 'uncle/change-' + legacy['owner'][:12]
        (self.state / 'pr/journal.json').write_text(json.dumps(legacy))
        self.ok(self.publish())
        j = self.journal()
        self.assertEqual(j['phase'], 'created')
        self.assertEqual(j['verdict_run'], '-')
        self.assertTrue(j['head_branch'].startswith('uncle/change-'))
        self.assertEqual(self.git('show', 'HEAD:source.txt'), 'audited')
        self.assertEqual(self.git('show', 'HEAD:FINAL_AUDIT.md'), 'READY')
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}'), j['commit_tree'])
        self.assertEqual(self.git('ls-remote', 'origin', 'refs/heads/' + j['head_branch']).split()[0], j['intended_head'])
        body = (self.root / 'server.body').read_text()
        self.assertIn('Implemented audited fix', body)
        self.assertIn('Run smoke test', body)
        self.assertIn('Closes owner/repo#42', body)
        # The attestation is driver-generated; no operator input produced it.
        self.assertIn('UNCLE CHANGE ATTESTATION', body)
        self.assertIn('Audited tree', body)
        self.assertIn(self.journal()['commit_tree'][:12], body)
        self.assertLess(body.index('UNCLE CHANGE ATTESTATION'), body.index('Closes owner/repo#42'))
        self.assertFalse(Path((self.root / 'server.bodypath').read_text()).exists())
        create = self.creates()[0]
        self.assertEqual(create[create.index('--title') + 1], 'Fix café 日本語')
        self.assertEqual(create[create.index('--repo') + 1], 'owner/repo')
        self.assertEqual(create[create.index('--head') + 1], 'owner:' + j['head_branch'])
        self.assertEqual(create[create.index('--base') + 1], 'main')
        self.ok(self.engine('handoff'))
        self.assertEqual(len(self.creates()), 1)
        self.assertFalse((self.state / 'issue-closed').exists())

    def test_decline_eof_auth_and_resume(self):
        for text in ('', '\nSummary\nManual\nn\n'):
            self.assertNotEqual(self.engine('handoff', text).returncode, 0)
            self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)
            self.assertEqual(len(self.creates()), 0)
        self.assertNotEqual(self.publish(AUTH_RC='1').returncode, 0)
        self.ok(self.publish())
        self.assertEqual(len(self.creates()), 1)

    def test_source_drift(self):
        (self.repo / 'source.txt').write_text('changed after audit\n')
        self.assertIn('Reviewed files changed', self.publish().stdout)
        self.assertEqual(len(self.creates()), 0)

    def test_mode_drift(self):
        (self.repo / 'source.txt').chmod(0o755)
        self.assertIn('Reviewed files changed', self.publish().stdout)

    def test_branch_drift(self):
        self.git('checkout', '-qb', 'other')
        self.assertIn('HEAD or branch changed', self.publish().stdout)

    def test_head_drift(self):
        self.git('commit', '--no-gpg-sign', '--allow-empty', '-qm', 'after audit')
        self.assertIn('HEAD or branch changed', self.publish().stdout)

    def test_origin_and_verdict_drift(self):
        (self.state / 'origin').write_text('other/repo\t42\tgh\n')
        self.assertIn('Origin or audit changed', self.publish().stdout)
        (self.state / 'origin').write_text('owner/repo\t42\tgh\n')
        verdict = self.state / 'audit-verdict'
        verdict.write_text(verdict.read_text().replace('READY', 'UNKNOWN'))
        self.assertIn('owned READY', self.publish().stdout)

    def not_ready_verdict(self):
        verdict = self.state / 'audit-verdict'
        run, _, sha = verdict.read_text().strip().split('\t')
        verdict.write_text('\t'.join([run, 'NOT_READY', sha]) + '\n')

    def test_not_ready_verdict_dialog(self):
        self.not_ready_verdict()
        result = self.engine('validate')
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('owned READY', result.stdout)
        for text in ('n\n', 'yes please\n', ''):
            self.assertNotEqual(self.engine('verdict-override', text).returncode, 0, repr(text))
            self.assertFalse((self.state / 'pr/verdict-override').exists())
        unattended = self.engine('verdict-override', 'y\n', UNCLE_UNATTENDED='1')
        self.assertNotEqual(unattended.returncode, 0)
        self.assertIn('owned READY', unattended.stdout)
        self.assertFalse((self.state / 'pr/verdict-override').exists())
        self.assertEqual(self.engine('validate').returncode, 3)

    def test_verdict_override_creates_pr(self):
        # Issue 59 (D-17): with a driver-created envelopes/ directory the
        # override is recorded and validate() accepts it, but handoff refuses
        # before any git write; the legacy path without the directory still
        # publishes exactly as before.
        (self.state / 'envelopes').mkdir()
        self.not_ready_verdict()
        result = self.engine('verdict-override', 'y\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('Override recorded', result.stdout)
        verdict = (self.state / 'audit-verdict').read_text().strip().split('\t')
        record = (self.state / 'pr/verdict-override').read_text().strip().split('\t')
        self.assertEqual(record[:3], verdict)
        self.assertRegex(record[3], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        self.ok(self.engine('validate'))
        blocked = self.publish()
        self.assertEqual(blocked.returncode, 3, blocked.stdout)
        self.assertIn('PR pending: Attestation blocked', blocked.stdout)
        self.assertEqual(self.creates(), [])
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)
        self.assertEqual(self.journal()['phase'], 'bound')
        self.assertFalse((self.repo / '.uncle/attestation.json').exists())
        release = json.loads((self.state / 'envelopes/release.json').read_text())
        self.assertEqual(release['result'], 'fail')
        self.assertEqual(release['override']['gate'], 'verdict-override')
        # Without the directory (a journal from before attestation) the
        # override still creates the PR, and says so in the body.
        import shutil
        shutil.rmtree(self.state / 'envelopes')
        self.ok(self.publish())
        j = self.journal()
        self.assertEqual(j['phase'], 'created')
        self.assertEqual(len(self.creates()), 1)
        body = (self.root / 'server.body').read_text()
        self.assertIn('operator override', body)
        self.assertIn('NOT_READY', body)
        self.ok(self.engine('handoff'))
        self.assertEqual(len(self.creates()), 1)
        # A record bound to a different audit authorizes nothing.
        record[2] = '0' * 64
        (self.state / 'pr/verdict-override').write_text('\t'.join(record) + '\n')
        self.assertEqual(self.engine('validate').returncode, 3)

    def test_complete_driver_verdict_override(self):
        (self.repo / 'CHANGE_SPEC.md').write_text('## Acceptance criteria\n| ID | Criterion | Verification |\n|---|---|---|\n| AC-1 | Fixture behavior | Fixture check |\n')
        (self.repo / 'CHANGE_PLAN.md').write_text('Approved fixture plan\n')
        (self.repo / 'IMPLEMENTATION_NOTES.md').write_text('## Acceptance delivery\n| ID | Status | Changed code | Observed targeted verification |\n|---|---|---|---|\n| AC-1 | IMPLEMENTED | source.txt | Fixture check PASS |\n')
        approvals = self.state / 'approvals'
        approvals.mkdir(exist_ok=True)
        for artifact in ('CHANGE_SPEC', 'CHANGE_PLAN'):
            digest = hashlib.sha256((self.repo / (artifact + '.md')).read_bytes()).hexdigest()
            (approvals / (artifact + '.sha256')).write_text(digest + '\n')
        # A NOT READY audit the validator accepts: one explicit blocking finding.
        self.exe('reviewer', """#!/usr/bin/env python3
from pathlib import Path
import sys
Path(sys.argv[sys.argv.index('--output-last-message') + 1]).write_text(
    '# Audit\\n\\n## Findings\\n\\n| ID | Severity | Evidence | Required correction | Blocks |\\n'
    '|---|---|---|---|---|\\n| FA-1 | blocking | fixture | fix it | YES |\\n\\nNOT READY\\n')
""")
        (self.state / 'state').write_text('42:FINAL_AUDIT\n')
        env = dict(self.env, UNCLE_PROJECT_ROOT=str(self.repo), WORKFLOW_AUDIT_GATE='0',
                   WORKFLOW_REVIEWER_CMD=str(self.bin / 'reviewer'), WORKFLOW_CLOSE_ISSUE='1', UNATTENDED='0')
        command = ['bash', str(ROOT / 'scripts/change-workflow.sh')]
        declined = subprocess.run(command, cwd=self.repo, env=env, input='n\n',
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        self.ok(declined)
        self.assertIn('The audit verdict is NOT_READY, not READY.', declined.stdout)
        self.assertIn('PR pending', declined.stdout)
        self.assertEqual(len(self.creates()), 0)
        self.assertFalse((self.state / 'pr/verdict-override').exists())
        # Issue 59 (D-17): the driver created envelopes/ on FINAL_AUDIT entry
        # and recorded audit.json as fail, so the override is recorded, the
        # run reaches COMPLETE, and the handoff refuses to publish.
        self.assertTrue((self.state / 'envelopes').is_dir())
        self.assertEqual(json.loads((self.state / 'envelopes/audit.json').read_text())['result'], 'fail')
        (self.state / 'state').write_text('42:FINAL_AUDIT\n')
        approved = subprocess.run(command, cwd=self.repo, env=env, input='y\n\nSummary\nManual\ny\n',
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        self.ok(approved)
        self.assertIn('Override recorded', approved.stdout)
        self.assertNotIn('needs your help', approved.stdout)
        self.assertIn('PR pending: Attestation blocked', approved.stdout)
        self.assertIn('the override is recorded but does not release', approved.stdout)
        self.assertEqual(len(self.creates()), 0, approved.stdout)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)
        self.assertEqual(json.loads((self.state / 'envelopes/release.json').read_text())['result'], 'fail')
        self.assertEqual((self.state / 'state').read_text().strip(), '42:COMPLETE')
        self.assertFalse((self.state / 'issue-closed').exists())

    def test_source_drift_during_audit(self):
        self.ok(self.engine('freeze'))
        (self.repo / 'source.txt').write_text('during audit\n')
        self.assertIn('changed during audit', self.engine('bind').stdout)

    def test_source_drift_during_prompt(self):
        process = subprocess.Popen(['bash', '-c', '. "$1"; change_pr_engine handoff', 'test', str(LIB)],
            cwd=self.repo, env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        output = ''
        while not output.endswith(']: '):
            ch = process.stdout.read(1)
            self.assertTrue(ch, output)
            output += ch
        (self.repo / 'source.txt').write_text('during prompt\n')
        remainder, _ = process.communicate('\nSummary\nManual\ny\n', timeout=15)
        self.assertIn('Reviewed files changed', remainder)
        self.assertEqual(len(self.creates()), 0)

    def test_commit_and_push_crash_recovery(self):
        # A completed commit whose wrapper fails before journaling is adopted
        # on resume rather than duplicated.
        self.assertNotEqual(self.publish(CRASH_GIT='commit').returncode, 0)
        self.assertEqual((self.journal()['phase'], self.journal()['intended_head']), ('prepared', ''))
        self.assertNotEqual(self.git('rev-parse', 'HEAD'), self.original)
        self.assertNotEqual(self.engine('handoff', CRASH_GIT='push').returncode, 0)
        sha = self.journal()['intended_head']
        self.assertEqual(self.journal()['phase'], 'prepared')
        self.assertEqual(self.git('rev-parse', sha + '^{tree}'), self.journal()['commit_tree'])
        self.ok(self.engine('handoff'))
        self.assertEqual(self.journal()['intended_head'], sha)
        self.assertEqual(len(self.creates()), 1)

    def test_published_lookup_failure_retries_safely(self):
        self.assertNotEqual(self.publish(LOOKUP_FAIL='1').returncode, 0)
        self.assertEqual(self.journal()['phase'], 'published')
        self.ok(self.engine('handoff'))
        self.assertEqual(len(self.creates()), 1)

    def test_server_success_timeout_reconciles(self):
        self.assertNotEqual(self.publish(CREATE_TIMEOUT='1').returncode, 0)
        self.assertEqual(self.journal()['phase'], 'unknown')
        self.ok(self.engine('handoff'))
        self.assertEqual(len(self.creates()), 1)

    def test_unknown_empty_or_failed_lookup_never_recreates(self):
        self.assertNotEqual(self.publish(CREATE_FAIL='1').returncode, 0)
        self.assertEqual(self.journal()['phase'], 'unknown')
        self.assertNotEqual(self.engine('handoff', LOOKUP_FAIL='1').returncode, 0)
        self.assertIn('unknown', self.engine('handoff').stdout)
        self.assertIn('Unresolved PR outcome', self.engine('freeze').stdout)
        self.assertEqual(len(self.creates()), 1)

    def test_creating_crash_reconciles_and_duplicate_stops(self):
        self.ok(self.publish())
        path = self.state / 'pr/journal.json'
        j = self.journal()
        j['phase'] = 'creating'
        path.write_text(json.dumps(j))
        self.assertIn('Multiple matching PRs', self.engine('handoff', DUPLICATE='1').stdout)
        self.ok(self.engine('handoff'))
        self.assertEqual(len(self.creates()), 1)

    def test_fork_identity(self):
        self.git('remote', 'add', 'upstream', str(self.bare))
        self.ok(self.publish(FORK='1'))
        create = self.creates()[0]
        self.assertEqual(create[create.index('--head') + 1], 'forker:' + self.journal()['head_branch'])
        self.assertEqual(create[create.index('--repo') + 1], 'owner/repo')

    def test_ambiguous_remote(self):
        self.git('remote', 'add', 'duplicate', str(self.bare))
        self.assertIn('Ambiguous head remote', self.publish().stdout)
        self.assertEqual(len(self.creates()), 0)

    def test_originless_derives_repository(self):
        (self.state / 'origin').unlink()
        self.freeze()
        result = self.engine('handoff', 'Custom title\nSummary\nManual\ny\n')
        self.ok(result)
        self.assertNotIn('Base repository [', result.stdout)
        self.assert_named('uncle')
        self.assertFalse([a for a in self.calls() if a[:2] == ['issue', 'view']])
        self.assertNotIn('Closes ', (self.root / 'server.body').read_text())
        self.assertEqual(self.creates()[0][self.creates()[0].index('--title') + 1], 'Custom title')

    def test_missing_or_corrupt_binding_denies(self):
        path = self.state / 'pr/journal.json'
        path.write_text('{}')
        self.assertIn('Missing/corrupt', self.publish().stdout)
        path.unlink()
        self.assertNotEqual(self.publish().returncode, 0)
        self.assertEqual(len(self.creates()), 0)

    def test_returned_pr_sha_mismatch_is_pending(self):
        self.assertIn('Returned PR SHA differs', self.publish(WRONG_PR_SHA='1').stdout)
        self.assertEqual(self.journal()['phase'], 'unknown')
        self.assertEqual(len(self.creates()), 1)
        self.ok(self.engine('handoff'))
        self.assertEqual(len(self.creates()), 1)

    def test_existing_pr_head_drift_is_diagnosed(self):
        self.ok(self.publish())
        j = self.journal()
        subprocess.run([REAL_GIT, '--git-dir', str(self.bare), 'update-ref',
                        'refs/heads/' + j['head_branch'], self.original], check=True)
        self.assertIn('drifted after creation', self.engine('handoff').stdout)
        self.assertEqual(len(self.creates()), 1)

    def test_title_shortening_and_fallback(self):
        (self.repo / 'CHANGE_REQUEST.md').write_text('## Summary\n\n' + 'é' * 90 + '\n')
        self.freeze()
        result = self.engine('handoff')
        self.assertIn('PR title [default: ' + 'é' * 72 + ']: ', result.stdout)
        (self.repo / 'CHANGE_REQUEST.md').write_text('No Summary section\n')
        self.freeze()
        self.assertIn('PR title [default: Completed change]: ', self.engine('handoff').stdout)

    def test_raw_bytes_ignore_clean_filters(self):
        (self.repo / '.gitattributes').write_text('source.txt text eol=lf\n')
        (self.repo / 'source.txt').write_bytes(b'audited\r\n')
        self.freeze()
        self.ok(self.publish())
        raw = subprocess.check_output([REAL_GIT, 'show', 'HEAD:source.txt'], cwd=self.repo)
        self.assertEqual(raw, b'audited\r\n')
        (self.repo / 'source.txt').write_bytes(b'audited\n')
        self.assertIn('Reviewed files changed', self.engine('handoff').stdout)

    def test_symlink_and_untracked_bytes_are_published(self):
        (self.repo / 'extra.txt').write_text('new file\n')
        (self.repo / 'link').symlink_to('source.txt')
        self.freeze()
        self.ok(self.publish())
        self.assertEqual(self.git('show', 'HEAD:extra.txt'), 'new file')
        self.assertIn('120000', self.git('ls-tree', 'HEAD', 'link'))

    def test_remote_drift_during_prompt(self):
        process = subprocess.Popen(['bash', '-c', '. "$1"; change_pr_engine handoff', 'test', str(LIB)],
            cwd=self.repo, env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        output = ''
        while not output.endswith(']: '):
            ch = process.stdout.read(1)
            self.assertTrue(ch, output)
            output += ch
        target = self.journal()['head_branch']
        subprocess.run([REAL_GIT, '--git-dir', str(self.bare), 'update-ref',
                        'refs/heads/' + target, self.original], check=True)
        remainder, _ = process.communicate('\nSummary\nManual\ny\n', timeout=15)
        self.assertIn('Remote changed during prompts', remainder)
        self.assertEqual(len(self.creates()), 0)

    def test_fork_same_branch_wrong_sha_denies(self):
        self.git('checkout', '-qb', 'feature')
        self.freeze()
        self.git('remote', 'add', 'upstream', str(self.bare))
        other = self.git('commit-tree', '--no-gpg-sign', self.git('rev-parse', 'HEAD^{tree}'), '-p', self.original, '-m', 'remote edit')
        self.git('push', '-q', 'origin', other + ':refs/heads/feature')
        self.assertIn('Remote head differs', self.publish(FORK='1').stdout)
        self.assertEqual(len(self.creates()), 0)

    def test_symlink_audit_denies_binding(self):
        self.ok(self.engine('freeze'))
        (self.repo / 'FINAL_AUDIT.md').unlink()
        (self.repo / 'FINAL_AUDIT.md').symlink_to('source.txt')
        self.assertIn('regular file', self.engine('bind').stdout)

    def test_worktree_git_file(self):
        worktree = self.root / 'worktree'
        self.git('worktree', 'add', '-qb', 'feature', str(worktree))
        self.repo = worktree
        self.state = self.repo / '.uncle/workflow'
        self.state.mkdir(parents=True)
        (self.state / 'origin').write_text('owner/repo\t42\tgh\n')
        (self.repo / 'source.txt').write_text('worktree edit\n')
        self.assertTrue((self.repo / '.git').is_file())
        self.freeze()
        self.ok(self.publish())
        self.assertEqual(self.git('show', 'HEAD:source.txt'), 'worktree edit')


# Cases own independent repositories, keys, and fake GitHub servers.
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
workers = int(os.environ.get('WORKFLOW_TEST_JOBS', '8'))
if not 1 <= workers <= 8:
    raise SystemExit('WORKFLOW_TEST_JOBS must be from 1 to 8')
def run_case(name):
    output = io.StringIO()
    started = time.monotonic()
    result = unittest.TextTestRunner(stream=output).run(HandoffTests(name))
    return name, time.monotonic() - started, result, output.getvalue()
started = time.monotonic()
failures = 0
names = unittest.defaultTestLoader.getTestCaseNames(HandoffTests)
print(f'PR handoff: {len(names)} cases, up to {workers} workers', flush=True)
with ThreadPoolExecutor(max_workers=workers) as pool:
    for future in as_completed([pool.submit(run_case, name) for name in names]):
        name, elapsed, result, output = future.result()
        status = 'PASS' if result.wasSuccessful() else 'FAIL'
        print(f'{status} {name} ({elapsed:.2f}s)', flush=True)
        if not result.wasSuccessful():
            print(output, flush=True)
            failures += 1
print(f'PR handoff: {len(names) - failures} passed, {failures} failed '
      f'in {time.monotonic() - started:.2f}s', flush=True)
raise SystemExit(bool(failures))
PY
pr_rc=$?
COUNT=$((COUNT + 1))
if [[ "$pr_rc" != 0 ]]; then fail "PR handoff integration tests failed ($pr_rc)"; fi

if [[ "$FAILED" -ne 0 ]]; then
    echo "close-flow-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "close-flow-test.sh: $COUNT checks passed"

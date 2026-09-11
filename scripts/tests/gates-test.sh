#!/usr/bin/env bash
set -uo pipefail

# Hermetic coverage of the two gates that were added around implementation in
# scripts/change-workflow.sh:
#
#   the green check   the driver re-runs the project's own verification
#                     commands instead of reading the agent's report of them
#   the diff gate     the operator sees the code before anything downstream
#                     reads it, and a failing check turns approval into a
#                     recorded override
#
# The real driver runs in a scratch git repository against stub agent and
# reviewer CLIs. Nothing here touches the network, a model, or the developer's
# checkout. The verdict gate is covered by close-flow-test.sh, which already
# owns the FINAL_AUDIT fixtures.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/sha256.sh"   # hash_file, portable across platforms

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
COUNT=0
CASE_NAME=""
CASE=""
REPO=""
OUT=""
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
    if ! grep -qF -- "$1" "$OUT"; then
        fail "expected output to contain: $1"
        sed 's/^/    /' < "$OUT"
    fi
}

expect_not_out() {
    COUNT=$((COUNT + 1))
    if grep -qF -- "$1" "$OUT"; then
        fail "expected output NOT to contain: $1"
        sed 's/^/    /' < "$OUT"
    fi
}

expect_state() {
    COUNT=$((COUNT + 1))
    local actual
    actual="$(cat "$REPO/.uncle/workflow/state" 2>/dev/null)"
    if [[ "$actual" != "$1" ]]; then
        fail "expected state '$1', got '$actual'"
    fi
}

expect_file() {
    COUNT=$((COUNT + 1))
    if [[ ! -s "$REPO/$1" ]]; then
        fail "expected $1 to exist and be non-empty"
    fi
}

expect_no_file() {
    COUNT=$((COUNT + 1))
    if [[ -e "$REPO/$1" ]]; then
        fail "expected $1 not to exist"
    fi
}

expect_in_file() {
    COUNT=$((COUNT + 1))
    if ! grep -qF -- "$2" "$REPO/$1" 2>/dev/null; then
        fail "expected $1 to contain: $2"
    fi
}

# ---------------------------------------------------------------------------
# Scratch fixture
# ---------------------------------------------------------------------------

# A repository mid-workflow: the plan is approved, the tree is committed and
# clean, and the driver is one state away from writing code.
new_case() {
    CASE_NAME="$1"
    CASE="$TMP/$1"
    REPO="$CASE/repo"
    OUT="$CASE/out.txt"

    mkdir -p "$REPO/scripts/lib" "$REPO/prompts/change" \
             "$REPO/.uncle/workflow/approvals" "$REPO/app" "$CASE/bin"
    : > "$OUT"

    cp "$ROOT"/scripts/lib/*.sh "$REPO/scripts/lib/"
    cp "$ROOT"/scripts/lib/*.py "$REPO/scripts/lib/"

    # Prompt files the driver reads and pipes to the stub CLIs. Each carries a
    # token the stub agent switches on.
    printf 'STUB:plan\n'      > "$REPO/prompts/change/change-plan.md"
    printf 'STUB:implement\n' > "$REPO/prompts/change/implement-change.md"
    printf 'STUB:execute\n'   > "$REPO/prompts/change/execute-change-checklist.md"
    printf 'review the plan\n'   > "$REPO/prompts/change/adversarial-review.md"
    printf 'write a checklist\n' > "$REPO/prompts/change/manual-checklist.md"
    printf 'audit it\n'          > "$REPO/prompts/change/final-audit.md"

    cat > "$REPO/CHANGE_REQUEST.md" <<'EOF'
# Change Request

Make app/main.sh print a different greeting.
EOF

    cat > "$REPO/BASELINE_REPORT.md" <<'EOF'
# Baseline Report

## 8. Exact build and test commands executed

```
bash app/test.sh
```

## 9. Baseline test results

Passing.
EOF

    printf '# Change Spec\n\nChange the greeting.\n' > "$REPO/CHANGE_SPEC.md"

    cat > "$REPO/CHANGE_PLAN.md" <<'EOF'
# Change Plan

## 20. Implementation sequence

1. Change the greeting.

## Change-impact table

| Component | Planned change | Test coverage |
|---|---|---|
| `app/main.sh` | New greeting | `app/test.sh` |
| `app/added.sh` | A new helper | manual |
EOF

    local f
    for f in BASELINE_REPORT CHANGE_SPEC CHANGE_PLAN; do
        hash_file "$REPO/${f}.md" \
            > "$REPO/.uncle/workflow/approvals/${f}.sha256"
    done

    # The project under change: one script, one test that checks it.
    printf '#!/bin/sh\necho hello\n' > "$REPO/app/main.sh"
    cat > "$REPO/app/test.sh" <<'EOF'
#!/bin/sh
sh app/main.sh | grep -q . || exit 1
EOF

    git -C "$REPO" init -q .
    git -C "$REPO" config user.email test@example.com
    git -C "$REPO" config user.name Test
    git -C "$REPO" config commit.gpgsign false
    git -C "$REPO" add -A
    git -C "$REPO" commit -qm baseline

    # Stub agent: one JSON result event, plus whatever artifact the prompt
    # implies. FAKE_IMPL is the per-case body of the implementation stage.
    cat > "$CASE/bin/fake-agent" <<'AGENT'
#!/usr/bin/env bash
prompt="$(cat)"
case "$prompt" in
    *STUB:implement*)
        printf '# Implementation Notes\n\nChanged app/main.sh.\n' \
            > IMPLEMENTATION_NOTES.md
        printf '# Change Test Report\n\nEverything passed. Trust me.\n' \
            > CHANGE_TEST_REPORT.md
        if [[ -n "${FAKE_IMPL:-}" ]]; then
            bash -c "$FAKE_IMPL"
        fi
        ;;
    *STUB:execute*)
        printf '# Verification Report\n\nMC-1 PASS\n' > VERIFICATION_REPORT.md
        ;;
    *STUB:plan*)
        printf '# Change Plan\n\n## Change-impact table\n\n| Component |\n|---|\n| `app/main.sh` |\n' \
            > CHANGE_PLAN.md
        ;;
esac
printf '%s\n' '{"type":"result","subtype":"success","is_error":false,"num_turns":1,"duration_ms":5,"total_cost_usd":0,"usage":{"input_tokens":1,"output_tokens":1,"cache_read_input_tokens":0,"cache_creation_input_tokens":0},"session_id":"stub"}'
AGENT
    chmod +x "$CASE/bin/fake-agent"

    # Stub reviewer: writes its output file, ending in a READY verdict so the
    # audit gate is not what stops these runs.
    cat > "$CASE/bin/fake-reviewer" <<'REV'
#!/usr/bin/env bash
out=""
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--output-last-message" ]]; then out="$2"; shift; fi
    shift
done
printf '%s\n' "$out" >> .uncle/workflow/reviewer-calls
if [[ "${FAKE_COMPACT_REVIEW:-0}" == 1 && "$out" == *MANUAL_CHECKLIST.base.md ]]; then
    printf 'Repeated background that adds no findings. Repeated background that adds no findings.\n' > "$out"
else
    : > "$out"
fi
printf 'MC-1 Check the greeting.\n\nREADY\n' >> "$out"
REV
    chmod +x "$CASE/bin/fake-reviewer"
}

# green_baseline <status> <command> — the record the PLAN stage would have left.
green_baseline() {
    printf '%s\t%s\n' "$1" "$2" > "$REPO/.uncle/workflow/green-check.baseline.tsv"
    printf '%s\n' "$2" > "$REPO/.uncle/workflow/green-check.commands"
    hash_file "$REPO/BASELINE_REPORT.md" \
        > "$REPO/.uncle/workflow/green-check.source"
}

set_state() {
    printf '%s\n' "$1" > "$REPO/.uncle/workflow/state"
}

# gate_input <line>... — the keystrokes one human_gate consumes: the ENTER
# after reviewing, then the Y/N answer.
gate_input() {
    printf '%s\n' "$@" > "$CASE/gate-input"
    printf '%s' "$CASE/gate-input"
}

run_driver() {
    run_driver_stdin /dev/null "$@"
}

run_driver_stdin() {
    local stdin_file="$1"
    shift

    cp "$ROOT/scripts/change-workflow.sh" "$REPO/scripts/change-workflow.sh"
    env -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u STAGEGATE_RUN_ID \
        PATH="$CASE/bin:$PATH" \
        WORKFLOW_AGENT_CMD="$CASE/bin/fake-agent" \
        WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" \
        WORKFLOW_PARALLEL_CHECKLIST=0 \
        "$@" \
        bash "$REPO/scripts/change-workflow.sh" \
        < "$stdin_file" > "$OUT" 2>&1
    RC=$?
}

# ---------------------------------------------------------------------------
# The diff gate
# ---------------------------------------------------------------------------

# Implementation no longer runs straight into verification.
new_case implement-stops-for-review
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh"
expect_status 0
expect_out "HUMAN REVIEW REQUIRED"
expect_out "Gate not accepted."
expect_not_out "Change workflow complete."
expect_state "WAIT_IMPLEMENT_APPROVAL"
expect_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md"

# The document the operator is shown is the change, not a description of it.
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "echo goodbye"
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "- app/main.sh"
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "## Green check"
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "Changed app/main.sh."
expect_no_file ".uncle/workflow/approvals/IMPLEMENTATION_REVIEW.sha256"

# A new file the agent created is in the diff. It is the one file in the change
# with no prior reviewer, and `git diff` alone would not show it.
new_case untracked-file-is-reviewed
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver FAKE_IMPL="printf 'TOKEN_NEW_FILE\n' > app/added.sh"
expect_status 0
expect_state "WAIT_IMPLEMENT_APPROVAL"
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "TOKEN_NEW_FILE"
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "- app/added.sh"

# Approving runs the rest of the pipeline through to COMPLETE.
new_case approval-advances-to-complete
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver_stdin "$(gate_input '' y)" \
    FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh"
expect_status 0
expect_out "Recorded approval for .uncle/workflow/IMPLEMENTATION_REVIEW.md"
expect_out "Change workflow complete."
expect_state "COMPLETE"
expect_file ".uncle/workflow/approvals/IMPLEMENTATION_REVIEW.sha256"
expect_no_file ".uncle/workflow/green-check-override"
expect_no_file ".uncle/workflow/audit-override"

# Declining leaves the state where it was, so re-running re-opens the gate
# rather than skipping it.
new_case decline-holds-the-state
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver_stdin "$(gate_input '' n)" \
    FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh"
expect_status 0
expect_out "Gate not accepted."
expect_state "WAIT_IMPLEMENT_APPROVAL"
expect_no_file ".uncle/workflow/approvals/IMPLEMENTATION_REVIEW.sha256"

# The approval attests to the tree. Code that moves after it re-opens the gate
# instead of carrying a stale approval into verification.
new_case tree-moved-after-approval
green_baseline 0 'bash app/test.sh'
printf 'not-the-digest-of-anything\n' \
    > "$REPO/.uncle/workflow/approvals/IMPLEMENTATION_REVIEW.sha256"
printf '#!/bin/sh\necho edited\n' > "$REPO/app/main.sh"
set_state CHECKLIST
run_driver
expect_status 0
expect_out "The working tree changed after the implementation was approved."
expect_state "WAIT_IMPLEMENT_APPROVAL"

# ---------------------------------------------------------------------------
# The frozen-scope check
# ---------------------------------------------------------------------------

# A file the agent created outside the plan's change-impact table is scope
# creep. `git diff` does not report untracked files, so this went unexamined.
new_case new-file-outside-the-plan-fails
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver FAKE_IMPL="printf 'x\n' > app/unplanned.py"
expect_status 1
expect_out "Files changed outside CHANGE_PLAN.md's change-impact table:"
expect_out "app/unplanned.py"
expect_out "Not recorded as deviations in IMPLEMENTATION_NOTES.md:"
expect_state "IMPLEMENT"

# Going outside the plan is allowed; doing it silently is not. Naming the file
# in IMPLEMENTATION_NOTES.md is what makes it a recorded deviation.
new_case new-file-recorded-as-a-deviation
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver FAKE_IMPL="printf 'x\n' > app/unplanned.py; printf 'Deviation: app/unplanned.py was needed.\n' >> IMPLEMENTATION_NOTES.md"
expect_status 0
expect_out "(all recorded in IMPLEMENTATION_NOTES.md)"
expect_state "WAIT_IMPLEMENT_APPROVAL"

# A file that was already sitting untracked in the checkout is not something
# the agent did, and must not be charged to the change.
new_case preexisting-untracked-file-is-not-scope-creep
green_baseline 0 'bash app/test.sh'
printf 'my scratch notes\n' > "$REPO/scratch.txt"
set_state IMPLEMENT
run_driver FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh"
expect_status 0
expect_not_out "scratch.txt"
expect_state "WAIT_IMPLEMENT_APPROVAL"
COUNT=$((COUNT + 1))
if grep -qF "my scratch notes" "$REPO/.uncle/workflow/IMPLEMENTATION_REVIEW.md"; then
    fail "a pre-existing untracked file leaked into the reviewed diff"
fi

# The workflow's own reports are untracked in a target repository. They are not
# the change, and must not be reported as scope creep now that untracked files
# are examined.
new_case workflow-artifacts-are-not-scope-creep
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh; printf 'x\n' > DEFECTS.md"
expect_status 0
expect_not_out "outside CHANGE_PLAN.md's change-impact table"
expect_state "WAIT_IMPLEMENT_APPROVAL"

# ---------------------------------------------------------------------------
# The green check
# ---------------------------------------------------------------------------

# The driver runs the commands itself. The agent's report says everything
# passed; the commands say otherwise, and the gate reports the commands.
new_case regression-is-found-despite-the-report
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
# One newline, so the gate reaches its Y/N prompt before EOF declines it: the
# wording of that prompt is what this case is about.
run_driver_stdin "$(gate_input '')" FAKE_IMPL="printf 'exit 1\n' > app/test.sh"
expect_status 0
expect_out "GREEN CHECK FAILED: 1 regression(s)"
expect_out "Approving here is an override, and it is recorded."
expect_out "Ready to override"
expect_state "WAIT_IMPLEMENT_APPROVAL"
expect_in_file ".uncle/workflow/green-check.tsv" "REGRESSION"
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "1 command(s) regressed"

# Overriding a failing check is allowed, recorded, and reported at the end.
new_case regression-override-is-recorded
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver_stdin "$(gate_input '' y)" FAKE_IMPL="printf 'exit 1\n' > app/test.sh"
expect_status 0
expect_out "Change workflow complete."
expect_out "Completed with a failing green check, by human override:"
expect_file ".uncle/workflow/green-check-override"
expect_in_file ".uncle/workflow/green-check-override" "1 regression(s) overridden"

# A check that was already failing before the change is not this change's
# regression, and does not turn the gate into an override.
new_case preexisting-failure-does-not-block
green_baseline 1 'bash app/test.sh'
set_state IMPLEMENT
run_driver_stdin "$(gate_input '')" FAKE_IMPL="printf 'exit 1\n' > app/test.sh"
expect_status 0
expect_out "Green check: no regressions."
expect_not_out "GREEN CHECK FAILED"
expect_out "Ready to approve"
expect_in_file ".uncle/workflow/green-check.tsv" "PREEXISTING"

# A check that passes stays out of the way entirely.
new_case passing-check-is-quiet
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh"
expect_status 0
expect_out "Green check: no regressions."
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "No regressions."

# With no commands to run, the gate says so rather than implying a pass.
new_case no-commands-is-reported-as-not-run
set_state IMPLEMENT
run_driver FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh"
expect_status 0
expect_out "Green check NOT RUN: no commands were found in BASELINE_REPORT.md."
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "NOT RUN"
expect_state "WAIT_IMPLEMENT_APPROVAL"

# ---------------------------------------------------------------------------
# The kill switches
# ---------------------------------------------------------------------------

# Turning the human gate off does not turn the machine check off: with no
# human left to weigh a regression, the run stops instead.
new_case no-gate-and-a-regression-stops
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver WORKFLOW_DIFF_GATE=0 FAKE_IMPL="printf 'exit 1\n' > app/test.sh"
expect_status 1
expect_out "Refusing to continue: 1 verification"
expect_state "WAIT_IMPLEMENT_APPROVAL"

# Turned off with everything green, the pipeline runs as it did before.
new_case no-gate-and-green-continues
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver WORKFLOW_DIFF_GATE=0 \
    FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh"
expect_status 0
expect_out "no human reads the diff."
expect_out "Change workflow complete."
expect_state "COMPLETE"

# With the green check off, the agent's report is the only evidence, and the
# review document says exactly that.
new_case green-check-disabled-says-so
green_baseline 0 'bash app/test.sh'
set_state IMPLEMENT
run_driver_stdin "$(gate_input '')" WORKFLOW_GREEN_CHECK=0 \
    FAKE_IMPL="printf 'exit 1\n' > app/test.sh"
expect_status 0
expect_out "Ready to approve"
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "DISABLED"
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "unverified account"

# ---------------------------------------------------------------------------
# The baseline capture
# ---------------------------------------------------------------------------

# The baseline is taken from the approved BASELINE_REPORT.md, after its gate
# and before any code changes.
new_case baseline-is-captured-at-plan
set_state PLAN
run_driver
expect_status 0
expect_out "Recording the green-check baseline before anything changes."
expect_file ".uncle/workflow/green-check.baseline.tsv"
expect_in_file ".uncle/workflow/green-check.baseline.tsv" "bash app/test.sh"
COUNT=$((COUNT + 1))
if [[ "$(awk -F'\t' 'NR==1 {print $1}' "$REPO/.uncle/workflow/green-check.baseline.tsv")" != "0" ]]; then
    fail "the unmodified tree should have recorded a passing baseline"
fi

# A baseline report with no command block is a warning, not a stopped run.
new_case baseline-without-commands-warns
printf '# Baseline Report\n\nNo commands section.\n' > "$REPO/BASELINE_REPORT.md"
hash_file "$REPO/BASELINE_REPORT.md" \
    > "$REPO/.uncle/workflow/approvals/BASELINE_REPORT.sha256"
set_state PLAN
run_driver
expect_status 0
expect_out "has no fenced command block"
expect_no_file ".uncle/workflow/green-check.baseline.tsv"

# ---------------------------------------------------------------------------
# The new-application driver
# ---------------------------------------------------------------------------
#
# scripts/stagegate.sh carries the same three gates against different
# artifacts: the plan supplies the verification commands, there is no baseline
# to compare against, and the audit verdict was previously not classified at
# all.

new_stagegate_case() {
    new_case "$1"

    mkdir -p "$REPO/prompts"
    printf 'Change the greeting.\n' > "$REPO/REQUIREMENTS.md"
    printf 'STUB:implement\n' > "$REPO/prompts/implement.md"
    printf 'STUB:execute\n'   > "$REPO/prompts/execute-checklist.md"
    printf 'STUB:preflight\n' > "$REPO/prompts/preflight.md"
    printf 'STUB:repair\n' > "$REPO/prompts/repair.md"
    printf 'review tests\n' > "$REPO/prompts/test-review.md"
    printf 'write a checklist\n' > "$REPO/prompts/manual-checklist.md"
    printf 'audit it\n'          > "$REPO/prompts/final-audit.md"

    cat > "$REPO/UPDATED_PROJECT_PLAN.md" <<'EOF'
# Updated Project Plan

## Verification commands

```
bash app/test.sh
```

## Non-goals

## Protected verification paths

```
app/test.sh
```
EOF
    hash_file "$REPO/UPDATED_PROJECT_PLAN.md" \
        > "$REPO/.uncle/workflow/approvals/UPDATED_PROJECT_PLAN.sha256"
    # New-app reviewer with a real acceptance table, configurable failures,
    # and an invocation log so tests can prove stages were not reached.
    cat > "$CASE/bin/fake-reviewer" <<'REV'
#!/usr/bin/env bash
out=""
review_prompt="${!#}"
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--output-last-message" ]]; then out="$2"; shift; fi
    shift
done
printf '%s\n' "$out" >> .uncle/workflow/reviewer-calls
if [[ "$out" == TEST_REVIEW.md ]]; then
    printf '%s\n' "$review_prompt" > .uncle/workflow/received-test-review-prompt.md
    status="${FAKE_TEST_REVIEW:-PASS}"
    if [[ "$status" == FAIL_ONCE ]]; then
        status=PASS
        [[ -e .uncle/workflow/repaired ]] || status=FAIL
    fi
    if [[ "$status" == MALFORMED ]]; then
        printf 'PASS\n' > "$out"
        exit 0
    fi
    printf '## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n' > "$out"
    for id in COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS; do
        printf '| %s | YES | %s | stub evidence |\n' "$id" "$status" >> "$out"
    done
else
    if [[ "${FAKE_COMPACT_REVIEW:-0}" == 1 && "$out" == FINAL_AUDIT.md ]]; then
        printf 'Repeated background that adds no findings. Repeated background that adds no findings.\n' > "$out"
    else
        : > "$out"
    fi
    if [[ "$out" == FINAL_AUDIT.md && "${FAKE_AUDIT:-READY}" == 'NOT READY' ]]; then
        printf '## Findings\n\n| ID | Evidence | Required correction | Blocks |\n|---|---|---|---|\n| FA-1 | Missing review | Review greeting | YES |\n\nNOT READY\n' >> "$out"
    else
        printf 'MC-1 Check the greeting.\n\n%s\n' "${FAKE_AUDIT:-READY}" >> "$out"
    fi
fi
REV
    chmod +x "$CASE/bin/fake-reviewer"
}

run_stagegate() {
    run_stagegate_stdin /dev/null "$@"
}

run_stagegate_stdin() {
    local stdin_file="$1"
    shift

    cp "$ROOT/scripts/stagegate.sh" "$REPO/scripts/stagegate.sh"
    env PATH="$CASE/bin:$PATH" \
        WORKFLOW_AGENT_CMD="$CASE/bin/fake-agent" \
        WORKFLOW_REVIEWER_CMD="$CASE/bin/fake-reviewer" \
        WORKFLOW_SPECULATE=0 \
        "$@" \
        bash "$REPO/scripts/stagegate.sh" \
        < "$stdin_file" > "$OUT" 2>&1
    RC=$?
}

# The agent stub writes the change pipeline's report name; the new-application
# pipeline reads a different one.
stagegate_agent() {
    cat > "$CASE/bin/fake-agent" <<'AGENT'
#!/usr/bin/env bash
prompt="$(cat)"
gate_report() {
    printf '## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n| MC-1 | YES | %s | stub observation |\n' "$2" > "$1"
}
case "$prompt" in
    *STUB:preflight*)
        gate_report PREFLIGHT_REPORT.md "${FAKE_PREFLIGHT:-PASS}"
        ;;
    *STUB:repair*)
        printf 'repaired\n' > .uncle/workflow/repaired
        printf '\nRepair disposition.\n' >> IMPLEMENTATION_NOTES.md
        printf '\nRetested.\n' >> AUTOMATED_TEST_REPORT.md
        if [[ -n "${FAKE_REPAIR:-}" ]]; then bash -c "$FAKE_REPAIR"; fi
        ;;
    *STUB:implement*)
        printf 'implemented\n' > .uncle/workflow/implemented
        printf '# Implementation Notes\n\nBuilt app/main.sh.\n' \
            > IMPLEMENTATION_NOTES.md
        printf '# Automated Test Report\n\nAll green. Trust me.\n' \
            > AUTOMATED_TEST_REPORT.md
        if [[ -n "${FAKE_IMPL:-}" ]]; then
            bash -c "$FAKE_IMPL"
        fi
        ;;
    *STUB:execute*)
        status="${FAKE_VERIFICATION:-PASS}"
        if [[ "$status" == FAIL_ONCE ]]; then
            status=PASS
            [[ -e .uncle/workflow/repaired ]] || status=FAIL
        fi
        gate_report VERIFICATION_REPORT.md "$status"
        printf '# Defects\n\nNo unresolved defects in fixture.\n' > DEFECTS.md
        if [[ -n "${FAKE_VERIFY_EDIT:-}" ]]; then bash -c "$FAKE_VERIFY_EDIT"; fi
        ;;
esac
printf '%s\n' '{"type":"result","subtype":"success","is_error":false,"num_turns":1,"duration_ms":5,"total_cost_usd":0,"usage":{"input_tokens":1,"output_tokens":1},"session_id":"stub"}'
AGENT
    chmod +x "$CASE/bin/fake-agent"
}

new_stagegate_case sg-implement-stops-for-review
stagegate_agent
set_state IMPLEMENT
run_stagegate FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh"
expect_status 0
expect_out "HUMAN REVIEW REQUIRED: .uncle/workflow/IMPLEMENTATION_REVIEW.md"
expect_out "Green check: all verification commands passed."
expect_state "WAIT_IMPLEMENT_APPROVAL"
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "echo goodbye"
expect_in_file ".uncle/workflow/IMPLEMENTATION_REVIEW.md" "Built app/main.sh."

# No baseline exists in a new application, so any failing command is a failure
# of the build, and approving it is an override.
new_stagegate_case sg-failing-check-forces-override
stagegate_agent
set_state IMPLEMENT
run_stagegate_stdin "$(gate_input '')" FAKE_IMPL="printf 'exit 1\n' > app/test.sh"
expect_status 0
expect_out "GREEN CHECK FAILED: 1 command(s)"
expect_out "Ready to override"
expect_state "WAIT_IMPLEMENT_APPROVAL"

# A plan with no command block stops before implementation.
new_stagegate_case sg-plan-without-commands
stagegate_agent
printf '# Updated Project Plan\n\nNo commands.\n' > "$REPO/UPDATED_PROJECT_PLAN.md"
hash_file "$REPO/UPDATED_PROJECT_PLAN.md" \
    > "$REPO/.uncle/workflow/approvals/UPDATED_PROJECT_PLAN.sha256"
set_state IMPLEMENT
run_stagegate FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh"
expect_status 1
expect_out "No Verification commands"
expect_state PREFLIGHT
expect_no_file ".uncle/workflow/implemented"

# Approving carries the run through the remaining stages to COMPLETE.
new_stagegate_case sg-approval-advances-to-complete
stagegate_agent
set_state IMPLEMENT
run_stagegate_stdin "$(gate_input '' y)" \
    FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh"
expect_status 0
expect_out "Recorded approval for .uncle/workflow/IMPLEMENTATION_REVIEW.md"
expect_out "Audit verdict: READY"
expect_out "Workflow complete."
expect_state "COMPLETE"

# The new-application pipeline did not classify its audit verdict at all. A
# NOT READY audit now stops the run instead of completing it.
new_stagegate_case sg-not-ready-stops-at-gate
stagegate_agent
set_state IMPLEMENT
run_stagegate_stdin "$(gate_input '' y)" \
    FAKE_AUDIT="NOT READY" \
    FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh"
expect_status 1
expect_out "Audit verdict: NOT_READY"
expect_out "No decision received; audit remains pending."
expect_not_out "Workflow complete."
expect_state "WAIT_AUDIT_OVERRIDE"

# Unavailable prerequisites stop before source changes, then resume in place.
new_stagegate_case sg-preflight-blocked
stagegate_agent
set_state IMPLEMENT
run_stagegate FAKE_PREFLIGHT=BLOCKED
expect_status 1
expect_state PREFLIGHT
expect_no_file .uncle/workflow/implemented
run_stagegate
expect_status 0
expect_state WAIT_IMPLEMENT_APPROVAL
expect_file .uncle/workflow/implemented

# Missing browser/reviewer access cannot be replaced by a passing narrative.
for result in BLOCKED 'NOT RUN'; do
    new_stagegate_case "sg-verification-$result"
    stagegate_agent
    set_state IMPLEMENT
    run_stagegate WORKFLOW_DIFF_GATE=0 FAKE_VERIFICATION="$result"
    expect_status 1
    expect_state VALIDATE_CHECKLIST
    expect_no_file FINAL_AUDIT.md
    expect_no_file .uncle/workflow/repaired
done

# A malformed review cannot pass or trigger unbounded implementation work.
new_stagegate_case sg-test-review-malformed
stagegate_agent
set_state IMPLEMENT
run_stagegate WORKFLOW_DIFF_GATE=0 FAKE_TEST_REVIEW=MALFORMED
expect_status 1
expect_state TEST_REVIEW
expect_no_file FINAL_AUDIT.md
expect_no_file .uncle/workflow/repaired

# Repair goes back through the human diff gate, preserving the original file
# inventory. Declining that gate must prevent acceptance execution and audit.
new_stagegate_case sg-test-failure-repairs-and-regates
stagegate_agent
set_state IMPLEMENT
run_stagegate_stdin "$(gate_input '' y)" FAKE_TEST_REVIEW=FAIL_ONCE \
    FAKE_IMPL="printf 'new source\n' > app/new.sh" \
    FAKE_REPAIR="printf '#!/bin/sh\nsh app/main.sh | grep -qx hello\n' > app/test.sh"
expect_status 0
expect_state WAIT_IMPLEMENT_APPROVAL
expect_file .uncle/workflow/repaired
expect_in_file .uncle/workflow/IMPLEMENTATION_REVIEW.md 'app/new.sh'
expect_in_file .uncle/workflow/TEST_CHANGES.diff '-sh app/main.sh | grep -q . || exit 1'
expect_in_file .uncle/workflow/IMPLEMENTATION_REVIEW.md '+sh app/main.sh | grep -qx hello'
expect_no_file VERIFICATION_REPORT.md
expect_no_file FINAL_AUDIT.md
run_stagegate_stdin "$(gate_input '' y)" FAKE_TEST_REVIEW=FAIL_ONCE
expect_status 0
expect_state COMPLETE
expect_in_file .uncle/workflow/repair-count '1'
expect_in_file .uncle/workflow/received-test-review-prompt.md 'Driver-supplied test review evidence'
expect_in_file .uncle/workflow/received-test-review-prompt.md 'All verification commands passed.'
expect_in_file .uncle/workflow/received-test-review-prompt.md "$REPO/.uncle/workflow/TEST_CHANGES.diff"

# A failed acceptance check repairs, reruns driver commands, repeats review,
# and reaches audit only after a fresh successful verification.
new_stagegate_case sg-verification-repairs-and-retests
stagegate_agent
set_state IMPLEMENT
run_stagegate WORKFLOW_DIFF_GATE=0 FAKE_VERIFICATION=FAIL_ONCE
expect_status 0
expect_state COMPLETE
expect_in_file .uncle/workflow/repair-source VERIFICATION_REPORT.md
expect_in_file .uncle/workflow/green-check.tsv PASS
COUNT=$((COUNT + 1))
if [[ "$(grep -c '^TEST_REVIEW.md$' "$REPO/.uncle/workflow/reviewer-calls")" != 2 ]]; then
    fail 'repair did not repeat independent test review'
fi

# A persistent defect is bounded across restarts, not just within one process.
new_stagegate_case sg-repair-limit
stagegate_agent
set_state IMPLEMENT
run_stagegate WORKFLOW_DIFF_GATE=0 FAKE_TEST_REVIEW=FAIL WORKFLOW_MAX_REPAIRS=1
expect_status 1
expect_state REPAIR
expect_in_file .uncle/workflow/repair-count '1'
expect_no_file FINAL_AUDIT.md
run_stagegate WORKFLOW_DIFF_GATE=0 FAKE_TEST_REVIEW=FAIL WORKFLOW_MAX_REPAIRS=1
expect_status 1
expect_state REPAIR
expect_in_file .uncle/workflow/repair-count '1'
expect_out 'Repair limit (1) reached'

# A reviewer cannot overrule the driver failure by returning PASS.
new_stagegate_case sg-review-cannot-bless-failed-command
stagegate_agent
set_state IMPLEMENT
run_stagegate_stdin "$(gate_input '' y)" FAKE_IMPL="printf 'exit 1\n' > app/test.sh" \
    WORKFLOW_MAX_REPAIRS=0
expect_status 1
expect_state REPAIR
expect_in_file .uncle/workflow/repair-source green-check.md
expect_no_file FINAL_AUDIT.md

new_stagegate_case sg-missing-driver-results-block
stagegate_agent
set_state IMPLEMENT
run_stagegate WORKFLOW_DIFF_GATE=0 WORKFLOW_GREEN_CHECK=0
expect_status 1
expect_state TEST_REVIEW
expect_no_file FINAL_AUDIT.md

# Legacy/manual resumes cannot take a pre-existing ready audit past missing
# acceptance evidence. Validation pauses without rerunning the reviewer.
new_stagegate_case sg-old-final-audit-resume
stagegate_agent
printf 'READY\n' > "$REPO/FINAL_AUDIT.md"
printf 'app/test.sh\n' > "$REPO/.uncle/workflow/verification.paths"
printf '%s\tapp/test.sh\n' "$(hash_file "$REPO/app/test.sh")" > "$REPO/.uncle/workflow/verification.manifest"
set_state FINAL_AUDIT
run_stagegate WORKFLOW_DIFF_GATE=0 FAKE_TEST_REVIEW=MALFORMED
expect_status 1
expect_state FINAL_AUDIT
expect_not_out 'Workflow complete.'

# Even a reported PASS is invalid when the verifier weakens a protected test.
new_stagegate_case sg-verifier-rewrites-test
stagegate_agent
set_state IMPLEMENT
run_stagegate WORKFLOW_DIFF_GATE=0 FAKE_VERIFY_EDIT="printf 'exit 0\n' > app/test.sh"
expect_status 1
expect_state REPAIR
expect_no_file FINAL_AUDIT.md
expect_in_file .uncle/workflow/VERIFICATION_INTEGRITY.md app/test.sh

# A test command that updates its own expected result cannot report green.
new_stagegate_case sg-command-rewrites-test
stagegate_agent
# The second command must never run against the rewritten suite.
sed '/^bash app\/test.sh$/a\
printf ran > .uncle/workflow/second-command
' "$REPO/UPDATED_PROJECT_PLAN.md" > "$CASE/plan.md"
cp "$CASE/plan.md" "$REPO/UPDATED_PROJECT_PLAN.md"
hash_file "$REPO/UPDATED_PROJECT_PLAN.md" > "$REPO/.uncle/workflow/approvals/UPDATED_PROJECT_PLAN.sha256"
set_state IMPLEMENT
run_stagegate FAKE_IMPL="printf 'echo exit 0 > app/test.sh\n' > app/test.sh"
expect_status 1
expect_state REPAIR
expect_no_file FINAL_AUDIT.md
expect_no_file .uncle/workflow/approvals/IMPLEMENTATION_REVIEW.sha256
expect_no_file .uncle/workflow/second-command
expect_in_file .uncle/workflow/VERIFICATION_INTEGRITY.md app/test.sh

# The real driver executes approved groups concurrently and still gates the
# complete results; the two checks rendezvous, so sequential execution fails.
new_stagegate_case sg-approved-parallel-checks
stagegate_agent
cat > "$REPO/UPDATED_PROJECT_PLAN.md" <<'EOF'
## Verification commands
```
bash app/concurrent.sh 1 2
bash app/concurrent.sh 2 1
test -f .uncle/workflow/done1 && test -f .uncle/workflow/done2
```
## Protected verification paths
```
app
```
## Parallel verification groups
```
1 2
```
EOF
cat > "$REPO/app/concurrent.sh" <<'EOF'
touch ".uncle/workflow/ready$1"
for n in {1..50}; do
    if test -f ".uncle/workflow/ready$2"; then
        touch ".uncle/workflow/done$1"
        exit 0
    fi
    sleep .1
done
exit 7
EOF
hash_file "$REPO/UPDATED_PROJECT_PLAN.md" > "$REPO/.uncle/workflow/approvals/UPDATED_PROJECT_PLAN.sha256"
set_state IMPLEMENT
run_stagegate WORKFLOW_DIFF_GATE=0
expect_status 0
expect_state COMPLETE
expect_in_file .uncle/workflow/green-check.tsv PASS
COUNT=$((COUNT+1))
if [[ "$(find "$REPO/.uncle/workflow/metrics" -name '*.json' -exec cat {} + | jq -s '[.[]|select(.kind=="check")]|length')" != 6 ]]; then
    fail 'driver did not record each check at implementation and checklist execution'
fi

new_stagegate_case sg-invalid-parallel-plan
stagegate_agent
printf '\n## Parallel verification groups\n```\n1 3\n```\n' >> "$REPO/UPDATED_PROJECT_PLAN.md"
hash_file "$REPO/UPDATED_PROJECT_PLAN.md" > "$REPO/.uncle/workflow/approvals/UPDATED_PROJECT_PLAN.sha256"
set_state IMPLEMENT
run_stagegate
expect_status 1
expect_state PREFLIGHT
expect_out 'Invalid Parallel verification groups'
expect_out 'at least two consecutive numbers per line'
expect_no_file .uncle/workflow/implemented


# Newly capped outputs are reported and preserved, and both drivers keep
# building: the budget is advisory. FINAL_AUDIT additionally uses its two
# compaction attempts and continues with the preserved review. The blocking
# form is covered by the enforced review-cache cases below and the budget
# unit tests.
for artifact in IMPLEMENTATION_NOTES AUTOMATED_TEST_REPORT VERIFICATION_REPORT DEFECTS FINAL_AUDIT; do
    new_stagegate_case "sg-budget-$artifact"
    stagegate_agent
    set_state IMPLEMENT
    run_stagegate WORKFLOW_DIFF_GATE=0 "WORKFLOW_DOC_MAX_BYTES_$artifact=1"
    expect_status 0
    expect_out "Document budget exceeded: $artifact.md"
    expect_out 'budget is advisory'
    expect_file "$artifact.md"
    expect_out "Workflow complete."
    expect_state COMPLETE
    if [[ "$artifact" == FINAL_AUDIT ]]; then
        expect_no_file '.uncle/workflow/logs/final-audit.compact-3.log'
        COUNT=$((COUNT + 1))
        [[ $(grep -c '/candidate.md$' "$REPO/.uncle/workflow/reviewer-calls") == 2 ]] || fail 'expected exactly two final audit compaction calls'
    fi
done

for artifact in IMPLEMENTATION_NOTES CHANGE_TEST_REPORT VERIFICATION_REPORT; do
    new_case "change-budget-$artifact"
    green_baseline 0 'bash app/test.sh'
    set_state IMPLEMENT
    run_driver WORKFLOW_DIFF_GATE=0 "WORKFLOW_DOC_MAX_BYTES_$artifact=1"
    expect_status 0
    expect_out "Document budget exceeded: $artifact.md"
    expect_out 'budget is advisory'
    expect_file "$artifact.md"
    expect_out "Change workflow complete."
    expect_state COMPLETE
done

new_case change-budget-background-checklist
green_baseline 0 'bash app/test.sh'
printf 'write a base checklist\n' > "$REPO/prompts/change/manual-checklist-base.md"
set_state IMPLEMENT
run_driver FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh" WORKFLOW_PARALLEL_CHECKLIST=1 WORKFLOW_DOC_MAX_BYTES_MANUAL_CHECKLIST_BASE=1
expect_status 0
expect_out 'still exceeds the budget after 2 attempts; continuing with the preserved original'
expect_file '.uncle/workflow/MANUAL_CHECKLIST.base.md'
expect_state WAIT_IMPLEMENT_APPROVAL
expect_no_file '.uncle/workflow/logs/manual-checklist-base.compact-3.log'
COUNT=$((COUNT + 1))
[[ $(grep -c '/candidate.md$' "$REPO/.uncle/workflow/reviewer-calls") == 2 ]] || fail 'expected exactly two background compaction calls'
printf 'MC-1 Check the greeting.\n\nREADY\n' > "$CASE/expected.md"
COUNT=$((COUNT + 1))
cmp -s "$CASE/expected.md" "$REPO/.uncle/workflow/MANUAL_CHECKLIST.base.md" || fail 'background exhaustion changed original bytes'

new_case change-budget-step-handoff
green_baseline 0 'bash app/test.sh'
printf '\n## 20. Implementation sequence\n\n1. First step.\n2. Second step.\n' >> "$REPO/CHANGE_PLAN.md"
hash_file "$REPO/CHANGE_PLAN.md" > "$REPO/.uncle/workflow/approvals/CHANGE_PLAN.sha256"
set_state IMPLEMENT
run_driver WORKFLOW_STEPWISE_IMPLEMENT=1 WORKFLOW_DOC_MAX_BYTES_IMPLEMENTATION_NOTES=1
expect_status 0
expect_out 'Document budget exceeded: IMPLEMENTATION_NOTES.md'
expect_state WAIT_IMPLEMENT_APPROVAL
expect_no_file '.uncle/workflow/implement-step-done'
expect_in_file '.uncle/workflow/logs/implementation-step-1.gated-prompt.md' 'Compact output budgets'

# A successful compaction reuses the generated review and permits advancement.
new_stagegate_case sg-compact-final-audit
stagegate_agent
set_state IMPLEMENT
run_stagegate WORKFLOW_DIFF_GATE=0 FAKE_COMPACT_REVIEW=1 WORKFLOW_DOC_MAX_BYTES_FINAL_AUDIT=50
expect_status 0
expect_out 'Compaction accepted:'
expect_state COMPLETE
expect_file FINAL_AUDIT.md
COUNT=$((COUNT + 1))
[[ -e "$REPO/.uncle/workflow/logs/final-audit.compact-1.log" ]] || fail 'compaction log missing'

new_case change-compact-background-checklist
green_baseline 0 'bash app/test.sh'
printf 'write a base checklist\n' > "$REPO/prompts/change/manual-checklist-base.md"
set_state IMPLEMENT
run_driver FAKE_IMPL="printf '#!/bin/sh\necho goodbye\n' > app/main.sh" WORKFLOW_PARALLEL_CHECKLIST=1 FAKE_COMPACT_REVIEW=1 WORKFLOW_DOC_MAX_BYTES_MANUAL_CHECKLIST_BASE=50
expect_status 0
expect_out 'Compaction accepted:'
expect_state WAIT_IMPLEMENT_APPROVAL
expect_file '.uncle/workflow/MANUAL_CHECKLIST.base.md'

# Budget failures reuse the finished review, not a new full reviewer run.
# The pause being tested here is the enforced path; by default an overrun is
# advisory and the run would simply continue.
new_stagegate_case sg-review-cache
printf 'requirements\n' > "$REPO/REQUIREMENTS.md"
printf 'plan\n' > "$REPO/PROJECT_PLAN.md"
printf 'review plan\n' > "$REPO/prompts/adversarial-review.md"
hash_file "$REPO/PROJECT_PLAN.md" > "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256"
set_state ADVERSARIAL_REVIEW
for attempt in 1 2; do
    run_stagegate WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_REVIEW_COMPACT=0 WORKFLOW_DOC_MAX_BYTES_ADVERSARIAL_REVIEW=1
    expect_status 42
    expect_state ADVERSARIAL_REVIEW
    COUNT=$((COUNT + 1))
    [[ $(grep -c '^ADVERSARIAL_REVIEW.md$' "$REPO/.uncle/workflow/reviewer-calls") == 1 ]] || fail 'full review repeated'
done
expect_out 'Reusing completed plan review'
# Raising only the budget adopts the preserved review without another call.
run_stagegate WORKFLOW_DOC_MAX_BYTES_ADVERSARIAL_REVIEW=100
expect_status 0
expect_state WAIT_REVIEW_ACKNOWLEDGEMENT
COUNT=$((COUNT + 1))
[[ $(grep -c '^ADVERSARIAL_REVIEW.md$' "$REPO/.uncle/workflow/reviewer-calls") == 1 ]] || fail 'budget adjustment reran reviewer'
# Real input changes force a new review.
printf 'changed requirements\n' >> "$REPO/REQUIREMENTS.md"
set_state ADVERSARIAL_REVIEW
run_stagegate WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_REVIEW_COMPACT=0 WORKFLOW_DOC_MAX_BYTES_ADVERSARIAL_REVIEW=1
expect_status 42
COUNT=$((COUNT + 1))
[[ $(grep -c '^ADVERSARIAL_REVIEW.md$' "$REPO/.uncle/workflow/reviewer-calls") == 2 ]] || fail 'changed inputs reused stale review'

new_stagegate_case sg-speculative-budget-pause
printf 'requirements\n' > "$REPO/REQUIREMENTS.md"
printf 'plan\n' > "$REPO/PROJECT_PLAN.md"
printf 'review plan\n' > "$REPO/prompts/adversarial-review.md"
set_state WAIT_PLAN_APPROVAL
run_stagegate_stdin "$(gate_input '' y)" WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_SPECULATE=1 WORKFLOW_REVIEW_COMPACT=0 WORKFLOW_DOC_MAX_BYTES_ADVERSARIAL_REVIEW=1
expect_status 42
expect_state ADVERSARIAL_REVIEW
expect_out 'pausing without another full review'
COUNT=$((COUNT + 1))
[[ $(grep -c '^ADVERSARIAL_REVIEW.md$' "$REPO/.uncle/workflow/reviewer-calls") == 1 ]] || fail 'speculative budget failure repeated review'

new_case change-review-cache
set_state PLAN
for attempt in 1 2; do
    run_driver WORKFLOW_DOC_BUDGET_ENFORCE=1 WORKFLOW_REVIEW_COMPACT=0 WORKFLOW_DOC_MAX_BYTES_ADVERSARIAL_REVIEW=1
    expect_status 42
    expect_state PLAN
    COUNT=$((COUNT + 1))
    [[ $(grep -c '^ADVERSARIAL_REVIEW.md$' "$REPO/.uncle/workflow/reviewer-calls") == 1 ]] || fail 'change workflow repeated review'
done
expect_out 'Reusing completed plan review'

# Explicit source prerequisites stop both drivers before any planning launch.
new_stagegate_case sg-early-source
printf 'Use `resume.pdf` as the authoritative source.\n' > "$REPO/REQUIREMENTS.md"
set_state REQUIREMENTS
run_stagegate
expect_status 42
expect_state REQUIREMENTS
expect_out 'missing or empty source file: resume.pdf'
expect_not_out 'Launching agent'

new_case change-early-source
printf 'Use `data.csv` as the authoritative source.\n' > "$REPO/CHANGE_REQUEST.md"
set_state PLAN
run_driver
expect_status 42
expect_state PLAN
expect_out 'missing or empty source file: data.csv'
expect_not_out 'Launching agent'

if [[ "$FAILED" -ne 0 ]]; then
    echo "gates-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "gates-test.sh: $COUNT checks passed"

# --- `local` inside the top-level state machine ----------------------------
# Each driver's state machine is a `while true; do` loop at column 0, not a
# function, so a `local` declaration inside it is a runtime error -- and
# `bash -n` accepts it, so nothing else in this suite would notice. Anchored on
# column 0 rather than counted braces: awk and jq snippets in these files carry
# braces inside quotes, and counting them misreads the nesting.
for driver in "$ROOT/scripts/stagegate.sh" "$ROOT/scripts/change-workflow.sh"; do
    awk -v file="$driver" '
        /^while true; do$/ { inloop = 1; next }
        /^done$/           { inloop = 0; next }
        inloop && $1 == "local" {
            printf "FAIL: %s:%d declares `local` in the top-level state machine: %s\n", file, NR, $0
            bad = 1
        }
        END { exit bad ? 1 : 0 }
    ' "$driver" || exit 1
done
echo 'gates-test.sh: no `local` in the drivers state machines'

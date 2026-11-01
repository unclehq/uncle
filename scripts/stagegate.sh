#!/usr/bin/env bash
set -euo pipefail

# Two roots, and they are not the same directory for a packaged install.
#
# ROOT is where uncle itself lives: the prompts, the libs, and the agent shims
# it ships. For a Homebrew install that is the read-only Cellar libexec.
#
# PROJECT_ROOT is the project being worked on: .uncle/workflow, the artifacts,
# the diff, the project's own gates. `uncle` exports UNCLE_PROJECT_ROOT (the
# directory it was launched from); a driver run directly falls back to $ROOT,
# which is the checkout it lives in.
# Conflating the two writes a project's state into the install directory and
# reads the wrong .uncle/config.
if [[ -n "${UNCLE_RUNTIME_ROOT:-}" && -d "$UNCLE_RUNTIME_ROOT/scripts" ]]; then
    ROOT="$(cd -L "$UNCLE_RUNTIME_ROOT" && pwd -L)"
else
    ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
PROJECT_ROOT="${UNCLE_PROJECT_ROOT:-$ROOT}"
if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "Project root does not exist: $PROJECT_ROOT" >&2
    exit 1
fi
cd "$PROJECT_ROOT"
PROJECT_ROOT="$PWD"
# Every workflow-generated document lives here, never the project root.
mkdir -p .uncle/docs
. "$ROOT/scripts/lib/generated-input.sh"
# A generated brief is stored in .uncle/docs; a hand-authored root brief keeps
# its long-standing precedence through generated_input_path.
export DOCUMENT_BUDGET_SOURCE="$(generated_input_path REQUIREMENTS.md)"

# Prompt files are named relative to the uncle install, but the cwd is now the
# project. Resolve them the way gates are resolved: the project's own copy
# wins, otherwise the prompt that shipped with uncle. An absolute path or a
# path that exists in the project is returned untouched, which is what keeps
# composed prompts under .uncle/workflow working.
. "$ROOT/scripts/lib/workflow-paths-app.sh"

STAGEGATE_VERSION="0.1.0"

usage() {
    cat <<'EOF'
Usage: stagegate.sh [-h|--help] [--version] [--unattended]

Run the human-gated new-application workflow from REQUIREMENTS.md. The driver
is a resumable state machine; re-run it to continue from the current stage.

--unattended runs with nobody at the terminal: every gate that would wait for
a person is auto-waived and recorded, and the run reports how many judgments
no one made. It never turns a failing check into a passing one -- a failed
verification suite still stops the run, because that waits on a result and not
on a person.

Takes no positional arguments; all configuration is via WORKFLOW_* environment
variables (see scripts/README.md). Approvals are recorded with
./scripts/workflow.sh.
EOF
}

# Unattended is opt-in and never inferred. A run that merely has no terminal
# is a piped run, not a licence to approve on the operator's behalf; the only
# thing that turns the gates off is someone typing the flag.
UNATTENDED=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)    usage; exit 0 ;;
        --version)    printf '%s\n' "$STAGEGATE_VERSION"; exit 0 ;;
        --unattended) UNATTENDED=1; shift ;;
        *)            printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 1 ;;
    esac
done
export UNCLE_UNATTENDED="$UNATTENDED"
# A repair is a new implementation attempt, not a harmless validator retry.
# Verification failures are evidence, not a reason to discard an otherwise
# complete build.  Keep going by default and give the final audit the complete
# record; set this to 0 for the older stop-and-decide behaviour.
WORKFLOW_AUTO_REPAIR="${WORKFLOW_AUTO_REPAIR:-1}"
WORKFLOW_CONTINUE_ON_TEST_FAILURE="${WORKFLOW_CONTINUE_ON_TEST_FAILURE:-1}"
# How many automatic repair passes a failing driver verification gets before the
# run stops insisting on it. This used to be one, so a suite with a dozen failures
# was handed to a single bounded agent run, and whatever that run did not finish
# was carried forward as "nonblocking evidence". Bounded by the repair limit.
#
# An attended run defaults to 0 (stop and let the person decide) because they
# are right there to approve a repair attempt. An unattended run has nobody to
# ask, so a 0 default means the very first ordinary code defect -- a build
# error, a mismatched export, a failing unit test -- ends the run for good
# with no attempt to self-heal at all; every other failure class in this
# driver (audit findings, an unrunnable app) already gets a bounded repair
# attempt before giving up, and this is the one knob that silently stayed at
# "never try" for the mode that most needs it.
if [[ -z "${WORKFLOW_AUTO_REPAIR_ATTEMPTS:-}" ]]; then
    WORKFLOW_AUTO_REPAIR_ATTEMPTS=$([[ "$UNATTENDED" == 1 ]] && echo 2 || echo 0)
fi
case "$WORKFLOW_AUTO_REPAIR_ATTEMPTS" in
    ''|*[!0-9]*) echo "WORKFLOW_AUTO_REPAIR_ATTEMPTS must be an integer from 0 to 100." >&2; exit 1 ;;
esac

# New applications get the same bounded source repair opportunity as other
# failed verification. Explicit WORKFLOW_REPAIR=0 remains an opt-out; exhausted
# runtime-readiness repairs still stop instead of declaring a broken app ready.
WORKFLOW_REPAIR="${WORKFLOW_REPAIR:-1}"
if [[ "$WORKFLOW_REPAIR" != 1 ]]; then
    WORKFLOW_AUTO_REPAIR=0
    WORKFLOW_AUTO_REPAIR_ATTEMPTS=0
fi

# The shared module-interfaces stage (derive an exact export and UI-name contract before the isolated workers start) is
# off for a new application build. It was added days ago, nothing shows it helped, it runs serially on the critical path
# (9 to 26 s), and it can fail: one unrecognised kind in its UI contract once discarded the whole thing. The change-request
# driver keeps it. WORKFLOW_MODULE_INTERFACES=1 turns it back on here.
WORKFLOW_MODULE_INTERFACES="${WORKFLOW_MODULE_INTERFACES:-0}"

# Serialize both workflow families before mutable initialization.
if [[ "${UNCLE_DRIVER_SUPERVISED:-}" != 1 ]] || ! python3 "$ROOT/scripts/lib/plan-executability.py" lock-child "$$" "$PPID" 2>/dev/null; then
    driver_args=(bash "${BASH_SOURCE[0]}")
    [[ "$UNATTENDED" != 1 ]] || driver_args+=(--unattended)
    exec python3 "$ROOT/scripts/lib/plan-executability.py" lock-run "${driver_args[@]}"
fi
python3 "$ROOT/scripts/lib/workflow_family.py" app
unset UNCLE_NEW_WORKFLOW

# Family-conditional document names for states shared with change-workflow.sh
# (IMPLEMENT, WAIT_IMPLEMENT_APPROVAL, MANUAL_CHECKLIST, EXECUTE_CHECKLIST,
# VALIDATE_CHECKLIST, FINAL_AUDIT, WAIT_AUDIT_OVERRIDE). This script is always
# the app family; change-workflow.sh sets WORKFLOW_FAMILY=change and overrides
# these before sourcing any shared stage function. Defaults here MUST stay
# byte-identical to the historical app-family hardcoded paths -- see
# scripts/tests/stagegate-family-doc-defaults-test.sh.
WORKFLOW_FAMILY="${WORKFLOW_FAMILY:-app}"
if [[ "$WORKFLOW_FAMILY" == "change" ]]; then
    PLAN_DOC=".uncle/docs/CHANGE_PLAN.md"
    PLAN_DOC_NAME="CHANGE_PLAN"
    TEST_REPORT_DOC=".uncle/docs/CHANGE_TEST_REPORT.md"
else
    PLAN_DOC=".uncle/docs/UPDATED_PROJECT_PLAN.md"
    PLAN_DOC_NAME="UPDATED_PROJECT_PLAN"
    TEST_REPORT_DOC=".uncle/docs/AUTOMATED_TEST_REPORT.md"
fi
# NOTE: FINAL_AUDIT's TEST_REVIEW.md ingestion (app family only) is not a
# simple path swap -- change-workflow.sh has no TEST_REVIEW stage and reads
# ADVERSARIAL_REVIEW.md through separate, differently-shaped control flow
# (continue_nonblocking_test_review has no change-family analogue). Left
# hardcoded here; phase (c) decides whether it becomes a branch or stays
# wrapper logic around the shared FINAL_AUDIT function.
. "$ROOT/scripts/lib/project-git.sh"
. "$ROOT/scripts/lib/preview-build.sh"
. "$ROOT/scripts/lib/install-warm.sh"
. "$ROOT/scripts/lib/background-verify.sh"
. "$ROOT/scripts/lib/checklist-lanes.sh"
. "$ROOT/scripts/lib/checklist-stage.sh"
uncle_ensure_project_git || exit 1
. "$ROOT/scripts/lib/plan-recovery.sh"
. "$ROOT/scripts/lib/plan-scope.sh"
. "$ROOT/scripts/lib/parallel-implement.sh"
. "$ROOT/scripts/lib/module-interfaces-stage.sh"
. "$ROOT/scripts/lib/change-class-stage.sh"
. "$ROOT/scripts/lib/review-schema.sh"
. "$ROOT/scripts/lib/state.sh"

# Absolute, not "$PROJECT_ROOT"-relative: this value is embedded verbatim
# into agent- and reviewer-facing prompts ("write your canonical JSON to
# `%s`"). An agent's own shell keeps cwd across its tool calls for the whole
# session, so a stage that `cd`s into a subdirectory (e.g. to build or test)
# leaves later writes of a relative path nested under that subdirectory
# instead of at the project root, and the driver then reports the delivery
# as missing.
STATE_DIR="$PROJECT_ROOT/.uncle/workflow"
APPROVAL_DIR="$STATE_DIR/approvals"
LOG_DIR="$STATE_DIR/logs"
SPEC_DIR="$STATE_DIR/speculative"
STATE_FILE="$STATE_DIR/state"
BRIEF_SNAPSHOT="$STATE_DIR/REQUIREMENTS.md.source"
export UNCLE_RUNNER_POOL_OWNER_PID="${UNCLE_RUNNER_POOL_OWNER_PID:-$$}"

# Post-implementation gate: the generated document the operator reads, and the
# diff it is built from.
REVIEW_FILE="$STATE_DIR/IMPLEMENTATION_REVIEW.md"
DIFF_FILE="$STATE_DIR/change.diff"

# Green check. There is no baseline in a new application: nothing was passing
# before, so every failing command is this build's problem.
GREEN_CMDS="$STATE_DIR/green-check.commands"
GREEN_CUR="$STATE_DIR/green-check.current.tsv"
GREEN_CLASS="$STATE_DIR/green-check.tsv"
GREEN_MD="$STATE_DIR/green-check.md"

# The audit verdict, and the records of a human choosing to finish over a
# failing check.
VERDICT_FILE="$STATE_DIR/audit-verdict"
GREEN_OVERRIDE_FILE="$STATE_DIR/green-check-override"
AUDIT_OVERRIDE_FILE="$STATE_DIR/audit-override"
# Every gate an unattended run passed through without a person. This is the
# whole cost of the flag in one file, and COMPLETE reads it back.
UNATTENDED_FILE="$STATE_DIR/unattended-gates"

# Untracked paths that existed before implementation started. Read by
# change_diff_files, so the review diff shows what this build produced rather
# than whatever was already sitting in the directory.
UNTRACKED_BASELINE="$STATE_DIR/untracked-before.txt"
WORKFLOW_UNTRACKED_BASELINE="$UNTRACKED_BASELINE"

mkdir -p "$APPROVAL_DIR" "$LOG_DIR" "$SPEC_DIR"

# The generated brief is an input, not stage output. A preview or an agent may
# create and remove its own files, but it must never be able to make the
# approved source brief disappear before the planner reads it. Preserve the
# first readable copy and restore only when the live input is missing; a human
# edit remains authoritative and is never overwritten.
preserve_requirements_source() {
    if [[ -s "$DOCUMENT_BUDGET_SOURCE" && ! -s "$BRIEF_SNAPSHOT" ]]; then
        cp "$DOCUMENT_BUDGET_SOURCE" "$BRIEF_SNAPSHOT"
    elif [[ ! -s "$DOCUMENT_BUDGET_SOURCE" && -s "$BRIEF_SNAPSHOT" ]]; then
        mkdir -p "$(dirname "$DOCUMENT_BUDGET_SOURCE")"
        cp "$BRIEF_SNAPSHOT" "$DOCUMENT_BUDGET_SOURCE"
        echo "Restored missing requirements source: $DOCUMENT_BUDGET_SOURCE"
    fi
}
preserve_requirements_source

# Run the stage that follows a human gate in the background while the human is
# still reading. Set to 0 to make every stage strictly serial again.
#
# Token cost: a speculative stage that gets discarded was paid for and thrown
# away. Discards only happen when the reviewer edits the gated file or declines
# the gate, so the expected waste is low — but if tokens matter more than wall
# clock, or you habitually edit documents during review, set this to 0.
WORKFLOW_SPECULATE="${WORKFLOW_SPECULATE:-1}"
# Preflight probes the environment. Blocking on it cost 147s and $1.32 on a
# calculator build before a line of code was written. It now runs beside
# implementation and reports through the supervisor instead of gating.
# WORKFLOW_PREFLIGHT_BLOCKING=1 restores the gate.
PREFLIGHT_BLOCKING="${WORKFLOW_PREFLIGHT_BLOCKING:-0}"
PREFLIGHT_BG_PID=""
# Requirements and the plan are distinct canonical artifacts. A runner has a
# single file-backed delivery slot, so merging them lets it successfully write
# one packet while silently omitting the other (calculator4 hit exactly that
# failure). Keep the stages separate by default; the old optimization is now
# opt-in only for a runner explicitly known to publish both artifacts.
MERGE_REQUIREMENTS_PLAN="${WORKFLOW_MERGE_REQUIREMENTS_PLAN:-0}"

# Agent/reviewer CLI commands. Defaults are `claude` and `codex`. Swap either
# for a compatible CLI or a wrapper script. The agent CLI must accept the same
# flags as `claude -p` (model, effort, max-turns, output-format stream-json,
# allowedTools, stdin prompt). The reviewer CLI must accept the same flags as
# `codex exec` (ephemeral, sandbox read-only, model, output-last-message).
AGENT_CMD="${WORKFLOW_AGENT_CMD:-$ROOT/scripts/agent-kimi.sh}"
REVIEWER_CMD="${WORKFLOW_REVIEWER_CMD:-codex}"

# Per-stage model and reasoning effort, keyed by log name. Planning and
# implementation carry the design; requirements extraction and checklist
# execution are closer to transcription, so they do not need the top tier.
# Override any of these from the environment, e.g.
#   WORKFLOW_MODEL_REQUIREMENTS=opus WORKFLOW_EFFORT_REQUIREMENTS=high
DEFAULT_MODEL="claude-sonnet-5"
DEFAULT_EFFORT="low"

# Stop after implementation and show the operator the actual diff, the green
# check, and the agent's own notes, before anything downstream reads them.
#
# Stages 1-4 gate prose. Without this gate, stages 5-8 — implementation,
# checklist, checklist execution, audit — run unattended, and the person who
# approved the plan never sees the code it produced.
#
# Set to 0 only when something else reviews the diff. The driver then refuses
# to continue past a failing green check, because no human gate is left to
# weigh it.
DIFF_GATE="${WORKFLOW_DIFF_GATE:-1}"

# Re-run the plan's own verification commands from the driver after
# implementation. .uncle/docs/AUTOMATED_TEST_REPORT.md is the implementing agent's account
# of checks the implementing agent ran; this runs them with no agent in the
# path. The commands come from .uncle/docs/UPDATED_PROJECT_PLAN.md, which the operator has
# already approved.
#
# Set to 0 to return to trusting the report.
GREEN_CHECK="${WORKFLOW_GREEN_CHECK:-1}"

# Final audit reports residual risk; it does not turn a useful delivered build
# into a stalled workflow merely because every possible concern is not closed.
# Set to 1 only for a release process that explicitly requires a human override
# for a NOT READY verdict.
# `--unattended` automates the build, not the final owner decision.  A final
# NOT_READY verdict is the one point where a user may deliberately accept
# unperformed human work, so it must open the review dialog by default.
AUDIT_GATE="${WORKFLOW_AUDIT_GATE:-1}"

# The .uncle/docs/FINAL_AUDIT.md verdict classifier, the independent verification run, and
# the generated document the post-implementation gate shows. Sourced
# self-relative so the driver still runs from any CWD.
#
# state.sh is here for context_exhausted, which run_codex_review has always
# called and this driver never defined: the recovery hint after a reviewer runs
# out of tokens could not print, because the test for it failed as a missing
# command.
. "$ROOT/scripts/lib/state.sh"
. "$ROOT/scripts/lib/waivers.sh"
. "$ROOT/scripts/lib/audit-verdict.sh"
. "$ROOT/scripts/lib/anchored-repair.sh"
. "$ROOT/scripts/lib/thinking-off.sh"
. "$ROOT/scripts/lib/green-check.sh"
. "$ROOT/scripts/lib/implementation-review.sh"
. "$ROOT/scripts/lib/gates.sh"
. "$ROOT/scripts/lib/stage-config.sh"
. "$ROOT/scripts/lib/model-jobs.sh"
. "$ROOT/scripts/lib/acceptance.sh"
. "$ROOT/scripts/lib/acceptance-gate.sh"
. "$ROOT/scripts/lib/repair-limit.sh"
. "$ROOT/scripts/lib/repair-judge.sh"
. "$ROOT/scripts/lib/checklist-capability.sh"
. "$ROOT/scripts/lib/human-input.sh"
. "$ROOT/scripts/lib/verification-integrity.sh"
. "$ROOT/scripts/lib/performance.sh"

. "$ROOT/scripts/lib/sha256.sh"
. "$ROOT/scripts/lib/triage.sh"
[ -r "$ROOT/scripts/lib/finished-extras.sh" ] && . "$ROOT/scripts/lib/finished-extras.sh" || true
declare -f finished_extras > /dev/null || finished_extras() { :; }

# One EXIT hook for the whole run: cancel speculation, then hand the exit
# status to the triage hook, which writes the failure bundle for anything
# that is not a decline, a cancel, or a stop a person chose. Installed here
# so a failure before any stage starts (lock, origin, prerequisites) is
# bundled too; cancel_speculation is defined further down.
on_exit() {
    local rc=$?
    if declare -f workflow_model_cancel > /dev/null; then workflow_model_cancel; fi
    if declare -f cancel_speculation > /dev/null; then cancel_speculation; fi
    if declare -f manual_checklist_draft_cancel > /dev/null; then manual_checklist_draft_cancel; fi
    if declare -f preview_build_cancel > /dev/null; then preview_build_cancel; fi
    if declare -f install_warm_cancel > /dev/null; then install_warm_cancel; fi
    python3 -B "$ROOT/scripts/lib/app_server.py" stop "$STATE_DIR" > /dev/null 2>&1 || true
    python3 -B "$ROOT/scripts/lib/preview_server.py" stop "$STATE_DIR" > /dev/null 2>&1 || true
    if [[ "$rc" != 0 ]] && declare -f green_background_cancel > /dev/null; then green_background_cancel; fi
    if [[ -n "${PARALLEL_PREWARM_PID:-}" ]] && kill -0 "$PARALLEL_PREWARM_PID" 2>/dev/null; then
        kill "$PARALLEL_PREWARM_PID" 2>/dev/null || true
        wait "$PARALLEL_PREWARM_PID" 2>/dev/null || true
    fi
    # A probe must not outlive the run that started it.
    if [[ -n "${PREFLIGHT_BG_PID:-}" ]] && kill -0 "$PREFLIGHT_BG_PID" 2>/dev/null; then
        kill "$PREFLIGHT_BG_PID" 2>/dev/null || true
        wait "$PREFLIGHT_BG_PID" 2>/dev/null || true
    fi
    if [[ "$rc" != 0 ]]; then finished_extras print --kind new --reason not-applicable --stopped; fi
    triage_on_exit "$rc"
}
trap on_exit EXIT

# A repair always comes back through the independent checks and human diff
# gate. Bound retries across restarts so an unfixable defect cannot spin.
MAX_REPAIRS="${WORKFLOW_MAX_REPAIRS:-4}"
case "$MAX_REPAIRS" in
    ''|*[!0-9]*) echo "WORKFLOW_MAX_REPAIRS must be an integer from 0 to 100." >&2; exit 1 ;;
esac
if [[ ${#MAX_REPAIRS} -gt 3 ]]; then
    echo "WORKFLOW_MAX_REPAIRS must be an integer from 0 to 100." >&2
    exit 1
fi
MAX_REPAIRS=$((10#$MAX_REPAIRS))
if [[ "$MAX_REPAIRS" -gt 100 ]]; then
    echo "WORKFLOW_MAX_REPAIRS must be an integer from 0 to 100." >&2
    exit 1
fi

provided_file() { printf '%s/provided/%s' "$STATE_DIR" "$1"; }

# A prerequisite the operator handed over at the gate.
#
# The report is the agent's and is not edited, so the resolution is recorded
# beside it the way a waiver is -- but it says the opposite thing. A waiver
# says a required check was not performed; this says the input the check asked
# for is now on disk, and names it by digest so a later stage and the audit can
# see exactly what satisfied the row rather than taking the driver's word.
record_provided() {
    local report="$1" id="$2" target="$3" how="$4"
    mkdir -p "$STATE_DIR/provided" || return 1
    {
        printf 'id: %s\n' "$id"
        printf 'report: %s\n' "$report"
        printf 'recorded: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'how: %s\n' "$how"
        printf 'path: %s\n' "$target"
        printf 'sha256: %s\n' "$(hash_file "$target")"
    } > "$(provided_file "$id")" || return 1
}

# An unattended run is still accountable for what it skipped. Each gate it
# passed without a person is appended here, dated, so the summary can say what
# nobody looked at rather than reporting a clean run.
. "$ROOT/scripts/lib/workflow-records.sh"

# An unattended run says so up front and ledgers what enabled it, so a mode
# inherited from a wrapper is visible in the run's own record.
if [[ "$UNATTENDED" == 1 ]]; then
    echo "UNATTENDED RUN: no human prompts; blocking audit findings are skipped and ledgered ($UNATTENDED_FILE)."
    if ! grep -qs $'\tunattended-enabled\t' "$UNATTENDED_FILE" 2>/dev/null; then
        record_unattended_gate unattended-enabled "enabled by the --unattended flag (UNCLE_UNATTENDED=1)"
    fi
fi

# The verdict the build finishes with. A waiver (a person's, or an unattended run's) leaves READY
# in the verdict file and the auditor's own verdict in audit-verdict.original; the run reports
# the effective one and says out loud, on the next line, that findings were waived unreviewed.
completed_verdict() {
    local verdict
    verdict="$(verdict_file_field "$VERDICT_FILE" audit_class 2>/dev/null)"
    printf '%s' "$verdict"
}


# A failing verification command, named by its 1-based position in the approved
# command list, so a waiver has a stable id that is also a safe filename. The
# command text itself is not usable: it contains slashes and spaces, and it is
# the thing most likely to be reworded between runs.
green_failed_ids() {
    local class="$1" commands="$2"
    [[ -s "$class" && -s "$commands" ]] || return 0
    awk -F'\t' '
        NR == FNR { position[$0] = FNR; next }
        $1 == "REGRESSION" && ($2 in position) { printf "green-%s ", position[$2] }
    ' "$commands" "$class"
}



# An attended gate decision the audit should see next to the waivers: a skip
# is not a waiver a person justified id by id, and a decline is not a crash.
# One dated line each, so the summary can say what the operator chose.
record_gate_decision() {
    local what="$1" detail="$2"
    mkdir -p "$STATE_DIR" 2>/dev/null || true
    printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$what" "$detail" \
        >> "$STATE_DIR/gate-decisions" 2>/dev/null || true
}

# Preserve the distinction between a passing build and one that deliberately
# continued despite failed verification.  This is driver-owned evidence, not a
# waiver and never rewrites a test or acceptance result to PASS.  Final audit
# prompts already receive the workflow directory, so it can assess this ledger
# alongside green-check.tsv and the canonical report JSON.
record_nonblocking_failure() {
    local source="$1" detail="$2"
    mkdir -p "$STATE_DIR"
    printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$source" "$detail" \
        >> "$STATE_DIR/nonblocking-test-failures.tsv"
}

# A nonblocking disposition is durable workflow state.  Later gates must not
# re-open the same canonical report and send it back through REPAIR forever.
has_nonblocking_failure() {
    local source="$1" ledger="$STATE_DIR/nonblocking-test-failures.tsv"
    [[ -s "$ledger" ]] || return 1
    awk -F'\t' -v source="$source" '$2 == source { found=1 } END { exit !found }' "$ledger"
}

# A report-level test-review finding is evidence for the final audit, not
# automatically proof that source repair will help.  When the driver has
# already run every approved command successfully, continue in the same
# explicit, auditable mode used for failed green-check commands.  This avoids
# a coverage/packet-format finding bouncing FINAL_AUDIT back to REPAIR forever.
# Automatic repair is on, at least one pass ran, and every pass allowed has been used.
repair_exhausted() {
    local used
    used="$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 0)"
    [[ "${WORKFLOW_REPAIR:-1}" == 1 && "$WORKFLOW_AUTO_REPAIR_ATTEMPTS" -ge 1 && "$used" -ge "$WORKFLOW_AUTO_REPAIR_ATTEMPTS" ]]
}

# Where a failure that is known to remain goes after test review. Once the repair passes are used up, nothing more can fix it,
# and the checklists would only be run against a build that is known not to pass: it goes straight to the final audit, which
# reads the failure. While passes remain, or when repair was never available, the checklists still run first. This is only for a
# failure that is actually present; a clean test review after successful repairs still goes through the checklists.
#
# Severity gates the skip. Only a failure that leaves nothing to look at (the application cannot build or start, or the test runner
# executed no tests: green_application_not_runnable) goes straight to the audit. Anything else, a failing assertion or a wrong
# oracle included, still gets the checklists, which are how the application is actually observed in a browser; the audit then reads
# their results beside the failure.
test_review_next_stage() {
    # Once the checklist has run (VALIDATE_CHECKLIST marks it) the checklists are not run again: a repair that cannot proceed goes to
    # the audit. Without this, REPAIR -> MANUAL_CHECKLIST -> VALIDATE_CHECKLIST -> REPAIR cycled with no agent call and no limit.
    if [[ -e "$STATE_DIR/checklist-ran" ]]; then
        printf FINAL_AUDIT
    elif repair_exhausted && [[ "${WORKFLOW_POSTFLIGHT_GREEN_CHECK:-1}" == 1 ]] \
       && { ! declare -f green_application_not_runnable > /dev/null || green_application_not_runnable; }; then
        printf FINAL_AUDIT
    else
        printf MANUAL_CHECKLIST
    fi
}

continue_nonblocking_test_review() {
    local next="$1" result
    [[ "$WORKFLOW_CONTINUE_ON_TEST_FAILURE" == "1" ]] || return 1
    [[ "$GREEN_CHECK" == 1 && -s "$GREEN_CLASS" ]] || return 1
    # A failing driver check blocks this only while repair could still help.
    # Once no automatic repair remains, REPAIR would send the run back through
    # the checklist and return here, so the failure goes to the audit instead.
    if [[ "$(green_regressions "$GREEN_CLASS")" -ne 0 ]]; then
        [[ "$(green_failure_route "$WORKFLOW_CONTINUE_ON_TEST_FAILURE" \
              "$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 0)" \
              "$WORKFLOW_AUTO_REPAIR_ATTEMPTS")" == continue ]] || return 1
    fi
    result="$(python3 -B "$ROOT/scripts/lib/acceptance_json.py" \
        "$STATE_DIR/documents/TEST_REVIEW.json" COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS)"
    [[ "$result" != PASS ]] || return 1
    # A test review that FAILED rows (assertions too weak to reject an injected
    # defect, a missing test) names something repair can fix, and carrying it
    # forward as "nonblocking evidence" meant it never was. While automatic
    # attempts remain, hand it to repair first; rows that are merely NOT RUN or
    # BLOCKED are evidence gaps no code change closes, and still pass through.
    if [[ "$result" == REPAIR && "$next" == MANUAL_CHECKLIST && "${WORKFLOW_AUTO_REPAIR:-1}" == 1 ]] \
        && [[ "$(green_failure_route "$WORKFLOW_CONTINUE_ON_TEST_FAILURE" \
               "$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 0)" "$WORKFLOW_AUTO_REPAIR_ATTEMPTS")" == repair ]]; then
        echo "Test review found failing rows; sending them to repair (automatic attempt $(($(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 0) + 1)) of $WORKFLOW_AUTO_REPAIR_ATTEMPTS)."
        return 1
    fi
    echo 'Test-review findings are recorded as nonblocking evidence after a passing driver green check.'
    record_nonblocking_failure TEST_REVIEW.json "canonical test-review acceptance $result after passing driver green check"
    if [[ "$next" == MANUAL_CHECKLIST ]]; then next="$(test_review_next_stage)"; fi
    set_state "$next"
    return 0
}

# The blocker rows with their evidence, at the gate. The report already says
# why each prerequisite is blocked and what would settle it; making the
# operator open the file to learn that is how review gets skipped.
preflight_blocked_review() {
    local report="$1" id evidence
    shift
    for id in "$@"; do
        echo
        echo "$id [$(acceptance_row_status "$report" "$id")]"
        evidence="$(acceptance_row_evidence "$report" "$id")"
        [[ -z "$evidence" ]] || echo "  $evidence"
    done
    echo
}

# One question, four answers. Return codes, not stdout: the TUI dialog
# protocol owns stdout, and a captured answer string would swallow the prompt.
# A closed stdin is not a decision: the run stays pending rather than
# recording a decline nobody chose.
preflight_blocked_menu() {
    local choice
    while :; do
        gate_prompt "Blocked prerequisites: [r]eview, [p]rovide, [s]kip, [d]ecline? "
        if ! { if declare -f gate_read > /dev/null; then gate_read choice; else IFS= read -r choice; fi; }; then
            echo "No answer at the preflight gate; the run remains pending."
            exit 1
        fi
        case "$choice" in
            r|R) return 10 ;;
            p|P) return 11 ;;
            s|S) return 12 ;;
            d|D|"") return 13 ;;
            *) echo "  answer r, p, s, or d." ;;
        esac
    done
}

# review / provide / skip / decline for blocked prerequisites.
#
# A blocker used to offer two moves -- hand the input over through the provide
# dialog, or sign a waiver for it -- and stopping was the failure case rather
# than a choice. Reviewing first, skipping without a per-id signature, and
# declining cleanly are all legitimate answers, so the gate asks and records
# what was chosen. Skip writes one waiver per outstanding id with a reason
# that says nobody assessed them; decline preserves the state and leaves with
# the rerun instruction. Providing reuses the existing dialog and its
# one-attempt-per-blocker-set guard, then returns to the menu for whatever is
# still outstanding.
preflight_blocked_gate() {
    local report="$1" class="$2"
    shift 2
    local outstanding_ids="$*" menu_choice human_records collected blocked_id outstanding
    while [[ -n "$outstanding_ids" ]]; do
        echo
        echo "Prerequisites $class: see $report."
        echo "Outstanding:"
        # shellcheck disable=SC2086
        printf '  %s\n' $outstanding_ids
        # Menu return codes are choices, not failures under set -e.
        if preflight_blocked_menu; then
            menu_choice=0
        else
            menu_choice=$?
        fi
        case "$menu_choice" in
            10)
                # shellcheck disable=SC2086
                preflight_blocked_review "$report" $outstanding_ids
                ;;
            11)
                # shellcheck disable=SC2086
                if human_input_repeating "$STATE_DIR" $outstanding_ids; then
                    echo "These are the same prerequisites as the last attempt, so what was"
                    echo "provided did not resolve them. Providing again would only repeat;"
                    echo "review the evidence, skip them, or decline and amend the plan."
                else
                    human_records="$(mktemp)" || human_records=""
                    collected=1
                    if [[ -n "$human_records" ]]; then
                        collected=0
                        # shellcheck disable=SC2086
                        collect_human_inputs "$report" "$human_records" $outstanding_ids \
                            || collected=$?
                    fi
                    if [[ "$collected" == 0 ]] && apply_human_inputs "$human_records"; then
                        record_provided_inputs "$human_records" "$report"
                    fi
                    rm -f "$human_records"
                fi
                outstanding=""
                while IFS= read -r blocked_id; do
                    [[ -n "$blocked_id" ]] || continue
                    [[ -s "$(provided_file "$blocked_id")" ]] \
                        || outstanding="$outstanding $blocked_id"
                done <<< "$outstanding_ids"
                outstanding_ids="${outstanding# }"
                if [[ -z "$outstanding_ids" ]]; then
                    human_input_reset "$STATE_DIR"
                    echo "Prerequisites settled at the gate; continuing."
                fi
                ;;
            12)
                # shellcheck disable=SC2086
                if ! write_waivers "$report" \
                    "Operator chose skip at the preflight gate: knowingly left unprovided and unassessed." \
                    $outstanding_ids; then
                    echo "Could not record the skip; the run remains pending."
                    exit 1
                fi
                record_gate_decision skip "$class: $outstanding_ids"
                human_input_reset "$STATE_DIR"
                echo "Skipped $class at the gate; the report keeps the rows blocked."
                return 0
                ;;
            13)
                record_gate_decision decline "$class: $outstanding_ids"
                echo
                echo "Declined at the preflight gate; nothing was provided or signed."
                echo "Amend the plan, or resolve the named action and rerun."
                exit 0
                ;;
        esac
    done
    return 0
}

# What to print when the only thing missing is an action someone can take.
# Implementation needs tools, inputs, and checks that can be performed. It
# does not need a signature: nobody's approval is consumed by writing code, and
# a run that stops here because a reviewer has not signed yet has stopped for
# something the next stage was never going to use. The signature is consumed at
# verification, and the gates there still block on it.
preflight_acceptable() {
    case "$1" in
        PASS|BLOCKED-HUMAN) return 0 ;;
        *) return 1 ;;
    esac
}

# The same question, asked after the gate has done something about it.
#
# A blocker settled at the gate -- the file handed over, or the check waived --
# does not change .uncle/docs/PREFLIGHT_REPORT.md, which is the agent's document and stays
# as written. So the report still says BLOCKED-SETUP, and asking it alone would
# send the run back to re-probe inputs that are already sitting on disk: a full
# agent stage, minutes and tokens, to rediscover what the operator just typed
# in. This reads the report and the gate's own records together.
preflight_settled() {
    local result="$1" ids id
    case "$result" in
        PASS|BLOCKED-HUMAN) return 0 ;;
        BLOCKED-SETUP) ;;
        *) return 1 ;;
    esac
    ids="$(acceptance_blocked_ids .uncle/docs/PREFLIGHT_REPORT.md BLOCKED-SETUP)"
    [[ -n "$ids" ]] || return 1
    while IFS= read -r id; do
        [[ -n "$id" ]] || continue
        [[ -s "$(provided_file "$id")" || -s "$(waive_file "$id")" ]] || return 1
    done <<< "$ids"
    return 0
}

# Turn what the gate collected into records, and say which blockers are still
# outstanding. A target that was named but never landed is not provided: the
# next stage would find nothing there, which is the failure this is meant to
# prevent rather than cause.
#
# The driver checks that the file exists and is not empty. It does not check
# that the contents are right -- only the preflight agent can judge that, and
# not re-running it is the whole point. The digest in each record is what makes
# that trade auditable afterwards.
record_provided_inputs() {
    local records="$1" report="$2" id action target payload
    local -a pairs=()
    [[ -s "$records" ]] || return 0
    while IFS="$(printf '\t')" read -r id action target payload; do
        [[ -n "$id" && -n "$target" ]] || continue
        if [[ -s "$target" ]]; then
            record_provided "$report" "$id" "$target" "$action" || continue
            pairs+=("$id=$target")
            echo "  $id: satisfied by $target"
        else
            echo "  $id: $target was not written; still outstanding" >&2
        fi
    done < "$records"
    [[ "${#pairs[@]}" -gt 0 ]] || return 0
    # Mark the rows in the report itself rather than leaving the driver's
    # records as the only place the resolution exists. A row still reading
    # BLOCKED after its input landed is what sent the run back to re-run the
    # stage; the rewritten evidence says the operator supplied it, so nothing
    # downstream mistakes it for something preflight went and checked.
    if ! python3 "$ROOT/scripts/lib/mark-provided.py" "$report" "${pairs[@]}"; then
        echo "  could not mark $report; the gate records still stand." >&2
    fi
}

# The plan has to carry three machine-read blocks, and the driver used to look
# for them only after the operator had read the plan and approved it -- so a
# missing block spent a human review and then demanded the approval be renewed.
# Checked before the gate now; still checked after, because that is the copy
# the run actually executes.
# "Missing X" is unhelpful when the plan contains something one word away from
# X. Show what headings it does have, so a rename is obvious.
plan_headings() {
    grep -nE '^#+[ \t]' "$1" 2>/dev/null | sed 's/^/    /' | head -30
}

plan_structure_problem() {
    local plan="$1" commands ownership_gaps
    commands="$(mktemp)" || return 0
    if ! verify_commands "$plan" > "$commands" || [[ ! -s "$commands" ]]; then
        rm -f "$commands"
        printf 'no Verification commands block'
        return 0
    fi
    # `.uncle/config` is uncle's own configuration FILE and `.uncle/` is driver state:
    # a plan that runs its tests from `.uncle/config/playwright.config.js` or
    # `.uncle/tests/` names a path that cannot exist, and every stage after it
    # reports a missing config. Project files belong in the project tree.
    if grep -qE '(^|[^[:alnum:]_./-])\.?/?\.uncle/(config|tests)(/|[[:space:]]|$)' "$commands"; then
        rm -f "$commands"
        printf 'verification commands that run files under .uncle/'
        return 0
    fi
    if ! repair_parallel_groups "$plan" "$commands"; then
        rm -f "$commands"
        printf 'invalid Parallel verification groups'
        return 0
    fi
    rm -f "$commands"
    if ! verification_paths "$plan" > /dev/null; then
        printf 'no Protected verification paths block'
        return 0
    fi
    # calculator-local (2026-09-28): package.json was a protected/frozen
    # path the plan named throughout, but no Implementation-order step's
    # Owns: covered it -- only a Reconcile step's `Owns: *`, whose own
    # description ruled out creating new files. Nothing enforced the plan's
    # own promise, and the gap surfaced only much later as an npm ENOENT at
    # green-check time, after a full implementation cycle had already run.
    if [[ -s "${STATE_DIR:-.uncle/workflow}/documents/$(basename "${plan%.md}").json" ]]; then
        ownership_gaps="$(python3 -B "$ROOT/scripts/lib/plan_ownership_gap.py" "$plan" "$PWD" "${STATE_DIR:-.uncle/workflow}" 2>/dev/null)"
        if [[ -n "$ownership_gaps" ]]; then
            printf 'a protected verification path with no owning implementation step'
            return 0
        fi
    fi
    return 1
}

# The text the planner is shown when its plan fails the structural check: what the
# driver rejected and what to change. Appended to the next updated-plan prompt.
plan_structure_feedback() {
    local problem="$1" plan="$2" gaps
    printf '\n\n## Plan structure error (binding)\n\n'
    printf 'The driver rejected the plan you just wrote: it has %s.\n\n' "$problem"
    case "$problem" in
        'a protected verification path with no owning implementation step')
            # The checker exits 1 when it finds gaps -- the case being reported here.
            # Under errexit and pipefail that status ended the driver before the
            # one-retry below could send the plan back (runs 11 and 12).
            gaps="$(python3 -B "$ROOT/scripts/lib/plan_ownership_gap.py" "$plan" "$PWD" "${STATE_DIR:-.uncle/workflow}" 2>/dev/null | sed 's/^/- `/; s/$/`/' || true)"
            printf 'These Protected verification paths do not exist yet and no implementation step names them in its `Owns:`:\n\n%s\n\n' "$gaps"
            printf 'Fix it one of two ways: add each path to the `Owns:` of the step that creates it (a reconcile step'"'"'s `Owns: *` does not count), or, if nothing will create a path, remove it from Protected verification paths. Only list a path as protected when it already exists or a step explicitly owns it. Return only edit ops for these paths and steps; never the complete plan.\n'
            ;;
        'verification commands that run files under .uncle/')
            printf '`.uncle/config` is uncle'"'"'s own configuration file and `.uncle/` is driver state, so nothing can be created under `.uncle/config/` or `.uncle/tests/`. Put the test runner config and the tests in the project tree (for example `playwright.config.js` and `tests/` at the project root), name them in the `Owns:` of the step that creates them, list them under Protected verification paths, and point the Verification commands at those paths. Return only edit ops for these paths and steps; never the complete plan.\n' ;;
        'no Verification commands block')
            printf 'The plan needs `## Verification commands` with one fenced block of shell commands, one per line, and nothing else in it.\n' ;;
        'no Protected verification paths block')
            printf 'The plan needs a heading with the words "protected" and "paths", then one fenced block of repository-relative paths, one per line.\n' ;;
        *)
            printf 'Correct that and return the delivery again in the same shape: edit ops against the current plan, not the whole plan.\n' ;;
    esac
}


verification_integrity_failure() {
    {
        echo '## Verification input changes'
        echo
        echo 'Verification changed protected inputs or could not establish their integrity.'
        echo 'Repair the tests or runner explicitly; do not accept regenerated expectations.'
        echo 'Record each test change and its requirement-based justification in .uncle/docs/IMPLEMENTATION_NOTES.md.'
        echo
        echo '```text'
        cat "$STATE_DIR/verification-integrity.log"
        echo '```'
    } > "$STATE_DIR/VERIFICATION_INTEGRITY.md"
    printf '%s\n' "$STATE_DIR/VERIFICATION_INTEGRITY.md" > "$STATE_DIR/repair-source"
    set_state REPAIR
    echo "Verification inputs changed or are unavailable. See $STATE_DIR/VERIFICATION_INTEGRITY.md."
    exit 1
}

capture_verification_inputs() {
    local snapshot digest file absent_paths scope
    # Preserve the canonical-path parser's actual diagnostic.  REPAIR uses it
    # to distinguish a malformed plan field (return to UPDATED_PLAN) from a
    # genuine protected-input change.  Replacing it with a generic “missing”
    # message stranded calculator4 in code repair for a planning error.
    verification_paths .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/verification.paths" \
        2> "$STATE_DIR/verification-integrity.log" \
        || verification_integrity_failure
    # A lockfile the plan's own install command will create cannot be a protected input (see install_command.py).
    python3 -B "$ROOT/scripts/lib/install_command.py" unprotect "$STATE_DIR/verification.paths" . 2>/dev/null | tee -a "$STATE_DIR/verification-integrity.log" || true
    absent_paths="$STATE_DIR/verification.absent-paths"
    : > "$absent_paths"
    # Only the first snapshot may record plan-owned inputs that do not exist
    # before implementation.  This includes files in greenfield builds, not
    # just test directories. Later missing paths remain integrity failures, so
    # a repair cannot hide a deleted source file or test suite.
    if [[ ! -e "$STATE_DIR/verification-snapshot" ]]; then
        while IFS= read -r scope; do
            [[ ! -e "${scope%/}" ]] && printf '%s\n' "$scope" >> "$absent_paths"
        done < "$STATE_DIR/verification.paths"
    fi
    if ! WORKFLOW_ALLOW_ABSENT_PROTECTED_DIRECTORIES="$absent_paths" verification_manifest "$STATE_DIR/verification.paths" \
        > "$STATE_DIR/verification.manifest" 2> "$STATE_DIR/verification-integrity.log"; then
        verification_integrity_failure
    fi
    EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
    [[ -n "$EXPECTED_VERIFICATION" ]] || verification_integrity_failure
    # Keep actual earlier assertions, not just their hashes or the repair
    # agent's description. New snapshots never overwrite prior evidence.
    # Snapshot evidence is workflow state, not project source. Keeping it
    # under the project lets broad discovery (`vitest run`, pytest, etc.) run
    # copied tests and report false failures. Store it outside the tree while
    # preserving the absolute path in workflow state for later comparisons.
    snapshot="$(mktemp -d "${TMPDIR:-/tmp}/uncle-verification-snapshot.XXXXXX")"
    while IFS=$'\t' read -r digest file; do
        [[ "$digest" != DIRECTORY && "$digest" != ABSENT ]] || continue
        mkdir -p "$snapshot/$(dirname "$file")"
        cp "$file" "$snapshot/$file"
    done < "$STATE_DIR/verification.manifest"
    : > "$STATE_DIR/TEST_CHANGES.diff"
    if [[ -n "${PREVIOUS_VERIFICATION_SNAPSHOT:-}" && -d "$PREVIOUS_VERIFICATION_SNAPSHOT" ]]; then
        diff -ru "$PREVIOUS_VERIFICATION_SNAPSHOT" "$snapshot" \
            > "$STATE_DIR/TEST_CHANGES.diff" || [[ "$?" == 1 ]]
        if [[ ! -s "$STATE_DIR/TEST_CHANGES.diff" ]]; then
            printf 'No protected verification input changes in this repair.\n' > "$STATE_DIR/TEST_CHANGES.diff"
        fi
    else
        printf 'Initial snapshot; no prior test version to compare.\n' > "$STATE_DIR/TEST_CHANGES.diff"
    fi
    printf '%s\n' "$snapshot" > "$STATE_DIR/verification-snapshot"
}

check_verification_inputs() {
    local actual started="$SECONDS" absent_paths="$STATE_DIR/verification.absent-paths"
    if ! actual="$(WORKFLOW_ALLOW_ABSENT_PROTECTED_DIRECTORIES="$absent_paths" verification_manifest "$STATE_DIR/verification.paths" 2> "$STATE_DIR/verification-integrity.log")"; then
        verification_integrity_failure
    fi
    if [[ "$actual" != "$EXPECTED_VERIFICATION" ]]; then
        diff -u <(printf '%s\n' "$EXPECTED_VERIFICATION") <(printf '%s\n' "$actual") \
            > "$STATE_DIR/verification-integrity.log" || true
        verification_integrity_failure
    fi
    if [[ -f "$STATE_DIR/VERIFICATION_INTEGRITY.md" ]]; then
        mv "$STATE_DIR/VERIFICATION_INTEGRITY.md" "$STATE_DIR/VERIFICATION_INTEGRITY.previous.md"
    fi
    perf_record integrity manifest "$((SECONDS-started))" 0
}

# bash 3.2 (macOS system bash) has no ${var^^}.
. "$ROOT/scripts/lib/prompt-io.sh"

# The gate used to require the words APPROVE/ACKNOWLEDGE. Automation that still
# pipes them now declines; say so, so the break is visible in the output rather
# than silent.
. "$ROOT/scripts/lib/prompt-io-app.sh"

# bash 3.2 has no associative arrays, so per-stage settings are a case table
# with an environment override resolved through the variable name.
stage_setting() {
    local kind="$1"
    local stage="$2"
    local fallback="$3"
    local var

    var="WORKFLOW_${kind}_$(upper "$stage" | tr -c 'A-Z0-9' '_')"
    eval "printf '%s' \"\${$var:-$fallback}\""
}

# Same lookup, but only an *unset* variable falls back. A stage configured
# with an empty model is asking for no model at all: claude, kimi, and codex
# have their own defaults, and passing one uncle invented for them is worse
# than passing none.
stage_setting_opt() {
    local kind="$1"
    local stage="$2"
    local fallback="$3"
    local var

    var="WORKFLOW_${kind}_$(upper "$stage" | tr -c 'A-Z0-9' '_')"
    eval "printf '%s' \"\${$var-$fallback}\""
}

# Precedence, for every per-stage setting: an explicit WORKFLOW_* variable
# wins, then the project's .uncle/config, then the driver's built-in default.
# The config file is read at the moment the stage starts, so an edit made at a
# human gate applies to the stages after it.
stage_model() {
    local lookup_stage="$1"
    local fallback="$DEFAULT_MODEL"
    case "$1" in
        requirements|requirements-investigate) lookup_stage="project-plan" ;;
        preview-build-part-*) lookup_stage="preview-build" ;;
        execute-checklist) fallback="kimi" ;;
    esac
    if uncle_has_config || [[ -n "${UNCLE_RESOLVED_RUNNER:-}" ]]; then
        fallback="$(uncle_stage_model "$lookup_stage" "${UNCLE_RESOLVED_RUNNER-$(uncle_stage_runner "$lookup_stage")}")"
    fi
    stage_setting_opt MODEL "$lookup_stage" "$fallback"
}




stage_effort() {
    uncle_effective_stage_effort "$(stage_runner_config_name "$1")"
}

# Turn caps bound the worst case — a stage looping on a broken command — and
# nothing else. They are set well above what a healthy stage uses, because
# tripping one throws away the whole stage and the replay costs more than the
# cap saved. A document stage that needs 40 turns has already gone wrong;
# implementation and checklist execution legitimately run long.
stage_turns() {
    local fallback=40
    case "$1" in
        implementation|repair) fallback=200 ;;
        # Read the brief, write one file, stop.  A longer leash only lets it explore and install.
        preview-build|preview-build-part-*) fallback=8 ;;
        implementation-report) fallback=20 ;;
        execute-checklist) fallback=120 ;;
    esac
    # All normal document stages, including OpenCode-backed ones, receive the
    # same 40-step default.  A compact prompt makes a healthy stage finish far
    # below that ceiling; a five-step special case instead turns one ordinary
    # exploratory read or write retry into OpenCode's terminal "maximum steps"
    # failure.  Operators may still override any stage with WORKFLOW_TURNS_*.
    stage_setting TURNS "$1" "$fallback"
}

# Tool grants are also a token lever. An agent holding Bash will shell out to
# explore the tree even when Glob and Grep would answer the question, and
# TodoWrite re-sends the whole list on every update — pure overhead for a stage
# whose entire output is one document.
stage_tools() {
    local fallback="Read,Glob,Grep,Write"
    case "$1" in
        updated-plan|updated-plan-investigate|derive-brief)
            fallback="Read,Glob,Grep,Write,Edit" ;;
        # Fixes a contradiction in the assembled plan with a targeted edit instead of reporting and stopping.
        project-plan-stage-duties)
            fallback="Read,Glob,Grep,Write,Edit" ;;
        # The preview is one hand-written file: with Bash it scaffolds and installs, with Edit and
        # Glob it explores, and each of those is minutes of a stage that exists to be quick.
        preview-build|preview-build-part-*) fallback="Read,Write" ;;
        implementation|implementation-investigate|implementation-report|repair|repair-investigate|execute-checklist|preflight|preflight-investigate)
            fallback="Read,Glob,Grep,Write,Edit,TodoWrite,Bash"
            ;;
    esac
    stage_setting TOOLS "$1" "$fallback"
}

# New application pipeline stage order, used to report "stage N/M" to the TUI.
# Matches run_stage's case arms.
STATUS_STAGE_SEQ="derive-brief requirements project-plan adversarial-review updated-plan preflight implementation test-review manual-checklist execute-checklist final-audit"


# Map state-machine destinations which immediately launch an agent to the
# matching configured stage.  Gates and deterministic validation states do
# not need a runner.  Keeping this explicit avoids ever guessing a runner for
# a repair/reviewer panel whose command is not the command it will actually
# use.
unattended_prewarm_stage_for_state() {
    [[ "${UNATTENDED:-0}" == 1 ]] || return 0
    [[ "${UNCLE_RUNNER_REUSE:-1}" != 0 ]] || return 0
    local target="$1" stage="" side=agent
    case "$target" in
        REQUIREMENTS) stage=requirements ;;
        PROJECT_PLAN) stage=project-plan ;;
        PREFLIGHT) stage=preflight ;;
        IMPLEMENT) stage=implementation ;;
        REPAIR) stage=repair ;;
        # One packet worker is enough to warm the shared reviewer pool: all
        # same-config workers attach to that process concurrently.
        ADVERSARIAL_REVIEW) stage=adversarial-review-worker-requirements; side=reviewer ;;
        UPDATED_PLAN) stage=updated-plan-review-worker-scope; side=reviewer ;;
        TEST_REVIEW) stage=test-review-worker-coverage; side=reviewer ;;
        MANUAL_CHECKLIST) stage=manual-checklist-review-worker-coverage; side=reviewer ;;
        FINAL_AUDIT) stage=final-audit-review-worker-coverage; side=reviewer ;;
    esac
    [[ -n "$stage" ]] || return 0
    # A compact test harness can replace set_state without loading the runner
    # configuration helpers.  Warming is optional in that environment too.
    declare -f stage_runner_config_name >/dev/null || return 0
    declare -f uncle_resolve_stage_runner >/dev/null || return 0
    local runner_stage cmd model effort turns tools config_side=AGENT
    [[ "$side" != reviewer ]] || config_side=REVIEWER
    runner_stage="$(stage_runner_config_name "$stage")"
    uncle_resolve_stage_runner "$runner_stage" "$config_side" >/dev/null 2>&1 || return 0
    [[ "${UNCLE_RESOLVED_RUNNER:-}" != self-hosted && -n "${UNCLE_RESOLVED_RUNNER:-}" ]] || return 0
    stage_command_overridden "$config_side" "$stage" && return 0
    if [[ "$side" == reviewer ]]; then
        cmd="$(stage_reviewer_cmd "$runner_stage")" || return 0
    else
        cmd="$(stage_agent_cmd "$runner_stage")" || return 0
    fi
    model="$(stage_model "$stage")"
    effort="$(stage_effort "$stage")"
    turns="$(stage_turns "$stage")"
    tools="$(stage_tools "$stage")"
    # Use the same argument shape as run_claude.  native_stage derives the
    # exact native CLI command from these arguments and asks runner_pool to
    # start it without sending a prompt or opening a model turn.
    local -a warm_args env_args
    if [[ "$side" == reviewer ]]; then
        # Native Stage normalizes Claude reviewer invocations to this exact
        # persistent protocol command.  Passing Codex-style `-c` settings
        # here left `Stage.effort` empty, produced a different digest, and
        # made the actual reviewer start a second pool instead of reusing the
        # warm one.
        warm_args=(-p --output-format stream-json --verbose --allowedTools Read,Glob,Grep,Write --strict-mcp-config)
        [[ -z "$effort" ]] || warm_args+=(--effort "$effort")
        [[ -z "$model" ]] || warm_args+=(-m "$model")
        env_args=(-u UNCLE_ARTIFACT_DELIVERY)
    else
        warm_args=(-p)
        [[ -z "$model" ]] || warm_args+=(--model "$model")
        warm_args+=(--effort "$effort" --strict-mcp-config --max-turns "$turns"
                    --output-format stream-json --verbose --allowedTools "$tools")
        env_args=(-u UNCLE_ARTIFACT_DELIVERY)
    fi
    env "${env_args[@]}" \
        python3 "$ROOT/scripts/lib/native_stage.py" --prewarm \
            --runner "$UNCLE_RESOLVED_RUNNER" --side "$side" --stage "$stage" -- \
            "${warm_args[@]}" >/dev/null 2>&1 || true
}

set_state() {
    # In unattended runs we know the next state before publishing it.  Start
    # its idle CLI first, in the background, so the following loop iteration
    # normally attaches to an already-live process.  Attended runs retain the
    # exact historical lifecycle and no speculative process is ever started.
    unattended_prewarm_stage_for_state "$1" &
    printf '%s\n' "$1" > "$STATE_FILE"
}

get_state() {
    state_read "$STATE_FILE" DERIVE_BRIEF
}

# Used after an agent stage: a missing artifact here usually means a denied
# tool, not a refusal to work.
require_artifact() {
    local requested="$1" canonical
    if declare -f canonical_artifact_path >/dev/null; then
        canonical="$(canonical_artifact_path "$requested")"
    else
        # Minimal test harnesses source this helper independently.
        canonical="$requested"
    fi
    if [[ ! -s "$canonical" ]]; then
        supervision_validation_failed require_artifact "$canonical" "Stage produced no artifact: $canonical"
        echo
        echo "Stage produced no artifact: $canonical"
        echo "Check the log for '[tool ERROR]' lines — a denied Write is the"
        echo "most common cause. A '[done] error_max_turns' line means the"
        echo "turn cap was too low; raise it with WORKFLOW_TURNS_<STAGE>."
        echo "State has not advanced, so the stage replays cleanly."
        exit 1
    fi
    # Rendered Markdown is deliberately outside the operational contract.
    # A presentation budget warning must never fail an otherwise valid JSON
    # artifact or send the workflow into repair.
    [[ "$requested" == "$canonical" ]] && check_document_budget "$requested" || true
}

ensure_project_plan_json() {
    local source=".uncle/docs/PROJECT_PLAN.md"
    local canonical="$STATE_DIR/documents/PROJECT_PLAN.json"
    [[ -s "$canonical" ]] && return 0
    # A pre-render JSON plan may already have a human approval hash. Mirror it
    # without rewriting the approval-view bytes, then fall back to a legacy
    # Markdown export only when it was never JSON.
    python3 "$ROOT/scripts/lib/plan_context.py" canonicalize-project-plan "$source" . || return 1
    [[ -s "$canonical" ]] && return 0
    # Compatibility bridge for a pre-JSON plan that reached an approval gate
    # before this migration.  This is deterministic parsing at the boundary,
    # not a downstream Markdown input: after export, every later stage reads
    # only the canonical packet.
    python3 "$ROOT/scripts/lib/plan_context.py" export-project-plan "$source" . || return 1
    require_file "$canonical"
}

verify_approval() {
    local view="$1" file
    local name="$2"
    local approval="$APPROVAL_DIR/${name}.sha256"

    file="$(approval_artifact_path "$view")"

    case "$name" in
        UPDATED_PROJECT_PLAN) python3 "$ROOT/scripts/lib/plan_context.py" render-plan "$view" . || return 1 ;;
    esac
    [[ -s "$file" ]] || { echo "Required approval artifact missing: $file"; exit 1; }
    if [[ ! -s "$approval" ]]; then
        # State that presupposes an approval nobody recorded: send the run to
        # the gate rather than stopping on a file the operator never heard of.
        echo "$view has no approval on record."
        echo "Review and approve it."
        triage_reopen_gate "$name"
        require_file "$approval"
    fi

    local expected
    local actual

    expected="$(cat "$approval")"
    actual="$(hash_file "$file")"

    if [[ "$expected" != "$actual" ]]; then
        echo "$view's canonical JSON changed after approval."
        echo "Review and approve it again."
        triage_reopen_gate "$name"
        exit 1
    fi
}

# An approved document that changed -- by hand, or by a triage action the
# operator selected -- sends the run back to the gate that approved it, so
# the new bytes are read and approved by a keystroke. Nothing is written
# under approvals/ here; the stale digest stays until the operator answers.
# A document with no gate of its own keeps the plain exit 1 above.
triage_reopen_gate() {
    local gate=""
    case "$1" in
        REQUIREMENTS_INTERPRETATION) gate=WAIT_REQUIREMENTS_APPROVAL ;;
        PROJECT_PLAN) gate=WAIT_PLAN_APPROVAL ;;
        ADVERSARIAL_REVIEW) gate=WAIT_REVIEW_ACKNOWLEDGEMENT ;;
        UPDATED_PROJECT_PLAN) gate=WAIT_UPDATED_PLAN_APPROVAL ;;
    esac
    [[ -n "$gate" ]] || return 0
    set_state "$gate"
    echo "Reopening $gate: re-run the driver to review and approve what is there now."
    exit 0
}

. "$ROOT/scripts/lib/approval-gates-app.sh"

# Render the stream-json event feed as readable progress lines.
# Non-JSON lines (startup warnings) are dropped rather than fataling jq.
format_claude_stream() {
    jq -R -r --unbuffered '
        (fromjson? // empty) as $e
        | if $e.uncle_chat_output == true then empty
          elif $e.type == "assistant" then
              ($e.message.content[]?
               | if .type == "text" then .text
                 elif .type == "tool_use" then "  [tool] \(.name)"
                 else empty end)
          elif $e.type == "user" then
              ($e.message.content[]?
               | select(.type == "tool_result" and .is_error == true)
               | .content
               | (if type == "array" then map(.text? // "") | join(" ")
                  else tostring end)
               | "  [tool ERROR] \(.[0:200])")
          elif $e.type == "result" then
              "\n[done] \($e.subtype) — \($e.num_turns) turns, \(if ($e.duration_ms | type) == "number" then (($e.duration_ms / 1000 | floor | tostring) + "s") else "time unknown" end)\(if $e.error_detail then "\n  cause: \($e.error_detail)" else "" end)"
          else empty end
    '
}

# Tool grants come from stage_tools. In -p mode there is no interactive prompt,
# so anything not granted is auto-denied — and the stage only discovers that
# after doing all of its work, which is why the stages that run commands get
# Bash broadly rather than a command allowlist: every omission costs a full
# stage re-run to discover.
# Never use --dangerously-skip-permissions (CLAUDE.md rule 8).
# Pass a third argument to run_claude to override the grant for one stage.

. "$ROOT/scripts/lib/stage-runtime.sh"
. "$ROOT/scripts/lib/stage-runtime-app.sh"

# Bounded automatic source repair is on for every runner, hosted or self-hosted (prompts/repair.md, or the investigate/format
# split for a self-hosted model). It used to be reserved for the self-hosted runner, which meant a build with a fixable defect
# (an error-state bug, a palette bug) ended NOT READY with nothing attempted. WORKFLOW_REPAIR=0 still opts out.




# issue 103: how many isolated candidates race for one self-hosted stage
# attempt. Per-stage WORKFLOW_SELF_HOSTED_CANDIDATES_<STAGE> wins over the
# global WORKFLOW_SELF_HOSTED_CANDIDATES, which defaults to 1: racing is off
# unless asked for, now that self-hosted stages enforce their JSON schema over
# direct HTTP and a malformed answer is rare. Setting either to 1 takes the untouched single-shot branch below, not the
# coordinator with a race of one -- see IMPLEMENTATION_NOTES.md for why that
# is a deliberate deviation from the plan's literal wording.
self_hosted_candidate_count() {
    local stage="$1" var fallback
    var="WORKFLOW_SELF_HOSTED_CANDIDATES_$(upper "$stage" | tr -c 'A-Z0-9' '_')"
    if [[ -n "${!var:-}" ]]; then
        printf '%s' "${!var}"
        return
    fi
    if [[ -n "${WORKFLOW_SELF_HOSTED_CANDIDATES:-}" ]]; then
        printf '%s' "$WORKFLOW_SELF_HOSTED_CANDIDATES"
        return
    fi
    # Unlike the env vars above (a one-off override for this invocation),
    # `.uncle/config` is where every other per-stage setting (runner, model,
    # effort) already lives and persists across runs -- read it the same
    # way. Check the stage's own row first: `preview-build` has no config
    # row of its own for runner/model (it inherits whichever stage is first
    # configured with a model, uncle_config_stage's own special case) but a
    # candidate count set specifically for it -- WORKFLOW_SELF_HOSTED_CANDIDATES_PREVIEW_BUILD
    # already works this way -- must not be forced to also match whatever it
    # inherits its model from. Only fall through to that inherited stage
    # (e.g. an adversarial-review lens has no config row of its own and
    # should use its parent's) when the stage's own row has nothing set.
    fallback="$(uncle_stage_key "$stage" candidates)"
    [[ -n "$fallback" ]] || fallback="$(uncle_stage_key "$(uncle_config_stage "$stage")" candidates)"
    [[ -n "$fallback" ]] || fallback="$(uncle_config_get self-hosted.candidates)"
    printf '%s' "${fallback:-1}"
}

# Race `count` isolated invocations of one self-hosted stage attempt,
# promoting the first to produce a valid result (candidate_race.py,
# AC-1..AC-5). Each candidate's own body is exactly today's single-shot
# invocation in run_claude below -- generated once per race as a small script
# so the delivery-file contract and produced log stay the same shape; only
# the outer fan-out/selection is new. On success, populates $log_file with
# the winner's own stream (so perf_stream/format_claude_stream and the
# turns/context-overflow retry greps in run_claude see the log they always
# have) and copies the winner's delivery file to $delivery_target. Returns
# the winner's status (always 0 -- only a validated candidate is ever
# selected) or a nonzero status when every candidate failed, with every
# candidate's own output concatenated into $log_file for diagnosis.
# green_failure_route <continue-on-failure> <repairs-used> <attempts>
# What to do with a driver verification that failed: `repair` while automatic
# attempts remain, then `continue` (carry it to the final audit as unresolved
# evidence) when the run is configured to, else `ask` the owner.
green_failure_route() {
    local continue_on_failure="$1" used="$2" attempts="$3"
    if [[ "$used" -lt "$attempts" ]]; then
        printf 'repair'
    elif [[ "$continue_on_failure" == 1 ]]; then
        printf 'continue'
    else
        printf 'ask'
    fi
}

# A failed assertion can be useful delivery evidence when the application is
# still usable. A compile failure, a preview server that cannot start, or a
# runner that discovered zero tests is different: the product or its promised
# verification never actually ran. Treating either as a nonblocking result
# created blank-page and "No tests found" completion paths.
green_application_not_runnable() {
    local log="${1:-$LOG_DIR/green-check.log}"
    [[ -s "$log" ]] || return 1
    grep -qiE '(^|[^[:alpha:]])(build failed|failed to resolve import|is not exported by|could not resolve|error when starting (dev|preview) server|process from config\.webServer was not able to start|webserver.*exit code|no test files found|testDir.*does not exist|application_runtime_unrunnable)' "$log"
}

# A handful of "application cannot render" causes are purely mechanical --
# an include glob that does not match where the tests actually landed, a
# CommonJS require() in a file package.json declares an ES module -- fixing
# them changes *where* a check looks or *how* a file is parsed, never *what*
# it asserts. REPAIR cannot reliably fix these itself: the files involved
# (vitest.config.js, the spec files) are often protected, so a repair agent
# either cannot touch them or, worse, "fixes" the symptom by weakening what
# they check. scaffold_reconcile.py makes exactly these two fixes with no
# model in the loop, so they never need to spend the repair budget at all.
#
# A protected file changing without an attributed reason is exactly what
# the driver's own verification-integrity check exists to catch (and did,
# the one time this project edited vitest.config.js by hand outside the
# governed workflow instead of through this function). Re-baselining via
# capture_verification_inputs, and recording the exact change in
# IMPLEMENTATION_NOTES.md as a deviation, is what keeps this attributed
# instead of repeating that incident.
reconcile_scaffold_mismatches() {
    local marker="$STATE_DIR/scaffold-reconcile-attempted" changes
    [[ "${WORKFLOW_SCAFFOLD_RECONCILE:-1}" == 1 ]] || return 1
    [[ ! -e "$marker" ]] || return 1
    touch "$marker"
    changes="$(python3 -B "$ROOT/scripts/lib/scaffold_reconcile.py" . 2>/dev/null)"
    [[ -n "$changes" ]] || return 1
    {
        echo
        echo '### Driver scaffold reconciliation'
        echo
        echo 'The driver -- not an implementation agent -- made the following mechanical'
        echo 'fix(es) because the application and its real tests were otherwise correct,'
        echo 'but a protected scaffold file disagreed with the code it scaffolds in a way'
        echo 'only an exact-match glob, an import statement, or a find-text snippet'
        echo 'controls. Nothing an assertion checks was changed.'
        echo
        while IFS= read -r change; do
            [[ -n "$change" ]] || continue
            python3 -B -c '
import json, sys
c = json.loads(sys.argv[1])
print("- `%s`: %s" % (c["file"], c["reason"]))
' "$change"
        done <<< "$changes"
    } >> .uncle/docs/IMPLEMENTATION_NOTES.md
    echo "Driver scaffold reconciliation applied $(wc -l <<< "$changes" | tr -d ' ') mechanical fix(es); recorded in .uncle/docs/IMPLEMENTATION_NOTES.md."
    # The files just changed are now the approved baseline: nothing here is
    # an unreviewed drift from what was implemented, it is the driver's own
    # attributed correction of it, recorded above.
    capture_verification_inputs
    EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest" 2>/dev/null)"
    rm -f "$STATE_DIR/green-check.fingerprint"
    run_green_check_auto || true
    green_wait_final || true
    return 0
}

# Return 0 when browser/verification work is safe, 2 after scheduling the one
# bounded repair attempt for an unattended run, and 1 when a person must
# inspect the persistent setup failure.
#
# This used to force a full re-entry into IMPLEMENT: it discarded the
# parallel-implementation completion markers so every plan step's worker
# reran from scratch, on the theory that a provably unbuildable app needs
# more than REPAIR can give it. In practice nearly every case seen (a
# scaffold test-discovery glob, a missing export, a CSS mismatch) was a
# small, localized fix -- and a full fan-out re-run burns the single most
# expensive path available (minutes, every plan step, millions of tokens)
# to get it. REPAIR is the bounded path every other green-check failure
# already uses for exactly this kind of fix, $GREEN_MD is already an
# eligible repair source, and REPAIR's own shared budget
# (WORKFLOW_AUTO_REPAIR_ATTEMPTS) still bounds this the same as any other
# repair -- this marker only prevents a second attempt at this specific
# failure shape within the same run.
route_unrunnable_application() {
    green_application_not_runnable || return 0
    if reconcile_scaffold_mismatches && ! green_application_not_runnable; then
        echo 'Scaffold reconciliation resolved the runtime failure; proceeding without spending the repair budget.'
        return 0
    fi
    local marker="$STATE_DIR/runtime-readiness-repair-attempted"
    if [[ "$WORKFLOW_REPAIR" != 1 ]]; then
        # Once per run. One caller sits inside FINAL_AUDIT itself and treats a return of 2 as "the state changed, go round
        # again": without this, setting FINAL_AUDIT from FINAL_AUDIT re-entered it, re-read the same log, recorded the same
        # failure and returned 2 again, forever (calculator: 426 ledger lines in four minutes, the audit never started).
        # The marker is keyed on the run, not on the log, because the log is rewritten on every pass.
        local recorded="$STATE_DIR/runtime-unrunnable-recorded" run_id
        run_id="$(cat "$STATE_DIR/run-started-at" 2>/dev/null)"; run_id="${run_id:-no-run-id}"
        if [[ "$(cat "$recorded" 2>/dev/null)" == "$run_id" ]]; then
            return 0    # already carried to the audit; let the audit run
        fi
        printf '%s\n' "$run_id" > "$recorded"
        # The verdict above comes from reading the verification log, not from loading the page, so it is a reason to flag the build
        # and never a reason to skip the checklists: manual-checklist and execute-checklist are how the application is actually
        # looked at. Record the failure once for the audit and carry on; a checklist that cannot drive the app reports BLOCKED or
        # FAIL rows, which is evidence the audit can read, where skipping them left it none.
        record_nonblocking_failure green-check 'the verification log says the application cannot render or its test runner did not execute tests; repair is disabled, so the checklists still run to observe it directly'
        record_test_failure_disposition || true
        echo 'The verification log says the application cannot render or its test runner executed no tests. Repair is disabled for new application builds: the failure is recorded for the final audit and the checklists still run.'
        return 0
    fi
    if [[ "${UNATTENDED:-0}" == 1 && ! -e "$marker" ]]; then
        touch "$marker"
        # Deliberately not $GREEN_MD: REPAIR's own ineligibility fallback
        # treats that source (and TEST_REVIEW.md) as "a verification finding
        # already judged by a completed test-review/checklist pass; skip
        # straight to FINAL_AUDIT" -- true for those two, false here. This
        # fires from inside TEST_REVIEW itself, before test-review,
        # manual-checklist or execute-checklist have run even once; if the
        # repair budget is already spent, the run must stop for a person
        # (the existing default branch below), not silently skip the whole
        # checklist pipeline with zero evidence the app works at all.
        {
            printf '# Application startup verification failed\n\n'
            printf 'Repair the startup failure before browser/checklist verification.\n'
            printf 'Driver command results: `%s`\nFull execution evidence: `%s/green-check.log`\n\n' "$GREEN_MD" "$LOG_DIR"
            [[ ! -f "$GREEN_MD" ]] || cat "$GREEN_MD"
        } > "$STATE_DIR/runtime-unrunnable-application"
        printf '%s\n' "$STATE_DIR/runtime-unrunnable-application" > "$STATE_DIR/repair-source"
        echo 'The application cannot render or its configured test runner did not execute tests; repairing once before browser/checklist work.'
        set_state REPAIR
        return 2
    fi
    echo 'Application or verification setup is not runnable; browser/checklist work is not started.' >&2
    echo "See $LOG_DIR/green-check.log and correct the implementation before resuming." >&2
    return 1
}

# A race runs every candidate in its own copy of the project, and only the
# winner's stream and delivery file used to cross back.  Everything else a stage
# produces lives in that copy: an investigation stage's Written document, an
# implementation stage's source edits, execute-checklist's reports.  Left behind,
# a stage that succeeded changed nothing, and the driver either found no file or
# synthesized an empty "NOT RUN" report.  Promote what the winner changed (see
# promote_candidate.py: only its own changes, only project files and workflow
# documents, never over a live file edited meanwhile).
promote_winner_work() {
    python3 -B "$ROOT/scripts/lib/promote_candidate.py" promote "$1" "$PWD" \
        || echo "Warning: the winning candidate could not be promoted; its work stays in $1" >&2
}

race_self_hosted_candidates() {
    local log_name="$1" count="$2" prompt_file="$3" delivery_target="$4" log_file="$5"
    local work_dir="$STATE_DIR/candidate-race/$log_name"
    rm -rf "$work_dir"
    mkdir -p "$work_dir"

    # A non-artifact self-hosted stage (anything not in self_hosted.py's
    # PLAN_ARTIFACTS) gets NO isolation from self_hosted.py itself -- it runs
    # `_run_opencode` straight against the live root, on the assumption that
    # exactly one such process is ever in flight. Racing N of those
    # concurrently against the SAME live tree, several with a broad Edit
    # grant (`may_write = side == 'agent' or bool(delivery)`), is exactly the
    # clobbering hazard AC-3 exists to prevent -- so every candidate here
    # gets its OWN isolated copy of the project first, reusing
    # self_hosted.py's own `copy_generated_documents` so the isolation
    # boundary (what crosses in: docs and packets, never .uncle state/creds)
    # matches the one self_hosted.py already enforces for its own copytree,
    # instead of a second, drifting definition of the same boundary. A
    # PLAN_ARTIFACTS stage still isolates a second time one level deeper
    # inside self_hosted.py itself; redundant, not unsafe.
    local config_path
    config_path="$(uncle_config_file)"
    [[ "$config_path" = /* ]] || config_path="$PWD/$config_path"

    local isolate_script="$work_dir/isolate.py"
    cat > "$isolate_script" <<'ISOLATE_PY'
import shutil
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
from self_hosted import copy_generated_documents
root, staged = Path(sys.argv[1]), Path(sys.argv[2])
excluded = shutil.ignore_patterns('.git', '.uncle', '.opencode*', 'node_modules', '.venv', 'venv', '__pycache__')
def ignore(directory, names):
    return set(excluded(directory, names)) | {name for name in names if (Path(directory) / name).is_symlink()}
shutil.copytree(root, staged, ignore=ignore)
copy_generated_documents(root, staged)
from promote_candidate import snapshot
snapshot(staged)
ISOLATE_PY

    local launch_script="$work_dir/launch.sh"
    {
        printf '#!/usr/bin/env bash\nset -uo pipefail\n'
        printf 'python3 -B %q %q "$CANDIDATE_DIR/project" %q || exit 1\n' \
            "$isolate_script" "$PWD" "$ROOT/scripts/lib"
        printf 'export UNCLE_CONFIG=%q\n' "$config_path"
        printf 'cd "$CANDIDATE_DIR/project" || exit 1\n'
        printf 'mkdir -p "$CANDIDATE_DIR/project/.uncle/workflow" || exit 1\n'
        printf 'env UNCLE_ARTIFACT_DELIVERY="$CANDIDATE_DIR/project/.uncle/workflow/candidate-delivery.json" '
        local part
        for part in "${client_cmd[@]}"; do printf '%q ' "$part"; done
        printf -- '-p '
        for part in "${model_args[@]+"${model_args[@]}"}"; do printf '%q ' "$part"; done
        printf -- '--effort %q --strict-mcp-config --max-turns %q --output-format stream-json --verbose --allowedTools %q < %q > "$CANDIDATE_DIR/raw.jsonl" 2>&1\n' \
            "$effort" "$turns" "$tools" "$prompt_file"
        printf 'echo $? > "$CANDIDATE_DIR/status"\n'
    } > "$launch_script"

    local validate_script="$work_dir/validate.sh"
    {
        printf '#!/usr/bin/env bash\nset -uo pipefail\n'
        printf 'status_file="$CANDIDATE_DIR/status"\n'
        printf '[[ -f "$status_file" ]] || { echo "no status file"; exit 1; }\n'
        printf 'status="$(cat "$status_file")"\n'
        printf '[[ "$status" == "0" ]] || { echo "agent exited with status $status"; exit 1; }\n'
        # Final delivery/schema validation stays a one-time, post-selection
        # step in run_claude's existing case block below, run only against
        # the winner -- never here, which would write every losing
        # candidate's document into the live tree too.
        case "$log_name" in
            requirements|project-plan|updated-plan|change-plan|updated-change-plan)
                printf '[[ -s "$CANDIDATE_DIR/project/.uncle/workflow/candidate-delivery.json" ]] || { echo "no delivery.json written"; exit 1; }\n'
                printf 'python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$CANDIDATE_DIR/project/.uncle/workflow/candidate-delivery.json" || { echo "delivery.json is not valid JSON"; exit 1; }\n'
                ;;
            *-worker-*)
                printf '[[ -s "$CANDIDATE_DIR/project/.uncle/workflow/candidate-delivery.json" ]] || { echo "no delivery.json written"; exit 1; }\n'
                ;;
        esac
    } > "$validate_script"
    chmod +x "$launch_script" "$validate_script"

    # Tell the TUI every candidate began, the same way publish_worker_start
    # does for -worker- fan-out (parallel_steps.py): without this the panel
    # shows the whole race as idle until it is already decided.
    if [[ -n "${UNCLE_STATUS_FILE:-}" ]]; then
        local n
        for ((n = 0; n < count; n++)); do
            printf '{"event":"start","model":"%s","mode":"act","stage":"%s","stage_index":0,"stage_total":0,"stage_turns":0}\n' \
                "${model:-}" "${log_name}-candidate-${n}" >> "$UNCLE_STATUS_FILE"
        done
    fi

    local evidence_file="$LOG_DIR/${log_name}.candidate-race-evidence.json"
    local winner_dir status=0
    winner_dir="$(python3 -B "$ROOT/scripts/lib/candidate_race.py" run \
        --stage "$log_name" --count "$count" \
        --work-dir "$work_dir/candidates" \
        --launch-script "$launch_script" --validate-script "$validate_script" \
        --evidence "$evidence_file")" || status=$?

    # One completion glyph per candidate (AC-6): validated-winner -> exit 0,
    # stopped-nonselected/stopped-timeout -> a distinct "stopped, not judged"
    # exit code the TUI reads apart from a genuine failure, everything else
    # (rejected-invalid, crashed) -> a plain failure exit. This is a private
    # convention between this function and uncle_tui.py's candidate glyph
    # rendering, not a general meaning for process_exit elsewhere.
    if [[ -f "$evidence_file" ]]; then
        local candidate_total
        candidate_total="$(jq '.candidates | length' "$evidence_file" 2>/dev/null || echo 0)"
        local i
        for ((i = 0; i < candidate_total; i++)); do
            local entry cid cstatus celapsed cdir cexit clog
            entry="$(jq -c ".candidates[$i]" "$evidence_file")"
            cid="$(jq -r '.id' <<<"$entry")"
            cstatus="$(jq -r '.status' <<<"$entry")"
            celapsed="$(jq -r '.elapsed // 0' <<<"$entry")"
            cdir="$(jq -r '.directory // empty' <<<"$entry")"
            case "$cstatus" in
                validated-winner) cexit=0 ;;
                stopped-nonselected|stopped-timeout) cexit=130 ;;
                *) cexit=1 ;;
            esac
            clog="/dev/null"
            [[ -n "$cdir" && -f "$cdir/raw.jsonl" ]] && clog="$cdir/raw.jsonl"
            perf_record agent "${log_name}-candidate-${cid}" "$celapsed" "$cexit" "$clog" "$cmd" "$model" "$effort"
        done
    fi

    if [[ "$status" -ne 0 || -z "$winner_dir" ]]; then
        : > "$log_file"
        local candidate_dir
        for candidate_dir in "$work_dir"/candidates/candidate-*; do
            [[ -d "$candidate_dir" ]] || continue
            {
                printf '\n=== %s ===\n' "$candidate_dir"
                cat "$candidate_dir/raw.jsonl" 2>/dev/null
            } >> "$log_file"
        done
        return 1
    fi

    promote_winner_work "$winner_dir"
    cat "$winner_dir/raw.jsonl" | perf_stream "$log_name" | tee "$log_file" | format_claude_stream
    if [[ -n "$delivery_target" && -s "$winner_dir/project/.uncle/workflow/candidate-delivery.json" ]]; then
        cp "$winner_dir/project/.uncle/workflow/candidate-delivery.json" "$delivery_target"
    fi
    return 0
}

# A merged pass has two operational outputs but the JSON delivery contract has
# one output path. It is therefore disabled by default. Explicit opt-in stays
# available only for bespoke runners which really do publish both packets.
merged_requirements_plan_enabled() {
    local runner
    uncle_resolve_stage_runner "$(stage_runner_config_name requirements)" AGENT 2>/dev/null || return 1
    runner="$UNCLE_RESOLVED_RUNNER"
    [[ "$MERGE_REQUIREMENTS_PLAN" == "1" ]] \
        && [[ "$runner" == multi-artifact ]]
}

# Requirements and the initial project plan have no useful conversational
# history. Reusing a long-lived runner here made a small calculator brief
# inherit tens of thousands of cached planning tokens and turned the plan into
# a multi-minute response. Start these independent artifacts cold; later
# worker panels still use their deliberate shared-prefix reuse.
run_initial_planning_agent() {
    SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 run_claude "$@"
}

# Requirements agents must see the selected brief as literal prompt content.
# Self-hosted runners do not inherit the driver's internal "packet" in the
# way native clients do.  A prompt which merely says "read the document named
# in the driver packet" therefore leads them to interpret the workflow prompt
# itself as the requirements.  Bind the exact selected source for the three
# prompts that create an interpretation; later planning stages intentionally
# consume the canonical interpretation JSON instead.
bind_requirements_source() {
    local prompt_file="$1" log_name="$2" source_prompt="$3"
    case "${source_prompt##*/}" in
        requirements.md|requirements-plan.md|requirements-investigate.md) ;;
        *) printf '%s\n' "$prompt_file"; return 0 ;;
    esac

    local bound_prompt="$LOG_DIR/${log_name}.requirements-bound-prompt.md"
    {
        cat "$prompt_file"
        cat <<'REQUIREMENTS_SOURCE'

## Binding requirements source (highest priority)

The exact project brief follows. Interpret this brief, not the workflow prompt,
output rules, a driver-packet description, or any generated document. If the
brief conflicts with an earlier generated interpretation, the brief is the
source of truth for this requirements stage. Do not claim that the brief was
omitted: its contents are included below.

REQUIREMENTS_SOURCE
        python3 "$ROOT/scripts/lib/requirements-context.py" --brief \
            "${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md}" .
    } > "$bound_prompt"
    printf '%s\n' "$bound_prompt"
}

run_claude() {
    local prompt_file
    prompt_file="$(resolve_prompt "$1")"
    local log_name="$2"
    case "$log_name" in
        requirements|project-plan|change-plan)
            python3 "$ROOT/scripts/lib/early-prerequisites.py" "${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md}" || exit $? ;;
    esac

    local tools="${3:-$(stage_tools "$log_name")}"
    local model
    local effort
    local turns
    local cmd
    local UNCLE_RESOLVED_RUNNER runner_stage
    runner_stage="$(stage_runner_config_name "$log_name")"
    uncle_resolve_stage_runner "$runner_stage" AGENT || return 1

    cmd="$(stage_agent_cmd "$runner_stage")" || return 1
    model="$(stage_model "$log_name")"
    effort="$(stage_effort "$log_name")"
    turns="${UNCLE_WORKER_MAX_TURNS:-$(stage_turns "$log_name")}"
    local no_thinking=0
    if uncle_stage_thinking_off "$log_name"; then
        no_thinking=1
        case "${UNCLE_RESOLVED_RUNNER:-}" in
            codex|kimi) if uncle_runner_accepts_no_thinking "$UNCLE_RESOLVED_RUNNER" "$model"; then effort=none; fi ;;
        esac
    fi
    local turns_retried=""
    local artifact_retried=""
    local artifact_error=""
    local agent_delivery=""
    local anchored_repair=""
    # Packet-producing workers get a private, workspace-local delivery file.
    # Never infer this data from streamed chat: local models commonly wrap or
    # truncate otherwise valid JSON there.
    if [[ -n "${UNCLE_WORKER_PACKET_PATH:-}" ]]; then
        agent_delivery="$UNCLE_WORKER_PACKET_PATH"
        rm -f "$agent_delivery"
    else
        case "$log_name" in
            requirements|project-plan|updated-plan)
                mkdir -p "$STATE_DIR/artifact-delivery"
                agent_delivery="$STATE_DIR/artifact-delivery/${log_name}.json"
                rm -f "$agent_delivery"
                ;;
        esac
    fi
    local -a client_cmd=("$cmd")
    case "${cmd##*/}" in
        claude|codex) client_cmd=(env -u UNCLE_STATUS_FILE -u UNCLE_PROJECT_ROOT -u UNCLE_CONFIG -u STAGEGATE_RUN_ID -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u DOCUMENT_BUDGET_SOURCE "$cmd") ;;
    esac
    if [[ -n "${UNCLE_RESOLVED_RUNNER:-}" && "$UNCLE_RESOLVED_RUNNER" != self-hosted ]] \
       && { [[ "${UNCLE_STEERING:-}" == 1 ]] \
            || { [[ "${UNCLE_RUNNER_REUSE:-1}" != 0 ]] && ! stage_command_overridden AGENT "$log_name"; }; }; then
        client_cmd=(python3 "$ROOT/scripts/lib/native_stage.py" --runner "$UNCLE_RESOLVED_RUNNER" --side agent --stage "$log_name" --)
    fi

    # Forced JSON: the driver names a JSON Schema, Claude must answer through a schema-validated
    # StructuredOutput call, and the validated object is what the driver reads -- never chat text,
    # never a file the model may forget to write. Codex adapters enforce their final-answer schema and
    # deliver the restored object themselves, retaining the file contract when enforcement is unavailable.
    local -a schema_args=()
    if [[ -n "${UNCLE_OUTPUT_SCHEMA_FILE:-}" ]]; then
        # Direct, or through native_stage.py (steering sessions, i.e. every run under the TUI): the flag
        # reaches the same Claude process, and native_stage reports its validated object on the result event.
        if [[ "${cmd##*/}" == claude && "$UNCLE_RESOLVED_RUNNER" == claude && -n "${UNCLE_STRUCTURED_OUTPUT_PATH:-}" ]]; then
            schema_args=(--json-schema "$(cat "$UNCLE_OUTPUT_SCHEMA_FILE")")
        elif [[ "$UNCLE_RESOLVED_RUNNER" == codex && "${cmd##*/}" == agent-codex.sh ]]; then
            : # Codex adapters constrain the final answer and deliver the restored object.
        else
            echo "Stage $log_name asked for schema-checked output, which this runner cannot give." >&2
            return 1
        fi
    fi

    require_file "$prompt_file"
    status_stage_context "$log_name" "${model:-}" act

    while true; do
        case "$log_name" in
            updated-plan*|updated-change-plan*|preflight*)
                (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_archive_attempt "$LOG_DIR/${log_name}.jsonl") || return 1 ;;
        esac
        echo
        echo "Launching agent ($cmd): $log_name"
        echo "Model: ${model:-(runner default)} (effort: $effort, max turns: $turns)"
        echo "Tools: $tools"
        echo

        # Plain `$AGENT_CMD -p` buffers the entire session and prints nothing until
        # it exits, which is indistinguishable from a hang. Stream events instead.
        #
        # The prompt goes in on stdin, not as a positional argument: --allowedTools
        # is variadic and silently swallows a trailing prompt argument, which fails
        # with "Input must be provided either through stdin or as a prompt argument".
        #
        # --strict-mcp-config with no --mcp-config loads zero MCP servers. No stage
        # needs one, and skipping them removes both server startup and their tool
        # schemas from every request.
        local status=0
        local effective_prompt
        effective_prompt="$(gated_prompt "$prompt_file" "$log_name")"
        effective_prompt="$(bind_requirements_source "$effective_prompt" "$log_name" "$prompt_file")"
        # Worker fan-out has no decision authority and already receives a
        # compact, schema-bound prompt. Supervising every batch wastes calls
        # and can mistake a transient prompt path for a parent-stage failure.
        case "$log_name" in
            *-worker-*) ;;
            *)
                supervision_prompt "$effective_prompt" "$log_name" "$LOG_DIR/${log_name}.jsonl"
                effective_prompt="$SUPERVISION_PROMPT"
                ;;
        esac
        case "$log_name" in
            *-worker-*)
                if [[ "${#schema_args[@]}" -gt 0 ]]; then
                    : # the structured-output contract below replaces the Write contract
                elif [[ -n "$agent_delivery" ]]; then
                    cat >> "$effective_prompt" <<'CANONICAL_WORKER_PACKET_CONTRACT'

## Canonical worker-packet delivery (binding)

Use your Write tool to create exactly one complete JSON object at `
CANONICAL_WORKER_PACKET_CONTRACT
                    printf '%s' "$agent_delivery" >> "$effective_prompt"
                    cat >> "$effective_prompt" <<'CANONICAL_WORKER_PACKET_CONTRACT'
`. This private packet file is the only worker handoff the driver reads.
Do not write another file. Chat text is diagnostics only.
CANONICAL_WORKER_PACKET_CONTRACT
                    if [[ -n "${UNCLE_WORKER_PACKET_ERROR:-}" ]]; then
                        printf '\nThe previous packet was rejected: %s\nUse Write to replace the same packet file with corrected JSON.\n' "$UNCLE_WORKER_PACKET_ERROR" >> "$effective_prompt"
                    fi
                fi
                ;;
            requirements|project-plan|updated-plan)
                # A self-hosted runner already gets its own delivery contract
                # from self_hosted.py's delivery_notice, pointing at the
                # disposable staged copy's own path. Appending this one too
                # -- naming the live tree's $agent_delivery, which sits
                # outside that sandbox and is denied -- gave the model two
                # conflicting instructions; one real run tried the denied
                # live path, then narrated success without writing anywhere.
                # A schema-checked answer is delivered by the StructuredOutput call below; a Write instruction beside it is a conflict.
                if [[ "${UNCLE_RESOLVED_RUNNER:-}" != self-hosted && "${#schema_args[@]}" -eq 0 ]]; then
                    cat >> "$effective_prompt" <<'CANONICAL_ARTIFACT_CONTRACT'

## Canonical artifact contract (binding)

Use your Write tool to create exactly one complete `uncle.artifact/v1` JSON
object at `
CANONICAL_ARTIFACT_CONTRACT
                    printf '%s' "$agent_delivery" >> "$effective_prompt"
                    cat >> "$effective_prompt" <<'CANONICAL_ARTIFACT_CONTRACT'
`. This file is the only authoritative handoff; chat text is diagnostics only.
Do not write a Markdown view or modify another file.
CANONICAL_ARTIFACT_CONTRACT
                    if [[ -n "$artifact_error" && -n "$anchored_repair" ]]; then
                        anchored_repair_note "$artifact_error" "$agent_delivery" >> "$effective_prompt"
                    elif [[ -n "$artifact_error" ]]; then
                        printf '\nThe previous canonical delivery was rejected: %s\nUse Write to replace the same delivery file with a complete corrected JSON object.\n' "$artifact_error" >> "$effective_prompt"
                    fi
                fi
                ;;
        esac
        if [[ "${#schema_args[@]}" -gt 0 ]]; then
            cat >> "$effective_prompt" <<'STRUCTURED_OUTPUT_CONTRACT'

## Delivery (binding)

Deliver by calling the StructuredOutput tool exactly once, with the complete object. Its input is checked
against a JSON Schema, so every required field must be present and nothing outside the schema may be added.
Do not write the content as chat text first and do not write any file: the tool call is the whole answer.
STRUCTURED_OUTPUT_CONTRACT
        fi
        local -a model_args=()
        [[ -n "$model" ]] && model_args=(--model "$model")
        # Stages that transcribe decided inputs into a document run without thinking (thinking-off.sh).
        local -a thinking_env=()
        if [[ "$no_thinking" == 1 && "${UNCLE_RESOLVED_RUNNER:-}" == claude ]]; then
            thinking_env=(MAX_THINKING_TOKENS=0)
        fi
        local started="$SECONDS"
        local candidates
        candidates="$(self_hosted_candidate_count "$log_name")"
        if [[ "${UNCLE_RESOLVED_RUNNER:-}" == self-hosted && "$candidates" -gt 1 ]]; then
            race_self_hosted_candidates "$log_name" "$candidates" "$effective_prompt" \
                "$agent_delivery" "$LOG_DIR/${log_name}.jsonl" || status=$?
        else
            env UNCLE_ARTIFACT_DELIVERY="$agent_delivery" "${thinking_env[@]+"${thinking_env[@]}"}" "${client_cmd[@]}" -p \
                "${model_args[@]+"${model_args[@]}"}" \
                "${schema_args[@]+"${schema_args[@]}"}" \
                --effort "$effort" \
                --strict-mcp-config \
                --max-turns "$turns" \
                --output-format stream-json \
                --verbose \
                --allowedTools "$tools" \
                < "$effective_prompt" \
                2>&1 \
                | perf_stream "$log_name" | tee "$LOG_DIR/${log_name}.jsonl" \
                | format_claude_stream || status=$?
        fi
        perf_record agent "$log_name" "$((SECONDS-started))" "$status" \
            "$LOG_DIR/${log_name}.jsonl" "$cmd" "$model" "$effort"
        supervision_stage_end "$log_name" "$status" "$LOG_DIR/${log_name}.jsonl"

        if [[ "$status" -ne 0 ]]; then
            local log="$LOG_DIR/${log_name}.jsonl"
            if grep -qiE 'context (length|window)|maximum context|out of (tokens|context)|token limit|too many tokens|context_length_exceeded' "$log"; then
                echo
                echo "The model ran out of context/tokens."
                printf '%s' "Enter a new model id to retry this stage (or Enter to stop): "
                local new_model
                if read -r new_model && [[ -n "$new_model" ]]; then
                    model="$(printf '%s' "$new_model" | tr -d '[:space:]')"
                    continue
                fi
                echo
                triage_stop_reason "$STATE_DIR" human
            fi
            # A step whose scope needs more turns than it was allotted is not
            # stuck or wrong -- it can be mid-way through correctly applying a
            # diagnosed fix when it hits this. Unlike a model choice, a turn
            # count is not a decision an operator needs to make; double it
            # once, unattended or not, the same bounded-retry shape
            # self_hosted.py already uses for an output-token ceiling.
            if [[ -z "${UNCLE_WORKER_MAX_TURNS:-}" && -z "$turns_retried" ]] && grep -qiE 'maximum number of turns|max.?turns' "$log"; then
                turns_retried=1
                local larger_turns=$((turns * 2))
                [[ "$larger_turns" -le 200 ]] || larger_turns=200
                if [[ "$larger_turns" -gt "$turns" ]]; then
                    echo "Stage $log_name reached its turn limit ($turns) mid-task; retrying once with $larger_turns."
                    turns="$larger_turns"
                    continue
                fi
            fi
            echo "Agent ($cmd) exited with status $status."
            echo "Raw event log: $log"
            exit "$status"
        fi

        if [[ "${#schema_args[@]}" -gt 0 ]]; then
            if ! python3 -B "$ROOT/scripts/lib/structured_output.py" extract "$LOG_DIR/${log_name}.jsonl" "$UNCLE_STRUCTURED_OUTPUT_PATH"; then
                if [[ -z "${UNCLE_WORKER_MAX_TURNS:-}" && -z "$artifact_retried" ]]; then
                    artifact_retried=1
                    echo "Stage $log_name returned no schema-checked object; retrying once."
                    continue
                fi
                echo "Stage $log_name returned no schema-checked object." >&2
                # Every other validator failure in this file reports to the
                # supervision event stream (supervision_validation_failed);
                # this local retry-then-exit path used to be the one silent
                # exception, invisible to the out-of-process supervisor
                # controller. Report it here too -- a real observability gap,
                # closed per explicit decision, not a guess.
                supervision_validation_failed no-artifact "${UNCLE_STRUCTURED_OUTPUT_PATH:-}" "Stage $log_name returned no schema-checked object."
                exit 1
            fi
        fi

        case "$log_name" in
            *-worker-*)
                if [[ -n "$agent_delivery" && ! -s "$agent_delivery" ]]; then
                    python3 -B "$ROOT/scripts/lib/structured_output.py" recover "$LOG_DIR/${log_name}.jsonl" "$agent_delivery" 2>/dev/null \
                        && echo "Worker $log_name printed its packet instead of writing it; took it from the reply."
                fi
                if [[ -n "$agent_delivery" && ! -s "$agent_delivery" ]]; then
                    echo "Worker $log_name did not write its required canonical JSON packet: $agent_delivery" >&2
                    # See the schema_args branch above: this path used to exit
                    # without ever reporting to supervision. Closing the same gap here.
                    supervision_validation_failed no-artifact "$agent_delivery" "Worker $log_name did not write its required canonical JSON packet"
                    exit 1
                fi
                ;;
            requirements|project-plan|updated-plan)
                if ! artifact_error="$(python3 "$ROOT/scripts/lib/publish_agent_artifact.py" "$log_name" "$LOG_DIR/${log_name}.jsonl" . "$agent_delivery" 2>&1)"; then
                    if [[ -z "$artifact_retried" ]]; then
                        artifact_retried=1
                        if [[ "${UNCLE_RESOLVED_RUNNER:-}" != self-hosted ]] && anchored_repair_keeps "$agent_delivery"; then
                            anchored_repair=1
                            tools="$(anchored_repair_tools "$tools")"
                            echo "Canonical artifact rejected; asking $log_name once to correct it in place with the exact schema error."
                        else
                            rm -f "$agent_delivery"
                            echo "Canonical artifact rejected; retrying $log_name once with the exact schema error."
                        fi
                        printf '%s\n' "$artifact_error"
                        continue
                    fi
                    printf '%s\n' "$artifact_error" >&2
                    # Same gap as the two branches above, closed the same way:
                    # a stage that never produced a valid canonical artifact,
                    # even after the one deterministic local retry, used to
                    # exit without the out-of-process supervisor controller
                    # ever learning about it.
                    supervision_validation_failed no-artifact "$agent_delivery" "$artifact_error"
                    exit 1
                fi
                ;;
        esac
        break
    done
}

. "$ROOT/scripts/lib/reviewer-artifacts.sh"


# Reviewer-side counterpart to race_self_hosted_candidates, for
# run_codex_review's self-hosted branch (adversarial-review, test-review,
# manual-checklist, final-audit, and each of their -worker- lenses -- e.g.
# adversarial-review's 4-lens panel racing 4 candidates each renders as 4
# rows of 4 in the TUI, one row per lens/parent_stage grouping). A plain
# read-only reviewer run is already safe to race unmodified (`may_write` in
# self_hosted.py's permission table is false with no delivery file), but the
# `*.json`-output/delivery-file branch below grants Edit broadly, so every
# candidate here still gets its own isolated project copy exactly like the
# agent-side race, rather than relying on the read-only case being the only
# one ever raced.
race_self_hosted_reviewer_candidates() {
    local log_name="$1" count="$2" prompt_file="$3" reviewer_sandbox="$4" \
        delivery_mode="$5" output_target="$6" log_file="$7"
    local work_dir="$STATE_DIR/candidate-race/$log_name"
    rm -rf "$work_dir"
    mkdir -p "$work_dir"

    local config_path
    config_path="$(uncle_config_file)"
    [[ "$config_path" = /* ]] || config_path="$PWD/$config_path"

    local isolate_script="$work_dir/isolate.py"
    cat > "$isolate_script" <<'ISOLATE_PY'
import shutil
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
from self_hosted import copy_generated_documents
root, staged = Path(sys.argv[1]), Path(sys.argv[2])
excluded = shutil.ignore_patterns('.git', '.uncle', '.opencode*', 'node_modules', '.venv', 'venv', '__pycache__')
def ignore(directory, names):
    return set(excluded(directory, names)) | {name for name in names if (Path(directory) / name).is_symlink()}
shutil.copytree(root, staged, ignore=ignore)
copy_generated_documents(root, staged)
from promote_candidate import snapshot
snapshot(staged)
ISOLATE_PY

    # In delivery_mode, $prompt_file already has the literal, binding
    # instruction text baked in by the caller ("Use your Write tool to
    # create exactly one JSON object at `$delivery_file`") -- $delivery_file
    # being the single shared, non-candidate path. Handing every candidate
    # that same prompt while pointing UNCLE_ARTIFACT_DELIVERY at its own
    # per-candidate path gives the model two conflicting locations, and the
    # isolation sandbox denies the one the text names (it sits outside the
    # candidate's own project copy) -- so every candidate must instead see
    # its OWN path written into its OWN copy of the prompt, substituted at
    # run time (only $CANDIDATE_DIR, not $delivery_file, is known yet here).
    cp "$prompt_file" "$work_dir/prompt-template.md"
    local render_script="$work_dir/render-prompt.py"
    cat > "$render_script" <<'RENDER_PY'
import sys
from pathlib import Path
template, old, new, target = sys.argv[1:5]
Path(target).write_text(
    Path(template).read_text(encoding='utf-8').replace(old, new), encoding='utf-8')
RENDER_PY

    local launch_script="$work_dir/launch.sh"
    {
        printf '#!/usr/bin/env bash\nset -uo pipefail\n'
        printf 'python3 -B %q %q "$CANDIDATE_DIR/project" %q || exit 1\n' \
            "$isolate_script" "$PWD" "$ROOT/scripts/lib"
        printf 'export UNCLE_CONFIG=%q\n' "$config_path"
        printf 'cd "$CANDIDATE_DIR/project" || exit 1\n'
        printf 'mkdir -p "$CANDIDATE_DIR/project/.uncle/workflow" || exit 1\n'
        # self_hosted.py's reviewer side hard-requires the model to Write its
        # own delivery file whenever UNCLE_ARTIFACT_DELIVERY is non-empty
        # (may_write is unconditional for the agent side, but not here) --
        # setting it unconditionally would make every plain, read-only
        # review fail for never writing a file it was never asked to write.
        # Match delivery_mode exactly: a real per-candidate path only in the
        # *.json/delivery-file case, empty (not unset) otherwise, exactly
        # like the non-race $delivery_file this mirrors.
        if [[ "$delivery_mode" == 1 ]]; then
            printf 'python3 -B %q %q %q "$CANDIDATE_DIR/project/candidate-delivery.json" "$CANDIDATE_DIR/prompt.md" || exit 1\n' \
                "$render_script" "$work_dir/prompt-template.md" "$delivery_file"
            printf 'env UNCLE_ARTIFACT_DELIVERY="$CANDIDATE_DIR/project/candidate-delivery.json" '
        else
            printf 'cp %q "$CANDIDATE_DIR/prompt.md"\n' "$work_dir/prompt-template.md"
            printf 'env UNCLE_ARTIFACT_DELIVERY= '
        fi
        local part
        for part in "${client_cmd[@]}"; do printf '%q ' "$part"; done
        printf -- 'exec --ephemeral --skip-git-repo-check --sandbox %q ' "$reviewer_sandbox"
        for part in "${model_args[@]+"${model_args[@]}"}"; do printf '%q ' "$part"; done
        # self_hosted.py's reviewer branch requires a *.json output path
        # whenever a delivery file is in play ("file-backed reviewer
        # delivery requires a JSON output path") -- $output_target is
        # always *.json when delivery_mode=1 (that's what set delivery_mode
        # in the first place), so match it here too. A plain "output" (no
        # extension) tripped this on every candidate, in every lens, every
        # time, live on a real project -- confirmed by re-reading the
        # archived candidate logs there ("file-backed reviewer delivery
        # requires a JSON output path"), not merely a unit-test finding.
        if [[ "$delivery_mode" == 1 ]]; then
            printf -- '--output-last-message "$CANDIDATE_DIR/output.json" '
        else
            printf -- '--output-last-message "$CANDIDATE_DIR/output" '
        fi
        printf -- '"$(cat "$CANDIDATE_DIR/prompt.md")" < /dev/null > "$CANDIDATE_DIR/raw.jsonl" 2>&1\n'
        printf 'echo $? > "$CANDIDATE_DIR/status"\n'
    } > "$launch_script"

    local validate_script="$work_dir/validate.sh"
    {
        printf '#!/usr/bin/env bash\nset -uo pipefail\n'
        printf 'status_file="$CANDIDATE_DIR/status"\n'
        printf '[[ -f "$status_file" ]] || { echo "no status file"; exit 1; }\n'
        printf 'status="$(cat "$status_file")"\n'
        printf '[[ "$status" == "0" ]] || { echo "reviewer exited with status $status"; exit 1; }\n'
        # Final schema/kind validation stays a one-time, post-selection step
        # in run_codex_review's existing code below, run only against the
        # winner -- exactly the same split agent-side racing already makes.
        if [[ "$delivery_mode" == 1 ]]; then
            printf '[[ -s "$CANDIDATE_DIR/project/candidate-delivery.json" ]] || { echo "no delivery.json written"; exit 1; }\n'
            printf 'python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$CANDIDATE_DIR/project/candidate-delivery.json" || { echo "delivery.json is not valid JSON"; exit 1; }\n'
        else
            printf '[[ -s "$CANDIDATE_DIR/output" ]] || { echo "no output written"; exit 1; }\n'
        fi
    } > "$validate_script"
    chmod +x "$launch_script" "$validate_script"

    if [[ -n "${UNCLE_STATUS_FILE:-}" ]]; then
        local n
        for ((n = 0; n < count; n++)); do
            printf '{"event":"start","model":"%s","mode":"review","stage":"%s","stage_index":0,"stage_total":0,"stage_turns":0}\n' \
                "${model:-}" "${log_name}-candidate-${n}" >> "$UNCLE_STATUS_FILE"
        done
    fi

    local evidence_file="$LOG_DIR/${log_name}.candidate-race-evidence.json"
    local winner_dir status=0
    winner_dir="$(python3 -B "$ROOT/scripts/lib/candidate_race.py" run \
        --stage "$log_name" --count "$count" \
        --work-dir "$work_dir/candidates" \
        --launch-script "$launch_script" --validate-script "$validate_script" \
        --evidence "$evidence_file")" || status=$?

    if [[ -f "$evidence_file" ]]; then
        local candidate_total
        candidate_total="$(jq '.candidates | length' "$evidence_file" 2>/dev/null || echo 0)"
        local i
        for ((i = 0; i < candidate_total; i++)); do
            local entry cid cstatus celapsed cdir cexit clog
            entry="$(jq -c ".candidates[$i]" "$evidence_file")"
            cid="$(jq -r '.id' <<<"$entry")"
            cstatus="$(jq -r '.status' <<<"$entry")"
            celapsed="$(jq -r '.elapsed // 0' <<<"$entry")"
            cdir="$(jq -r '.directory // empty' <<<"$entry")"
            case "$cstatus" in
                validated-winner) cexit=0 ;;
                stopped-nonselected|stopped-timeout) cexit=130 ;;
                *) cexit=1 ;;
            esac
            clog="/dev/null"
            [[ -n "$cdir" && -f "$cdir/raw.jsonl" ]] && clog="$cdir/raw.jsonl"
            perf_record reviewer "${log_name}-candidate-${cid}" "$celapsed" "$cexit" "$clog" "$cmd" "$model" "$effort"
        done
    fi

    if [[ "$status" -ne 0 || -z "$winner_dir" ]]; then
        : > "$log_file"
        local candidate_dir
        for candidate_dir in "$work_dir"/candidates/candidate-*; do
            [[ -d "$candidate_dir" ]] || continue
            {
                printf '\n=== %s ===\n' "$candidate_dir"
                cat "$candidate_dir/raw.jsonl" 2>/dev/null
            } >> "$log_file"
        done
        return 1
    fi

    promote_winner_work "$winner_dir"

    # A reviewer's own stdout is plain text (self_hosted.py's `print(text)`
    # for side == 'reviewer'), not the agent side's JSON chat-event stream --
    # the non-race reviewer call above never pipes through
    # format_claude_stream either, only perf_stream | tee.
    cat "$winner_dir/raw.jsonl" | perf_stream "$log_name" | tee "$log_file"
    if [[ "$delivery_mode" == 1 ]]; then
        [[ -s "$winner_dir/project/candidate-delivery.json" ]] && cp "$winner_dir/project/candidate-delivery.json" "$output_target"
    else
        [[ -s "$winner_dir/output" ]] && cp "$winner_dir/output" "$output_target"
    fi
    return 0
}

run_codex_review() {
    local prompt_file
    prompt_file="$(resolve_prompt "$1")"
    local output_file="$2"
    local log_name="$3"

    require_file "$prompt_file"

    local cmd
    local UNCLE_RESOLVED_RUNNER
    uncle_resolve_stage_runner "$log_name" REVIEWER || return 1
    cmd="$(stage_reviewer_cmd "$log_name")" || return 1
    local -a client_cmd=("$cmd")
    case "${cmd##*/}" in
        claude|codex) client_cmd=(env -u UNCLE_STATUS_FILE -u UNCLE_PROJECT_ROOT -u UNCLE_CONFIG -u STAGEGATE_RUN_ID -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u DOCUMENT_BUDGET_SOURCE "$cmd") ;;
    esac
    if [[ -n "${UNCLE_RESOLVED_RUNNER:-}" && "$UNCLE_RESOLVED_RUNNER" != self-hosted ]] \
       && { [[ "${UNCLE_STEERING:-}" == 1 ]] \
            || { [[ "${UNCLE_RUNNER_REUSE:-1}" != 0 ]] && ! stage_command_overridden REVIEWER "$log_name"; }; }; then
        client_cmd=(python3 "$ROOT/scripts/lib/native_stage.py" --runner "$UNCLE_RESOLVED_RUNNER" --side reviewer --stage "$log_name" --)
    fi
    # A read-only panel lens on a hosted runner answers through the runner's structured output (scripts/lib/review-schema.sh).
    review_schema_setup "$prompt_file" "$log_name" "$output_file" "$([[ "${client_cmd[0]}" == python3 ]] && echo 1 || echo 0)"
    local review_schema="$REVIEW_SCHEMA_FILE"

    # Keep the reviewer read-only. The shell writes the reviewer's final
    # message into the designated review artifact.
    local model_args=()
    local model effort fallback="${CODEX_MODEL:-}"
    if uncle_has_config || [[ -n "${UNCLE_RESOLVED_RUNNER:-}" ]]; then fallback="$(uncle_stage_model "$log_name" "${UNCLE_RESOLVED_RUNNER-$(uncle_stage_runner "$log_name")}")"; fi
    if ! uncle_has_config; then fallback="${CODEX_MODEL-$fallback}"; fi
    model="$(stage_setting_opt MODEL "$log_name" "$fallback")"
    effort="$(stage_effort "$log_name")"
    [[ -z "$effort" ]] || model_args+=(-c "model_reasoning_effort=$effort")

    if [[ -n "$model" ]]; then
        model_args+=(-m "$model")
    fi

    # The reviewer writes a document a human reads, so it gets the output
    # rules the same way an agent stage does.
    if [[ "$log_name" != plan-executability ]]; then
        prompt_file="$(gated_prompt "$prompt_file" "$log_name" reviewer)"
    fi
    if [[ "$log_name" != plan-executability ]]; then
        case "$log_name" in *-worker-*|updated-plan|adversarial-review|test-review|manual-checklist|final-audit)
            ;;
        *)
            supervision_prompt "$prompt_file" "$log_name" "$LOG_DIR/${log_name}.log"
            prompt_file="$SUPERVISION_PROMPT"
        esac
    fi

    # Canonical JSON is file-backed workflow data, never a final chat reply.
    local delivery_file="" reviewer_sandbox="read-only"
    if [[ "$output_file" == *.json && -z "$review_schema" ]]; then
        mkdir -p "$STATE_DIR/artifact-delivery"
        delivery_file="${output_file}.delivery.json"
        rm -f "$delivery_file"
        { cat "$prompt_file"; printf '\n## Canonical JSON delivery (binding)\n\nUse your Write tool to create exactly one JSON object at `%s`. This is the only artifact the driver reads. Do not write or modify any other file. Chat text is diagnostics only.\n' "$delivery_file"; } > "$STATE_DIR/${log_name}-delivery-prompt.md"
        prompt_file="$STATE_DIR/${log_name}-delivery-prompt.md"
        reviewer_sandbox="workspace-write"
    fi
    if [[ -n "$review_schema" ]]; then
        printf '\n## Delivery (binding)\n\nYour final answer is the complete packet, delivered through the structured-output tool the runner provides. Do not write a file.\n' >> "$prompt_file"
    fi

    local review_key
    review_key="$(review_input_key "$output_file" "$prompt_file" "$cmd" "$model" "$effort" "$log_name")"
    if restore_plan_review "$output_file" "$review_key"; then
        if [[ "$log_name" == adversarial-review ]] && ! python3 "$ROOT/scripts/lib/adversarial-context.py" --validate-json . >/dev/null 2>&1; then
            echo 'Discarding cached adversarial review: canonical JSON is missing or invalid.'
            rm -f "$output_file"
        else
        if [[ "$log_name" != adversarial-review && "$log_name" != adversarial-review-investigate ]]; then
        finish_review_budget "$output_file" "$cmd" "$model" "$effort" "$log_name" || exit 1
    fi
        save_plan_review "$output_file" "$review_key"
        return 0
        fi
    fi

    echo
    echo "Launching reviewer ($cmd): $log_name"
    [[ -z "$model" ]] || echo "Model: $model"
    status_stage_context "$log_name" "${model:-}" review
    local status=0
    local started retry_answer empty_retried="" schema_error=""
    while true; do
        case "$log_name" in
            updated-plan*|preflight*)
                (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_archive_attempt "$LOG_DIR/${log_name}.log") || return 1 ;;
        esac
        started="$SECONDS"
        [[ -z "$review_schema" ]] || rm -f "$review_schema.out"
        local reviewer_candidates raced=0
        reviewer_candidates="$(self_hosted_candidate_count "$log_name")"
        if [[ "${UNCLE_RESOLVED_RUNNER:-}" == self-hosted && "$reviewer_candidates" -gt 1 ]]; then
            raced=1
            local delivery_mode=0
            [[ -n "$delivery_file" ]] && delivery_mode=1
            race_self_hosted_reviewer_candidates "$log_name" "$reviewer_candidates" "$prompt_file" \
                "$reviewer_sandbox" "$delivery_mode" "$output_file" "$LOG_DIR/${log_name}.log" || status=$?
        else
        # stdin is the operator's gate-answer channel, not stage input: codex
        # appends a non-TTY stdin to the prompt and would block on it forever.
        # Project dirs need not be git repos; the read-only sandbox is the boundary.
        env UNCLE_ARTIFACT_DELIVERY="$delivery_file" UNCLE_OUTPUT_SCHEMA_FILE="$review_schema" UNCLE_STRUCTURED_OUTPUT_PATH="${review_schema:+$review_schema.out}" "${client_cmd[@]}" exec \
            --ephemeral \
            --skip-git-repo-check \
            --sandbox "$reviewer_sandbox" \
            "${model_args[@]+"${model_args[@]}"}" \
            --output-last-message "$output_file" \
            "$(cat "$prompt_file")" \
            < /dev/null 2>&1 | perf_stream "$log_name" | tee "$LOG_DIR/${log_name}.log" || status=$?
        fi
        # race_self_hosted_reviewer_candidates already wrote $output_file
        # straight from the winning candidate's own delivery/output file;
        # $delivery_file itself (the live, non-candidate path) was never
        # touched by any candidate, so this legacy single-shot handling must
        # not re-inspect it and mistake a successful race for a missing
        # delivery.
        # A Codex lens answered through its output schema: the runner already restored the object into the structured-output file.
        if [[ -n "$review_schema" && -s "$review_schema.out" ]]; then cp "$review_schema.out" "$output_file"; fi
        if [[ "$raced" != 1 && -n "$delivery_file" ]]; then
            if [[ -s "$delivery_file" ]]; then
                cp "$delivery_file" "$output_file"
            else
                # Leave output_file missing rather than failing here directly:
                # the empty-output retry below already exists and is proven
                # for exactly this shape (exit 0, nothing written, a chat-only
                # narration instead) -- it was only ever reachable for the
                # legacy non-delivery-file path. A weak self-hosted worker
                # narrating "the file has been written successfully" while
                # never calling Write is the same failure, and previously
                # skipped straight to status=1 with no retry at all, which is
                # fatal for a noninteractive panel worker (immediate return).
                echo "Reviewer $log_name did not write its required canonical JSON delivery: $delivery_file" >&2
                rm -f "$output_file"
            fi
        fi
        schema_error=""
        if [[ "$status" == 0 ]] && [[ -s "$output_file" ]]; then
            if ! schema_error="$(normalize_reviewer_packet "$output_file" "$cmd" 2>&1)"; then
                status=1
            elif ! schema_error="$(validate_reviewer_artifact "$output_file" "$cmd" 2>&1)"; then
                status=1
            fi
        fi
        perf_record reviewer "$log_name" "$((SECONDS-started))" "$status" \
            "$LOG_DIR/${log_name}.log" "$cmd" "$model" "$effort"
        supervision_stage_end "$log_name" "$status" "$LOG_DIR/${log_name}.log"

        if [[ "$status" -ne 0 || ! -s "$output_file" ]] && context_exhausted "$LOG_DIR/${log_name}.log"; then
            echo
            echo "The reviewer ran out of context/tokens."
            echo "Change the reviewer model (Configure → reviewer) and re-run to resume this stage."
        fi

        # A reviewer that exits successfully but writes nothing -- a
        # conversational summary asking for guidance instead of the document
        # -- is not done, whatever its own transcript claims. Left as a plain
        # exit-0 with no output, this used to reach a later validation state
        # that only checks what this stage already produced, with no path
        # back to re-running it: "resume" alone could never recover. One
        # bounded, silent retry with the same prompt plus a note of what
        # happened; a second empty result is treated like any other failure
        # below (including the panel-worker/non-interactive return path).
        if [[ "$status" == 0 && ! -s "$output_file" ]]; then
            if [[ -z "$empty_retried" ]]; then
                empty_retried=1
                echo
                echo "Reviewer $log_name exited successfully but wrote no $output_file; retrying once."
                {
                    cat "$prompt_file"
                    printf '\n\n## Required retry\n\nThe previous attempt ended without writing %s at all -- a status summary or a request for guidance is not a substitute for it. Write the complete document now. This driver is unattended; nobody will answer a question left open.\n' "$output_file"
                } > "$STATE_DIR/${log_name}-empty-retry-prompt.md"
                prompt_file="$STATE_DIR/${log_name}-empty-retry-prompt.md"
                continue
            fi
            status=1
        fi

        # calculator-local/issue-98 (2026-09-28): a worker that DID write a
        # file, but in a shape it invented instead of the required schema --
        # e.g. keying rows by acceptance-criterion name with status/verified
        # fields, not the {schema,kind,findings:[{id,summary,evidence}]}
        # worker-packet envelope. This previously went straight to status=1
        # with no retry, same dead end as the empty-output case above. One
        # bounded retry, with the exact schema error the driver already has,
        # same one-shot budget as that case.
        if [[ "$status" != 0 && -n "$schema_error" && -s "$output_file" ]]; then
            if [[ -z "$empty_retried" ]]; then
                empty_retried=1
                echo
                echo "Reviewer $log_name wrote $output_file in the wrong shape; retrying once with the exact schema error."
                {
                    cat "$prompt_file"
                    printf '\n\n## Required retry\n\nThe previous attempt wrote %s, but the driver rejected it:\n\n%s\n\nWrite the complete document again, in exactly the required schema -- not a shape you invent, whatever seems reasonable for the content. This driver is unattended; nobody will answer a question left open.\n' "$output_file" "$schema_error"
                } > "$STATE_DIR/${log_name}-schema-retry-prompt.md"
                prompt_file="$STATE_DIR/${log_name}-schema-retry-prompt.md"
                rm -f "$output_file"
                status=0
                continue
            fi
        fi

        [[ "$status" != 0 ]] || break
        # Panel workers are detached and have no operator stdin.  A failed
        # packet is advisory, so return it to the panel coordinator instead of
        # trying to open an unreachable retry prompt.
        [[ "${UNCLE_NONINTERACTIVE:-0}" == 1 ]] && return "$status"
        gate_prompt "Reviewer $log_name failed (exit $status). Retry this reviewer stage? [Y/N]"
        if ! { if declare -f gate_read > /dev/null; then gate_read retry_answer; else IFS= read -r retry_answer; fi; }; then return "$status"; fi
        case "$retry_answer" in y|Y) status=0 ;; *) return "$status" ;; esac
    done
    require_file "$output_file"
    [[ "$log_name" != plan-executability ]] || return 0
    # Do not reuse results if inputs changed while the reviewer was reading them.
    if [[ -n "$review_key" && "$review_key" == "$(review_input_key "$output_file" "$prompt_file" "$cmd" "$model" "$effort" "$log_name")" ]]; then
        save_plan_review "$output_file" "$review_key"
    else
        review_key=""
    fi
    if [[ "$log_name" != adversarial-review && "$log_name" != adversarial-review-investigate ]]; then
        finish_review_budget "$output_file" "$cmd" "$model" "$effort" "$log_name" || exit 1
    fi
    save_plan_review "$output_file" "$review_key"
}

# Validate and, if necessary, retry a lens as soon as its packet exists.
# This stays inside the speculative stage: no partial review is published or
# handed to plan writers. Collation and all approval checks remain barriers.
run_adversarial_review_lens() {
    local directory="$1" lens="$2" output retry_output packet_error reviewer_pid
    # Keep the original reviewer in its own unguarded subprocess: guarding a
    # shell function with || true disables errexit throughout that function.
    ( UNCLE_NONINTERACTIVE=1 run_codex_review "$directory/prompts/$lens.md" \
        "$directory/$lens.json" "adversarial-review-worker-$lens" < /dev/null ) &
    reviewer_pid=$!
    wait "$reviewer_pid" || true
    output="$directory/$lens.json"
    retry_output="$directory/$lens.validated.json"
    if ! packet_error="$(python3 "$ROOT/scripts/lib/worker_packets.py" "$directory" "$retry_output" \
            --kind adversarial-review-worker-packet --expected "$lens" 2>&1)"; then
        echo "Adversarial-review worker $lens returned an invalid packet; retrying that worker once."
        printf '\n## Required retry\n\nYour preceding private packet was rejected: %s\nUse Write to replace the assigned packet path with one complete `adversarial-review-worker-packet` JSON object. Do not return Markdown, prose, or a draft in chat.\n' "$packet_error" >> "$directory/prompts/$lens.md"
        rm -f "$output" "$output.delivery.json" "$retry_output"
        UNCLE_NONINTERACTIVE=1 run_codex_review "$directory/prompts/$lens.md" "$output" "adversarial-review-worker-$lens-retry" < /dev/null || true
        python3 "$ROOT/scripts/lib/worker_packets.py" "$directory" "$retry_output" \
            --kind adversarial-review-worker-packet --expected "$lens" || return 1
    fi
    rm -f "$retry_output"
}

# Read-only specialist packets improve review coverage. Only the complete,
# validated panel can produce the canonical review.
run_adversarial_review_panel() {
    local directory="$STATE_DIR/adversarial-review-panel" lens prompt output pid failed=0 lenses
    lenses="$(change_class_lenses 'requirements regression security testability')"
    local -a pids=()
    [[ "${WORKFLOW_ADVERSARIAL_REVIEW_PANEL:-1}" == 1 ]] || return 0
    ensure_project_plan_json || return 1
    rm -rf "$directory"
    mkdir -p "$directory/prompts"
    # The plan as data (docs/plan-model.md): sections of blocks and rows with ids, no Markdown narrative.  Off by default
    # until a live run has compared the findings it produces; WORKFLOW_AGENT_PLAN_VIEW=1 turns it on.
    local plan_input=".uncle/workflow/documents/PROJECT_PLAN.json" plan_input_note=""
    if [[ "${WORKFLOW_AGENT_PLAN_VIEW:-0}" == 1 ]] \
            && python3 -B "$ROOT/scripts/lib/plan_model.py" view "$STATE_DIR/documents/PROJECT_PLAN.json" "$directory/plan-view.json" 2>/dev/null; then
        plan_input="$directory/plan-view.json"
        plan_input_note=' That file is the plan as JSON: sections of blocks, with rows, list items and steps that each have an `id`. Cite those ids.'
    fi
    local slices
    . "$ROOT/scripts/lib/model-jobs.sh"
    slices="$(python3 -B "$ROOT/scripts/lib/adversarial_slices.py" count "$(workflow_model_runner adversarial-review REVIEWER)")" || return 1
    # Slices replace the four whole lenses; a build class that trims the lens set keeps whole lenses.
    if [[ "$slices" -gt 1 && "$lenses" == "requirements regression security testability" ]]; then
        . "$ROOT/scripts/lib/adversarial-slices.sh"
        run_adversarial_review_slices "$directory" "$plan_input" \
            "$STATE_DIR/documents/REQUIREMENTS_INTERPRETATION.json" "$slices" new || return 1
    else
    for lens in $lenses; do
        prompt="$directory/prompts/$lens.md"
        output="$directory/$lens.json"
        cp "$ROOT/prompts/change/adversarial-review-worker.md" "$prompt"
        printf '\n## Canonical inputs (binding)\n\nRead only `.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json` and `%s`.%s\n\n## Assigned review lens\n\nFocus only on **%s**.\n' "$plan_input" "$plan_input_note" "$lens" >> "$prompt"
        ( . "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_enter adversarial-review REVIEWER || exit 1; run_adversarial_review_lens "$directory" "$lens" ) \
            > "$LOG_DIR/adversarial-review-worker-$lens.log" 2>&1 &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do
        if ! wait "$pid"; then
            echo 'Adversarial-review worker failed validation; stopping the panel.' >&2
            failed=1
        fi
    done
    [[ "$failed" == 0 ]] || return 1
    fi
    python3 "$ROOT/scripts/lib/worker_packets.py" "$directory" "$STATE_DIR/documents/ADVERSARIAL_REVIEW_WORKERS.json" --kind adversarial-review-worker-packet --expected $lenses || return 1
    # Worker packets are already validated, complete, and deduplicated by
    # stable finding ID.  Rendering them directly makes the collated JSON the
    # sole authoritative review and avoids asking a weak parent model to
    # restate the same evidence as a Markdown investigation followed by a
    # second formatting pass.  This also lets a speculative review succeed
    # without a parent response that can be merely narration.
    python3 -B "$ROOT/scripts/lib/adversarial_packets.py" . || return 1
}

run_updated_plan_panel() {
    (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_archive_stage updated-plan) || return 1
    local directory="$STATE_DIR/updated-plan-panel" lens prompt output pid
    local -a pids=()
    [[ "${WORKFLOW_UPDATED_PLAN_PANEL:-1}" == 1 ]] || return 0
    ensure_project_plan_json || return 1
    require_file "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" || return 1
    echo "Updated-plan review panel: launching its workers in parallel."
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    # The dispositions lens is split by finding when the review is long (see updated_plan_slices.py).
    local ids; local -a names=()
    while IFS=$'\t' read -r lens ids; do
        names+=("$lens")
        prompt="$directory/prompts/$lens.md"; output="$directory/$lens.json"
        cp "$ROOT/prompts/change/updated-plan-review-worker.md" "$prompt"
        printf '\n## Assigned review lens\n\nFocus only on **%s**.\n' "${lens%%-*}" >> "$prompt"
        [[ -z "$ids" ]] || printf '\nYour findings: %s. Report only these finding IDs.\n' "${ids//,/, }" >> "$prompt"
        ( . "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_enter updated-plan REVIEWER || exit 1; UNCLE_NONINTERACTIVE=1 run_codex_review "$prompt" "$output" "updated-plan-review-worker-$lens" < /dev/null ) > "$LOG_DIR/updated-plan-worker-$lens.log" 2>&1 &
        pids+=("$!")
    done < <(python3 -B "$ROOT/scripts/lib/updated_plan_slices.py" "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json")
    for pid in "${pids[@]}"; do wait "$pid" || echo 'Updated-plan worker failed; canonical packet validation will stop the panel.' >&2; done
    python3 "$ROOT/scripts/lib/updated_plan_worker_packets.py" "$directory" "$STATE_DIR/documents/UPDATED_PLAN_WORKERS.json" \
        --expected "${names[@]}" || return 1
    # The parent receives a sealed input file, not paths it must rediscover.
    # In particular, do not let a missing/partial worker output degrade into a
    # broad agent search that burns its turn budget without writing a plan.
    echo "Updated-plan review panel: worker packets collected; preparing sealed synthesis input."
    UPDATED_PLAN_PROMPT="$directory/synthesis.md"
    python3 -B "$ROOT/scripts/lib/updated_plan_synthesis_prompt.py" \
        "$STATE_DIR/documents/PROJECT_PLAN.json" \
        "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" \
        "$STATE_DIR/documents/UPDATED_PLAN_WORKERS.json" \
        "$UPDATED_PLAN_PROMPT" || return 1
}

# Resolve the findings in parallel, one writer per run of findings, and merge their patches without a
# model (see updated_plan_edits.py).  Any problem returns nonzero before anything is published, and the
# caller runs the single synthesis call. Self-hosted work uses a bounded pool.
# Edits that overlap go to one short resolver call (WORKFLOW_UPDATED_PLAN_EDITS=0 turns the whole thing off).
# Start one updated-plan edit writer in the background (see run_updated_plan_edit_writers); `owner` is passed
# for the writer that also owns the protected verification paths.
# Wait for the first writer to be well under way (its first model event, or a fixed time) so the others can reuse its prompt prefix
# from the cache.  WORKFLOW_PREFIX_WARM_SECONDS: 0 turns it off; default 12 s hosted, off self-hosted (no event arrives until the
# whole answer does).  Only worth it when several writers follow.
updated_plan_warm_prefix() {
    local name="$1" total="$2" limit="${WORKFLOW_PREFIX_WARM_SECONDS:-}" waited=0 log
    [[ "$total" -ge 4 ]] || return 0
    if [[ -z "$limit" ]]; then
        # Self-hosted: off.  Measured on the calculator-local vLLM server, eleven simultaneous cold 12.7k-token prompts all
        # finished in 6.5 s (one prefill is batched across them), while a warm-first start took 5.5 s + 1.8 s = 7.3 s, and the
        # tokens are free there.  The time on a local server is decoding, not prefill.
        if stage_uses_self_hosted updated-plan AGENT; then limit=0; else limit=12; fi
    fi
    [[ "$limit" -gt 0 ]] 2>/dev/null || return 0
    log="$LOG_DIR/updated-plan-worker-edits-$name.jsonl"
    echo "Updated plan: writer $name goes first so the others can reuse its prompt from the cache (up to ${limit}s)."
    while (( waited < limit )); do
        if ! stage_uses_self_hosted updated-plan AGENT && grep -q '"type": *"assistant"' "$log" 2>/dev/null; then break; fi
        sleep 1; waited=$((waited + 1))
    done
}

updated_plan_launch_writer() {
    local directory="$1" delivery="$2" name="$3" ids="$4" owner="$5" schema_file=""
    . "$ROOT/scripts/lib/model-jobs.sh"
    workflow_archive_attempt "$LOG_DIR/updated-plan-worker-edits-$name.log" "$LOG_DIR/updated-plan-worker-edits-$name.jsonl" "$directory/$name.json" || return 1
    # The plan model (docs/plan-model.md): writers edit it by id.  WORKFLOW_UPDATED_PLAN_OPS=0 keeps the text patches.
    local helper="$ROOT/scripts/lib/updated_plan_edits.py" schema_command=edit
    if [[ "${WORKFLOW_UPDATED_PLAN_OPS:-1}" == 1 ]]; then helper="$ROOT/scripts/lib/updated_plan_ops.py"; schema_command=edit-ops; fi
    UNCLE_PLAN_JSON="$STATE_DIR/documents/PROJECT_PLAN.json" python3 -B "$helper" prompt "$UPDATED_PLAN_PROMPT" "$ids" "$directory/prompts/$name.md" $owner || return 1
    echo "Updated-plan edit writer $name: ${ids//,/, }"
    if [[ "$delivery" == hosted || "$schema_command" == edit-ops ]]; then
        mkdir -p "$directory/schemas"
        schema_file="$directory/schemas/$name.json"
        local scope_args=()
        [[ "$schema_command" != edit-ops ]] || scope_args=(--scope "$directory/prompts/$name.scope.json")
        if [[ "$schema_command" == edit-ops ]] && stage_uses_self_hosted updated-plan AGENT; then scope_args+=(--attempt "${UNCLE_UPDATED_PLAN_SCHEMA_ATTEMPT:-first}"); fi
        python3 -B "$ROOT/scripts/lib/worker_schemas.py" "$schema_command" "$STATE_DIR/documents/PROJECT_PLAN.json" "$schema_file" $owner ${scope_args[@]+"${scope_args[@]}"} || return 1
    fi
    local writer_turns answer_tokens
    read -r writer_turns answer_tokens < <(python3 -B "$ROOT/scripts/lib/updated_plan_ops.py" budget "$ids" "$(. "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_granularity updated-plan)")
    [[ -n "$writer_turns" && -n "$answer_tokens" ]] || return 1
    (( writer_turns > 0 )) || writer_turns=""
    rm -f "$directory/$name.json"
    ( . "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_enter updated-plan AGENT || exit 1; [[ -z "$schema_file" ]] || export UNCLE_WORKER_SCHEMA_FILE="$schema_file"; [[ "$delivery" != hosted || -z "$schema_file" ]] || export UNCLE_OUTPUT_SCHEMA_FILE="$schema_file" UNCLE_STRUCTURED_OUTPUT_PATH="$directory/$name.json"
      export UNCLE_UPDATED_PLAN_ATTEMPTS_DIR="$directory" UNCLE_UPDATED_PLAN_FINDINGS="$ids"
      export UNCLE_WORKER_MAX_TURNS="$writer_turns" UNCLE_UPDATED_PLAN_ANSWER_TOKENS="$answer_tokens"
      local writer_status=0
      trap 'writer_status=$?; if [[ "$writer_status" != 0 ]]; then workflow_writer_failure "updated-plan-worker-edits-$name" "$writer_status"; fi; workflow_model_leave; exit "$writer_status"' EXIT
      ( UNCLE_WORKER_PACKET_PATH="$directory/$name.json" SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 \
        workflow_model_writer updated-plan run_claude "$directory/prompts/$name.md" "updated-plan-worker-edits-$name" ) || writer_status=$?
      if [[ "$writer_status" == 124 || "$writer_status" == 137 ]]; then exit "$writer_status"; fi
      if [[ "${WORKFLOW_UPDATED_PLAN_OPS:-1}" == 1 ]]; then
          if [[ ! -s "$directory/$name.json" ]]; then
              python3 -B "$ROOT/scripts/lib/structured_output.py" recover "$LOG_DIR/updated-plan-worker-edits-$name.jsonl" "$directory/$name.json" 2>/dev/null || true
          fi
          python3 -B "$ROOT/scripts/lib/updated_plan_ops.py" capture "$directory/$name.json" || exit "$((writer_status == 0 ? 1 : writer_status))"
          local validation_status=0
          if stage_uses_self_hosted updated-plan AGENT; then
              python3 -B "$helper" check-writer "$STATE_DIR/documents/PROJECT_PLAN.json" "$directory/$name.json" "$ids" 2> "$directory/prompts/$name.rejection" || validation_status=$?
          fi
          [[ "$validation_status" == 0 || "$validation_status" == 5 ]] || exit "$validation_status"
          if [[ "$validation_status" == 5 ]]; then
              cat "$directory/prompts/$name.rejection" >&2
              workflow_writer_failure "updated-plan-worker-edits-$name" "$validation_status" "schema rejection"
              workflow_archive_attempt "$directory/$name.json" "$LOG_DIR/updated-plan-worker-edits-$name-retry.jsonl" || exit 1
              cp "$directory/prompts/$name.md" "$directory/prompts/$name.retry.md"
              printf '\n\n## Your previous answer was rejected\n\n' >> "$directory/prompts/$name.retry.md"
              cat "$directory/prompts/$name.rejection" >> "$directory/prompts/$name.retry.md"
              python3 -B "$ROOT/scripts/lib/worker_schemas.py" edit-ops "$STATE_DIR/documents/PROJECT_PLAN.json" "$schema_file" $owner --scope "$directory/prompts/$name.scope.json" --attempt retry || exit 1
              rm -f "$directory/$name.json"
              writer_status=0
              ( UNCLE_WORKER_PACKET_PATH="$directory/$name.json" SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 \
                UNCLE_UPDATED_PLAN_CHEAP_RETRY=1 workflow_model_writer updated-plan run_claude "$directory/prompts/$name.retry.md" "updated-plan-worker-edits-$name-retry" ) || writer_status=$?
              if [[ "$writer_status" == 124 || "$writer_status" == 137 ]]; then exit "$writer_status"; fi
              if [[ ! -s "$directory/$name.json" ]]; then
                  python3 -B "$ROOT/scripts/lib/structured_output.py" recover "$LOG_DIR/updated-plan-worker-edits-$name-retry.jsonl" "$directory/$name.json" 2>/dev/null || true
              fi
              python3 -B "$helper" capture "$directory/$name.json" || exit "$((writer_status == 0 ? 1 : writer_status))"
              python3 -B "$helper" check-writer "$STATE_DIR/documents/PROJECT_PLAN.json" "$directory/$name.json" "$ids" 2> "$directory/prompts/$name.rejection" || {
                  cat "$directory/prompts/$name.rejection" >&2
                  workflow_writer_failure "updated-plan-worker-edits-$name" 5 "schema rejection"
                  exit 5
              }
          fi
      else
          [[ "$writer_status" == 0 ]] || exit "$writer_status"
      fi ) \
        > "$LOG_DIR/updated-plan-worker-edits-$name.log" 2>&1 &
}

UPDATED_PLAN_ADVISOR_PIDS=()
run_updated_plan_edit_writers() {
    local directory="$STATE_DIR/updated-plan-edits" helper="$ROOT/scripts/lib/updated_plan_edits.py" name ids pid failed=0 resolve_command=resolve
    local -a pids=() names=()
    . "$ROOT/scripts/lib/model-jobs.sh"
    local jobs
    jobs="$(workflow_writer_jobs updated-plan)"
    [[ "${WORKFLOW_UPDATED_PLAN_EDITS:-1}" == 1 ]] || return 1
    if [[ "${WORKFLOW_UPDATED_PLAN_OPS:-1}" == 1 ]]; then helper="$ROOT/scripts/lib/updated_plan_ops.py"; resolve_command=resolve-ops; fi
    # Forced, schema-checked JSON wherever the runner can enforce it: hosted Claude through --json-schema, a
    # self-hosted model through the grammar its adapter derives from the packet kind named in the prompt.
    # A caller can deliberately select the universally-supported file handoff.
    # This is important for the bounded updated-plan fan-out: nested native
    # structured-output sessions have failed before emitting an event, while
    # the private Write-path packet contract is used successfully by every
    # runner.  The packet is parsed and semantically merged below, so chat is
    # still never an artifact source.
    local delivery="${WORKFLOW_UPDATED_PLAN_WRITER_DELIVERY:-auto}"
    case "$delivery" in
        file|local|hosted) ;;
        auto)
            delivery=file
            if stage_supports_structured_output updated-plan-worker-edits-1; then
                delivery=hosted
            elif stage_uses_self_hosted updated-plan AGENT; then
                delivery=local
            fi
            ;;
        *)
            echo "Invalid WORKFLOW_UPDATED_PLAN_WRITER_DELIVERY: $delivery" >&2
            return 1
            ;;
    esac
    . "$ROOT/scripts/lib/model-jobs.sh"
    workflow_terminal_failure && return 1
    workflow_archive_attempt "$directory" || return 1
    [[ -f "${UPDATED_PLAN_PROMPT:-}" ]] || return 1
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    cp "$STATE_DIR/documents/PROJECT_PLAN.json" "$directory/base-plan.json" || return 1
    printf '%s\n' "${helper##*/}" > "$directory/merge-helper"
    python3 -B "$helper" slices "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" > "$directory/slices.tsv" || return 1
    [[ -s "$directory/slices.tsv" ]] || return 1
    local -a ids_of=() owner_of=() started=() hedge=() finished=()
    local index=0
    while IFS=$'\t' read -r name ids; do
        # Do not put a false test in a command substitution assignment.  With
        # the driver's `set -e`, the second slice's false `[[ name == 1 ]]`
        # used to terminate the entire parent immediately after writer 1
        # launched, leaving no worker error or packet to diagnose.
        if [[ "$name" == 1 ]]; then
            owner_of[index]=owner
        else
            owner_of[index]=''
        fi
        ids_of[index]="$ids"
        workflow_model_slot "$jobs" ${pids[@]+"${pids[@]}"}
        updated_plan_launch_writer "$directory" "$delivery" "$name" "$ids" "${owner_of[index]}" || {
            workflow_model_drain "$jobs" ${pids[@]+"${pids[@]}"}; return 1
        }
        pids+=("$!"); names+=("$name"); started[index]="$SECONDS"; hedge[index]=""; finished[index]=0
        # The writers' prompts are the same for 97% of their length, and a prefix cache (hosted Claude's, or vLLM's) can only
        # serve a prefix a finished request has already computed.  Started all at once, every writer computes (and a hosted one
        # pays to write) the same 64k tokens.  So the first writer that shares the prefix (the owner's differs early) goes
        # alone for a short while, and the others find the prefix cached.
        if [[ "$index" == 1 && "${#pids[@]}" == 2 ]]; then
            updated_plan_warm_prefix "$name" "$(wc -l < "$directory/slices.tsv" | tr -d ' ')"
        fi
        index=$((index + 1))
    done < "$directory/slices.tsv"
    local -a failed_names=()
    local total="${#pids[@]}" left="${#pids[@]}" i status hedge_after="${WORKFLOW_UPDATED_PLAN_HEDGE_SECONDS:-35}"
    # Duplicate attempts consume the self-hosted pool's capacity without covering
    # another finding. Keep hedging restricted to hosted runners.
    if stage_uses_self_hosted updated-plan AGENT; then hedge_after=999999; fi
    # Join the writers.  A writer is mostly hidden reasoning and a few run several times longer than the rest
    # (noinit: one finding, no output at all for 80+ s while its 19 siblings finished in 8-20 s), and the stage
    # waits for the slowest.  Once half have finished, a writer still running after $hedge_after s gets an identical
    # twin; whichever delivers first is used and the other is stopped.
    while (( left > 0 )); do
        for i in "${!pids[@]}"; do
            [[ "${finished[i]}" == 0 ]] || continue
            if ! kill -0 "${pids[i]}" 2>/dev/null; then
                status=0; wait "${pids[i]}" || status=$?
                # A writer can exit cleanly with a packet that does not parse (a local model dropped a comma): that
                # is a failed writer, asked again per finding, not a reason to abandon every other writer's work.
                if [[ "$status" == 0 ]] && ! python3 -B -c 'import json,sys; json.load(open(sys.argv[1]))' "$directory/${names[i]}.json" 2>/dev/null; then
                    echo "Updated-plan edit writer ${names[i]} delivered a packet that is not valid JSON." >&2
                    status=1
                fi
                if [[ "$status" == 0 ]]; then
                    finished[i]=1; left=$((left - 1))
                    [[ -z "${hedge[i]}" ]] || { pkill -P "${hedge[i]}" 2>/dev/null; kill "${hedge[i]}" 2>/dev/null; }
                    [[ "${names[i]}" != *h ]] || cp "$directory/${names[i]}.json" "$directory/${names[i]%h}.json"
                elif [[ -n "${hedge[i]}" ]] && kill -0 "${hedge[i]}" 2>/dev/null; then
                    pids[i]="${hedge[i]}"; hedge[i]=""; names[i]="${names[i]}h"   # the twin is now the writer
                else
                    echo "Updated-plan edit writer ${names[i]} did not complete." >&2
                    finished[i]=1; left=$((left - 1)); failed_names+=("${names[i]%h}")
                fi
            elif [[ -n "${hedge[i]}" ]] && ! kill -0 "${hedge[i]}" 2>/dev/null; then
                status=0; wait "${hedge[i]}" || status=$?
                if [[ "$status" == 0 && -s "$directory/${names[i]}h.json" ]]; then
                    cp "$directory/${names[i]}h.json" "$directory/${names[i]}.json"
                    pkill -P "${pids[i]}" 2>/dev/null; kill "${pids[i]}" 2>/dev/null
                    echo "Updated-plan edit writer ${names[i]}: its twin delivered first."
                    finished[i]=1; left=$((left - 1))
                fi
                hedge[i]=""
            elif [[ -z "${hedge[i]}" && "${names[i]}" != *h && $((total - left)) -ge $(((total + 1) / 2)) \
                    && $((SECONDS - started[i])) -ge "$hedge_after" ]]; then
                echo "Updated-plan edit writer ${names[i]} is slow; starting a twin."
                updated_plan_launch_writer "$directory" "$delivery" "${names[i]}h" "${ids_of[i]}" "${owner_of[i]}" || true
                hedge[i]="$!"
            fi
        done
        (( left > 0 )) && sleep 1
    done
    if [[ "${#failed_names[@]}" -gt 0 ]]; then
        # A writer that delivered nothing usable (its own JSON would not parse) is asked again as one writer per
        # finding: less text to escape, a fresh attempt each, all at once.  Anything that fails again is final.
        # An account limit (session, usage or rate) fails every call alike: more calls only burn time, so stop
        # here and let the caller's single call report it.
        local limited name_failed
        for name_failed in "${failed_names[@]}"; do
            if grep -qiE "hit your (session|usage) limit|usage limit|rate.?limit|too many requests|quota" "$LOG_DIR/updated-plan-worker-edits-$name_failed.log" 2>/dev/null; then
                echo "Updated-plan edit writers stopped by an account limit: $(grep -hiE 'limit|quota' "$LOG_DIR/updated-plan-worker-edits-$name_failed.log" | head -1)" >&2
                return 1
            fi
        done
        echo "Updated-plan edit writer(s) ${failed_names[*]} failed; asking again, one finding at a time."
        pids=(); names=()
        local rows retry_ids=()
        rows="$(python3 -B "$helper" resplit "$directory/slices.tsv" "${failed_names[@]}")" || return 1
        while IFS=$'\t' read -r name ids; do
            [[ -n "$name" ]] || continue
            local retry_owner=''
            if [[ "$name" == 1 || "$name" == 1-1 ]]; then
                retry_owner=owner
            fi
            workflow_model_slot "$jobs" ${pids[@]+"${pids[@]}"}
            UNCLE_UPDATED_PLAN_CHEAP_RETRY="$(stage_uses_self_hosted updated-plan AGENT && echo 1)" \
            UNCLE_UPDATED_PLAN_SCHEMA_ATTEMPT=retry updated_plan_launch_writer "$directory" "$delivery" "$name" "$ids" "$retry_owner" || {
                workflow_model_drain "$jobs" ${pids[@]+"${pids[@]}"}; return 1
            }
            pids+=("$!"); names+=("$name"); retry_ids+=("$ids")
        done <<< "$rows"
        local again=()
        for pid in "${!pids[@]}"; do
            wait "${pids[$pid]}" || { echo "Updated-plan edit writer ${names[$pid]} did not complete again." >&2; again+=("$pid"); }
        done
        if [[ "${#again[@]}" -gt 0 ]]; then
            # Every packet that landed is kept. A finding that failed twice gets one last try by the
            # other delivery path (schema-first <-> tool loop) before the whole stage is redone: in
            # run 14 two such findings discarded eighteen good packets and restarted the stage twice.
            local previous="${WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST-}" had_previous=0 last_pids=() last_names=() index
            [[ -n "${WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST+x}" ]] && had_previous=1
            if stage_uses_self_hosted updated-plan AGENT; then export WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST=off
            elif [[ "${previous:-on}" == off ]]; then export WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST=on
            else export WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST=off; fi
            echo "Updated-plan edit writer(s) failed again; one last try each by the other delivery path."
            for index in "${again[@]}"; do
                workflow_model_slot "$jobs" ${last_pids[@]+"${last_pids[@]}"}
                updated_plan_launch_writer "$directory" "$delivery" "${names[$index]}" "${retry_ids[$index]}" "$([[ "${names[$index]}" == 1 || "${names[$index]}" == 1-1 ]] && echo owner)" || failed=1
                last_pids+=("$!"); last_names+=("${names[$index]}")
            done
            for index in "${!last_pids[@]}"; do
                wait "${last_pids[$index]}" || {
                    echo "Updated-plan edit writer ${last_names[$index]} did not complete by either path." >&2
                    python3 -B "$ROOT/scripts/lib/updated_plan_defer.py" writer "$directory" "${last_names[$index]}" updated-plan || failed=1
                }
            done
            if [[ "$had_previous" == 1 ]]; then export WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST="$previous"
            else unset WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST; fi
        fi
        if [[ "$failed" != 0 ]]; then
            if stage_uses_self_hosted updated-plan AGENT; then
                : > "$STATE_DIR/updated-plan-writers-exhausted"
                printf '%s\n' 'updated-plan: writer attempts exhausted' > "$STATE_DIR/stop-reason"
                echo 'Updated-plan writer attempts exhausted; completed packets retained for diagnosis.' >&2
            else
                workflow_writer_exhausted updated-plan
            fi
            return 1
        fi
    fi
    # When the specialists ran beside the writers (run_updated_plan_decide), one reconciler checks their corrections
    # against what the writers decided, while the merge and the resolvers run; its edits are added last.
    local reconcile_pid="" late_ops=""
    if [[ "${#UPDATED_PLAN_ADVISOR_PIDS[@]}" -gt 0 ]]; then
        late_ops="$directory/reconcile.json"
        updated_plan_start_reconcile "$directory" "$delivery" "$late_ops"
        reconcile_pid="$UPDATED_PLAN_RECONCILE_PID"
    fi
    local merge_status=0
    python3 -B "$helper" merge "$STATE_DIR/documents/PROJECT_PLAN.json" "$directory/slices.tsv" "$directory" "$directory/merged.json" || merge_status=$?
    if [[ "$merge_status" == 0 && -n "$reconcile_pid" ]]; then
        wait "$reconcile_pid" 2>/dev/null || true
        if [[ -s "$late_ops" ]]; then
            UNCLE_LATE_OPS="$late_ops" python3 -B "$helper" merge "$STATE_DIR/documents/PROJECT_PLAN.json" "$directory/slices.tsv" "$directory" "$directory/merged.json" || return 1
        fi
    fi
    if [[ "$merge_status" == 3 ]]; then
        # Only the overlapping edits go to a model, with the text around them; the rest stays mechanical.
        echo "Updated-plan edits overlap; one small resolver call per overlapping group, all at once."
        local group_prompt group_id resolver_failed=0
        local resolver_granularity
        resolver_granularity="$(. "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_granularity updated-plan)" || return 1
        pids=(); names=()
        for group_prompt in "$directory"/prompts/resolve-*.md; do
            group_id="${group_prompt##*/resolve-}"; group_id="${group_id%.md}"
            local resolver_schema=""
            if [[ "$delivery" == hosted || "$resolve_command" == resolve-ops ]]; then
                resolver_schema="$directory/schemas/resolve-$group_id.json"
                mkdir -p "$directory/schemas"
                local scope_args=()
                [[ "$resolve_command" != resolve-ops ]] || scope_args=(--scope "$directory/prompts/resolve-$group_id.scope.json")
                if [[ "$resolve_command" == resolve-ops ]] && stage_uses_self_hosted updated-plan AGENT; then scope_args+=(--attempt first); fi
                python3 -B "$ROOT/scripts/lib/worker_schemas.py" "$resolve_command" "$STATE_DIR/documents/PROJECT_PLAN.json" "$resolver_schema" ${scope_args[@]+"${scope_args[@]}"} || return 1
            fi
            workflow_model_slot "$jobs" ${pids[@]+"${pids[@]}"}
            ( . "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_enter updated-plan AGENT || exit 1; [[ -z "$resolver_schema" ]] || export UNCLE_WORKER_SCHEMA_FILE="$resolver_schema"; [[ "$delivery" != hosted || -z "$resolver_schema" ]] || export UNCLE_OUTPUT_SCHEMA_FILE="$resolver_schema" UNCLE_STRUCTURED_OUTPUT_PATH="$directory/resolutions-$group_id.json"
              export UNCLE_UPDATED_PLAN_ATTEMPTS_DIR="$directory"
              export UNCLE_UPDATED_PLAN_FINDINGS="$(python3 -B "$ROOT/scripts/lib/updated_plan_defer.py" group-ids "$directory" "$group_id")"
              if [[ "$resolver_granularity" == small ]]; then
                  local resolver_turns answer_tokens
                  read -r resolver_turns answer_tokens < <(python3 -B "$ROOT/scripts/lib/updated_plan_ops.py" resolver-budget "$directory" "$group_id")
                  [[ -n "$resolver_turns" && -n "$answer_tokens" ]] || exit 1
                  (( resolver_turns > 0 )) || resolver_turns=""
                  export UNCLE_WORKER_MAX_TURNS="$resolver_turns" UNCLE_UPDATED_PLAN_ANSWER_TOKENS="$answer_tokens"
              fi
              UNCLE_WORKER_PACKET_PATH="$directory/resolutions-$group_id.json" SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 \
                workflow_model_writer updated-plan run_claude "$group_prompt" "updated-plan-worker-resolve-$group_id" ) \
                > "$LOG_DIR/updated-plan-worker-resolve-$group_id.log" 2>&1 &
            pids+=("$!"); names+=("$group_id")
        done
        for pid in "${!pids[@]}"; do
            wait "${pids[$pid]}" || {
                local resolver_status=$?
                workflow_writer_failure "updated-plan-worker-resolve-${names[$pid]}" "$resolver_status"
                echo "Updated-plan resolver ${names[$pid]} did not complete." >&2
                resolver_failed=1
                rm -f "$directory/resolutions-${names[$pid]}.json"
            }
        done
        resolver_failed=0
        # A resolver answer that cannot be applied (text quoted from the wrong place) gets one more try, for that
        # group only, with the reason -- a few seconds, against the full single call.
        local bad_groups
        if ! bad_groups="$(python3 -B "$helper" check "$STATE_DIR/documents/PROJECT_PLAN.json" "$directory")"; then
            echo "Updated-plan resolver answer(s) could not be applied; asking again: $(echo $bad_groups)"
            # Keep successful groups; only a still-invalid small resolver gets the other delivery path.
            local resolver_attempt
            for resolver_attempt in retry alternate; do
                resolver_failed=0
                pids=(); names=()
                for group_id in $bad_groups; do
                    local retry_schema=""
                    [[ "$delivery" != hosted && "$resolve_command" != resolve-ops ]] || retry_schema="$directory/schemas/resolve-$group_id.json"
                    if [[ "$resolve_command" == resolve-ops ]] && stage_uses_self_hosted updated-plan AGENT; then
                        local schema_attempt=first
                        [[ ! -f "$directory/prompts/resolve-$group_id.validator-rejected" ]] || schema_attempt=retry
                        python3 -B "$ROOT/scripts/lib/worker_schemas.py" resolve-ops "$STATE_DIR/documents/PROJECT_PLAN.json" "$retry_schema" --scope "$directory/prompts/resolve-$group_id.scope.json" --attempt "$schema_attempt" || return 1
                    fi
                    workflow_model_slot "$jobs" ${pids[@]+"${pids[@]}"}
                    if [[ -s "$directory/prompts/resolve-$group_id.validator-rejected" ]]; then
                        workflow_writer_failure "updated-plan-worker-resolve-$group_id" 5 "schema rejection" "$directory/prompts/resolve-$group_id.validator-rejected"
                    fi
                    workflow_archive_attempt "$LOG_DIR/updated-plan-worker-resolve-$group_id-retry.log" "$LOG_DIR/updated-plan-worker-resolve-$group_id-retry.jsonl" "$directory/resolutions-$group_id.json" || return 1
                    ( . "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_enter updated-plan AGENT || exit 1; [[ -z "$retry_schema" ]] || export UNCLE_WORKER_SCHEMA_FILE="$retry_schema"; [[ "$delivery" != hosted || -z "$retry_schema" ]] || export UNCLE_OUTPUT_SCHEMA_FILE="$retry_schema" UNCLE_STRUCTURED_OUTPUT_PATH="$directory/resolutions-$group_id.json"
                      export UNCLE_UPDATED_PLAN_ATTEMPTS_DIR="$directory"
                      export UNCLE_UPDATED_PLAN_FINDINGS="$(python3 -B "$ROOT/scripts/lib/updated_plan_defer.py" group-ids "$directory" "$group_id")"
                      if [[ "$resolver_granularity" == small ]]; then
                          local resolver_turns answer_tokens
                          read -r resolver_turns answer_tokens < <(python3 -B "$ROOT/scripts/lib/updated_plan_ops.py" resolver-budget "$directory" "$group_id")
                          [[ -n "$resolver_turns" && -n "$answer_tokens" ]] || exit 1
                          (( resolver_turns > 0 )) || resolver_turns=""
                          export UNCLE_WORKER_MAX_TURNS="$resolver_turns" UNCLE_UPDATED_PLAN_ANSWER_TOKENS="$answer_tokens"
                          if [[ "$resolver_attempt" == alternate ]]; then
                              local alternate_mode
                              alternate_mode="$(python3 -B "$ROOT/scripts/lib/updated_plan_ops.py" resolver-fallback-mode)" || exit 1
                              export WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST="$alternate_mode"
                          fi
                      fi
                      UNCLE_WORKER_PACKET_PATH="$directory/resolutions-$group_id.json" SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 \
                        workflow_model_writer updated-plan run_claude "$directory/prompts/resolve-$group_id.retry.md" "updated-plan-worker-resolve-$group_id-retry" ) \
                        > "$LOG_DIR/updated-plan-worker-resolve-$group_id-retry.log" 2>&1 &
                    pids+=("$!"); names+=("$group_id")
                done
                for pid in "${!pids[@]}"; do
                    wait "${pids[$pid]}" || {
                        local resolver_status=$?
                        workflow_writer_failure "updated-plan-worker-resolve-${names[$pid]}-retry" "$resolver_status"
                        echo "Updated-plan resolver retry ${names[$pid]} did not complete." >&2
                        resolver_failed=1
                        rm -f "$directory/resolutions-${names[$pid]}.json"
                    }
                done
                if [[ "$resolver_granularity" != small ]]; then
                    break
                fi
                if bad_groups="$(python3 -B "$helper" check "$STATE_DIR/documents/PROJECT_PLAN.json" "$directory")"; then break; fi
                if [[ "$resolver_attempt" == alternate ]]; then break; fi
            done
        fi
        [[ -z "$reconcile_pid" ]] || wait "$reconcile_pid" 2>/dev/null || true
        if ! bad_groups="$(python3 -B "$helper" check "$STATE_DIR/documents/PROJECT_PLAN.json" "$directory")"; then
            for group_id in $bad_groups; do
                workflow_writer_failure "updated-plan-worker-resolve-$group_id-retry" 5 "schema rejection" "$directory/prompts/resolve-$group_id.retry.md"
            done
            UNCLE_LATE_OPS="$late_ops" python3 -B "$ROOT/scripts/lib/updated_plan_defer.py" resolvers "$directory" "$bad_groups" updated-plan "$STATE_DIR/documents/PROJECT_PLAN.json" "$helper" || { workflow_writer_exhausted updated-plan; return 1; }
        else
            UNCLE_LATE_OPS="$late_ops" python3 -B "$helper" merge "$STATE_DIR/documents/PROJECT_PLAN.json" "$directory/slices.tsv" "$directory" "$directory/merged.json" "$directory" || { workflow_writer_exhausted updated-plan; return 1; }
        fi
    elif [[ "$merge_status" != 0 ]]; then
        return 1
    fi
    workflow_publish_updated_plan updated-plan "$directory" || return 1
}

# The specialists' corrections, checked once against what the deciders wrote.  Runs in the background: it waits for the
# specialists (they started with the deciders and are usually done), collates them, and asks one model call for the
# edits no decider made.  Any failure here just means no extra edits.  Sets UPDATED_PLAN_RECONCILE_PID.
updated_plan_start_reconcile() {
    local directory="$1" delivery="$2" late="$3" panel="$STATE_DIR/updated-plan-panel"
    UPDATED_PLAN_RECONCILE_PID=""
    rm -f "$late"
    (
        local pid schema_args=()
        for pid in "${UPDATED_PLAN_ADVISOR_PIDS[@]}"; do
            while kill -0 "$pid" 2>/dev/null; do sleep 0.5; done
        done
        python3 "$ROOT/scripts/lib/updated_plan_worker_packets.py" "$panel" "$STATE_DIR/documents/UPDATED_PLAN_WORKERS.json" \
            --expected ownership verification scope > /dev/null 2>&1 || exit 0
        UNCLE_PLAN_JSON="$STATE_DIR/documents/PROJECT_PLAN.json" python3 -B "$ROOT/scripts/lib/updated_plan_ops.py" reconcile \
            "$UPDATED_PLAN_PROMPT" "$directory/slices.tsv" "$directory" "$STATE_DIR/documents/UPDATED_PLAN_WORKERS.json" \
            "$directory/prompts/reconcile.md" || exit 0
        local schema_file=""
        mkdir -p "$directory/schemas"
        schema_file="$directory/schemas/reconcile.json"
        python3 -B "$ROOT/scripts/lib/worker_schemas.py" edit-ops "$STATE_DIR/documents/PROJECT_PLAN.json" "$schema_file" --scope "$directory/prompts/reconcile.scope.json" || exit 0
        [[ -z "$schema_file" ]] || export UNCLE_WORKER_SCHEMA_FILE="$schema_file"; [[ "$delivery" != hosted || -z "$schema_file" ]] || export UNCLE_OUTPUT_SCHEMA_FILE="$schema_file" UNCLE_STRUCTURED_OUTPUT_PATH="$late"
        . "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_enter updated-plan || exit 1
        UNCLE_WORKER_PACKET_PATH="$late" SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 \
            run_claude "$directory/prompts/reconcile.md" updated-plan-worker-reconcile
    ) > "$LOG_DIR/updated-plan-worker-reconcile.log" 2>&1 &
    UPDATED_PLAN_RECONCILE_PID="$!"
}

# Decide and edit in one pass.  The specialist round (three "dispositions" workers that decide each finding and describe the fix
# in prose, then eighteen writers that re-read the whole plan to turn that prose into ops) did every finding twice.  Here the writers
# read the review themselves and answer with their disposition and their ops; the three lens specialists run beside them, and one
# reconciler adds what the lenses asked for and no writer did.  Nonzero leaves nothing published, and the caller runs the
# specialist round and the writers as before.  WORKFLOW_UPDATED_PLAN_DECIDE=0 turns it off.
run_updated_plan_decide() {
    [[ "${WORKFLOW_UPDATED_PLAN_DECIDE:-1}" == 1 && "${WORKFLOW_UPDATED_PLAN_OPS:-1}" == 1 && "${WORKFLOW_UPDATED_PLAN_EDITS:-1}" == 1 ]] || return 1
    ensure_project_plan_json || return 1
    require_file "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" || return 1
    local directory="$STATE_DIR/updated-plan-panel" lens prompt status=0 pid
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    UPDATED_PLAN_PROMPT="$directory/synthesis.md"
    python3 -B "$ROOT/scripts/lib/updated_plan_synthesis_prompt.py" \
        "$STATE_DIR/documents/PROJECT_PLAN.json" "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" - "$UPDATED_PLAN_PROMPT" || return 1
    echo "Updated plan: writers decide and edit from the review; the specialists check beside them."
    UPDATED_PLAN_ADVISOR_PIDS=()
    for lens in ownership verification scope; do
        prompt="$directory/prompts/$lens.md"
        cp "$ROOT/prompts/change/updated-plan-review-worker.md" "$prompt"
        printf '\n## Assigned review lens\n\nFocus only on **%s**.\n' "$lens" >> "$prompt"
        ( . "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_enter updated-plan REVIEWER || exit 1; UNCLE_NONINTERACTIVE=1 run_codex_review "$prompt" "$directory/$lens.json" "updated-plan-review-worker-$lens" < /dev/null ) \
            > "$LOG_DIR/updated-plan-worker-$lens.log" 2>&1 &
        UPDATED_PLAN_ADVISOR_PIDS+=("$!")
    done
    run_updated_plan_edit_writers || status=$?
    # Stop any specialist still running (a failed decide falls back to the specialist round, which reuses these files).
    for pid in ${UPDATED_PLAN_ADVISOR_PIDS[@]+"${UPDATED_PLAN_ADVISOR_PIDS[@]}"}; do
        python3 -B "$ROOT/scripts/lib/writer_deadline.py" stop "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
    UPDATED_PLAN_ADVISOR_PIDS=()
    return "$status"
}

# Three lenses (tooling, data, reviewers) run concurrently: each only reads
# files and runs local version-check/status commands, so nothing collides.
# The fourth lens (browser) launches a real browser and/or binds a real port
# -- side effects that would race against a concurrent instance of themselves
# or each other -- so it always runs afterward, alone. A worker packet is the
# authoritative source for its own rows; unlike the review panels there is no
# separate synthesis agent to fall back on, so any worker failure fails the
# whole panel and the caller falls back to the single-agent investigation.
run_preflight_readonly_worker() {
    local prompt="$1" worker="$2" output="$3" scratch status=0 source="$PWD"
    if [[ -n "${4:-}" ]]; then
        scratch="$4"
        python3 -B "$ROOT/scripts/lib/preflight_readonly.py" prepare "$PWD" "$scratch" > /dev/null || return 1
    else
        scratch="$(python3 -B "$ROOT/scripts/lib/preflight_readonly.py" prepare "$PWD")" || return 1
    fi
    ( cd "$scratch" && UNCLE_PREFLIGHT_READONLY=1 UNCLE_CONFIG="${UNCLE_CONFIG:-$source/.uncle/config}" \
      UNCLE_WORKER_PACKET_PATH="$output" run_claude "$prompt" "$worker" "Read,Glob,Grep,Bash" ) || status=$?
    if grep -q 'read-only preflight refused' "$LOG_DIR/$worker.jsonl" "$LOG_DIR/$worker.log" 2>/dev/null; then
        : > "$STATE_DIR/preflight-readonly-violation"
        printf '%s: read-only preflight violation\n' "$worker" > "$STATE_DIR/stop-reason"
        status=1
    fi
    if ! python3 -B "$ROOT/scripts/lib/preflight_readonly.py" check "$scratch" "$worker"; then
        printf '%s: read-only preflight violation; refusing worker output.\n' "$worker" >&2
        : > "$STATE_DIR/preflight-readonly-violation"
        printf '%s: read-only preflight violation\n' "$worker" > "$STATE_DIR/stop-reason"
        status=1
    fi
    python3 -B "$ROOT/scripts/lib/preflight_readonly.py" remove "$scratch" || status=1
    return "$status"
}

run_preflight_investigation_panel() {
    local directory="$STATE_DIR/preflight-panel" lens prompt output pid scratch
    local -a pids=() names=() done_workers=() scratches=()
    [[ "${WORKFLOW_PREFLIGHT_PANEL:-1}" == 1 ]] || return 1
    (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_terminal_failure) && return 1
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    echo "Preflight investigation panel: launching 3 workers in parallel (tooling, data, reviewers); browser follows serially."
    for lens in tooling data reviewers; do
        prompt="$directory/prompts/$lens.md"; output="$directory/$lens.json"
        cp "$ROOT/prompts/preflight-investigate-worker.md" "$prompt"
        printf '\n## Assigned lens\n\nFocus only on **%s**.\n' "$lens" >> "$prompt"
        scratch="$(python3 -B "$ROOT/scripts/lib/preflight_readonly.py" allocate "$PWD")" || return 1
        scratches+=("$scratch")
        ( run_preflight_readonly_worker "$prompt" "preflight-worker-$lens" "$output" "$scratch" ) \
            > "$LOG_DIR/preflight-worker-$lens.log" 2>&1 &
        pids+=("$!"); names+=("$lens"); done_workers+=(0)
    done
    local left=3 index sibling
    while (( left > 0 )); do
        for index in "${!pids[@]}"; do
            [[ "${done_workers[index]}" == 0 ]] || continue
            if ! kill -0 "${pids[index]}" 2>/dev/null; then
                if ! wait "${pids[index]}"; then
                    echo "Preflight worker preflight-worker-${names[index]} failed; refusing its output." >&2
                    for sibling in "${!pids[@]}"; do
                        [[ "$sibling" == "$index" || "${done_workers[sibling]}" == 1 ]] && continue
                        python3 -B "$ROOT/scripts/lib/writer_deadline.py" stop "${pids[sibling]}" 2>/dev/null || true
                        wait "${pids[sibling]}" 2>/dev/null || true
                    done
                    for scratch in "${scratches[@]}"; do
                        python3 -B "$ROOT/scripts/lib/preflight_readonly.py" remove "$scratch" || true
                    done
                    return 1
                fi
                done_workers[index]=1; left=$((left - 1))
            fi
        done
        (( left == 0 )) || sleep 0.1
    done
    prompt="$directory/prompts/browser.md"; output="$directory/browser.json"
    cp "$ROOT/prompts/preflight-investigate-worker.md" "$prompt"
    printf '\n## Assigned lens\n\nFocus only on **browser**.\n' >> "$prompt"
    run_preflight_readonly_worker "$prompt" "preflight-worker-browser" "$output" \
        > "$LOG_DIR/preflight-worker-browser.log" 2>&1 \
        || { echo 'Preflight browser worker failed; falling back to the single-agent investigation.' >&2; return 1; }
    python3 "$ROOT/scripts/lib/preflight_worker_packets.py" "$directory" "$STATE_DIR/documents/PREFLIGHT_REPORT.json" \
        --expected tooling data reviewers browser \
        || { echo 'Preflight worker packets rejected; falling back to the single-agent investigation.' >&2; return 1; }
    python3 "$ROOT/scripts/lib/acceptance_context.py" --render \
        "$STATE_DIR/documents/PREFLIGHT_REPORT.json" .uncle/docs/PREFLIGHT_REPORT.md || return 1
}

run_updated_plan_fast_path() {
    ensure_project_plan_json || return 1
    require_file "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" || return 1
    # An empty adversarial review has no dispositions or plan edits to decide.
    # Avoid launching four empty specialists and a parent that can only copy
    # the approved plan; plan ingestion below still renders and validates it.
    python3 -B "$ROOT/scripts/lib/updated_plan_fast_path.py" \
        "$STATE_DIR/documents/PROJECT_PLAN.json" \
        "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" \
        "$STATE_DIR/documents/UPDATED_PROJECT_PLAN.json" \
        --render .uncle/docs/UPDATED_PROJECT_PLAN.md
}

# A non-empty review used to take the expensive "committee" path by default:
# three advisory reviewers, one or more plan writers, then sometimes a
# reconciler and conflict resolvers.  All of those calls reread the same base
# plan and review.  They improve neither the canonical inputs nor the merge
# when a single writer can make the small, ID-bound patch directly.
#
# Keep one compiler call as the normal path.  Its sealed prompt contains only
# the canonical plan and condensed review; it has no tools to spend time on
# discovery, no worker directory to inspect, and writes a patch rather than a
# second full plan.  This makes the normal updated-plan critical path one LLM
# round trip (target: about 30 seconds on a responsive runner), rather than
# the slowest of a panel plus a reconciliation round.  The historical panel
# remains available with WORKFLOW_UPDATED_PLAN_COMPACT=0 for diagnosing an
# unusual model-specific failure.
run_updated_plan_compact() {
    [[ "${WORKFLOW_UPDATED_PLAN_COMPACT:-1}" == 1 ]] || return 1
    ensure_project_plan_json || return 1
    require_file "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" || return 1
    local directory="$STATE_DIR/updated-plan-compact"
    rm -rf "$directory"; mkdir -p "$directory" "$STATE_DIR/artifact-delivery"
    UPDATED_PLAN_PROMPT="$directory/synthesis.md"
    python3 -B "$ROOT/scripts/lib/updated_plan_synthesis_prompt.py" \
        "$STATE_DIR/documents/PROJECT_PLAN.json" \
        "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" \
        - "$UPDATED_PLAN_PROMPT" || return 1
    echo 'Updated-plan compact path: one JSON patch compiler; skipping advisory and edit-writer fan-out.'
    # run_claude exits the whole process on a stage it cannot recover (its
    # retries are for transient/format problems, not for "this runner cannot
    # satisfy this contract"). A subshell lets this one caller see that exit
    # as a status instead of losing the entire driver to it.
    local compact_status=0
    if stage_supports_structured_output updated-plan; then
        local schema="$directory/synthesis.json"
        python3 -B "$ROOT/scripts/lib/worker_schemas.py" synthesis plan protected "$schema" || return 1
        ( UNCLE_OUTPUT_SCHEMA_FILE="$schema" \
          UNCLE_STRUCTURED_OUTPUT_PATH="$STATE_DIR/artifact-delivery/updated-plan.json" \
            run_claude "$UPDATED_PLAN_PROMPT" updated-plan ) || compact_status=$?
    else
        ( run_claude "$UPDATED_PLAN_PROMPT" updated-plan ) || compact_status=$?
    fi
    [[ "$compact_status" == 0 ]] && return 0
    if (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_terminal_failure); then return "$compact_status"; fi
    # A self-hosted model can fail the compact path's strict patch contract
    # (replace_text only matches text already in the base plan) the same way
    # on every retry and every resumed process -- nothing about restarting
    # teaches it the mistake it keeps making. Escalate once per run to the
    # full writer panel, which does not require an exact-match patch; a
    # marker stops this from ping-ponging back and forth forever.
    if stage_uses_self_hosted updated-plan AGENT && [[ ! -e "$STATE_DIR/updated-plan-compact-failed" ]]; then
        touch "$STATE_DIR/updated-plan-compact-failed"
        echo "Updated-plan compact path failed on a self-hosted model; falling back to the full writer panel."
        return 2
    fi
    exit "$compact_status"
}

# A single compiler is fastest for a short review.  A long review is different:
# one response has to serialize every disposition and patch, as calculator's
# 23 findings did (12.8k output tokens / 80s).  Split only that response into
# a small number of independent patch batches.  There are no advisory
# reviewers and no reconciliation round; the existing typed-op merge is
# deterministic, and asks a resolver only for a genuine conflicting edit.
#
# Independent finding batches can use continuous batching on self-hosted servers.
# Keep their concurrency bounded and retain conflict resolution before publication.
run_updated_plan_adaptive() {
    local count threshold slice directory fast_merge=1 jobs=0 writer_status=0
    . "$ROOT/scripts/lib/model-jobs.sh"
    jobs="$(workflow_model_capacity updated-plan)"
    if [[ "$jobs" != 0 ]]; then fast_merge=0; fi
    [[ "${WORKFLOW_UPDATED_PLAN_COMPACT:-1}" == 1 ]] || return 1
    count="$(python3 -B - "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" <<'PY'
import json, sys
try:
    print(len(json.load(open(sys.argv[1], encoding='utf-8')).get('findings') or []))
except (OSError, ValueError):
    print(0)
PY
)"
    # Keep each response tiny.  On a large review, serializing one full plan
    # patch took calculator more than 80 seconds.  Two findings per writer
    # gives hosted runners enough independent work to finish near one short
    # response (rather than the sum), without the 20-way request burst of a
    # one-finding fan-out.
    threshold="${WORKFLOW_UPDATED_PLAN_PARALLEL_THRESHOLD:-5}"
    # Findings per writer: an explicit setting wins, then the build class (small builds batch more), then the
    # runner granularity default (small units for self-hosted).
    slice="${WORKFLOW_UPDATED_PLAN_PARALLEL_SLICE:-$(python3 -B "$ROOT/scripts/lib/change_class.py" get . edit_slice "$(python3 -B -c 'import sys; sys.path.insert(0, sys.argv[1]); import updated_plan_ops as o; print(o.option("group-size", int(sys.argv[2])))' "$ROOT/scripts/lib" "$(workflow_model_group_size updated-plan)")")}"
    if [[ "$count" =~ ^[0-9]+$ && "$threshold" =~ ^[0-9]+$ && "$slice" =~ ^[0-9]+$ ]] \
        && (( count >= threshold && slice > 0 && jobs != 1 )); then
        ensure_project_plan_json || return 1
        require_file "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" || return 1
        directory="$STATE_DIR/updated-plan-adaptive"
        rm -rf "$directory"; mkdir -p "$directory"
        UPDATED_PLAN_PROMPT="$directory/synthesis.md"
        python3 -B "$ROOT/scripts/lib/updated_plan_synthesis_prompt.py" \
            "$STATE_DIR/documents/PROJECT_PLAN.json" \
            "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" \
            - "$UPDATED_PLAN_PROMPT" || return 1
        echo "Updated-plan adaptive path: $count findings in batches of $slice; no advisory or reconciliation calls."
        UPDATED_PLAN_ADVISOR_PIDS=()
        # Do not use the nested structured-output protocol here.  Each child
        # writes one JSON packet at its private path; run_claude verifies the
        # path exists and this function parses/merges it before publication.
        WORKFLOW_UPDATED_PLAN_EDIT_SLICE="$slice" WORKFLOW_UPDATED_PLAN_WRITER_DELIVERY=file WORKFLOW_UPDATED_PLAN_FAST_MERGE="$fast_merge" WORKFLOW_UPDATED_PLAN_DRIVER_CONTRACT=1 WORKFLOW_PREFIX_WARM_SECONDS=0 \
            run_updated_plan_edit_writers || writer_status=$?
        if (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_terminal_failure); then cat "$STATE_DIR/stop-reason" >&2; return 1; fi
        if [[ "$writer_status" != 0 && "$jobs" != 0 ]]; then
            echo 'Updated-plan batches failed validation or delivery; falling back to the compact writer.'
            run_updated_plan_compact
            return $?
        fi
        return "$writer_status"
    fi
    run_updated_plan_compact
}

# Phase 1: kicked off the moment implementation finishes, before the driver's
# background verification has published final results. Judges only what the
# plan and source/test files can already tell on their own -- never opens the
# result files, so there is nothing here that must be thrown away once real
# results exist. Non-blocking: starts the workers and returns at once, so this
# investigation and the driver's verification run run concurrently instead of
# one stage sitting idle waiting for the other to finish first.
# The test-review panel's lenses: all three, narrowed only for the smallest classes (scripts/lib/change_class.py). The same list
# is read for the investigation, the panel, and the packet check, so they cannot disagree.
test_review_lenses() {
    change_class_panel_subset test_review_lenses 'coverage assertions oracle' WORKFLOW_TEST_REVIEW_LENSES
}

run_test_review_investigate() {
    local directory="$STATE_DIR/test-review-panel" lens prompt current
    [[ "${WORKFLOW_TEST_REVIEW_PANEL:-1}" == 1 ]] || return 0
    [[ "${WORKFLOW_TEST_REVIEW_PRESTART:-1}" == 1 ]] || return 0
    # One-shot per *tree*, not per run: a repair that changes source and
    # re-enters TEST_REVIEW must get a fresh investigation of the repaired
    # code, not the marker silently reusing the pre-repair one. Fingerprint
    # the source the same way early-checklist and green-check already do,
    # so a tree that has not changed since the last investigation still
    # skips relaunching it.
    current="$(python3 -B "$ROOT/scripts/lib/tree_fingerprint.py" "$PWD" 2>/dev/null)"
    if [[ -e "$directory/investigate-started" && -n "$current" \
            && "$current" == "$(cat "$directory/investigate.fingerprint" 2>/dev/null)" ]]; then
        return 0
    fi
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    : > "$directory/investigate-started"
    : > "$directory/investigate.pids"
    printf '%s' "$current" > "$directory/investigate.fingerprint"
    . "$ROOT/scripts/lib/model-jobs.sh"
    local jobs
    jobs="$(workflow_model_capacity test-review REVIEWER)" || return 1
    for lens in $(test_review_lenses); do
        prompt="$directory/prompts/investigate-$lens.md"
        cp "$ROOT/prompts/change/test-review-worker-investigate.md" "$prompt"
        if [[ "$lens" == oracle ]]; then
            printf 'Focus only on **ORACLE** and **NEGATIVE**: whether expected values are independently grounded, and whether critical tests target a representative defect.\n' >> "$prompt"
        else
            printf 'Focus only on **%s**.\n' "$(upper "$lens")" >> "$prompt"
        fi
        ( workflow_model_enter test-review REVIEWER "$jobs" || exit 1; UNCLE_NONINTERACTIVE=1 run_codex_review "$prompt" "$directory/investigate-$lens.md" "test-review-worker-$lens-investigate" < /dev/null ) \
            > "$LOG_DIR/test-review-worker-$lens-investigate.log" 2>&1 &
        echo "$!" >> "$directory/investigate.pids"
    done
}

run_test_review_panel() {
    local directory="$STATE_DIR/test-review-panel" lens prompt output pid
    local -a pids=()
    [[ "${WORKFLOW_TEST_REVIEW_PANEL:-1}" == 1 ]] || return 0
    # A safety net for any caller that reaches here without having started
    # phase 1 early (a resumed run, WORKFLOW_TEST_REVIEW_PRESTART=0): starts
    # it now, synchronously, with no loss beyond the overlap this exists to
    # get. If phase 1 already started, this is a no-op.
    run_test_review_investigate
    if [[ -s "$directory/investigate.pids" ]]; then
        while IFS= read -r pid; do
            [[ -n "$pid" ]] || continue
            wait "$pid" 2>/dev/null || echo 'Test-review investigation worker failed; the finalize pass will judge from results alone.' >&2
        done < "$directory/investigate.pids"
    fi
    mkdir -p "$directory/prompts"
    # INTEGRITY is a driver-owned fact: the green-check TSV is the canonical
    # execution record, so asking a reviewer to rediscover it is both slower
    # and less reliable.  The remaining three lenses are judgement calls.
    # oracle/negative merge because both judge whether tests are trustworthy.
    for lens in $(test_review_lenses); do
        prompt="$directory/prompts/$lens.md"; output="$directory/$lens.json"
        cp "$ROOT/prompts/change/test-review-worker-finalize.md" "$prompt"
        # The investigation is untrusted model output, not driver-written
        # text: on calculator4 a worker ignored the "plain prose" instruction
        # and returned a JSON-wrapped, self-contradicting blob instead, which
        # then confused the finalize pass into answering with the wrong row
        # id entirely. The instructed format is a Markdown document starting
        # with a heading; anything else is unusable and must not reach the
        # finalize prompt, rather than being pasted in and trusted.
        if [[ -s "$directory/investigate-$lens.md" ]] && head -n 5 "$directory/investigate-$lens.md" | grep -qE '^[[:space:]]*#'; then
            cat "$directory/investigate-$lens.md" >> "$prompt"
        else
            printf '(No usable investigation: it either did not complete before results were ready, or did not return the required plain-text report. Judge from the plan, source, and results alone.)\n' >> "$prompt"
        fi
        if [[ "$lens" == oracle ]]; then
            printf '\n## Assigned acceptance-gate rows\n\nFocus only on **ORACLE** and **NEGATIVE**: whether expected values are independently grounded, and whether critical tests have evidence of failing for representative defects and passing after restoration. Use exactly these ids, "ORACLE" and "NEGATIVE", in your JSON output -- never substitute a different row name from the investigation above.\n' >> "$prompt"
        else
            printf '\n## Assigned acceptance-gate row\n\nFocus only on **%s**. Use exactly this id, "%s", in your JSON output -- never substitute a different row name from the investigation above.\n' "$(upper "$lens")" "$(upper "$lens")" >> "$prompt"
        fi
        ( . "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_enter test-review REVIEWER || exit 1; UNCLE_NONINTERACTIVE=1 run_codex_review "$prompt" "$output" "test-review-worker-$lens" < /dev/null ) \
            > "$LOG_DIR/test-review-worker-$lens.log" 2>&1 &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do
        wait "$pid" || echo 'Test-review worker failed; canonical packet validation will stop the panel.' >&2
    done
    # A bad response is isolated to its lens. Retry that one compact worker
    # once; never discard its healthy siblings or restart the whole panel.
    for lens in $(test_review_lenses); do
        output="$directory/$lens.json"; prompt="$directory/prompts/$lens.md"
        if ! python3 -B "$ROOT/scripts/lib/test_review_packets.py" validate "$output" "$lens"; then
            echo "Test-review worker $lens returned an invalid packet; retrying that worker once."
            rm -f "$output"
            ( . "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_enter test-review REVIEWER || exit 1
              UNCLE_NONINTERACTIVE=1 run_codex_review "$prompt" "$output" "test-review-worker-$lens-retry" < /dev/null ) || true
        fi
    done
    python3 "$ROOT/scripts/lib/test_review_packets.py" "$directory" "$STATE_DIR/documents/TEST_REVIEW.json" $(test_review_lenses) || return 1
    python3 "$ROOT/scripts/lib/acceptance_context.py" --validate-json "$STATE_DIR/documents/TEST_REVIEW.json" || return 1
    python3 "$ROOT/scripts/lib/acceptance_context.py" --render "$STATE_DIR/documents/TEST_REVIEW.json" .uncle/docs/TEST_REVIEW.md || return 1
    cp "$STATE_DIR/documents/TEST_REVIEW.json" "$STATE_DIR/documents/TEST_REVIEW_WORKERS.json"
}

run_manual_checklist_panel() {
    local directory="$STATE_DIR/manual-checklist-panel" lens prompt output pid
    # `draft` is the same panel run early, while the code is still being written (manual_checklist_draft_start): it reads only what
    # exists before implementation and writes MANUAL_CHECKLIST_DRAFT.json, which manual_checklist_reconcile later compares with the build.
    local mode="${1:-final}" target="$STATE_DIR/documents/MANUAL_CHECKLIST.json" tag=""
    local -a pids=() pid_lenses=()
    [[ "${WORKFLOW_MANUAL_CHECKLIST_PANEL:-1}" == 1 ]] || return 0
    if [[ "$mode" == draft ]]; then
        directory="$STATE_DIR/manual-checklist-draft-panel"; target="$STATE_DIR/documents/MANUAL_CHECKLIST_DRAFT.json"; tag="draft-"
    fi
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    # A new application has nothing to regress: the regressions lens wrote a third copy of the
    # behavior checks (MC-400s repeating the MC-100s and MC-200s), about a third of a 42-check list.
    local lenses="coverage invariants resources"
    [[ "${WORKFLOW_MANUAL_CHECKLIST_REGRESSIONS:-0}" != 1 ]] || lenses="$lenses regressions"
    lenses="$(change_class_panel_subset checklist_lenses "$lenses" WORKFLOW_CHECKLIST_LENSES)"
    for lens in $lenses; do
        prompt="$directory/prompts/$lens.md"; output="$directory/$lens.json"
        cp "$ROOT/prompts/change/manual-checklist-review-worker.md" "$prompt"
        local range
        case "$lens" in coverage) range='MC-100 through MC-199';; invariants) range='MC-200 through MC-299';; resources) range='MC-300 through MC-399';; regressions) range='MC-400 through MC-499';; esac
        local inputs='`.uncle/workflow/documents/ADVERSARIAL_REVIEW.json`, and `.uncle/workflow/documents/TEST_REVIEW.json`'
        if [[ "${UNCLE_CHECKLIST_EARLY:-0}" == 1 ]]; then
            # Start beside TEST_REVIEW from stable plan/review inputs. Its
            # result is adopted only after the test review itself passes.
            inputs='`.uncle/workflow/documents/ADVERSARIAL_REVIEW.json`'
            printf '\n## Early speculative checklist\n\n`TEST_REVIEW.json` is intentionally not an input because it is being produced concurrently. Build checks from the approved plan, adversarial review, current tree, and driver evidence only. This packet is discarded unless the finished test review passes unchanged.\n' >> "$prompt"
        fi
        [[ "$mode" != draft ]] || inputs='`.uncle/workflow/documents/ADVERSARIAL_REVIEW.json`'
        printf '\n## Canonical inputs (binding)\n\nRead only these canonical JSON artifacts: `.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json`, `.uncle/workflow/documents/PROJECT_PLAN.json`, `.uncle/workflow/documents/UPDATED_PROJECT_PLAN.json`, %s, plus the completed driver record `.uncle/workflow/green-check.tsv`. Do not inspect any rendered Markdown view or enumerate directories.\n\nTreat the driver record as authoritative for dependency, build, unit, and automated-browser commands: cite it rather than proposing those commands again. Never require or mention Git history, commits, a prior revision, or a historical diff in any check field.\n\n## Assigned checklist lens\n\nFocus only on **%s**. Use IDs only in %s; no other worker owns that range.\n' "$inputs" "$lens" "$range" >> "$prompt"
        [[ "$mode" != draft ]] || python3 -B "$ROOT/scripts/lib/checklist_draft_prompt.py" "$prompt" || return 1
        ( UNCLE_NONINTERACTIVE=1 run_codex_review "$prompt" "$output" "manual-checklist-review-worker-${tag}$lens" < /dev/null ) \
            > "$LOG_DIR/manual-checklist-worker-${tag}$lens.log" 2>&1 &
        pids+=("$!")
        pid_lenses+=("$lens")
    done
    local index=0
    for pid in "${pids[@]}"; do
        wait "$pid" || echo 'Manual-checklist worker failed; canonical packet validation will stop the panel.' >&2
        lens="${pid_lenses[$index]}"; output="$directory/$lens.json"; prompt="$directory/prompts/$lens.md"
        if ! python3 -B "$ROOT/scripts/lib/manual_checklist_packets.py" validate "$output"; then
            echo "Manual-checklist worker $lens returned an invalid packet; retrying that worker once."
            printf '\n## Required retry\n\nYour preceding response was rejected because it was not one complete `manual-checklist-worker-packet` JSON object. Do not ask a question, discuss prior checklist documents, or return Markdown/prose. Produce the assigned lens packet now, even if its checks overlap a prior rendered report.\n' >> "$prompt"
            rm -f "$output"
            UNCLE_NONINTERACTIVE=1 run_codex_review "$prompt" "$output" "manual-checklist-review-worker-${tag}$lens-retry" < /dev/null || true
            python3 -B "$ROOT/scripts/lib/manual_checklist_packets.py" validate "$output" || return 1
        fi
        index=$((index + 1))
    done
    # Self-hosted models occasionally answer a checklist worker with a prose
    # question after seeing a stale rendered checklist.  Validate each compact
    # packet independently and give only that worker one explicit correction;
    # healthy packets stay intact and the full panel is never needlessly rerun.
    python3 "$ROOT/scripts/lib/manual_checklist_packets.py" "$directory" "$target" $lenses || return 1
    if [[ "$mode" == draft ]]; then
        python3 "$ROOT/scripts/lib/checklist_document.py" --validate-json "$target" || return 1
        return 0
    fi
    python3 -B "$ROOT/scripts/lib/checklist_driver_scope.py" \
        "$STATE_DIR/documents/MANUAL_CHECKLIST.json" \
        --proposed "$STATE_DIR/documents/MANUAL_CHECKLIST_PROPOSED.json" \
        --scope "$STATE_DIR/documents/MANUAL_CHECKLIST_DRIVER_SCOPE.json" || return 1
    python3 "$ROOT/scripts/lib/checklist_document.py" --validate-json "$STATE_DIR/documents/MANUAL_CHECKLIST.json" || return 1
    python3 "$ROOT/scripts/lib/checklist_document.py" --render-json "$STATE_DIR/documents/MANUAL_CHECKLIST.json" .uncle/docs/MANUAL_CHECKLIST.md || return 1
    cp "$STATE_DIR/documents/MANUAL_CHECKLIST.json" "$STATE_DIR/documents/MANUAL_CHECKLIST_WORKERS.json"
}

# --- the checklist draft and its reconciliation --------------------------------------------------------------------------------
# Manual-checklist writing is slow and does not depend on the code: its inputs are the approved requirements, plan and adversarial review.
# So it starts when implementation starts (manual_checklist_draft_start), by reviewers who never see the code, and after implementation a
# short reconciliation compares the draft with the build and the driver's results (manual_checklist_reconcile). The edits are applied
# deterministically (checklist_reconcile.py), so the draft stays the independent part of the review. Anything unusual (a stale draft,
# a draft that failed, a packet the rules refuse, WORKFLOW_CHECKLIST_DRAFT=0) falls back to the full panel, exactly as before.
MANUAL_DRAFT_PID=""

manual_checklist_draft_fingerprint() {
    local file
    for file in REQUIREMENTS_INTERPRETATION PROJECT_PLAN UPDATED_PROJECT_PLAN ADVERSARIAL_REVIEW; do
        [[ -s "$STATE_DIR/documents/$file.json" ]] || return 1
        printf '%s %s\n' "$file" "$(hash_file "$STATE_DIR/documents/$file.json")"
    done | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest())'
}

manual_checklist_draft_start() {
    [[ "${WORKFLOW_CHECKLIST_DRAFT:-1}" == 1 && "${WORKFLOW_MANUAL_CHECKLIST_PANEL:-1}" == 1 && -z "$MANUAL_DRAFT_PID" ]] || return 0
    local fingerprint
    fingerprint="$(manual_checklist_draft_fingerprint)" || return 0
    if [[ -s "$STATE_DIR/documents/MANUAL_CHECKLIST_DRAFT.json" && "$(cat "$STATE_DIR/manual-checklist-draft.done" 2>/dev/null)" == "$fingerprint" ]]; then
        return 0     # a resumed run: the draft for these exact inputs is already here
    fi
    rm -f "$STATE_DIR/manual-checklist-draft.done" "$STATE_DIR/documents/MANUAL_CHECKLIST_DRAFT.json"
    echo "Drafting the manual checklist from the approved plan while the code is written."
    ( run_manual_checklist_panel draft && printf '%s\n' "$fingerprint" > "$STATE_DIR/manual-checklist-draft.done" ) \
        > "$LOG_DIR/manual-checklist-draft.log" 2>&1 &
    MANUAL_DRAFT_PID=$!
}

manual_checklist_draft_cancel() {
    [[ -n "$MANUAL_DRAFT_PID" ]] || return 0
    python3 -B "$ROOT/scripts/lib/writer_deadline.py" stop "$MANUAL_DRAFT_PID" > /dev/null 2>&1 || true
    MANUAL_DRAFT_PID=""
}

# Succeeds when a draft exists for the plan and review as they are now.
manual_checklist_draft_usable() {
    if [[ -n "$MANUAL_DRAFT_PID" ]]; then wait "$MANUAL_DRAFT_PID" 2>/dev/null || true; MANUAL_DRAFT_PID=""; fi
    local fingerprint
    fingerprint="$(manual_checklist_draft_fingerprint)" || return 1
    [[ -s "$STATE_DIR/documents/MANUAL_CHECKLIST_DRAFT.json" && "$(cat "$STATE_DIR/manual-checklist-draft.done" 2>/dev/null)" == "$fingerprint" ]]
}

manual_checklist_reconcile() {
    [[ "${WORKFLOW_CHECKLIST_DRAFT:-1}" == 1 && "${WORKFLOW_MANUAL_CHECKLIST_PANEL:-1}" == 1 ]] || return 1
    manual_checklist_draft_usable || { echo 'No usable checklist draft; running the full checklist panel.'; return 1; }
    local directory="$STATE_DIR/manual-checklist-reconcile" packet
    rm -rf "$directory"; mkdir -p "$directory"
    packet="$directory/reconcile.json"
    cp "$ROOT/prompts/manual-checklist-reconcile.md" "$directory/prompt.md"
    echo 'Reconciling the checklist draft with the build and the driver results.'
    ( UNCLE_NONINTERACTIVE=1 run_codex_review "$directory/prompt.md" "$packet" manual-checklist-review-worker-reconcile < /dev/null ) \
        > "$LOG_DIR/manual-checklist-worker-reconcile.log" 2>&1 || true
    if ! python3 -B "$ROOT/scripts/lib/checklist_reconcile.py" apply "$STATE_DIR/documents/MANUAL_CHECKLIST_DRAFT.json" "$packet" \
            "$directory/final.json" "$STATE_DIR/documents/MANUAL_CHECKLIST_RECONCILIATION.json"; then
        echo 'The reconciliation could not be applied; running the full checklist panel.' >&2
        return 1
    fi
    cp "$directory/final.json" "$STATE_DIR/documents/MANUAL_CHECKLIST.json"
    python3 -B "$ROOT/scripts/lib/checklist_driver_scope.py" \
        "$STATE_DIR/documents/MANUAL_CHECKLIST.json" \
        --proposed "$STATE_DIR/documents/MANUAL_CHECKLIST_PROPOSED.json" \
        --scope "$STATE_DIR/documents/MANUAL_CHECKLIST_DRIVER_SCOPE.json" || return 1
    python3 "$ROOT/scripts/lib/checklist_document.py" --validate-json "$STATE_DIR/documents/MANUAL_CHECKLIST.json" || return 1
    python3 "$ROOT/scripts/lib/checklist_document.py" --render-json "$STATE_DIR/documents/MANUAL_CHECKLIST.json" .uncle/docs/MANUAL_CHECKLIST.md || return 1
    cp "$STATE_DIR/documents/MANUAL_CHECKLIST.json" "$STATE_DIR/documents/MANUAL_CHECKLIST_WORKERS.json"
    echo "Checklist reconciled: $(python3 -c "import json,sys; a=json.load(open(sys.argv[1])); print('%d draft checks, %d dropped, %d modified, %d added' % (a['draft_checks'], len(a['dropped']), len(a['modified']), len(a['added'])))" "$STATE_DIR/documents/MANUAL_CHECKLIST_RECONCILIATION.json")."
}

# Checklist work consumes a completed driver green-check. The browser/server
# may be prewarmed while test review runs, but manual or execute workers never
# run against a PENDING verification placeholder.
prewarm_checklist_browser() {
    [[ "${UNATTENDED:-0}" == 1 ]] || return 0
    [[ "${WORKFLOW_CHECKLIST_APP_SERVER:-1}" == 1 ]] || return 0
    # This is deliberately safe before a successful green check: app_server
    # prewarm refuses to install, build, or navigate a page.  If a prior build
    # is usable it leaves the local server warm; otherwise it returns without
    # turning a compiler failure into browser worker churn.
    python3 -B "$ROOT/scripts/lib/app_server.py" prewarm "$PWD" "$STATE_DIR" \
        > "$LOG_DIR/app-server.prewarm.log" 2>&1 < /dev/null &
}

# `audit_review_call PROMPT NAME OUTPUT`: one final-audit lens on the reviewer runner (NAME is third on the command line for the deadline).
audit_review_call() { UNCLE_NONINTERACTIVE=1 run_codex_review "$1" "$3" "$2" < /dev/null; }

run_final_audit_panel() {
    local directory="$STATE_DIR/final-audit-panel" lens prompt output pid audit_lenses
    local -a pids=()
    [[ "${WORKFLOW_FINAL_AUDIT_PANEL:-1}" == 1 ]] || return 0
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    audit_lenses="$(change_class_panel_subset final_audit_lenses 'verification scope regression waivers' WORKFLOW_FINAL_AUDIT_LENSES)"
    declare -F workflow_bounded_lens >/dev/null || . "$ROOT/scripts/lib/model-jobs.sh"
    local -a lens_order=() present=() missing=()
    for lens in $audit_lenses; do
        prompt="$directory/prompts/$lens.md"; output="$directory/$lens.json"
        cp "$ROOT/prompts/change/final-audit-review-worker.md" "$prompt"
        printf '\n## Assigned audit lens\n\nFocus only on **%s**.\n' "$lens" >> "$prompt"
        ( workflow_bounded_lens final-audit "final-audit-review-worker-$lens" "$output" "$directory" final-audit-worker-packet "$lens" audit_review_call "$prompt" < /dev/null ) \
            > "$LOG_DIR/final-audit-worker-$lens.log" 2>&1 &
        pids+=("$!"); lens_order+=("$lens")
    done
    local index=0
    for pid in "${pids[@]}"; do
        if wait "$pid"; then present+=("${lens_order[$index]}"); else missing+=("${lens_order[$index]}"); fi
        index=$((index + 1))
    done
    # A lens that still has no valid packet after its own retry is documented and left out; the audit goes on with the others.
    # Only if none delivered is there nothing to audit from.
    [[ "${#present[@]}" -gt 0 ]] || { echo 'No final-audit lens delivered a valid packet.' >&2; return 1; }
    for lens in ${missing[@]+"${missing[@]}"}; do
        echo "Final-audit lens $lens did not deliver a valid packet after a retry; the audit continues without it." >&2
        record_nonblocking_failure final-audit "lens $lens did not complete (documented; the audit continued without it)" || true
    done
    audit_lenses="${present[*]}"
    python3 "$ROOT/scripts/lib/worker_packets.py" "$directory" "$STATE_DIR/documents/FINAL_AUDIT_WORKERS.json" --kind final-audit-worker-packet --expected $audit_lenses || return 1
    python3 -B "$ROOT/scripts/lib/final_audit_packets.py" . || return 1
    FINAL_AUDIT_PROMPT="$directory/synthesis.md"; cp "$ROOT/prompts/final-audit.md" "$FINAL_AUDIT_PROMPT"
    printf '\n## Collated specialist findings (binding)\n\nRead only `%s/documents/FINAL_AUDIT_WORKERS.json`; do not read the worker directory.\n' "$STATE_DIR" >> "$FINAL_AUDIT_PROMPT"
}

# Parallel implementation steps run in isolation: a worker writing one file
# cannot read another step's owned files (they may not exist yet, and it
# would multiply the plan's token cost by every worker), so each one guesses
# the shape of whatever it imports from a sibling step. The guesses
# routinely disagree on small things a human developer would instead settle
# once, in writing, before anyone starts: initialState as an object vs. a
# function, an action field named op vs. operator, a key-mapper taking a
# string vs. an event. The merged result then fails to build, which reads
# as a model or driver defect when it is really a missing shared contract.
#
# Derive that contract once, from the approved plan, before the fan-out
# starts, and hand every worker the identical binding text. Non-fatal and
# cached by plan hash: a failure here still lets steps run exactly as they
# did before this existed, just without the shared contract.
# Execute plan-declared independent application steps in isolated worktrees.
# The shared parallel runner verifies each worker's owned-file boundary before
# merging, so this is enabled only for an explicit Owns:/Depends on schedule.
# Per-step worker prompt for run_parallel_application_implementation, called
# by the shared parallel_implement_run_groups (scripts/lib/parallel-implement.sh)
# as "$1"=step "$2"=group "$3"=prompt path "$4"=module-interfaces section.
# References checkpoint_dir/runtime_repair_marker from the caller's frame
# (bash dynamic scoping: a `local` stays visible to anything called while it
# is still on the stack).
_stagegate_parallel_build_step_prompt() {
    local step="$1" group="$2" prompt="$3" module_interfaces_section="$4"
    local step_line owned_paths
    cat "$ROOT/prompts/implement.md" > "$prompt"
    {
        echo; echo "## Assigned isolated implementation step $step"
        step_line="$(sed -n "${step}p" "$STATE_DIR/implement-steps.txt")"
        printf '%s\n' "$step_line"
        owned_paths="$(awk -F '\t' -v wanted="$step" '$1 == wanted { print "- `" $2 "`" }' "$STATE_DIR/implement-owns.tsv")"
        # Application steps merged into this worker (parallel-implement.sh): their text and files are this worker's too.
        local absorbed absorbed_owned
        for absorbed in ${UNCLE_ABSORBED_STEPS:-}; do
            echo; echo "## Also assigned step $absorbed (the same agent writes it, so the two agree on every name they share)"
            sed -n "${absorbed}p" "$STATE_DIR/implement-steps.txt"
            absorbed_owned="$(awk -F '\t' -v wanted="$absorbed" '$1 == wanted { print "- `" $2 "`" }' "$STATE_DIR/implement-owns.tsv")"
            [[ -z "$absorbed_owned" ]] || owned_paths="${owned_paths:+$owned_paths$'\n'}$absorbed_owned"
        done
        echo; echo '## Exact owned paths (binding)'
        if [[ -n "$owned_paths" ]]; then
            printf '%s\n' "$owned_paths"
        else
            echo '- `*`'
        fi
        echo; echo "Work only on this approved step and its declared owned files."
        echo "Do not edit workflow documents."
        if [[ "$owned_paths" == *'`package.json`'* ]]; then
            cat <<'DEPS_EOF'

## Dependencies (binding)

You write `package.json`, so it must declare every package that any file this build writes imports or runs, not only
the ones your own files use: the test runner and its DOM environment (for example `vitest` and `jsdom`), the testing
libraries the unit and DOM tests import, `@playwright/test`, the bundler and its framework plugin, and the runtime
packages the plan's stack names. A package imported anywhere but missing here fails the first test run with
"Cannot find package", and nothing else will add it.
DEPS_EOF
        fi
        if [[ -n "$module_interfaces_section" ]]; then
            printf '%s\n' "$module_interfaces_section"
        fi
        if [[ -e "$runtime_repair_marker" && -s "$LOG_DIR/green-check.log" ]]; then
            cat <<'EOF'

## Runtime repair (binding)

The driver is running this implementation pass because the previously merged
application could not build, serve, or discover tests. Fix the underlying
source/configuration defect in your owned paths; do not merely change reports
or tests to hide it. These are the most recent driver diagnostics:

EOF
            tail -n 30 "$LOG_DIR/green-check.log" >> "$prompt"
            echo >> "$prompt"
        fi
        cat <<'EOF'

## Speed (binding)

Steps run at the same time and the slowest one sets the stage's time, so every turn counts.
Your assigned step declaration below is the compact execution contract.

- Do not run `ls`, `find`, `cat` or any other exploratory command, and do not read files that other
  steps own: they are being written right now and may not exist yet. (Where your step's own text tells
  you to inspect or preserve a file that already exists, do exactly that.)
- Do not read the full requirements, plan, preflight report, or rendered workflow documents. They are
  intentionally not embedded for isolated steps: doing so multiplied a large plan by every parallel
  worker. Read one named canonical document only when the assigned step lacks a detail needed to make
  an owned-file change, and read the smallest relevant section.
- Write every file you own in your first response, as parallel Write calls, then stop.
- Do not run tests, builds or checks. The driver runs the whole verification right after the merge.
EOF
        echo "- Do not write an implementation-notes fragment unless this step has a deviation from the"
        echo "  plan, an unresolved concern or a plan blocker to report: the driver records the routine"
        echo "  fragment from the files you wrote. When you do have one, write it as one JSON object"
        echo "  matching the contract given earlier in this prompt, to"
        echo "  .uncle/workflow/parallel/notes/step-$step.json."
        if [[ ! "$step_line" =~ Owns:[[:space:]]*\* ]]; then
            cat <<'EOF'

## Isolated ownership boundary (binding)

You have a narrow file partition. Do not invoke a framework generator or
scaffolder (`npm create`, `npx create-*`, `create-vite`, `vite --template`,
or equivalent), because those tools write undeclared default files. Do not
create, delete, or modify any file outside this step's `Owns:` list. If a
framework scaffold is necessary, stop before creating it and record that the
approved plan must assign a whole-tree scaffold step; never guess its files.
EOF
        fi
        if [[ "$step_line" =~ ^[[:space:]]*[Rr]econcile:|Owns:[[:space:]]*\* ]]; then
            cat <<'EOF'

## Reconciliation execution boundary (binding)

This is a reconciliation step, not a second full verification stage. The
driver alone runs the approved `Verification commands` block after every
implementation step has merged. Do not run that block, an equivalent whole
suite, dependency installation, browser installation, or an end-to-end
regression sweep here. Do not write an application-wide test report from this
isolated worktree: it is not the canonical project tree and the driver cannot
adopt that report.

Inspect and fix only a concrete cross-step integration issue. Run at most one
narrow targeted smoke check for a changed integration point. Preserve required
defect-injection evidence only when it specifically covers an integration
invariant not already owned by an earlier step, using a disposable copy; do
not repeat the baseline suite after it. In the fragment, record the targeted
check or `DRIVER PENDING` for full verification.
EOF
        fi
    } >> "$prompt"
    # Do not embed the whole approved plan in every isolated coding
    # worker. On a modest application that turned one 60 KB plan into
    # hundreds of KB of repeated prefill, and the slowest worker then
    # dictated implementation latency. The declared step is the
    # compact contract; a worker can make one targeted Read only when
    # it genuinely needs a missing detail. Set this to 0 for an
    # unusually underspecified legacy plan that needs old embedding.
    if [[ "${WORKFLOW_COMPACT_IMPLEMENTATION_STEPS:-1}" != 1 \
          && -f "$ROOT/scripts/lib/worker_prompt.py" ]]; then
        local -a shared_inputs=()
        local shared
        for shared in REQUIREMENTS.md .uncle/docs/REQUIREMENTS_INTERPRETATION.md \
                      .uncle/docs/UPDATED_PROJECT_PLAN.md .uncle/docs/PREFLIGHT_REPORT.md; do
            [[ -s "$shared" ]] && shared_inputs+=("$shared")
        done
        if [[ ${#shared_inputs[@]} -gt 0 ]] \
           && python3 -B "$ROOT/scripts/lib/worker_prompt.py" --contract implementation "$prompt" "$prompt.shared" "${shared_inputs[@]}" 2>/dev/null; then
            mv "$prompt.shared" "$prompt"
        fi
    fi
}

# post_workers_fn for checklist_execute_worker_fastpath (scripts/lib/checklist-stage.sh):
# stops the app dev-server right after the checklist workers finish, exactly
# where this call sat before the fast-path extraction.
_stagegate_execute_checklist_stop_app_server() {
    python3 -B "$ROOT/scripts/lib/app_server.py" stop "$STATE_DIR" > /dev/null 2>&1 || true
}

# Per-group resume check: a group already merged under checkpoint_dir is
# skipped by parallel_implement_run_groups without rebuilding its prompts or
# calling parallel_run_group again.
_stagegate_parallel_group_already_merged() {
    local group="$1"
    [[ -e "$checkpoint_dir/group-$(printf '%s' "$group" | tr ' ' '_')" ]]
}

# Per-group resume marker, called by parallel_implement_run_groups once a
# group's notes have merged successfully.
_stagegate_parallel_mark_group_done() {
    local group="$1"
    touch "$checkpoint_dir/group-$(printf '%s' "$group" | tr ' ' '_')"
}

run_parallel_application_implementation() {
    local cmd model effort checkpoint_dir
    local complete_marker="$STATE_DIR/parallel-implementation-complete"
    local runtime_repair_marker="$STATE_DIR/runtime-readiness-force-implementation"
    # Completion markers are deliberately empty `touch` files.  Existence is
    # the contract; testing size makes every completed fan-out look unfinished
    # after a resume and reruns already merged code.
    if [[ -e "$complete_marker" && ! -e "$runtime_repair_marker" ]]; then
        echo 'Parallel implementation steps are already merged; reconciling their report only.'
        return 0
    fi
    parallel_prewarm_wait
    uncle_resolve_stage_runner implementation AGENT || return 1
    cmd="$(stage_agent_cmd implementation)" || return 1
    model="$(stage_model implementation)"
    effort="$(stage_effort implementation)"
    export PARALLEL_AGENT_CMD="$cmd" PARALLEL_AGENT_MODEL="$model"
    export PARALLEL_AGENT_EFFORT="$effort" PARALLEL_AGENT_TOOLS="$(stage_tools implementation)"
    checkpoint_dir="$STATE_DIR/parallel-implementation-groups"
    mkdir -p "$checkpoint_dir"
    plan_steps .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/implement-steps.txt"
    # `plan_steps` deliberately produces concise prose for the panel, but it
    # omits the machine-readable Owns fields.  Giving a worker only that prose
    # made it guess a root `launch.json` when the approved step owned
    # `.uncle/launch.json`; the ownership guard then threw away every parallel
    # result and forced a long serial implementation pass.  Keep the compact
    # prompt, while statefully attaching its exact file boundary.
    plan_step_owns .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/implement-owns.tsv"
    # Preserve worker handoffs in one canonical input for the report-only
    # reconciliation stage. A worker may record its narrow check here, but it
    # cannot truthfully attest to the whole merged application.
    # Do not erase handoffs for groups which have already merged.  A later
    # group can fail for a transient runner reason; its resume must continue
    # at that group, not ask completed workers to reapply their changes.
    if ! find "$checkpoint_dir" -type f -print -quit 2>/dev/null | grep -q .; then
        python3 "$ROOT/scripts/lib/implementation_notes.py" reset .
        rm -f .uncle/docs/IMPLEMENTATION_NOTES.md
    fi

    local groups_status=0
    # _stagegate_parallel_build_step_prompt carries the text and files of the steps merged into one worker.
    PARALLEL_BUILDER_SUPPORTS_MERGE=1
    parallel_implement_run_groups \
        .uncle/docs/UPDATED_PROJECT_PLAN.md \
        _stagegate_parallel_build_step_prompt \
        "Isolated step" \
        _stagegate_parallel_mark_group_done \
        _stagegate_parallel_group_already_merged || groups_status=$?
    [[ "$groups_status" == 0 ]] || return "$groups_status"

    # This marker is a recovery boundary. If report synthesis reaches a runner
    # limit, resuming retries just that small report stage rather than rerunning
    # already merged implementation steps.
    touch "$complete_marker"
    rm -f "$runtime_repair_marker"
}

# Parallel workers produce isolated code and handoffs. One normal agent
# invocation then produces the same canonical reports as serial implementation
# does. This preserves the stage contract without asking a worker to claim
# application-wide test results it could not have observed.
run_parallel_implementation_report() {
    local complete_marker="$STATE_DIR/parallel-implementation-complete"
    local report_marker="$STATE_DIR/parallel-implementation-report-complete"
    # -e, not -s: both markers are bare `touch`ed signal files, always 0
    # bytes by design. -s (nonempty) was always false for them, so this
    # function returned 1 here on every call, on every run, ever -- the
    # canonical .uncle/docs/IMPLEMENTATION_NOTES.md/AUTOMATED_TEST_REPORT.md reconciliation
    # this function exists for never actually happened, silently, until the
    # later `require_artifact .uncle/docs/AUTOMATED_TEST_REPORT.md` in the IMPLEMENT
    # state failed for a completely unrelated-looking reason.
    [[ -e "$complete_marker" ]] || return 1
    if [[ -e "$report_marker" ]]; then
        echo 'Parallel implementation report is already reconciled.'
        return 0
    fi
    echo 'Implementation report: recording merged worker evidence without a report-only model call.'
    python3 "$ROOT/scripts/lib/implementation_report_fallback.py" --project . --kind application --missing-only
    require_artifact .uncle/docs/IMPLEMENTATION_NOTES.md
    require_artifact .uncle/docs/AUTOMATED_TEST_REPORT.md
    touch "$report_marker"
}

# Independent checklist rows fan out through per-run temporary handoffs. The
# normal execution stage remains the only canonical report writer. Set to 0
# only to opt out of agent fan-out.
PARALLEL_CHECKLIST_WORKERS="${WORKFLOW_PARALLEL_CHECKLIST_WORKERS:-1}"

# One checklist worker session for the lane runner (checklist-lanes.sh): run it, check its packet, and
# give it one retry with the exact schema error.
checklist_run_worker() {
    local prompt="$1" label="$2" size="$3" packet="$4" worker_error
    # Bound the worker by progress, as the other writers are: a self-hosted worker that stops producing output is stopped, and only
    # its assigned rows are run again by reconciliation. Other runners are bounded only by their own ceiling.
    declare -F workflow_model_writer >/dev/null || . "$ROOT/scripts/lib/model-jobs.sh"
    SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 UNCLE_WORKER_PACKET_PATH="$packet" UNCLE_WRITER_CEILING="${WORKFLOW_EXECUTE_CHECKLIST_WORKER_SECONDS:-1800}" \
        workflow_model_writer execute-checklist run_claude "$prompt" "execute-checklist-worker-$label"
    if ! worker_error="$(python3 "$ROOT/scripts/lib/checklist_worker_packets.py" --expected placeholder --validate "$packet" 2>&1)"; then
        rm -f "$packet"
        echo "Worker $label packet rejected; retrying once with the exact schema error." >&2
        SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 UNCLE_WORKER_PACKET_PATH="$packet" UNCLE_WORKER_PACKET_ERROR="$worker_error" UNCLE_WRITER_CEILING="${WORKFLOW_EXECUTE_CHECKLIST_WORKER_SECONDS:-1800}" \
            workflow_model_writer execute-checklist run_claude "$prompt" "execute-checklist-worker-$label"
        python3 "$ROOT/scripts/lib/checklist_worker_packets.py" --expected placeholder --validate "$packet"
    fi
}

# Run only the rows that the independent checklist reviewer explicitly placed
# together. Each worker owns a private evidence file; it never writes the
# canonical reports or product files. Groups remain barriers, so a row that
# depends on an earlier group cannot start early. A worker failure is evidence
# for the synthesizer, not a reason to throw away results from its siblings.
run_parallel_checklist_workers() {
    local checklist_input="${1:-$STATE_DIR/documents/MANUAL_CHECKLIST.json}"
    local workers_output="${2:-$STATE_DIR/documents/EXECUTE_CHECKLIST_WORKERS.json}"
    local groups="$STATE_DIR/checklist-groups/groups.txt"
    # STATE_DIR is absolute in this driver; prefixing $PWD built /project//project/... and every
    # fan-out below returned early because that file never existed.
    case "$groups" in /*) ;; *) groups="$PWD/$groups" ;; esac
    local directory="" group id prompt packet batch_label compact_groups compact_batch_size compact_max_workers
    local worker_count=0 status pid jobs failed=0
    local -a ids pids pid_ids packet_names

    [[ "$PARALLEL_CHECKLIST_WORKERS" == 1 ]] || return 0
    if [[ "${WORKFLOW_EXECUTE_CHECKLIST_LANES:-1}" != 1 && ! -s "$groups" ]]; then
        return 0
    fi
    # A worker may not start a server (noinit: `npm run start` was denied and five browser checks were BLOCKED-SETUP after 86 s), so the
    # driver starts the application and every worker is told where it is.
    local worker_template="$ROOT/prompts/change/execute-checklist-worker.md" app_url=""
    if [[ "${WORKFLOW_CHECKLIST_APP_SERVER:-1}" == 1 ]] && app_url="$(python3 -B "$ROOT/scripts/lib/app_server.py" start "$PWD" "$STATE_DIR" 2>/dev/null)" && [[ -n "$app_url" ]]; then
        worker_template="$STATE_DIR/execute-checklist-worker-template.md"
        { cat "$ROOT/prompts/change/execute-checklist-worker.md"
          printf '\n## The application is already running (binding)\n\nThe driver started the application and it answers at %s. Drive that URL in the browser and with curl. Do not start, build or install anything yourself, and do not run `npm run start`, `vite` or any server: it is already up, and you are not allowed to start one.\n' "$app_url"
        } > "$worker_template"
        echo "Checklist: the application is running at $app_url for the browser checks."
    elif [[ "${WORKFLOW_CHECKLIST_APP_SERVER:-1}" == 1 ]]; then
        echo 'Checklist: the application could not be started by the driver; browser checks that need a running page may be BLOCKED-SETUP.'
    fi
    # A streamed lens is its own complete, validated checklist slice. Every
    # worker gets its exact immutable input instead of guessing the default.
    local bound_template="$STATE_DIR/execute-checklist-worker-${workers_output##*/}.md"
    cp "$worker_template" "$bound_template"
    printf '\n## Checklist input (binding)\n\nRead only `%s` for checklist rows in this lane. Do not read any other checklist document.\n' \
        "$checklist_input" >> "$bound_template"
    worker_template="$bound_template"
    # Lanes, the default: checks that share a resource or depend on one another run in order inside one
    # worker, everything else runs beside them, and nothing waits at a barrier (checklist_lanes.py).
    if [[ "${WORKFLOW_EXECUTE_CHECKLIST_COMPACT:-1}" == 1 && "${WORKFLOW_EXECUTE_CHECKLIST_LANES:-1}" == 1 ]]; then
        local lane_file="$STATE_DIR/checklist-groups/lanes.txt" lane_count
        [[ "$workers_output" == "$STATE_DIR/documents/EXECUTE_CHECKLIST_WORKERS.json" ]] \
            || lane_file="$STATE_DIR/checklist-groups/lanes.${workers_output##*/}.txt"
        case "$lane_file" in /*) ;; *) lane_file="$PWD/$lane_file" ;; esac
        mkdir -p "$(dirname "$lane_file")"
        if lane_count="$(checklist_lane_batches "$checklist_input" "$lane_file")"; then
            if [[ "$lane_count" -eq 0 ]]; then
                echo 'Checklist lanes: no required checks; recording an empty worker packet.'
                python3 "$ROOT/scripts/lib/checklist_worker_packets.py" "$(dirname "$lane_file")" \
                    "$workers_output" --expected
                return $?
            fi
            # A single lane is still execution work.  Sending it to the
            # parent makes the stage appear workerless and asks a full-context
            # synthesis agent to repeat the browser session.  Dispatch one
            # worker instead; it writes the normal packet and the driver keeps
            # the same JSON-only fast path.  Multiple lanes still fan out.
            [[ "$lane_count" -gt 1 ]] || echo "Checklist lanes: one shared-resource worker."
            directory="$(mktemp -d "$STATE_DIR/checklist-workers.XXXXXX")" || return 1
            {
                echo '# Parallel checklist worker evidence'
                echo
                echo 'Each batch ran as one worker; checks that share a resource or a dependency ran in order inside one.'
                echo 'The final execute-checklist stage is the sole writer of canonical reports.'
            } > "$directory/README.md"
            checklist_run_lanes "$directory" "$lane_file" "$worker_template"
            python3 "$ROOT/scripts/lib/checklist_worker_packets.py" "$directory" \
                "$workers_output" --expected "${packet_names[@]}" || return 1
            CHECKLIST_EXECUTE_PROMPT="$directory/execute-checklist-synthesis.md"
            cp "$ROOT/prompts/execute-checklist.md" "$CHECKLIST_EXECUTE_PROMPT"
            printf '\n## Collated worker results (binding)\n\nRead only `%s/documents/EXECUTE_CHECKLIST_WORKERS.json` for worker execution results. Do not read the worker directory, README, individual worker prompts, or raw worker output. It is complete, validated, ordered, and is the authoritative worker handoff. Do not rerun checks already represented there merely to compose reports.\n' \
                "$STATE_DIR" >> "$CHECKLIST_EXECUTE_PROMPT"
            return 0
        fi
    fi
    jobs="${WORKFLOW_VERIFY_JOBS:-4}"
    # Two digits now: ^[1-8]$ silently rejected anything above 9 and fell
    # back to 4, so raising the ceiling without widening the pattern would
    # have changed nothing.
    [[ "$jobs" =~ ^([1-9]|1[0-6])$ ]] || jobs=4
    # A checklist should not multiply model sessions or runtime setup. One
    # worker shares whatever evidence environment this project needs (browser,
    # service, CLI, database, or filesystem); driver green-check remains the
    # binding evidence for automated rows.
    if [[ "${WORKFLOW_EXECUTE_CHECKLIST_COMPACT:-1}" == 1 ]]; then
        compact_groups="$STATE_DIR/checklist-groups/compact.txt"
        # The reviewer's declared groups stay barriers; compact mode only bounds the
        # checks one worker takes inside a group (see compact_groups.py).
        python3 "$ROOT/scripts/lib/compact_groups.py" "$groups" "$checklist_input" > "$compact_groups" || return 1
        case "$compact_groups" in /*) groups="$compact_groups" ;; *) groups="$PWD/$compact_groups" ;; esac
        jobs=1
        compact_batch_size="${WORKFLOW_EXECUTE_CHECKLIST_COMPACT_BATCH_SIZE:-1}"
        [[ "$compact_batch_size" =~ ^[1-9][0-9]*$ ]] || compact_batch_size=1
        # Workers running at once inside one group; a larger group's batches simply grow.
        compact_max_workers="$(change_class_panel execute_workers 8 WORKFLOW_EXECUTE_CHECKLIST_MAX_WORKERS)"
        [[ "$compact_max_workers" =~ ^[1-9][0-9]*$ ]] || compact_max_workers=8
        echo "Checklist compact mode: declared groups kept as barriers, up to $compact_batch_size checks per worker session; automated rows cite driver green-check evidence."
    fi
    local group_total=0 max_groups
    while IFS= read -r group; do
        set -- $group
        worker_count=$((worker_count + $#))
        group_total=$((group_total + 1))
    done < "$groups"
    [[ "$worker_count" -gt 1 ]] || return 0
    # Every group is a barrier, so a checklist declared as many serial groups would take longer as workers
    # (each carries about fifteen seconds of startup) than as one agent running them in order.
    max_groups="${WORKFLOW_EXECUTE_CHECKLIST_MAX_GROUPS:-4}"
    [[ "$max_groups" =~ ^[1-9][0-9]*$ ]] || max_groups=4
    if [[ "$group_total" -gt "$max_groups" ]]; then
        echo "Checklist runs as one agent: its $worker_count checks fall into $group_total serial groups (over $max_groups), so workers would only add startup time."
        return 0
    fi

    # Runner Write tools are sandboxed to the workspace, so packets must be
    # created under workflow state rather than in an external temporary dir.
    directory="$(mktemp -d "$STATE_DIR/checklist-workers.XXXXXX")" || return 1
    mkdir -p "$directory/prompts"
    {
        echo '# Parallel checklist worker evidence'
        echo
        echo 'Only IDs on the same group line were executed concurrently.'
        echo 'The final execute-checklist stage is the sole writer of canonical reports.'
        echo
    } > "$directory/README.md"

    # One worker per batch, not one per check: a group of a dozen independent
    # checks used to launch a dozen full agent sessions, each rereading
    # .uncle/docs/MANUAL_CHECKLIST.md and both READMEs from scratch just to execute one
    # row. The group's own declaration already says these checks share no
    # exclusive resource, so running several of them one after another inside
    # a single session is exactly as safe as running them as separate
    # workers -- it only removes redundant context loads and process
    # start-up, bounded at `jobs` batches per group the same as before.
    #
    # Materialize every prompt and the full manifest before launching the
    # first child. Some runner adapters clean transient stage state as they
    # start; preparing siblings lazily made that cleanup race this driver's
    # writes.
    local n batches chunk start end i batch_index group_index=0
    while IFS= read -r group; do
        read -r -a ids <<< "$group"
        group_index=$((group_index + 1))
        n="${#ids[@]}"
        if [[ -n "$compact_batch_size" ]]; then
            batches=$(( (n + compact_batch_size - 1) / compact_batch_size ))
            [[ "$batches" -le "$compact_max_workers" ]] || batches="$compact_max_workers"
        else
            batches=$(( n < jobs ? n : jobs ))
        fi
        chunk=$(( (n + batches - 1) / batches ))
        i=0
        batch_index=0
        while [[ "$i" -lt "$n" ]]; do
            batch_index=$((batch_index + 1))
            batch_label="group-$group_index-batch-$batch_index"
            prompt="$directory/prompts/$batch_label.md"
            packet="$directory/$batch_label.json"
            cp "$worker_template" "$prompt"
            printf '\n## Assigned checks\n\n' >> "$prompt"
            end=$(( i + chunk < n ? i + chunk : n ))
            for ((start = i; start < end; start++)); do
                id="${ids[$start]}"
                printf -- '- Execute `%s`.\n' "$id" >> "$prompt"
            done
            printf '\n## Required result packet\n\nWrite the complete JSON packet to the private delivery path supplied by the driver. Chat text is diagnostics only.\n' >> "$prompt"
            packet_names+=("$batch_label")
            i="$end"
        done
    done < "$groups"

    group_index=0
    while IFS= read -r group; do
        read -r -a ids <<< "$group"
        group_index=$((group_index + 1))
        n="${#ids[@]}"
        if [[ -n "$compact_batch_size" ]]; then
            batches=$(( (n + compact_batch_size - 1) / compact_batch_size ))
            [[ "$batches" -le "$compact_max_workers" ]] || batches="$compact_max_workers"
        else
            batches=$(( n < jobs ? n : jobs ))
        fi
        echo "Checklist worker group: $group ($batches batch(es))"
        pids=()
        pid_ids=()
        for ((batch_index = 1; batch_index <= batches; batch_index++)); do
            batch_label="group-$group_index-batch-$batch_index"
            prompt="$directory/prompts/$batch_label.md"
            (
                local_worker_packet="$directory/$batch_label.json"
                SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 UNCLE_WORKER_PACKET_PATH="$local_worker_packet" \
                    run_claude "$prompt" "execute-checklist-worker-$batch_label"
                if ! local_worker_error="$(python3 "$ROOT/scripts/lib/checklist_worker_packets.py" --expected placeholder --validate "$local_worker_packet" 2>&1)"; then
                    rm -f "$local_worker_packet"
                    echo "Worker $batch_label packet rejected; retrying once with the exact schema error." >&2
                    SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 UNCLE_WORKER_PACKET_PATH="$local_worker_packet" UNCLE_WORKER_PACKET_ERROR="$local_worker_error" \
                        run_claude "$prompt" "execute-checklist-worker-$batch_label"
                    python3 "$ROOT/scripts/lib/checklist_worker_packets.py" --expected placeholder --validate "$local_worker_packet"
                fi
            ) > "$LOG_DIR/execute-checklist-worker-$batch_label.log" 2>&1 &
            pids+=("$!")
            pid_ids+=("$batch_label")
        done
        # Batches per group are already bounded at `jobs`, so every batch in
        # a group launches together; the barrier is only between groups.
        for ((status = 0; status < ${#pids[@]}; status++)); do
            pid="${pids[$status]}"
            wait "$pid" || echo "Worker ${pid_ids[$status]} did not complete; its packet is unavailable." >&2
            packet="$directory/${pid_ids[$status]}.json"
            if [[ ! -s "$packet" ]]; then
                echo "Worker ${pid_ids[$status]} did not write its required canonical result packet." >&2
            fi
        done
    done < "$groups"
    python3 "$ROOT/scripts/lib/checklist_worker_packets.py" "$directory" \
        "$workers_output" --expected "${packet_names[@]}" || return 1
    CHECKLIST_EXECUTE_PROMPT="$directory/execute-checklist-synthesis.md"
    cp "$ROOT/prompts/execute-checklist.md" "$CHECKLIST_EXECUTE_PROMPT"
    printf '\n## Collated worker results (binding)\n\nRead only `%s/documents/EXECUTE_CHECKLIST_WORKERS.json` for worker execution results. Do not read the worker directory, README, individual worker prompts, or raw worker output. It is complete, validated, ordered, and is the authoritative worker handoff. Do not rerun checks already represented there merely to compose reports.\n' \
        "$STATE_DIR" >> "$CHECKLIST_EXECUTE_PROMPT"
    return 0
}

# The project plan in sections (project_plan_sections.py): the core design first, then behaviors,
# invariants/tests and the closing sections side by side, then the traceability join.  Every worker
# shares the investigation prompt as its prefix.  Returns nonzero -- leaving nothing at $1 -- on any
# failure, so the caller runs the single-pass plan.
# One section worker, started in the background by the caller.  With schema-checked JSON (hosted Claude's
# --json-schema, or the grammar a self-hosted adapter enforces for the packet kind) the worker returns a packet
# and the driver renders its section file; otherwise (Codex) the worker writes the file itself.
# A small application is planned to a size budget. Only the sections that decide how many steps and files there are need to hear it.
project_plan_section_budget() {
    case "$1" in
        steps|sequence) change_class_budget >> "$2" ;;
    esac
}

project_plan_section_run() {
    local name="$1" directory="$2" helper="$ROOT/scripts/lib/project_plan_sections.py" delivery="$3" prompt
    prompt="$directory/prompts/$name.md"
    if [[ "$delivery" == file ]]; then
        python3 -B "$helper" prompt "$name" "$directory" "$ROOT/prompts/project-plan-investigate.md" "$prompt" || return 1
        project_plan_section_budget "$name" "$prompt"
        SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 run_claude "$prompt" "project-plan-section-$name"
        return
    fi
    # The section as typed blocks (docs/plan-model.md), not Markdown; WORKFLOW_PLAN_BLOCKS=0 keeps the Markdown bodies.
    local prompt_flag=--json schema_command=section
    if [[ "${WORKFLOW_PLAN_BLOCKS:-1}" == 1 ]]; then prompt_flag=--blocks; schema_command=section-model; fi
    python3 -B "$helper" prompt "$name" "$directory" "$ROOT/prompts/project-plan-investigate.md" "$prompt" "$prompt_flag" || return 1
    project_plan_section_budget "$name" "$prompt"
    rm -f "$directory/$name.json"
    if [[ "$delivery" == hosted ]]; then
        mkdir -p "$directory/schemas"
        python3 -B "$ROOT/scripts/lib/worker_schemas.py" "$schema_command" "$name" "$directory/schemas/$name.json" || return 1
        UNCLE_OUTPUT_SCHEMA_FILE="$directory/schemas/$name.json" UNCLE_STRUCTURED_OUTPUT_PATH="$directory/$name.json" \
            UNCLE_WORKER_PACKET_PATH="$directory/$name.json" SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 \
            run_claude "$prompt" "project-plan-section-$name"
    else
        UNCLE_WORKER_PACKET_PATH="$directory/$name.json" SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 \
            run_claude "$prompt" "project-plan-section-$name"
    fi
}

# After a section worker has finished: its section file exists, or this says why not.
project_plan_section_finish() {
    local name="$1" directory="$2" delivery="$3" helper="$ROOT/scripts/lib/project_plan_sections.py"
    if [[ "$delivery" != file ]]; then
        if [[ ! -s "$directory/$name.json" ]] && python3 -B "$ROOT/scripts/lib/structured_output.py" recover \
                "$LOG_DIR/project-plan-section-$name.jsonl" "$directory/$name.json" 2>/dev/null; then
            echo "Project plan section $name printed its packet instead of writing it; took it from the reply."
        fi
        python3 -B "$helper" render "$name" "$directory/$name.json" "$directory/$name.md" || return 1
        [[ -s "$directory/$name.md" ]]
        return
    fi
    [[ -s "$directory/$name.md" ]] && return 0
    # The worker answered in chat instead of calling Write (it happens): its answer is the section.
    python3 -B "$helper" recover "$LOG_DIR/project-plan-section-$name.jsonl" "$directory/$name.md" 2>/dev/null \
        && echo "Project plan section $name was answered in chat; used that answer."
}

# Take a completed section (optionally waiting for its PID); an unusable delivery gets one retry.
project_plan_section_settle() {
    local name="$1" directory="$2" delivery="$3" pid="${4:-}"
    [[ -z "$pid" ]] || wait "$pid" || { echo "Project plan section $name did not complete." >&2; return 1; }
    project_plan_section_finish "$name" "$directory" "$delivery" && return 0
    echo "Project plan section $name delivered nothing usable; running that worker once more."
    # Keep the failed attempt's logs: the rerun overwrites them, and why it failed is the evidence.
    cp "$LOG_DIR/project-plan-section-$name.jsonl" "$LOG_DIR/project-plan-section-$name.attempt1.jsonl" 2>/dev/null || true
    cp "$LOG_DIR/project-plan-section-$name.log" "$LOG_DIR/project-plan-section-$name.attempt1.log" 2>/dev/null || true
    project_plan_section_run "$name" "$directory" "$delivery" > "$LOG_DIR/project-plan-section-$name.log" 2>&1 || true
    project_plan_section_finish "$name" "$directory" "$delivery" || { echo "Project plan section $name wrote nothing." >&2; return 1; }
}

# Self-hosted sections form a small dependency graph: only outline gates the
# second phase. Each slot includes recovery/validation and the existing retry,
# so a slow or malformed sibling never holds an otherwise ready section back.
run_project_plan_sections_bounded() {
    local directory="$1" delivery="$2" jobs="$3" phase name index active failed=0 gate=0 next=0 gate_left
    local -a pending=() dependent=() pids=() names=() gate_names=()
    read -r -a gate_names < <(python3 -B "$ROOT/scripts/lib/project_plan_sections.py" gate)
    gate_left=${#gate_names[@]}
    while IFS= read -r phase; do
        if [[ "${#pending[@]}" == 0 ]]; then
            for name in $phase; do pending+=("$name"); done
        else
            for name in $phase; do dependent+=("$name"); done
        fi
    done < <(python3 -B "$ROOT/scripts/lib/project_plan_sections.py" phases)
    [[ "${#pending[@]}" -gt 0 ]] || return 1
    while :; do
        active=0
        for index in "${!pids[@]}"; do
            if kill -0 "${pids[$index]}" 2>/dev/null; then
                active=$((active + 1))
            else
                if wait "${pids[$index]}"; then
                    case " ${gate_names[*]} " in
                        *" ${names[$index]} "*) gate_left=$((gate_left - 1)); [[ "$gate_left" -gt 0 ]] || gate=1 ;;
                    esac
                else
                    failed=1
                fi
                unset "pids[$index]" "names[$index]"
            fi
        done
        if [[ "$gate" == 1 ]]; then
            pending+=("${dependent[@]}"); dependent=(); gate=2
        fi
        # On failure, drain only our workers before allowing the single-pass
        # fallback to start. No worker may keep writing into its fallback.
        if [[ "$failed" == 1 ]]; then
            for index in "${!pids[@]}"; do wait "${pids[$index]}" || true; done
            return 1
        fi
        while (( active < jobs && next < ${#pending[@]} )); do
            name="${pending[$next]}"
            echo "Project plan section worker: $name"
            (
                . "$ROOT/scripts/lib/model-jobs.sh"; workflow_model_enter project-plan || exit 1
                project_plan_section_run "$name" "$directory" "$delivery" > "$LOG_DIR/project-plan-section-$name.log" 2>&1 || exit 1
                project_plan_section_settle "$name" "$directory" "$delivery"
            ) &
            pids+=("$!"); names+=("$name")
            next=$((next + 1)); active=$((active + 1))
        done
        if (( active == 0 && next == ${#pending[@]} )); then
            [[ "$gate" == 2 ]]; return
        fi
        sleep 0.05
    done
}

run_project_plan_sections() {
    local output="$1" directory="$STATE_DIR/project-plan-sections"
    local helper="$ROOT/scripts/lib/project_plan_sections.py" phase name failed delivery=file index gate=1 gated
    local -a pids=() names=()
    gated=" $(python3 -B "$helper" gate) "
    . "$ROOT/scripts/lib/model-jobs.sh"
    local jobs
    jobs="$(workflow_model_capacity project-plan)"
    # Forced, schema-checked JSON wherever the runner can enforce it.
    if stage_supports_structured_output project-plan-section-outline; then
        delivery=hosted
    elif stage_uses_self_hosted project-plan AGENT; then
        delivery=local
    fi
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    if [[ "$jobs" != 0 ]]; then
        run_project_plan_sections_bounded "$directory" "$delivery" "$jobs" || return 1
    else
        # The first phase holds the outline and the workers that need only the requirements. The next phase starts when the
        # outline and the decision record (the gate) are done, whether or not the rest are; everything still running is
        # collected at the end.
        while IFS= read -r phase; do
            for name in $phase; do
                echo "Project plan section worker: $name"
                ( workflow_model_enter project-plan AGENT "$jobs" || exit 1; project_plan_section_run "$name" "$directory" "$delivery" ) > "$LOG_DIR/project-plan-section-$name.log" 2>&1 &
                pids+=("$!"); names+=("$name")
            done
            if [[ "$gate" == 1 ]]; then
                gate=0
                for index in "${!names[@]}"; do
                    [[ "$gated" == *" ${names[$index]} "* ]] || continue
                    if ! project_plan_section_settle "${names[$index]}" "$directory" "$delivery" "${pids[$index]}"; then
                        kill "${pids[@]}" 2>/dev/null || true
                        wait 2>/dev/null || true
                        return 1
                    fi
                    unset "pids[$index]" "names[$index]"
                done
            fi
        done < <(python3 -B "$helper" phases)
        failed=0
        for index in "${!pids[@]}"; do
            project_plan_section_settle "${names[$index]}" "$directory" "$delivery" "${pids[$index]}" || failed=1
        done
        [[ "$failed" == 0 ]] || return 1
    fi
    # The traceability table is built here from the workers' own mapping lines.  Only a plan whose workers
    # left too little behind needs the model, and then one worker reads everything and writes it.
    if ! python3 -B "$helper" trace-ready "$directory"; then
        echo "Project plan: the workers left too few requirement mappings; a traceability worker will write section 13."
        project_plan_section_run trace "$directory" "$delivery" > "$LOG_DIR/project-plan-section-trace.log" 2>&1 \
            || { echo "Project plan section trace did not complete." >&2; return 1; }
        project_plan_section_finish trace "$directory" "$delivery" || { echo "Project plan section trace wrote nothing." >&2; return 1; }
    fi
    python3 -B "$helper" assemble "$directory" "$output" || return 1
    # Stage-wide duties (.gitignore, whole-plan consistency) run once here, not in every section worker.
    . "$ROOT/scripts/lib/project-plan-stage.sh"; project_plan_stage_finish "$directory" "$output" || return 1
    # The same plan as a model, from the workers' typed blocks; kept beside the plan JSON when it agrees with it.
    python3 -B "$helper" assemble-model "$directory" "$directory/model.json" 2>/dev/null || rm -f "$directory/model.json"
    # The assembled plan must pass the checks a single-pass plan does before it is believed.
    python3 "$ROOT/scripts/lib/plan_context.py" plan-unprotected "$output" . > /dev/null 2>&1 || {
        echo 'The assembled project plan did not validate; falling back to the single-pass plan.' >&2
        return 1
    }
}

# A sectioned plan starts more than twenty specialist calls, which the
# fanned-out parallelism makes faster for every brief, not only a large one
# -- the per-section calls run concurrently, so more sections cost wall-clock
# only up to the slowest one, not their sum. Default on; WORKFLOW_PROJECT_PLAN_SECTIONS=auto
# restores the size-gated heuristic (small briefs get one serial planner
# instead) for anyone who wants to trade that speed for fewer total calls,
# and =0 turns sectioning off entirely.
project_plan_sections_enabled() {
    local setting="${WORKFLOW_PROJECT_PLAN_SECTIONS:-1}"
    local source="${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md}"
    local minimum="${WORKFLOW_PROJECT_PLAN_SECTIONS_MIN_BYTES:-12000}"
    case "$setting" in
        0|false|no|off) return 1 ;;
        1|true|yes|on) return 0 ;;
        auto|'') ;;
        *) echo "Invalid WORKFLOW_PROJECT_PLAN_SECTIONS value: $setting (use auto, 0, or 1)." >&2; return 1 ;;
    esac
    [[ -f "$source" ]] || return 1
    [[ "$minimum" =~ ^[0-9]+$ ]] || minimum=12000
    (( $(wc -c < "$source") >= minimum ))
}

# Every stage's actual work, with no state transitions and no approval checks,
# so a stage can be run either in the foreground or speculatively.
run_stage() {
    if (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_terminal_failure); then
        cat "$STATE_DIR/stop-reason" >&2
        return 1
    fi
    case "$1" in
        UPDATED_PLAN) (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_archive_stage updated-plan) || return 1 ;;
        PREFLIGHT) (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_archive_stage preflight) || return 1 ;;
    esac
    case "$1" in
        DERIVE_BRIEF)
            run_claude prompts/derive-brief.md derive-brief
            require_artifact "${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md}"
            # The brief already existed, so require_artifact cannot tell a
            # derivation that filled it from one that wrote nothing. Say which
            # happened: a gate on an unchanged document looks like a document
            # someone reviewed.
            if ! python3 "$ROOT/scripts/lib/early-prerequisites.py" \
                    "${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md}" >/dev/null 2>&1; then
                echo
                echo "Derivation left ${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md} unfilled:"
                python3 "$ROOT/scripts/lib/early-prerequisites.py" \
                    "${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md}" 2>&1 | sed 's/^/  /' || true
                echo "Read its Open questions section: either the issue settles"
                echo "too little to derive from, or the stage could not do its job."
                echo "Approving now carries an unfilled brief into planning, which"
                echo "the prerequisite check will stop."
            fi
            ;;
        REQUIREMENTS)
            # One pass writes both documents. The plan half otherwise re-reads
            # the brief and the interpretation that the requirements half just
            # produced, paying for a second process, a second cold context and
            # a second read of files already in hand. Both documents are still
            # written separately, validated separately and approved separately;
            # only the invocation is shared.
            if merged_requirements_plan_enabled; then
                run_initial_planning_agent prompts/requirements-plan.md project-plan
            elif stage_uses_self_hosted requirements AGENT; then
                requirements_investigation=".uncle/workflow/requirements-investigation.md"
                rm -f "$requirements_investigation"
                run_initial_planning_agent prompts/requirements-investigate.md requirements-investigate
                if [[ ! -s "$requirements_investigation" ]]; then
                    python3 "$ROOT/scripts/lib/recover_investigation.py" \
                        "$LOG_DIR/requirements-investigate.jsonl" "$requirements_investigation" \
                        --heading '## Required functionality' \
                        && echo 'Requirements investigation recovered from final runner output.'
                fi
                require_file "$requirements_investigation"
                cp "$requirements_investigation" .uncle/docs/REQUIREMENTS_INTERPRETATION.md
                python3 "$ROOT/scripts/lib/requirements-context.py" --export-json \
                    .uncle/docs/REQUIREMENTS_INTERPRETATION.md . || exit 1
                python3 "$ROOT/scripts/lib/requirements-context.py" --render-json \
                    . .uncle/docs/REQUIREMENTS_INTERPRETATION.md || exit 1
                echo 'Requirements fast path: deterministically rendered canonical JSON from the completed investigation.'
            elif stage_supports_structured_output requirements \
                 && mkdir -p "$STATE_DIR/artifact-delivery" \
                 && python3 -B "$ROOT/scripts/lib/worker_schemas.py" requirements "$STATE_DIR/requirements-schema.json"; then
                # Hosted Claude answers through a schema-checked call: no Write turn, and a missing section is a schema error the
                # model sees, not a crash in the renderer.  Anything else keeps the file contract.
                UNCLE_OUTPUT_SCHEMA_FILE="$STATE_DIR/requirements-schema.json" \
                    UNCLE_STRUCTURED_OUTPUT_PATH="$STATE_DIR/artifact-delivery/requirements.json" \
                    run_initial_planning_agent prompts/requirements.md requirements \
                    || run_initial_planning_agent prompts/requirements.md requirements
            else
                run_initial_planning_agent prompts/requirements.md requirements
            fi
            ;;
        PROJECT_PLAN)
            project_plan_investigation=".uncle/workflow/project-plan-investigation.md"
            rm -f "$project_plan_investigation"
            # Large plans are written in sections by parallel workers. Small
            # briefs use the single planner by default; setting
            # WORKFLOW_PROJECT_PLAN_SECTIONS=1 forces sections. Any failure -- a worker, a section out
            # of its lane, an assembled plan the validators refuse -- leaves no investigation behind and
            # the single-pass plan runs as it always did.
            project_plan_sectioned=0
            if project_plan_sections_enabled && run_project_plan_sections "$project_plan_investigation"; then
                project_plan_sectioned=1
                echo 'Project plan written in parallel sections and assembled by the driver.'
            else
                rm -f "$project_plan_investigation"
            fi
            if [[ "$project_plan_sectioned" == 1 ]] || stage_uses_self_hosted project-plan AGENT; then
                [[ "$project_plan_sectioned" == 1 ]] || run_initial_planning_agent prompts/project-plan-investigate.md project-plan-investigate
                if [[ ! -s "$project_plan_investigation" ]]; then
                    python3 "$ROOT/scripts/lib/recover_investigation.py" \
                        "$LOG_DIR/project-plan-investigate.jsonl" "$project_plan_investigation" \
                        --heading '# Project plan' \
                        && echo 'Project-plan investigation recovered from final runner output.'
                fi
                require_file "$project_plan_investigation"
                # The investigation has a deliberately mechanical boundary:
                # all prose becomes `narrative` and the one fenced
                # Verification commands block becomes `verification_commands`.
                # Do that conversion in the driver rather than spending a
                # second model call copying a large plan into JSON.
                cp "$project_plan_investigation" .uncle/docs/PROJECT_PLAN.md
                # Shape-only repair of the one unambiguous slip (commands as
                # `$ cmd` lines with no fence); anything else still fails below.
                python3 -B "$ROOT/scripts/lib/repair_document_format.py" .uncle/docs/PROJECT_PLAN.md || true
                python3 "$ROOT/scripts/lib/plan_context.py" export-project-plan \
                    .uncle/docs/PROJECT_PLAN.md . || exit 1
                python3 "$ROOT/scripts/lib/plan_context.py" render-project-plan \
                    .uncle/docs/PROJECT_PLAN.md . || exit 1
                if [[ -s "$STATE_DIR/project-plan-sections/model.json" ]]; then
                    python3 -B "$ROOT/scripts/lib/plan_model.py" attach "$STATE_DIR/documents/PROJECT_PLAN.json" \
                        "$STATE_DIR/project-plan-sections/model.json" \
                        || echo 'Project plan: the authored model was not stored (the narrative will be imported instead).' >&2
                fi
                echo 'Project-plan fast path: deterministically rendered canonical JSON from the completed investigation.'
            else
                run_initial_planning_agent prompts/project-plan.md project-plan
            fi
            if [[ -s .uncle/docs/PROJECT_PLAN.md ]]; then
                plan_ingest_error="$(python3 "$ROOT/scripts/lib/plan_context.py" plan-unprotected .uncle/docs/PROJECT_PLAN.md . 2>&1)" || {
                    printf '%s\n' "$plan_ingest_error" >&2
                    supervision_validation_failed project-plan .uncle/docs/PROJECT_PLAN.md "$plan_ingest_error"
                    exit 1
                }
                ensure_project_plan_json || exit 1
            fi
            require_artifact .uncle/docs/PROJECT_PLAN.md
            # Advisory: how much of the plan can implement at once, while it can still change.
            python3 -B "$ROOT/scripts/lib/plan_parallelism.py" .uncle/docs/PROJECT_PLAN.md 2>/dev/null \
                | tee "$STATE_DIR/plan-parallelism.txt" || true
            # The plan names the packages and the browser: fetch them now, while review runs.
            install_warm_start .uncle/docs/PROJECT_PLAN.md
            ;;
        ADVERSARIAL_REVIEW)
            ensure_project_plan_json || exit 1
            run_adversarial_review_panel
            # Gated on the panel actually being enabled, not just on a file
            # happening to exist there: with the panel disabled, a stale
            # canonical review left over from an earlier run (its own inputs
            # since changed) matched this same check on sight, serving it
            # back to a review this stage means to redo. Only the direct
            # run_codex_review call below has real input-change invalidation
            # (review_input_key/restore_plan_review); this fast path is only
            # valid when run_adversarial_review_panel is what just wrote it.
            if [[ "${WORKFLOW_ADVERSARIAL_REVIEW_PANEL:-1}" == 1 ]] \
                    && [[ -s "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" ]]; then
                echo 'Adversarial-review fast path: rendered authoritative worker findings without parent synthesis.'
                python3 "$ROOT/scripts/lib/adversarial-context.py" --validate-json . || exit 1
                python3 "$ROOT/scripts/lib/adversarial-context.py" --render-json . .uncle/docs/ADVERSARIAL_REVIEW.md || exit 1
                return 0
            fi
            if stage_uses_self_hosted adversarial-review REVIEWER; then
                adversarial_review_investigation=".uncle/workflow/adversarial-review-investigation.md"
                rm -f "$adversarial_review_investigation"
                run_codex_review \
                    "${ADVERSARIAL_REVIEW_PROMPT:-prompts/adversarial-review-investigate.md}" \
                    "$adversarial_review_investigation" \
                    adversarial-review-investigate
                cp "$adversarial_review_investigation" .uncle/docs/ADVERSARIAL_REVIEW.md
                python3 "$ROOT/scripts/lib/adversarial-context.py" --export-json \
                    .uncle/docs/ADVERSARIAL_REVIEW.md . || exit 1
                python3 "$ROOT/scripts/lib/adversarial-context.py" --render-json \
                    . .uncle/docs/ADVERSARIAL_REVIEW.md || exit 1
                echo 'Adversarial-review fallback: deterministically rendered canonical JSON from the completed investigation.'
            else
                run_codex_review \
                    "${ADVERSARIAL_REVIEW_PROMPT:-prompts/adversarial-review.md}" \
                    "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json" \
                    adversarial-review
            fi
            python3 "$ROOT/scripts/lib/adversarial-context.py" --validate-json . || exit 1
            python3 "$ROOT/scripts/lib/adversarial-context.py" --render-json . .uncle/docs/ADVERSARIAL_REVIEW.md || exit 1
            ;;
        UPDATED_PLAN)
            if [[ -s "$STATE_DIR/updated-plan-structure-feedback.md" ]]; then
                . "$ROOT/scripts/lib/updated-plan-repair.sh"
                run_updated_plan_structure_repair "$STATE_DIR/documents/UPDATED_PROJECT_PLAN.json" \
                    "$(cat "$STATE_DIR/updated-plan-structure-feedback.md")" updated-plan || return 1
                rm -f "$STATE_DIR/updated-plan-structure-feedback.md"
                return 0
            fi
            # A review with findings falls through to the normal collated
            # worker panel; a clean review needs no worker calls at all.
            if run_updated_plan_fast_path; then
                echo 'Updated-plan fast path: no adversarial findings; copied canonical plan without model synthesis.'
                return 0
            fi
            # Findings normally need one small, schema-bound patch.  Do not
            # turn that into a committee: every extra worker rereads the same
            # plan and review and makes this approval gate minutes slower.
            # A structural retry is the sole exception because it needs the
            # driver's exact validation feedback appended below.
            if [[ ! -s "$STATE_DIR/updated-plan-structure-feedback.md" && "${WORKFLOW_UPDATED_PLAN_COMPACT:-1}" == 1 ]]; then
                # Do not silently turn one rejected compact delivery into the
                # old many-call committee.  That made a nominally fast stage
                # unpredictably take minutes and hid the useful JSON schema
                # error.  Operators can still opt in early with
                # WORKFLOW_UPDATED_PLAN_COMPACT=0.  The one case this does
                # escalate automatically: a self-hosted model whose compact
                # delivery failed outright (status 2, see
                # run_updated_plan_compact) is a capability mismatch with the
                # strict exact-match patch contract, not a transient format
                # slip -- resuming the process teaches it nothing, so it
                # would otherwise fail identically forever. Fall through to
                # the panel below exactly once for that case.
                local adaptive_status=0
                run_updated_plan_adaptive || adaptive_status=$?
                [[ "$adaptive_status" == 2 ]] || return "$adaptive_status"
            fi
            # A non-empty review needs the panel.  Never continue into the
            # parent call if collation failed: the collated JSON is its only
            # specialist input and a clear packet error is actionable.
            if [[ ! -s "$STATE_DIR/updated-plan-structure-feedback.md" ]] && run_updated_plan_decide; then
                echo 'Updated plan: written by deciding writers and checked by the specialists.'
                return 0
            fi
            if (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_terminal_failure); then cat "$STATE_DIR/stop-reason" >&2; return 1; fi
            run_updated_plan_panel || return 1
            # The panel has already collated every specialist finding into
            # canonical JSON. Every runner gets the sealed compact prompt;
            # there is no repository-discovery fallback or Markdown handoff.
            local single_call=0
            if [[ -s "$STATE_DIR/updated-plan-structure-feedback.md" && -f "$UPDATED_PLAN_PROMPT" ]]; then
                cat "$STATE_DIR/updated-plan-structure-feedback.md" >> "$UPDATED_PLAN_PROMPT"
                rm -f "$STATE_DIR/updated-plan-structure-feedback.md"
                single_call=1   # a rejected plan is repaired by one call that sees the whole problem
            fi
            if [[ "$single_call" == 1 ]] || ! run_updated_plan_edit_writers; then
                if (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_terminal_failure); then cat "$STATE_DIR/stop-reason" >&2; return 1; fi
                # Forced JSON here too: the whole-plan call answers through a schema-checked StructuredOutput
                # call (hosted Claude) or the local grammar, never free text the driver has to dig a plan out of.
                if stage_supports_structured_output updated-plan; then
                    mkdir -p "$STATE_DIR/artifact-delivery" "$STATE_DIR/updated-plan-edits/schemas"
                    python3 -B "$ROOT/scripts/lib/worker_schemas.py" synthesis plan protected \
                        "$STATE_DIR/updated-plan-edits/schemas/synthesis.json" \
                        && UNCLE_OUTPUT_SCHEMA_FILE="$STATE_DIR/updated-plan-edits/schemas/synthesis.json" \
                           UNCLE_STRUCTURED_OUTPUT_PATH="$STATE_DIR/artifact-delivery/updated-plan.json" \
                           run_claude "$UPDATED_PLAN_PROMPT" updated-plan \
                        || run_claude "$UPDATED_PLAN_PROMPT" updated-plan
                else
                    run_claude "$UPDATED_PLAN_PROMPT" updated-plan
                fi
            fi
            ;;
        IMPLEMENT)
            green_background_cancel
            implementation_scaffold_template .uncle/docs/UPDATED_PROJECT_PLAN.md || return $?
            parallel_status=0
            run_parallel_application_implementation || parallel_status=$?
            if [[ "$parallel_status" != 0 ]]; then
                [[ "$parallel_status" == 2 ]] || return "$parallel_status"
                echo "Implementation fan-out unavailable: the approved plan has no independent owned steps; running one implementation agent."
                if stage_uses_self_hosted implementation AGENT; then
                    # Same split, different shape: the coding pass does the
                    # real Write/Edit/Bash work and writes AUTOMATED_TEST_REPORT.md
                    # (already plain Markdown) directly, but drafts its
                    # implementation notes as Markdown too, instead of the
                    # required JSON -- a long coding session that also has to
                    # land an exact schema at the very end kept losing the
                    # schema. The short format pass never looks at the code;
                    # it only converts the notes draft.
                    implementation_notes_investigation=".uncle/workflow/implementation-notes-investigation.md"
                    rm -f "$implementation_notes_investigation"
                    run_claude prompts/implement-investigate.md implementation-investigate
                    if [[ -s "$implementation_notes_investigation" ]]; then
                        python3 "$ROOT/scripts/lib/implementation_notes.py" append . \
                            "$implementation_notes_investigation" \
                            .uncle/docs/IMPLEMENTATION_NOTES.md Implementation || return 1
                        echo 'Implementation-notes fast path: preserved the completed investigation as a canonical fragment.'
                    else
                        # Coding is the work; this private prose checkpoint is
                        # merely a handoff.  A long self-hosted coding turn can
                        # finish its edits yet lose the final Write call.  Do
                        # not discard that tree or make an operator retry it.
                        # The driver below records an explicitly incomplete
                        # canonical handoff and its green check supplies the
                        # actual observed verification evidence.
                        echo 'Implementation notes checkpoint was omitted; recording incomplete canonical handoff evidence.'
                    fi
                else
                    run_claude prompts/implement.md implementation
                fi
                implementation_fast_check serial || return $?
                # A serial implementation agent can finish code while omitting
                # one or both reports.  Ingest a valid JSON-first test report
                # when one was supplied, but never spend a second model turn
                # merely to format or reconstruct handoff prose.  The
                # conservative driver fallback below preserves the gap as NOT
                # RUN and lets the driver-owned green check decide the code.
                if [[ -s .uncle/docs/AUTOMATED_TEST_REPORT.md ]]; then
                    python3 "$ROOT/scripts/lib/test_report.py" validate . application \
                        .uncle/docs/AUTOMATED_TEST_REPORT.md 2>/dev/null \
                        || echo 'Implementation test handoff was not valid JSON; recording incomplete canonical evidence instead.'
                fi
                if [[ ! -s "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json" || ! -s "$STATE_DIR/documents/AUTOMATED_TEST_REPORT.json" ]]; then
                    echo 'Implementation omitted a required handoff; recording incomplete reports without rerunning source.'
                    python3 "$ROOT/scripts/lib/implementation_report_fallback.py" --project . --kind application --missing-only
                fi
                local notes_ingest_error
                notes_ingest_error="$(python3 "$ROOT/scripts/lib/implementation_notes.py" validate . \
                    .uncle/workflow/documents/IMPLEMENTATION_NOTES.json --require-json 2>&1)" || {
                    echo "$notes_ingest_error"
                    supervision_validation_failed implementation-notes \
                        .uncle/workflow/documents/IMPLEMENTATION_NOTES.json "$notes_ingest_error"
                    return 1
                }
                python3 "$ROOT/scripts/lib/implementation_notes.py" render . .uncle/docs/IMPLEMENTATION_NOTES.md
                local test_report_ingest_error
                test_report_ingest_error="$(python3 "$ROOT/scripts/lib/test_report.py" validate . application \
                    .uncle/workflow/documents/AUTOMATED_TEST_REPORT.json 2>&1)" || {
                    echo "$test_report_ingest_error"
                    supervision_validation_failed automated-test-report \
                        .uncle/workflow/documents/AUTOMATED_TEST_REPORT.json "$test_report_ingest_error"
                    return 1
                }
            else
                run_parallel_implementation_report
            fi
            if [[ ! -s .uncle/docs/IMPLEMENTATION_NOTES.md || ! -s .uncle/docs/AUTOMATED_TEST_REPORT.md ]]; then
                echo 'Implementation reports missing; recording incomplete handoff evidence automatically.'
                python3 "$ROOT/scripts/lib/implementation_report_fallback.py" --project . --kind application --missing-only
            fi
            require_artifact .uncle/docs/IMPLEMENTATION_NOTES.md
            require_artifact .uncle/docs/AUTOMATED_TEST_REPORT.md
            # A runtime-readiness repair applies to this implementation pass
            # only. Keep its attempted marker (it bounds retries), but do not
            # leak the repair prompt into later report-only reconciliations.
            rm -f "$STATE_DIR/runtime-readiness-force-implementation"
            ;;
        PREFLIGHT)
            rm -f "$STATE_DIR/documents/PREFLIGHT_REPORT.json" .uncle/docs/PREFLIGHT_REPORT.md
            if python3 -B "$ROOT/scripts/lib/preflight.py" "$GREEN_CMDS" "$STATE_DIR/documents/PREFLIGHT_REPORT.json"; then
                echo "Preflight: runtime checks passed without a model call."
            else
                echo "Preflight: requesting model diagnosis of unresolved prerequisites."
                if stage_uses_self_hosted preflight AGENT; then
                    if run_preflight_investigation_panel; then
                        echo 'Preflight investigation panel: canonical JSON collated from parallel worker packets.'
                    else
                        (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_terminal_failure) && exit 1
                        preflight_investigation=".uncle/workflow/preflight-investigation.md"
                        rm -f "$preflight_investigation"
                        run_claude prompts/preflight-investigate.md preflight-investigate
                        require_file "$preflight_investigation"
                        cp "$preflight_investigation" .uncle/docs/PREFLIGHT_REPORT.md
                        python3 "$ROOT/scripts/lib/acceptance_context.py" --export-json \
                            .uncle/docs/PREFLIGHT_REPORT.md . PREFLIGHT_REPORT || exit 1
                        python3 "$ROOT/scripts/lib/acceptance_context.py" --render \
                            "$STATE_DIR/documents/PREFLIGHT_REPORT.json" \
                            .uncle/docs/PREFLIGHT_REPORT.md || exit 1
                        echo 'Preflight fast path: deterministically rendered canonical JSON from the completed investigation.'
                    fi
                else
                    run_claude prompts/preflight.md preflight
                    # Unlike the self-hosted investigation path above, this
                    # hosted call has no canonical-JSON delivery contract
                    # (preflight is not one of run_claude's special-cased
                    # log_names) -- it only writes the Markdown view. Ingest
                    # it the same way, or --validate-json below reads a
                    # canonical file that was never written.
                    python3 "$ROOT/scripts/lib/acceptance_context.py" --export-json \
                        .uncle/docs/PREFLIGHT_REPORT.md . PREFLIGHT_REPORT || exit 1
                fi
                # A diagnosing reviewer writes the canonical packet directly.
                # Markdown is rendered only after JSON validation below.
            fi
            python3 "$ROOT/scripts/lib/acceptance_context.py" --validate-json "$STATE_DIR/documents/PREFLIGHT_REPORT.json" || exit 1
            python3 "$ROOT/scripts/lib/acceptance_context.py" --render "$STATE_DIR/documents/PREFLIGHT_REPORT.json" .uncle/docs/PREFLIGHT_REPORT.md || exit 1
            require_artifact "$STATE_DIR/documents/PREFLIGHT_REPORT.json"
            ;;
        TEST_REVIEW)
            # Preserve the previous findings for the next review and repairs.
            if [[ -s .uncle/docs/TEST_REVIEW.md ]]; then
                cp .uncle/docs/TEST_REVIEW.md "$STATE_DIR/previous-test-review.md"
            fi
            rm -f .uncle/docs/TEST_REVIEW.md
            run_test_review_panel
            if [[ -s .uncle/docs/TEST_REVIEW.md ]]; then
                echo 'Test-review fast path: merged authoritative worker rows without parent synthesis.'
                return 0
            fi
            if stage_uses_self_hosted test-review REVIEWER; then
                # Split into two calls: a long, read-heavy investigation with
                # no strict output shape, then a short, mechanical conversion
                # of that investigation into the required JSON. A single
                # call asking a weak self-hosted model to both explore many
                # documents *and* hit an exact schema at the end of a long
                # turn kept losing the schema -- the investigation is where
                # the reading and judgment belong; the second call's only
                # job is formatting, with almost nothing else in its context
                # to lose track of. Proprietary models do not show this
                # failure, so they skip straight to the single call below.
                # The panel is the normal no-model-synthesis path. If it is
                # unavailable, use one canonical review call rather than an
                # investigation followed by a second formatting-only call.
                run_codex_review "${TEST_REVIEW_PROMPT:-prompts/test-review.md}" \
                    "$PROJECT_ROOT/.uncle/docs/TEST_REVIEW.md" test-review
            else
                # A malformed acceptance table gets one local, format-only
                # retry even when optional supervision is disabled. Reuse the
                # saved synthesis prompt and its collated JSON; re-running
                # the four specialists cannot fix a parent table-format error.
                # The marker remains after delivery so repeated malformed
                # output stops normally.
                if [[ -s "$STATE_DIR/test-review-format-retry.md" ]]; then
                    echo "Retrying test-review formatting only; reusing the saved collated worker packet."
                    test_review_prompt="$STATE_DIR/test-review-format-retry-prompt.md"
                    {
                        if [[ -s "$STATE_DIR/test-review-panel/synthesis.md" ]]; then
                            cat "$STATE_DIR/test-review-panel/synthesis.md"
                        else
                            cat "${TEST_REVIEW_PROMPT:-$ROOT/prompts/test-review.md}"
                        fi
                        printf '\n\n## Required format retry\n\n'
                        cat "$STATE_DIR/test-review-format-retry.md"
                    } > "$test_review_prompt"
                else
                    run_test_review_panel
                    test_review_prompt="${TEST_REVIEW_PROMPT:-prompts/test-review.md}"
                fi
                run_codex_review "$test_review_prompt" "$PROJECT_ROOT/.uncle/docs/TEST_REVIEW.md" test-review
            fi
            # The panel path above already leaves documents/TEST_REVIEW.json
            # (and returns before here). The single-reviewer path just wrote
            # the Markdown view; nothing ingests it into the canonical JSON
            # VALIDATE_TEST_REVIEW and later stages actually read. A failed
            # export here (a malformed table) must not abort the stage --
            # VALIDATE_TEST_REVIEW's own acceptance_result check reads the
            # Markdown directly and owns the one-shot format-retry path.
            if [[ ! -s "$STATE_DIR/documents/TEST_REVIEW.json" ]]; then
                python3 "$ROOT/scripts/lib/acceptance_context.py" --export-json \
                    .uncle/docs/TEST_REVIEW.md . TEST_REVIEW 2>/dev/null || true
            fi
            ;;
        REPAIR)
            green_background_cancel
            if stage_uses_self_hosted repair AGENT; then
                # Same split as implementation, with a twist: the format pass
                # cannot just emit a fresh document -- a repair only touches
                # some findings, and everything else's disposition from
                # earlier passes has to survive untouched. So the format
                # pass reads the current IMPLEMENTATION_NOTES.md itself and
                # merges the repair notes into it, rather than starting over.
                repair_notes_investigation=".uncle/workflow/repair-notes-investigation.md"
                rm -f "$repair_notes_investigation"
                run_claude "$REPAIR_PROMPT" repair-investigate
                # Some models answer with the completed notes as their final
                # message instead of writing the file (the same gap
                # requirements-investigate already covers for OpenCode
                # models); recover it deterministically before treating the
                # pass as having produced nothing.
                if [[ ! -s "$repair_notes_investigation" ]]; then
                    python3 "$ROOT/scripts/lib/recover_investigation.py" \
                        "$LOG_DIR/repair-investigate.jsonl" "$repair_notes_investigation" \
                        --heading '## Changed files' \
                        && echo 'Repair-notes investigation recovered from final runner output.'
                fi
                # require_file below exits the whole driver immediately on a
                # real miss here, and its own EXIT-trap triage write is
                # best-effort (failures are swallowed to stderr, which an
                # unattended run with no captured driver log never sees). A
                # repair-investigate pass that returns without the notes --
                # for any reason, recoverable or not -- otherwise strands the
                # run with no durable trace of why: no stop-reason, and a
                # TRIAGE.md that depends on a trap actually completing before
                # whatever ends the process (signal, crash, host kill) does.
                # Record the reason here, synchronously, before that happens.
                if [[ ! -s "$repair_notes_investigation" ]]; then
                    printf '%s\n' "repair-investigate: $repair_notes_investigation was not produced by the agent call or its recovery fallback; see $LOG_DIR/repair-investigate.jsonl for the transcript." \
                        > "$STATE_DIR/stop-reason"
                fi
                require_file "$repair_notes_investigation"
                python3 "$ROOT/scripts/lib/implementation_notes.py" append . \
                    "$repair_notes_investigation" \
                    .uncle/docs/IMPLEMENTATION_NOTES.md Repair || return 1
                echo 'Repair-notes fast path: merged the completed investigation as a canonical fragment.'
            else
                run_claude "$REPAIR_PROMPT" repair
            fi
            require_artifact .uncle/docs/IMPLEMENTATION_NOTES.md
            require_artifact .uncle/docs/AUTOMATED_TEST_REPORT.md
            ;;
        MANUAL_CHECKLIST)
            manual_checklist_reconcile || run_manual_checklist_panel
            # Only the canonical packet proves a panel completed. A rendered
            # view can survive a prior run or a user edit and is never an
            # execution input.
            if [[ -s "$STATE_DIR/documents/MANUAL_CHECKLIST.json" ]]; then
                echo 'Manual-checklist fast path: merged authoritative worker packets without parent synthesis.'
                return 0
            fi
            # A malformed checklist gets one local, format-only retry, the
            # same one-shot recovery execute-checklist's acceptance table
            # gets below: checklist_document.py already repairs label-only
            # deviations on its own, so a failure this far needs the model to
            # rewrite it, not another local patch.
            if stage_uses_self_hosted manual-checklist REVIEWER; then
                run_codex_review "${MANUAL_CHECKLIST_PROMPT:-prompts/manual-checklist.md}" \
                    "$STATE_DIR/documents/MANUAL_CHECKLIST.json" manual-checklist
            else
                manual_checklist_prompt="${MANUAL_CHECKLIST_PROMPT:-prompts/manual-checklist.md}"
                if [[ -s "$STATE_DIR/manual-checklist-format-retry.md" ]]; then
                    manual_checklist_prompt="$STATE_DIR/manual-checklist-format-retry-prompt.md"
                    {
                        cat "${MANUAL_CHECKLIST_PROMPT:-$ROOT/prompts/manual-checklist.md}"
                        printf '\n\n## Required format retry\n\n'
                        cat "$STATE_DIR/manual-checklist-format-retry.md"
                    } > "$manual_checklist_prompt"
                fi
                run_codex_review \
                    "$manual_checklist_prompt" \
                    "$STATE_DIR/documents/MANUAL_CHECKLIST.json" \
                    manual-checklist
            fi
            ;;
        EXECUTE_CHECKLIST)
            # The rendered checklist is for a reviewer to read. Execution
            # must be driven only by the collated canonical packet.
            if ! python3 "$ROOT/scripts/lib/checklist_document.py" --validate-json "$STATE_DIR/documents/MANUAL_CHECKLIST.json"; then
                set_state VALIDATE_MANUAL_CHECKLIST
                exit 1
            fi
            rm -f .uncle/docs/VERIFICATION_REPORT.md
            # The workers' schedule is derived from the checklist, and the checklist can be written again after it was derived
            # (noinit: the early checklist was grouped, then replaced by one with two more checks; the workers never saw those,
            # so one agent ran for 78 s and 9,000 tokens to execute them and rewrite every report).  Derive it from this checklist.
            snapshot_checklist_groups > /dev/null 2>&1 || true
            # Shared with change-workflow.sh (uncle consolidation phase (c)):
            # see checklist_execute_worker_fastpath in
            # scripts/lib/checklist-stage.sh.
            fastpath_status=0
            checklist_execute_worker_fastpath _stagegate_execute_checklist_stop_app_server || fastpath_status=$?
            if [[ "$fastpath_status" == 0 ]]; then
                return 0
            fi
            if [[ -s "$STATE_DIR/execute-checklist-uncovered.md" ]]; then
                cat "$STATE_DIR/execute-checklist-uncovered.md" >> "${CHECKLIST_EXECUTE_PROMPT:-/dev/null}"
            fi
            # A malformed acceptance table gets one local, format-only retry
            # even when optional supervision is disabled. The marker remains
            # after delivery so repeated malformed output stops normally.
            execute_checklist_prompt="${CHECKLIST_EXECUTE_PROMPT:-prompts/execute-checklist.md}"
            if [[ -s "$STATE_DIR/execute-checklist-format-retry.md" ]]; then
                execute_checklist_prompt="$STATE_DIR/execute-checklist-format-retry-prompt.md"
                {
                    cat "${CHECKLIST_EXECUTE_PROMPT:-$ROOT/prompts/execute-checklist.md}"
                    printf '\n\n## Required format retry\n\n'
                    cat "$STATE_DIR/execute-checklist-format-retry.md"
                } > "$execute_checklist_prompt"
            fi
            run_claude "$execute_checklist_prompt" execute-checklist
            ;;
        FINAL_AUDIT)
            run_final_audit_panel
            if [[ -s "$STATE_DIR/documents/FINAL_AUDIT.json" ]]; then
                echo 'Final-audit fast path: rendered authoritative worker findings without parent synthesis.'
                return 0
            fi
            # A malformed audit gets one local, format-only retry, the same
            # one-shot recovery .uncle/docs/MANUAL_CHECKLIST.md and execute-checklist's
            # acceptance table get.
            if stage_uses_self_hosted final-audit REVIEWER; then
                run_codex_review "${FINAL_AUDIT_PROMPT:-prompts/final-audit.md}" \
                    "$PROJECT_ROOT/.uncle/docs/FINAL_AUDIT.md" final-audit
            else
                final_audit_prompt="${FINAL_AUDIT_PROMPT:-prompts/final-audit.md}"
                if [[ -s "$STATE_DIR/final-audit-format-retry.md" ]]; then
                    final_audit_prompt="$STATE_DIR/final-audit-format-retry-prompt.md"
                    {
                        cat "${FINAL_AUDIT_PROMPT:-$ROOT/prompts/final-audit.md}"
                        printf '\n\n## Required format retry\n\n'
                        cat "$STATE_DIR/final-audit-format-retry.md"
                    } > "$final_audit_prompt"
                fi
                run_codex_review \
                    "$final_audit_prompt" \
                    "$PROJECT_ROOT/.uncle/docs/FINAL_AUDIT.md" \
                    final-audit
            fi
            ;;
        *)
            echo "run_stage: unknown stage: $1"
            exit 1
            ;;
    esac
}

# --- Green check ------------------------------------------------------------
# The driver runs the plan's own verification commands itself.
#
# The list comes from .uncle/docs/UPDATED_PROJECT_PLAN.md and nowhere else: the driver
# executes these with its own privileges, so they have to be commands the
# operator approved at the updated-plan gate, not commands an agent wrote after
# it. There is no baseline to compare against — nothing existed before this
# build — so any failure is a failure of the change.
#
# It reports; it does not decide. A failure turns the implementation gate from
# an approval into an explicit override, and the decision is recorded.
run_green_check() {
    if [[ "$GREEN_CHECK" != "1" ]]; then
        {
            echo "## Green check"
            echo
            echo "DISABLED (\`WORKFLOW_GREEN_CHECK=0\`). The driver did not run"
            echo "the plan's verification commands, so .uncle/docs/AUTOMATED_TEST_REPORT.md"
            echo "below is the implementing agent's unverified account of them."
        } > "$GREEN_MD"
        return 0
    fi

    verify_commands .uncle/docs/UPDATED_PROJECT_PLAN.md > "$GREEN_CMDS"
    # A clean install that needs a lockfile (`npm ci`) cannot run in a project that has none, and no step may install
    # to create one: run the install that does (install_command.py), and say so.
    python3 -B "$ROOT/scripts/lib/install_command.py" normalize "$GREEN_CMDS" . 2>/dev/null | tee -a "$STATE_DIR/green-check.rewrites" || true
    if ! verify_parallel_groups .uncle/docs/UPDATED_PROJECT_PLAN.md "$GREEN_CMDS" > "$STATE_DIR/green-check.groups"; then
        # Parallel scheduling is an optional optimisation, never a reason to
        # discard an already-approved verification command list.  In
        # particular, a background run must always publish a real result
        # instead of leaving its PENDING placeholder behind.
        echo 'Invalid Parallel verification groups; running the verification commands in order.'
        parallel_groups_format_hint
        : > "$STATE_DIR/green-check.groups"
    fi
    # A plan that declares no groups still runs a build beside the unit tests (auto_groups.py); WORKFLOW_AUTO_VERIFY_GROUPS=0 stops it.
    if [[ ! -s "$STATE_DIR/green-check.groups" && "${WORKFLOW_AUTO_VERIFY_GROUPS:-1}" == 1 ]]; then
        python3 -B "$ROOT/scripts/lib/auto_groups.py" "$GREEN_CMDS" > "$STATE_DIR/green-check.groups" 2>/dev/null || : > "$STATE_DIR/green-check.groups"
        [[ ! -s "$STATE_DIR/green-check.groups" ]] || echo "Verification: the plan declares no parallel groups; running commands $(tr '\n' ';' < "$STATE_DIR/green-check.groups" | sed 's/;$//; s/;/; and /g') together."
    fi

    if [[ ! -s "$GREEN_CMDS" ]]; then
        : > "$GREEN_CLASS"
        green_report "$GREEN_CLASS" "$GREEN_MD" .uncle/docs/UPDATED_PROJECT_PLAN.md \
            "$LOG_DIR/green-check.log" 0
        echo
        echo "Green check NOT RUN: .uncle/docs/UPDATED_PROJECT_PLAN.md has no fenced block"
        echo "under a 'Verification commands' heading, so the driver has no"
        echo "approved commands to run."
        return 0
    fi

    # The same code, tests and commands that already passed need not run again: the driver verifies
    # after implementation and once more before the checklist, and nothing changes in between.
    local green_fingerprint="" green_reused=0
    if [[ "${WORKFLOW_GREEN_CHECK_REUSE:-1}" == 1 ]]; then
        green_fingerprint="$(python3 -B "$ROOT/scripts/lib/tree_fingerprint.py" "$PWD" "$GREEN_CMDS" 2>/dev/null || true)"
        local remembered remembered_status
        # A bare `var=$(cmd)` assignment is NOT exempt from this script's
        # `set -e` the way a command substitution used as an argument is --
        # `cut`'s own failure (this fingerprint file does not exist before
        # the first run ever completes) silently killed this function
        # before a single check ran, same bug as change-workflow.sh's
        # run_green_check.
        remembered="$(cut -d' ' -f1 "$STATE_DIR/green-check.fingerprint" 2>/dev/null)" || true
        remembered_status="$(cut -d' ' -f2 "$STATE_DIR/green-check.fingerprint" 2>/dev/null)" || true
        if [[ -n "$green_fingerprint" && -s "$GREEN_MD" && -s "$GREEN_CLASS" && -f "$GREEN_CUR" \
              && "$remembered" == "$green_fingerprint" ]]; then
            # A clean run is always reusable.  A failing one is too, unless asked otherwise: the same code,
            # tests and commands fail the same way (a surviving mutant took 40-60 s to learn twice), and
            # any change -- a repair, an edit -- changes the fingerprint and runs it again.
            if [[ "$remembered_status" == clean || "${WORKFLOW_GREEN_CHECK_REUSE_FAILED:-1}" == 1 ]]; then
                green_reused=1
                echo
                if [[ "$remembered_status" == clean ]]; then
                    echo "Verification commands already passed on this exact tree; reusing that result."
                else
                    echo "Verification commands already failed on this exact tree; reusing that result (any change runs them again)."
                fi
            fi
        fi
    fi
    if [[ "$green_reused" == 0 ]]; then
    rm -f "$STATE_DIR/green-check.fingerprint"
    echo
    echo "Re-running the plan's verification commands from the driver:"
    # Migrate snapshots left by older Uncle versions before invoking project
    # commands. They are copies for integrity comparison, never inputs to
    # the application's test runner.
    local legacy_snapshot legacy_destination
    for legacy_snapshot in "$STATE_DIR"/verification-snapshot.*; do
        [[ -d "$legacy_snapshot" ]] || continue
        legacy_destination="$(mktemp -d "${TMPDIR:-/tmp}/uncle-verification-snapshot.XXXXXX")"
        rmdir "$legacy_destination"
        mv "$legacy_snapshot" "$legacy_destination"
        if [[ "$(cat "$STATE_DIR/verification-snapshot" 2>/dev/null || true)" == "$legacy_snapshot" ]]; then
            printf '%s\n' "$legacy_destination" > "$STATE_DIR/verification-snapshot"
        fi
    done
    local execution_status=0
    green_run "$GREEN_CMDS" "$GREEN_CUR" "$LOG_DIR/green-check.log" \
        check_verification_inputs "$STATE_DIR/green-check.groups" || execution_status=$?
    [[ "$execution_status" == 0 ]] || exit "$execution_status"

    # No baseline file: green_classify treats every failure as a regression,
    # which is the correct reading for a new application.
    green_classify "$STATE_DIR/green-check.no-baseline" "$GREEN_CUR" > "$GREEN_CLASS"
    green_report "$GREEN_CLASS" "$GREEN_MD" .uncle/docs/UPDATED_PROJECT_PLAN.md \
        "$LOG_DIR/green-check.log" 0
    fi

    local failures
    failures="$(green_regressions "$GREEN_CLASS")"
    # Remembered with its outcome.  Taken after the run, so files the run itself wrote are part of the
    # tree it describes.
    if [[ "$green_reused" == 0 && -n "$green_fingerprint" ]]; then
        local green_after green_outcome=clean
        [[ "$failures" == 0 ]] || green_outcome=failed
        green_after="$(python3 -B "$ROOT/scripts/lib/tree_fingerprint.py" "$PWD" "$GREEN_CMDS" 2>/dev/null || true)"
        if [[ -n "$green_after" ]]; then
            printf '%s %s\n' "$green_after" "$green_outcome" > "$STATE_DIR/green-check.fingerprint"
        else
            rm -f "$STATE_DIR/green-check.fingerprint"
        fi
    fi

    if [[ "$failures" -gt 0 ]]; then
        echo
        echo "$failures verification command(s) failed:"
        awk '
            { t = index($0, "\t") }
            t > 0 && substr($0, 1, t - 1) == "REGRESSION" {
                printf "  %s\n", substr($0, t + 1)
            }
        ' "$GREEN_CLASS"
        echo
        echo "Full output: $LOG_DIR/green-check.log"
        return 1
    fi

    echo
    echo "Green check: all verification commands passed."
    return 0
}

# --- Post-implementation review document ------------------------------------

. "$ROOT/scripts/lib/implementation-gates.sh"
. "$ROOT/scripts/lib/implementation-gates-app.sh"



# --- Speculative execution across human gates -------------------------------
#
# A human gate is dead time for the machine: the next stage's inputs are
# already final unless the reviewer edits them. So the next stage starts in the
# background as soon as the gate opens.
#
# The gate is not bypassed. The speculative result is adopted only if the
# reviewed file is byte-identical to what the background run read, and only
# after the approval has been recorded. Any edit during review discards the
# work and the stage replays normally.
#
# IMPLEMENT is deliberately never speculated: it writes source code, and
# CLAUDE.md forbids starting it before .uncle/docs/UPDATED_PROJECT_PLAN.md is approved.

spec_pid=""
spec_stage=""

cancel_speculation() {
    if [[ -n "$spec_pid" ]] && kill -0 "$spec_pid" 2>/dev/null; then
        echo "Cancelling speculative $spec_stage..."
        python3 -B "$ROOT/scripts/lib/writer_deadline.py" stop "$spec_pid" 2>/dev/null || true
        wait "$spec_pid" 2>/dev/null || true
    fi
    spec_pid=""
    spec_stage=""
}

trap on_exit EXIT

speculate() {
    local stage="$1"
    local view="$2" gate_file
    gate_file="$(canonical_artifact_path "$view")"

    [[ "$WORKFLOW_SPECULATE" == "1" ]] || return 0
    if (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_terminal_failure); then
        cat "$STATE_DIR/stop-reason" >&2
        return 1
    fi
    [[ -z "$spec_pid" ]] || return 0
    [[ -s "$gate_file" ]] || return 0

    # A speculative stage may clean its own state after an unsuccessful
    # attempt.  Recreate this driver-owned directory at the write boundary so
    # that cleanup cannot turn an otherwise successful approval gate into a
    # shell redirection failure.
    mkdir -p "$SPEC_DIR" || return 1
    hash_file "$gate_file" > "$SPEC_DIR/${stage}.input" || return 1

    echo "Starting $stage in the background while you review."
    echo "Its output is only used if the canonical JSON behind $view is unchanged at approval."

    # Fully detached from this terminal: the gate prompt owns stdin, and stage
    # output would otherwise interleave with it.
    (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_archive_attempt "$LOG_DIR/${stage}.speculative.log") || return 1
    : > "$LOG_DIR/${stage}.speculative.log"
    UNCLE_SPECULATIVE=true run_stage "$stage" >> "$LOG_DIR/${stage}.speculative.log" 2>&1 < /dev/null &
    spec_pid=$!
    spec_stage="$stage"
}

# The stage's own format validator, with the one-reading repairer allowed a
# pass first -- exactly what the VALIDATE_* state does afterwards.
speculation_artifact_valid() {
    case "$1" in
        ADVERSARIAL_REVIEW)
            python3 "$ROOT/scripts/lib/adversarial-context.py" --validate-json . >/dev/null 2>&1
            ;;
        *) return 0 ;;
    esac
}

# Succeeds when a usable speculative artifact is in place, in which case the
# caller skips the stage.
adopt_speculation() {
    local stage="$1"
    local view="$2" artifact_view="$3" gate_file artifact
    gate_file="$(canonical_artifact_path "$view")"
    artifact="$(canonical_artifact_path "$artifact_view")"
    local status=0

    [[ "$spec_stage" == "$stage" ]] || return 1

    echo
    echo "Waiting for the speculative $stage started during review..."
    wait "$spec_pid" || status=$?
    spec_pid=""
    spec_stage=""

    if [[ "$status" == 42 && "$(cat "$SPEC_DIR/${stage}.input")" == "$(hash_file "$gate_file")" ]]; then
        echo "Speculative $stage completed its review but could not fit the document budget."
        echo "Original preserved; pausing without another full review."
        echo "Log: $LOG_DIR/${stage}.speculative.log"
        exit 42
    fi

    if [[ "$status" -ne 0 ]]; then
        if (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_terminal_failure); then
            cat "$STATE_DIR/stop-reason" >&2
            exit "$status"
        fi
        echo "Speculative $stage failed (status $status). Running it again."
        echo "Log: $LOG_DIR/${stage}.speculative.log"
        # A reviewer that exits nonzero can still have written an invalid
        # artifact (e.g. run_codex_review's own validation rejected it)
        # before returning that status. Leaving it behind made the real
        # rerun's own fast path adopt it on sight, the same stale-content
        # mistake the validation-failure branch below already guards
        # against by moving its artifact out of the way first.
        mv -f "$artifact" "$LOG_DIR/${stage}.speculative.rejected.json" 2>/dev/null || rm -f "$artifact"
        rm -f "$STATE_DIR/envelopes/${stage}.json"
        return 1
    fi

    if [[ "$(cat "$SPEC_DIR/${stage}.input")" != "$(hash_file "$gate_file")" ]]; then
        echo "The canonical JSON behind $view changed during review. Discarding speculative $stage."
        rm -f "$artifact" "$artifact_view"
        # A discarded stage leaves no claim behind either (Issue 59).
        rm -f "$STATE_DIR/envelopes/${stage}.json"
        return 1
    fi

    if [[ ! -s "$artifact" ]]; then
        echo "Speculative $stage produced no artifact. Running it again."
        return 1
    fi

    # The same validation the VALIDATE_* state applies, before adoption: a
    # fragment adopted here failed there with "correct it and resume", which
    # left a run stopped on a document no one had finished writing.
    if ! speculation_artifact_valid "$stage" "$artifact"; then
        echo "Speculative $stage produced a document that fails validation. Running it again."
        mv -f "$artifact" "$LOG_DIR/${stage}.speculative.rejected.json" 2>/dev/null || rm -f "$artifact"
        rm -f "$STATE_DIR/envelopes/${stage}.json"
        echo "Rejected packet: $LOG_DIR/${stage}.speculative.rejected.json"
        return 1
    fi

    echo "Adopted speculative $stage — inputs unchanged since it started."
    echo "Log: $LOG_DIR/${stage}.speculative.log"
    if [[ "$stage" == UPDATED_PLAN ]]; then
        python3 -B "$ROOT/scripts/lib/updated_plan_defer.py" report-plan "$artifact" || return 1
    fi
    return 0
}

# Collect a backgrounded preflight probe. Never stops the run: the operator
# asked for implementation not to wait on it, so a problem is surfaced -- to the
# supervisor, to the log, and at the gate the operator is about to read -- while
# the code that was written in the meantime is kept. It says plainly that the
# prerequisites were not confirmed, because a probe that never reported is not
# the same as one that passed.
collect_background_preflight() {
    [[ -e "$STATE_DIR/preflight-backgrounded" ]] || return 0
    local status="" result=""

    if [[ -n "$PREFLIGHT_BG_PID" ]] && kill -0 "$PREFLIGHT_BG_PID" 2>/dev/null; then
        echo
        echo "Waiting for the prerequisite probe started before implementation..."
        wait "$PREFLIGHT_BG_PID" 2>/dev/null || true
    fi
    PREFLIGHT_BG_PID=""
    rm -f "$STATE_DIR/preflight-backgrounded"
    [[ -s "$STATE_DIR/preflight-bg.status" ]] && status="$(cat "$STATE_DIR/preflight-bg.status")"
    [[ -s "$STATE_DIR/documents/PREFLIGHT_REPORT.json" ]] && result="$(python3 -B "$ROOT/scripts/lib/acceptance_json.py" "$STATE_DIR/documents/PREFLIGHT_REPORT.json")"

    if [[ "$status" == 0 && "$result" == PASS ]]; then
        echo "Prerequisites confirmed (probed alongside implementation)."
        snapshot_preflight_capabilities "$STATE_DIR/documents/PREFLIGHT_REPORT.json" 2>/dev/null || true
        return 0
    fi

    echo
    echo "Prerequisite probe did not confirm this environment: ${result:-no report}."
    [[ -s .uncle/docs/PREFLIGHT_REPORT.md ]] && acceptance_problem .uncle/docs/PREFLIGHT_REPORT.md 2>/dev/null | sed 's/^/  /'
    echo "Implementation ran without waiting for it, so the code exists but the"
    echo "prerequisites behind it were not proved. Weigh this with the diff."
    echo "Log: $LOG_DIR/preflight.background.log"
    supervision_validation_failed preflight .uncle/docs/PREFLIGHT_REPORT.md \
        "Prerequisite probe did not confirm the environment: ${result:-no report}." 0 || true
    snapshot_preflight_capabilities "$STATE_DIR/documents/PREFLIGHT_REPORT.json" 2>/dev/null || true
    return 0
}

# Run a stage, using the speculative result when one is valid.
run_gated_stage() {
    local stage="$1"
    local gate_file="$2"
    local artifact="$3"

    if [[ "$stage" != UPDATED_PLAN || ! -s "$STATE_DIR/updated-plan-structure-feedback.md" ]]; then
        adopt_speculation "$stage" "$gate_file" "$artifact" && return 0
    fi
    if (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_terminal_failure); then
        cat "$STATE_DIR/stop-reason" >&2
        return 1
    fi
    run_stage "$stage"
}

python3 "$ROOT/scripts/lib/session-totals.py" "$STATE_DIR" "$DOCUMENT_BUDGET_SOURCE" \
    "${STAGEGATE_ORIGIN_REPO:-}#${STAGEGATE_ORIGIN_ISSUE:-}" || true

# A saved runner the dispatch cannot run (the removed cline, or a typo) stops the run here, with the one message that names the way out,
# before any stage, agent or background suite starts. It was written and tested but never called.
uncle_validate_config_runners || exit 1

# A stop reason belongs to the run that recorded it. Left in place, a
# previous "human" stop would silence the triage bundle on this run's failure.
rm -f "$STATE_DIR/stop-reason" "$STATE_DIR/updated-plan-writers-exhausted" "$STATE_DIR/preflight-readonly-violation"

# A fresh run (no state file yet) drops any stale start stamp; a resume keeps it.
[[ -e "$STATE_FILE" ]] || finished_extras reset
finished_extras start
# Application builds do not inherit completed verification from an earlier
# driver invocation. Preserve historical reports for inspection, not acceptance.
export WORKFLOW_CHECK_REUSE=0
rm -f "$STATE_DIR/green-check.fingerprint"
green_background_recover

while true; do
    preserve_requirements_source
    # Only a request to rerun a stage needs the helper; the loop turns over many times without one.
    [[ ! -e .uncle/workflow/rerun-request.json ]] || python3 "$ROOT/scripts/lib/rerun_stage.py" app || exit 1
    state="$(get_state)"
    if declare -f perf_stage >/dev/null; then perf_stage "$state"; fi

    echo
    echo "Current workflow state: $state"

    case "$state" in
        DERIVE_BRIEF)
            # A brief a human wrote is not ours to rewrite. Derivation runs
            # only when the prerequisite check says rows are still unfilled,
            # which is exactly the seeded-from-an-issue case.
            if python3 "$ROOT/scripts/lib/early-prerequisites.py" \
                    "${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md}" >/dev/null 2>&1; then
                echo "${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md} is already stated; skipping derivation."
                set_state REQUIREMENTS
                continue
            fi
            run_stage DERIVE_BRIEF
            set_state WAIT_DERIVE_APPROVAL
            ;;

        WAIT_DERIVE_APPROVAL)
            review_and_approve \
                "${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md}" \
                DERIVED_BRIEF \
                approve
            set_state REQUIREMENTS
            ;;

        REQUIREMENTS)
            # The brief is approved and the tree is still empty: the earliest
            # point at which there is something to build a first look from.
            preview_build_start
            run_stage REQUIREMENTS
            set_state VALIDATE_REQUIREMENTS
            ;;

        VALIDATE_REQUIREMENTS)
            echo "Validating saved requirements; discovery will not be rerun."
            require_artifact .uncle/docs/REQUIREMENTS_INTERPRETATION.md
            validation_error="$(python3 "$ROOT/scripts/lib/requirements-context.py" --validate-json . 2>&1)" || {
                printf '%s\n' "$validation_error" >&2
                supervision_validation_failed requirements "$STATE_DIR/documents/REQUIREMENTS_INTERPRETATION.json" "$validation_error"
                exit 1
            }
            python3 "$ROOT/scripts/lib/requirements-context.py" --render-json . .uncle/docs/REQUIREMENTS_INTERPRETATION.md || exit 1
            # A plan from the merged pass is a bonus, never a requirement. A
            # model that ran out of turns after the interpretation, or one too
            # weak to do both, must fall back to running the plan stage -- not
            # fail a validation of the document it did write.
            rm -f "$STATE_DIR/merged-plan.input"
            if merged_requirements_plan_enabled && [[ -s .uncle/docs/PROJECT_PLAN.md ]]; then
                # The interpretation the plan was written against. If the
                # operator edits it at the gate, the plan beside it is stale and
                # must be rewritten -- the same rule adoption applies to a
                # speculative stage.
                hash_file "$STATE_DIR/documents/REQUIREMENTS_INTERPRETATION.json" > "$STATE_DIR/merged-plan.input"
            fi
            set_state CLASSIFY
            ;;

        WAIT_REQUIREMENTS_APPROVAL)
            if ! merged_requirements_plan_enabled; then
                speculate PROJECT_PLAN .uncle/docs/REQUIREMENTS_INTERPRETATION.md
            fi
            review_and_approve \
                .uncle/docs/REQUIREMENTS_INTERPRETATION.md \
                REQUIREMENTS_INTERPRETATION \
                approve
            set_state PROJECT_PLAN
            ;;

        PROJECT_PLAN)
            verify_approval \
                .uncle/docs/REQUIREMENTS_INTERPRETATION.md \
                REQUIREMENTS_INTERPRETATION
            # Already running on a run that came through REQUIREMENTS; a run
            # resumed here starts it now.
            preview_build_start
            # Written already by the merged pass -- but only usable if the
            # document it was written against is byte-identical to what the
            # operator just approved. An edited interpretation means the plan
            # beside it answers a question nobody asked any more.
            merged_plan_usable=0
            if merged_requirements_plan_enabled && [[ -s .uncle/docs/PROJECT_PLAN.md \
                  && -s "$STATE_DIR/merged-plan.input" ]]; then
                if [[ "$(hash_file "$STATE_DIR/documents/REQUIREMENTS_INTERPRETATION.json")" \
                      == "$(cat "$STATE_DIR/merged-plan.input")" ]]; then
                    merged_plan_usable=1
                else
                    echo "Requirements changed during review; rewriting the plan."
                fi
            fi
            rm -f "$STATE_DIR/merged-plan.input"
            if [[ "$merged_plan_usable" == 1 ]]; then
                echo "Using the plan written with the approved requirements; not rerunning it."
            else
                run_gated_stage PROJECT_PLAN \
                    .uncle/docs/REQUIREMENTS_INTERPRETATION.md \
                    .uncle/docs/PROJECT_PLAN.md
            fi
            # Reused merged plans predate (or can outlive) their canonical
            # packet.  Hydrate it before opening the approval gate: the
            # speculative adversarial review consumes only this JSON file.
            ensure_project_plan_json || exit 1
            # Planned under the class decided from the requirements; raise it if the plan outgrew it (no model call).
            change_class_recheck app .uncle/docs/PROJECT_PLAN.md
            set_state WAIT_PLAN_APPROVAL
            ;;

        CLASSIFY)
            # How much scrutiny this build needs, decided from the approved requirements interpretation, so that it runs before
            # the plan (including the plan the speculative stage starts at the requirements gate) and the plan can use it.
            # Its own timed stage, fail-open. The plan's size is checked again after planning, which can only raise the class.
            classify_change_stage app .uncle/docs/REQUIREMENTS_INTERPRETATION.md || true
            set_state WAIT_REQUIREMENTS_APPROVAL
            ;;

        WAIT_PLAN_APPROVAL)
            speculate ADVERSARIAL_REVIEW .uncle/docs/PROJECT_PLAN.md
            review_and_approve .uncle/docs/PROJECT_PLAN.md PROJECT_PLAN approve
            set_state ADVERSARIAL_REVIEW
            ;;

        ADVERSARIAL_REVIEW)
            verify_approval .uncle/docs/PROJECT_PLAN.md PROJECT_PLAN
            # Normally started when planning began; a run resumed here starts
            # it now, so the review stages are not minutes of nothing on screen.
            preview_build_start
            run_gated_stage ADVERSARIAL_REVIEW \
                .uncle/docs/PROJECT_PLAN.md \
                .uncle/docs/ADVERSARIAL_REVIEW.md
            set_state VALIDATE_ADVERSARIAL_REVIEW
            ;;

        VALIDATE_ADVERSARIAL_REVIEW)
            verify_approval .uncle/docs/PROJECT_PLAN.md PROJECT_PLAN
            validation_error="$(python3 "$ROOT/scripts/lib/adversarial-context.py" --validate-json . 2>&1)" || {
                printf '%s\n' "$validation_error" >&2
                printf '%s\n' "$validation_error" > "$STATE_DIR/validation-error.txt"
                printf '%s\n' "validation: $validation_error" > "$STATE_DIR/stop-reason"
                supervision_validation_failed adversarial-review .uncle/docs/ADVERSARIAL_REVIEW.md "$validation_error"
                exit 1
            }
            rm -f "$STATE_DIR/validation-error.txt"
            python3 "$ROOT/scripts/lib/adversarial-context.py" --render-json . .uncle/docs/ADVERSARIAL_REVIEW.md || exit 1
            check_document_budget .uncle/docs/ADVERSARIAL_REVIEW.md || exit 1
            set_state WAIT_REVIEW_ACKNOWLEDGEMENT
            ;;

        WAIT_REVIEW_ACKNOWLEDGEMENT)
            speculate UPDATED_PLAN .uncle/docs/ADVERSARIAL_REVIEW.md
            review_and_approve \
                .uncle/docs/ADVERSARIAL_REVIEW.md \
                ADVERSARIAL_REVIEW \
                acknowledge
            set_state UPDATED_PLAN
            ;;

        UPDATED_PLAN)
            verify_approval .uncle/docs/PROJECT_PLAN.md PROJECT_PLAN
            verify_approval \
                .uncle/docs/ADVERSARIAL_REVIEW.md \
                ADVERSARIAL_REVIEW
            run_gated_stage UPDATED_PLAN \
                .uncle/docs/ADVERSARIAL_REVIEW.md \
                .uncle/docs/UPDATED_PROJECT_PLAN.md
            if [[ -s .uncle/docs/UPDATED_PROJECT_PLAN.md ]]; then
                plan_ingest_error="$(python3 "$ROOT/scripts/lib/plan_context.py" plan .uncle/docs/UPDATED_PROJECT_PLAN.md . 2>&1)" || {
                    printf '%s\n' "$plan_ingest_error" >&2
                    supervision_validation_failed updated-plan .uncle/docs/UPDATED_PROJECT_PLAN.md "$plan_ingest_error"
                    exit 1
                }
            fi
            # Prewarm only after the review has produced the final execution
            # plan.  Prewarming from PROJECT_PLAN can create sandboxes for a
            # different grouping/ownership layout; when UPDATED_PLAN then
            # changes the schedule, stale mirrors can be falsely attributed
            # with prior-step writes and force a costly serial fallback.
            parallel_prewarm_start .uncle/docs/UPDATED_PROJECT_PLAN.md "$ROOT/scripts/lib"
            set_state VALIDATE_UPDATED_PLAN
            ;;

        VALIDATE_UPDATED_PLAN)
            # Probe only: would an implementation started from .uncle/docs/PROJECT_PLAN.md,
            # running beside the review, have survived it? Records the answer
            # and acts on nothing. Cannot fail the stage.
            if [[ -s .uncle/docs/PROJECT_PLAN.md && -s .uncle/docs/UPDATED_PROJECT_PLAN.md ]]; then
                python3 -B "$ROOT/scripts/lib/plan_drift.py" \
                    .uncle/docs/PROJECT_PLAN.md .uncle/docs/UPDATED_PROJECT_PLAN.md \
                    "$STATE_DIR/plan-drift.json" 2>/dev/null || true
            fi
            verify_approval .uncle/docs/PROJECT_PLAN.md PROJECT_PLAN
            verify_approval .uncle/docs/ADVERSARIAL_REVIEW.md ADVERSARIAL_REVIEW
            require_artifact .uncle/docs/UPDATED_PROJECT_PLAN.md
            python3 -B "$ROOT/scripts/lib/plan_parallelism.py" .uncle/docs/UPDATED_PROJECT_PLAN.md 2>/dev/null \
                | tee "$STATE_DIR/plan-parallelism.txt" || true
            # Anything the review added to the dependencies; already-cached packages cost nothing.
            install_warm_start .uncle/docs/UPDATED_PROJECT_PLAN.md
            set_state WAIT_UPDATED_PLAN_APPROVAL
            ;;

        WAIT_UPDATED_PLAN_APPROVAL)
            # Reject a structurally incomplete plan before asking anyone to
            # read it. Approving a plan the next state will refuse wastes the
            # one thing this workflow cannot generate more of.
            plan_problem="$(plan_structure_problem .uncle/docs/UPDATED_PROJECT_PLAN.md)" && {
                echo
                echo ".uncle/docs/UPDATED_PROJECT_PLAN.md has $plan_problem."
                plan_headings .uncle/docs/UPDATED_PROJECT_PLAN.md
                if [[ "$plan_problem" == 'invalid Parallel verification groups' ]]; then
                    parallel_groups_format_hint
                elif [[ "$plan_problem" == 'no Protected verification paths block' ]]; then
                    echo 'Expected: a heading with the words "protected" and "paths", then'
                    echo 'one fenced block of repository-relative paths, one per line.'
                elif [[ "$plan_problem" == 'no Verification commands block' ]]; then
                    echo 'Expected: ## Verification commands with one fenced block of'
                    echo 'commands, one per line, and nothing else in it.'
                elif [[ "$plan_problem" == 'a protected verification path with no owning implementation step' ]]; then
                    echo 'These protected/frozen paths have no step in the Implementation'
                    echo 'order whose Owns: covers them, and do not exist yet -- nothing is'
                    echo 'tasked with creating them (a Reconcile step'"'"'s Owns: * does not'
                    echo 'count; name the file explicitly in the step that creates it):'
                    python3 -B "$ROOT/scripts/lib/plan_ownership_gap.py" \
                        .uncle/docs/UPDATED_PROJECT_PLAN.md "$PWD" "$STATE_DIR" 2>/dev/null | sed 's/^/  /' || true
                fi
                # Nobody is asked to approve a plan the next stage would reject, and a
                # dead stop here ended unattended runs for good. Give the planner the
                # exact error once; only a second failure stops for a person.
                if [[ ! -e "$STATE_DIR/updated-plan-structure-retried" ]]; then
                    touch "$STATE_DIR/updated-plan-structure-retried"
                    plan_structure_feedback "$plan_problem" .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/updated-plan-structure-feedback.md"
                    echo "Returning to UPDATED_PLAN once with this error for the planner to correct."
                    set_state UPDATED_PLAN
                    continue
                fi
                echo "The driver reads that block to run and protect verification,"
                echo "so amend the plan before approving it; you are not being asked"
                echo "to approve a plan that the next stage would reject."
                exit 1
            }
            # No speculation here: IMPLEMENT writes source code, and it may not
            # start before this approval exists.
            plan_status=0
            plan_assess || plan_status=$?
            if [[ "$plan_status" == 10 ]]; then continue; fi
            if [[ "$plan_status" != 0 ]]; then exit 1; fi
            review_and_approve \
                .uncle/docs/UPDATED_PROJECT_PLAN.md \
                UPDATED_PROJECT_PLAN \
                approve
            set_state PREFLIGHT
            ;;

        PREFLIGHT)
            verify_approval .uncle/docs/UPDATED_PROJECT_PLAN.md UPDATED_PROJECT_PLAN
            verify_commands .uncle/docs/UPDATED_PROJECT_PLAN.md > "$GREEN_CMDS"
            if [[ ! -s "$GREEN_CMDS" ]]; then
                echo "No Verification commands in .uncle/docs/UPDATED_PROJECT_PLAN.md. Amend the plan and renew its approval."
                exit 1
            fi
            if ! verify_parallel_groups .uncle/docs/UPDATED_PROJECT_PLAN.md "$GREEN_CMDS" > "$STATE_DIR/green-check.groups"; then
                echo 'Invalid Parallel verification groups. Amend the plan and renew approval.'
                parallel_groups_format_hint
                exit 1
            fi
            if ! verification_paths .uncle/docs/UPDATED_PROJECT_PLAN.md > /dev/null; then
                echo "Missing Protected verification paths in .uncle/docs/UPDATED_PROJECT_PLAN.md."
                echo "The heading needs the words 'protected' and 'paths', followed by"
                echo "one fenced block of repository-relative paths. Its headings are:"
                plan_headings .uncle/docs/UPDATED_PROJECT_PLAN.md
                echo "Amend the plan and renew its approval."
                exit 1
            fi
            # The structural checks above stay in front of implementation: they
            # cost nothing, need no model, and a plan missing its verification
            # commands or protected paths must not reach code. What moves is the
            # probe -- the part that spends minutes and dollars asking a model
            # about the environment.
            if [[ "$PREFLIGHT_BLOCKING" != "1" ]]; then
                : > "$STATE_DIR/preflight-backgrounded"
                rm -f "$STATE_DIR/preflight-bg.status"
                echo
                echo "Probing prerequisites in the background; implementation starts now."
                echo "A problem is reported through the supervisor, not by stopping here."
                (. "$ROOT/scripts/lib/model-jobs.sh"; workflow_archive_attempt "$LOG_DIR/preflight.background.log") || exit 1
                (
                    status=0
                    run_stage PREFLIGHT || status=$?
                    printf '%s\n' "$status" > "$STATE_DIR/preflight-bg.status"
                ) > "$LOG_DIR/preflight.background.log" 2>&1 < /dev/null &
                PREFLIGHT_BG_PID=$!
                hash_file .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/preflight-plan.sha256"
                set_state MODULE_INTERFACES
                continue
            fi
            rm -f "$STATE_DIR/preflight-backgrounded"
            run_stage PREFLIGHT
            if plan_executability_enabled && [[ -s "$STATE_DIR/plan-executability/assessment.json" ]]; then
                plan_tool preflight-check || exit 1
            fi
            preflight_result="$(python3 -B "$ROOT/scripts/lib/acceptance_json.py" "$STATE_DIR/documents/PREFLIGHT_REPORT.json")"
            case "$preflight_result" in
                PASS) human_input_reset "$STATE_DIR" ;;
                BLOCKED-HUMAN)
                    human_input_reset "$STATE_DIR"
                    echo
                    echo "Prerequisites await a person, not an arrangement:"
                    acceptance_blocked_ids .uncle/docs/PREFLIGHT_REPORT.md BLOCKED-HUMAN | sed 's/^/  /'
                    echo "Implementation does not consume a signature, so the run continues."
                    echo "Verification does: these must be signed before the checklist can"
                    echo "pass, and the gates there will say so again."
                    ;;
                BLOCKED-SETUP)
                    echo "Prerequisites BLOCKED-SETUP: see .uncle/docs/PREFLIGHT_REPORT.md."
                    echo "Outstanding, one action each:"
                    acceptance_blocked_ids .uncle/docs/PREFLIGHT_REPORT.md BLOCKED-SETUP | sed 's/^/  /'
                    # Offer to take them here. A prerequisite that is waiting
                    # on a person is waiting on the person sitting at this
                    # gate, and hand-editing markdown between runs is how its
                    # path ends up spelled two ways.
                    blocked_ids="$(acceptance_blocked_ids .uncle/docs/PREFLIGHT_REPORT.md BLOCKED-SETUP)"
                    # Unattended: nobody is sitting at this gate to supply the
                    # prerequisite, so asking is the one thing that cannot
                    # work. Waive them and go on -- the rows stay blocked in
                    # the report, so implementation proceeds knowing an input
                    # it expected is not there, which is a worse position than
                    # a person providing it and an honest one.
                    if [[ "${UNATTENDED:-0}" == 1 ]]; then
                        # shellcheck disable=SC2086
                        if [[ -z "$blocked_ids" ]] \
                            || ! record_waiver .uncle/docs/PREFLIGHT_REPORT.md $blocked_ids; then
                            echo "Unattended: could not record a waiver; stopping."
                            exit 1
                        fi
                        echo "Unattended: prerequisites waived, continuing without them."
                        human_input_reset "$STATE_DIR"
                    else
                        # The operator's answer to a blocker is a choice, not
                        # a signature: review the evidence, provide the input,
                        # skip with one recorded decision, or decline cleanly.
                        # shellcheck disable=SC2086
                        preflight_blocked_gate .uncle/docs/PREFLIGHT_REPORT.md BLOCKED-SETUP $blocked_ids
                    fi
                    ;;
                *)
                    echo "Prerequisites $preflight_result: see .uncle/docs/PREFLIGHT_REPORT.md."
                    if [[ "$preflight_result" == UNKNOWN ]]; then
                        # UNKNOWN means the table did not parse. Name the line:
                        # the verdict alone leaves an operator guessing which of
                        # a dozen rules the report missed.
                        acceptance_problem .uncle/docs/PREFLIGHT_REPORT.md | sed 's/^/  /'
                        echo "Resolve and rerun."
                        exit 1
                    fi
                    if [[ "$preflight_result" == BLOCKED-IMPOSSIBLE && "${UNATTENDED:-0}" != 1 ]]; then
                        impossible_ids="$(acceptance_blocked_ids .uncle/docs/PREFLIGHT_REPORT.md BLOCKED-IMPOSSIBLE)"
                        if [[ -n "$impossible_ids" ]]; then
                            # Effort will not clear these, but the answer is
                            # still a choice: review, provide out-of-band,
                            # skip on the record, or decline and amend.
                            # shellcheck disable=SC2086
                            preflight_blocked_gate .uncle/docs/PREFLIGHT_REPORT.md BLOCKED-IMPOSSIBLE $impossible_ids
                        fi
                    fi
                    echo "Resolve and rerun."
                    exit 1
                    ;;
            esac
            hash_file .uncle/docs/UPDATED_PROJECT_PLAN.md > "$STATE_DIR/preflight-plan.sha256"
            set_state MODULE_INTERFACES
            ;;

        MODULE_INTERFACES)
            module_interfaces_stage "$PLAN_DOC"
            ;;

        IMPLEMENT)
            verify_approval \
                "$PLAN_DOC" \
                "$PLAN_DOC_NAME"
            if [[ -e "$STATE_DIR/test-evidence-reconcile" ]]; then
                echo 'Implementation report reconciliation: preserving source and regenerating implementation-owned evidence.'
                # This is the existing implementation stage in a narrow
                # report-only mode: it may inspect/run checks and write its
                # reports, but cannot call Edit on application source/tests.
                run_claude prompts/test-evidence-handoff.md implementation 'Read,Glob,Grep,Write,Bash'
                python3 "$ROOT/scripts/lib/implementation_notes.py" validate . \
                    .uncle/workflow/documents/IMPLEMENTATION_NOTES.json --require-json
                python3 "$ROOT/scripts/lib/implementation_notes.py" render . .uncle/docs/IMPLEMENTATION_NOTES.md
                python3 "$ROOT/scripts/lib/test_report.py" validate . application \
                    .uncle/workflow/documents/AUTOMATED_TEST_REPORT.json
                require_artifact "$TEST_REPORT_DOC"
                require_artifact .uncle/docs/IMPLEMENTATION_NOTES.md
                rm -f "$STATE_DIR/test-evidence-reconcile"
                set_state TEST_REVIEW
                continue
            fi
            # The checklist does not depend on the code: draft it now, beside implementation, from the approved plan (best effort).
            manual_checklist_draft_start
            # Nothing may read or write the tree while the preview is still
            # writing it -- including the verification baseline captured below.
            preview_build_wait
            if preview_build_survived; then
                echo "The review left every section the preview was built from unchanged."
                echo "Implementation continues from that code rather than an empty tree."
            elif [[ "$PREVIEW_STARTED" == 1 ]]; then
                if [[ -s "$STATE_DIR/preview-build.plan" ]]; then
                    echo "The review changed the plan the preview was built from."
                else
                    echo "The preview was built from the brief, before the plan existed."
                fi
                echo "Implementation builds to the approved plan; preview code is not evidence."
            fi
            # A backgrounded probe has no report yet, and demanding one here
            # would send the run straight back to PREFLIGHT for ever. The plan
            # hash is still checked: a plan revised since the probe started
            # invalidates it either way.
            if [[ ! -s "$STATE_DIR/preflight-plan.sha256" ]] \
                || [[ "$(cat "$STATE_DIR/preflight-plan.sha256")" != "$(hash_file .uncle/docs/UPDATED_PROJECT_PLAN.md)" ]] \
                || { [[ ! -e "$STATE_DIR/preflight-backgrounded" ]] \
                     && ! preflight_settled "$(python3 -B "$ROOT/scripts/lib/acceptance_json.py" "$STATE_DIR/documents/PREFLIGHT_REPORT.json")"; }; then
                set_state PREFLIGHT
                continue
            fi
            # Taken before the agent runs, so a file that was already sitting
            # in the directory is not read as something this build produced.
            if [[ ! -e "$UNTRACKED_BASELINE" ]]; then
                snapshot_untracked "$UNTRACKED_BASELINE"
            fi

            plan_status=0
            plan_before_write || plan_status=$?
            case "$plan_status" in 0|22) ;; 10) continue ;; *) exit 1 ;; esac
            [[ "$plan_status" == 22 ]] || run_stage IMPLEMENT
            python3 -B "$ROOT/scripts/lib/completion_preview.py" --normalize "$PWD" || exit 1
            plan_status=0
            plan_after_write || plan_status=$?
            case "$plan_status" in 0) ;; 27) continue ;; 10) plan_revise; continue ;; *) exit 1 ;; esac
            verify_approval "$PLAN_DOC" "$PLAN_DOC_NAME"
            PREVIOUS_VERIFICATION_SNAPSHOT=""
            capture_verification_inputs

            # Start verification as soon as implementation is stable. It runs
            # while the implementation gate settles; later evidence workers
            # consume its published canonical result instead of re-running
            # driver-owned commands.
            run_green_check_auto || true
            collect_background_preflight

            # Probe only: records what a parallel implementation would have
            # done and whether the plan's file ownership matched the tree.
            # Runs nothing in parallel and cannot fail the stage.
            python3 -B "$ROOT/scripts/lib/step_groups.py" "$PLAN_DOC" . \
                > "$STATE_DIR/step-groups.json" 2>/dev/null || true
            plan_delivery_summary
            check_verification_inputs

            set_state WAIT_IMPLEMENT_APPROVAL
            ;;

        WAIT_IMPLEMENT_APPROVAL)
            green_failed="$(green_regressions "$GREEN_CLASS")"

            if [[ "$DIFF_GATE" != "1" ]]; then
                if [[ "$green_failed" -gt 0 ]]; then
                    if [[ "$WORKFLOW_CONTINUE_ON_TEST_FAILURE" == "1" ]]; then
                        echo "Continuing with $green_failed failed verification check(s); final audit will assess them."
                        record_nonblocking_failure green-check "$green_failed failed verification check(s); diff gate disabled"
                        record_test_failure_disposition
                        printf '%s\t%s\n' \
                            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
                            "$green_failed failing check(s) continued automatically" \
                            > "$GREEN_OVERRIDE_FILE"
                    else
                        echo
                        echo "Refusing to continue: $green_failed verification"
                        echo "check(s) failed, and WORKFLOW_DIFF_GATE=0 leaves no"
                        echo "human gate to weigh that against the diff."
                        echo "Fix the failure, or re-enable the gate."
                        exit 1
                    fi
                fi
                echo
                echo "Implementation gate disabled (WORKFLOW_DIFF_GATE=0);" \
                     "no human reads the diff."
                set_state TEST_REVIEW
                continue
            fi

            build_implementation_review

            gate_wording=approve
            if [[ "$green_failed" -gt 0 ]]; then
                gate_wording=override
                echo
                echo "=================================================="
                echo "GREEN CHECK FAILED: $green_failed command(s)"
                echo "=================================================="
                echo
                echo "The plan's own verification commands do not pass. They are"
                echo "listed in the review document and in"
                echo "$LOG_DIR/green-check.log."
                echo
                echo "Approving here is an override, and it is recorded."
            fi

            echo
            echo "$REVIEW_FILE is generated from the working tree: the diff, the"
            echo "green check, and the agent's own notes and test report. Edit"
            echo "the code, not the document — it is rebuilt each time this gate"
            echo "opens, and the approval records the state of the tree."

            review_and_approve \
                "$REVIEW_FILE" \
                IMPLEMENTATION_REVIEW \
                "$gate_wording"
            WORKFLOW_UNTRACKED_BASELINE="$WORKFLOW_UNTRACKED_BASELINE" python3 -B "$ROOT/scripts/lib/approval_snapshot.py" record "$STATE_DIR" || exit 1

            if [[ "$green_failed" -gt 0 ]]; then
                printf '%s\t%s\n' \
                    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
                    "$green_failed failing check(s) overridden" \
                    > "$GREEN_OVERRIDE_FILE"
            else
                rm -f "$GREEN_OVERRIDE_FILE"
            fi

            set_state TEST_REVIEW
            ;;

        TEST_REVIEW)
            # Start the plan/source-only half of test review now, before
            # anything else in this stage, so it runs concurrently with the
            # driver's background verification instead of waiting for it to
            # publish first. See run_test_review_investigate: it never opens
            # a result file, so nothing it produces is invalidated by
            # verification still being in flight.
            run_test_review_investigate
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi
            require_file "$STATE_DIR/verification.manifest"
            EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
            check_verification_inputs
            # Every test-review panel row's final status judges observed test
            # evidence.  A worker launched against the background verifier's
            # PENDING placeholder can only honestly emit NOT RUN, and its
            # immutable packet cannot be repaired by publishing green-check
            # results later.  Wait once before launching the finalize pass
            # (the plan/source investigation above already ran concurrently
            # with this wait), then materialize
            # the driver-owned report they consume.  Checklist stages still
            # reuse this completed result and never rerun these commands.
            # Resume interrupted verification; matching completed evidence is reused.
            run_green_check_auto || true
            green_wait_final || {
                echo 'Driver verification did not publish final evidence before test review.' >&2
                exit 1
            }
            python3 -B "$ROOT/scripts/lib/test_report.py" from-green . application \
                "$STATE_DIR/green-check.current.tsv" "$LOG_DIR/green-check.log" 2>/dev/null || true
            # Keep the inexpensive server/browser prerequisite warm even if
            # the last build failed.  It never builds or opens a page.
            prewarm_checklist_browser
            # Never start manual/browser evidence against an app the driver
            # has already proved cannot compile or serve.
            runtime_ready_rc=0
            route_unrunnable_application || runtime_ready_rc=$?
            if [[ "$runtime_ready_rc" == 2 ]]; then continue; fi
            [[ "$runtime_ready_rc" == 0 ]] || exit 1
            run_stage TEST_REVIEW
            check_verification_inputs
            set_state VALIDATE_TEST_REVIEW
            ;;

        VALIDATE_TEST_REVIEW)
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi
            require_file "$STATE_DIR/verification.manifest"
            EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
            check_verification_inputs
            ensure_rc=0; ensure_acceptance_canonical .uncle/docs/TEST_REVIEW.md || ensure_rc=$?
            if [[ "$ensure_rc" == 2 ]]; then continue; fi
            require_file "$STATE_DIR/documents/TEST_REVIEW.json"
            # Unattended only: a FAIL on test-suite thoroughness (COVERAGE,
            # ORACLE) does not by itself mean the application is wrong, only
            # that it was checked less exhaustively than the plan described.
            # Downgrading it to nonblocking never touches the reviewer's own
            # TEST_REVIEW.md or its FAIL status -- only the driver's routing
            # decision -- and only fires when every row that actually proves
            # correct behavior (ASSERTIONS, INTEGRITY, RESULTS, NEGATIVE) is
            # clean. See test_review_advisory.py for the full rationale.
            if [[ "${WORKFLOW_ADVISORY_TEST_REVIEW:-1}" == 1 && "$UNATTENDED" == 1 ]]; then
                advisory_downgraded="$(python3 -B "$ROOT/scripts/lib/test_review_advisory.py" "$STATE_DIR/documents/TEST_REVIEW.json")"
                if [[ -n "$advisory_downgraded" ]]; then
                    echo "Unattended: test-suite-thoroughness finding(s) ($(printf '%s' "$advisory_downgraded" | tr '\n' ' ')) continue as nonblocking evidence; the application's own behavior is fully verified."
                    record_nonblocking_failure TEST_REVIEW.json "test-suite thoroughness gap(s): $(printf '%s' "$advisory_downgraded" | tr '\n' ' ')"
                fi
            fi
            if [[ "$GREEN_CHECK" != 1 || ! -s "$GREEN_CLASS" ]]; then
                echo "Acceptance BLOCKED: the driver must run the approved verification suite."
                echo "Enable WORKFLOW_GREEN_CHECK and rerun IMPLEMENT to capture its results before checklist work."
                exit 1
            fi
            green_wait_final || { echo 'Driver verification did not publish final evidence before checklist work.' >&2; exit 1; }
            runtime_ready_rc=0
            route_unrunnable_application || runtime_ready_rc=$?
            if [[ "$runtime_ready_rc" == 2 ]]; then continue; fi
            [[ "$runtime_ready_rc" == 0 ]] || exit 1
            python3 -B "$ROOT/scripts/lib/test_report.py" from-green . application "$STATE_DIR/green-check.current.tsv" "$LOG_DIR/green-check.log" 2>/dev/null || true
            # Test-review workers may have run while green was still pending.
            # Re-collate their immutable packets now so only driver-owned
            # rows change from PENDING to the completed canonical result.
            if [[ -d "$STATE_DIR/test-review-panel" ]]; then
                python3 -B "$ROOT/scripts/lib/test_review_packets.py" "$STATE_DIR/test-review-panel" "$STATE_DIR/documents/TEST_REVIEW.json" $(test_review_lenses) || exit 1
                python3 -B "$ROOT/scripts/lib/acceptance_context.py" --render "$STATE_DIR/documents/TEST_REVIEW.json" .uncle/docs/TEST_REVIEW.md || exit 1
            fi
            # The direct worker fast path leaves the current acceptance report
            # TEST_REVIEW.json is produced and validated before this state;
            # its Markdown rendering is never ingested as workflow input.
            # Passing driver verification plus only an incomplete fallback
            # report needs evidence reconciliation, never a source-code repair.
            # Only when the driver's own suite had no failure: a failing command (a mutation runner that does not run) is
            # a defect to repair or waive, not missing documentation, and sending it back through the implementation stage
            # to "reconcile evidence" ran the agent a second time and the review a second time for nothing (noinit).
            if [[ ! -e "$STATE_DIR/test-evidence-handoff-attempted" ]] && [[ "$(green_regressions "$GREEN_CLASS")" -eq 0 ]] \
                && python3 -B "$ROOT/scripts/lib/test_review_route.py" "$STATE_DIR/documents/TEST_REVIEW.json" "$STATE_DIR/documents/AUTOMATED_TEST_REPORT.json"; then
                touch "$STATE_DIR/test-evidence-handoff-attempted" "$STATE_DIR/test-evidence-reconcile"
                echo 'Test review found an incomplete evidence handoff after a passing driver suite; returning to implementation-owned report reconciliation.'
                set_state IMPLEMENT
                continue
            fi
            if [[ ! -e "$STATE_DIR/test-mutation-evidence-attempted" ]] && [[ "$(green_regressions "$GREEN_CLASS")" -eq 0 ]] \
                && [[ "${WORKFLOW_MUTATION_EVIDENCE_REPAIR:-0}" == 1 ]] \
                && python3 -B "$ROOT/scripts/lib/test_review_route.py" --mutation-evidence-gap "$STATE_DIR/documents/TEST_REVIEW.json"; then
                touch "$STATE_DIR/test-mutation-evidence-attempted" "$STATE_DIR/test-evidence-reconcile"
                echo 'Test review found missing mutation evidence; running one implementation-owned evidence reconciliation before re-review.'
                set_state IMPLEMENT
                continue
            fi
            if [[ "$(green_regressions "$GREEN_CLASS")" -gt 0 ]] \
                && [[ "$(python3 -B "$ROOT/scripts/lib/acceptance_json.py" "$STATE_DIR/documents/TEST_REVIEW.json" COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS)" == PASS ]]; then
                green_route="$(green_failure_route "$WORKFLOW_CONTINUE_ON_TEST_FAILURE" "$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 0)" "$WORKFLOW_AUTO_REPAIR_ATTEMPTS")"
                if [[ "$green_route" == continue ]]; then
                    echo 'Test review is otherwise complete; continuing despite failed driver verification.'
                    record_nonblocking_failure green-check 'TEST_REVIEW passed while one or more driver verification commands failed'
                    record_test_failure_disposition
                    printf '%s\t%s\n' \
                        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
                        "$(green_regressions "$GREEN_CLASS") failing check(s) continued automatically" \
                        > "$GREEN_OVERRIDE_FILE"
                    acceptance_transition .uncle/docs/TEST_REVIEW.md "$(test_review_next_stage)" 'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS'
                    continue
                fi
                # Repair is the right answer for a check the code can satisfy.
                # It is the wrong answer for one the code cannot: the stage runs,
                # changes nothing that helps, and the run comes straight back
                # here. The operator is the only one who can tell those apart, so
                # ask before looping. A waiver never turns the command into a
                # pass -- green-check.md still records the failure, and the audit
                # still reads it -- it only stops the driver insisting that more
                # repair passes will help.
                green_ids="$(green_failed_ids "$GREEN_CLASS" "$GREEN_CMDS")"
                # shellcheck disable=SC2086
                if [[ -n "${green_ids// /}" ]] && waived_ids $green_ids; then
                    echo
                    echo "Verification failure waived earlier; continuing."
                    echo "$GREEN_MD still records the failure."
                    acceptance_transition .uncle/docs/TEST_REVIEW.md "$(test_review_next_stage)" 'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS'
                    continue
                fi
                # The first failure goes to repair unasked: most are real and
                # the stage fixes them. Offer the choice only once repair has had
                # a turn and the same command is still failing, which is the
                # shape of a check the code cannot satisfy.
                if [[ "$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 0)" -ge "$WORKFLOW_AUTO_REPAIR_ATTEMPTS" \
                      && "$WORKFLOW_AUTO_REPAIR_ATTEMPTS" -ge 1 \
                      && -n "${green_ids// /}" ]]; then
                    echo
                    echo "This verification failure survived a repair pass:"
                    awk -F'\t' '$1 == "REGRESSION" { printf "  %s\n", $2 }' "$GREEN_CLASS"
                    echo
                    echo "Repair it again, or waive it and continue. A waiver does not"
                    echo "make it pass: $GREEN_MD keeps the failure and the final audit"
                    echo "still reads it."
                    # shellcheck disable=SC2086
                    if record_waiver "$GREEN_MD" $green_ids; then
                        acceptance_transition .uncle/docs/TEST_REVIEW.md "$(test_review_next_stage)" 'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS'
                        continue
                    fi
                fi
                printf '%s\n' "$GREEN_MD" > "$STATE_DIR/repair-source"
                set_state REPAIR
            else
                continue_nonblocking_test_review MANUAL_CHECKLIST || \
                    acceptance_transition .uncle/docs/TEST_REVIEW.md MANUAL_CHECKLIST 'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS'
            fi
            ;;

        REPAIR)
            repair_source="$(cat "$STATE_DIR/repair-source" 2>/dev/null || true)"
            repair_count_existing="$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 0)"
            # Older installed drivers could route a checklist-only finding to
            # REPAIR before the nonblocking checklist continuation existed.
            # Do not ask a coding agent to "repair" a plan/report mismatch
            # after the driver has already proved the executable suite green.
            # Preserve the canonical finding for FINAL_AUDIT instead, so a
            # resumed run such as calculator4 advances without hiding the
            # nonexistent protected path or rewriting product source.
            if [[ "$repair_source" == .uncle/docs/VERIFICATION_REPORT.md ]] \
                && [[ "$GREEN_CHECK" == 1 ]] \
                && [[ "$(green_regressions "$GREEN_CLASS")" -eq 0 ]] \
                && [[ -s "$STATE_DIR/documents/VERIFICATION_REPORT.json" ]]; then
                checklist_acceptance="$(python3 -B "$ROOT/scripts/lib/acceptance_json.py" "$STATE_DIR/documents/VERIFICATION_REPORT.json")"
                if [[ "$checklist_acceptance" != PASS ]]; then
                    echo 'Resuming a checklist-only finding after a passing driver green check; carrying it to final audit as nonblocking evidence.'
                    record_nonblocking_failure VERIFICATION_REPORT.json "resumed checklist acceptance $checklist_acceptance after passing driver green check"
                    set_state FINAL_AUDIT
                    continue
                fi
            fi
            # A malformed protected-path field is a plan contract error, not
            # a source/test defect.  Sending it to REPAIR used to invite an
            # agent to edit product code while the driver was treating a
            # prose sentence as a path. Rebuild the canonical updated plan
            # instead; its file-backed delivery retry receives the exact
            # schema diagnostic.
            if [[ "$repair_source" == "$STATE_DIR/VERIFICATION_INTEGRITY.md" ]] \
                && grep -qE '^Invalid (canonical )?protected verification path' "$STATE_DIR/verification-integrity.log" 2>/dev/null; then
                echo 'Protected verification paths are malformed; returning to UPDATED_PLAN for a canonical plan correction.'
                rm -f "$STATE_DIR/verification.manifest" "$STATE_DIR/verification.paths" \
                    "$STATE_DIR/verification-snapshot" "$STATE_DIR/verification-integrity.log"
                set_state UPDATED_PLAN
                continue
            fi
            # Older runs can already be parked in REPAIR because their first
            # post-implementation snapshot rejected a source/test input that
            # the approved plan introduced but the implementation did not create.
            # There was no prior test input to protect. Take the explicit
            # absent-directory snapshot, run the normal driver green check,
            # and continue; invoking a repair agent cannot make that stale
            # snapshot failure meaningful.
            if [[ "$repair_source" == "$STATE_DIR/VERIFICATION_INTEGRITY.md" ]] \
                && [[ ! -e "$STATE_DIR/verification-snapshot" ]] \
                && grep -q '^Missing protected verification path:' "$STATE_DIR/verification-integrity.log" 2>/dev/null; then
                echo 'Repair reclassified as an initial absent verification-input snapshot; continuing with driver verification.'
                capture_verification_inputs
                run_green_check_auto || true
                plan_delivery_summary
                check_verification_inputs
                set_state WAIT_IMPLEMENT_APPROVAL
                continue
            fi
            if [[ "$WORKFLOW_AUTO_REPAIR" != 1 \
                    || ( "$repair_source" != "$GREEN_MD" && "$repair_source" != .uncle/docs/TEST_REVIEW.md \
                         && "$repair_source" != .uncle/docs/FINAL_AUDIT.md \
                         && "$repair_source" != "$STATE_DIR/runtime-unrunnable-application" \
                         && "$repair_source" != checklist-fail ) \
                    || "$repair_count_existing" -ge "$WORKFLOW_AUTO_REPAIR_ATTEMPTS" ]]; then
                if [[ "$WORKFLOW_CONTINUE_ON_TEST_FAILURE" == "1" ]] \
                    && [[ "$repair_source" == "$GREEN_MD" || "$repair_source" == .uncle/docs/TEST_REVIEW.md ]]; then
                    echo 'A verification finding is not eligible for another automatic repair; continuing it to final audit as unresolved evidence.'
                    record_nonblocking_failure "$(basename "$repair_source")" 'automatic repair not run; canonical finding remains unresolved'
                    record_test_failure_disposition
                    # Postflight verification happens only after checklist
                    # execution.  Returning to MANUAL_CHECKLIST here reruns
                    # unchanged workers merely to regenerate evidence the
                    # final audit can already read.
                    if [[ "${WORKFLOW_POSTFLIGHT_GREEN_CHECK:-1}" == 1 ]]; then
                        set_state FINAL_AUDIT
                    else
                        set_state MANUAL_CHECKLIST
                    fi
                    continue
                fi
                if [[ "$WORKFLOW_REPAIR" != 1 && "$repair_source" != .uncle/docs/FINAL_AUDIT.md ]]; then
                    echo "Repair is disabled for new application builds; $(basename "$repair_source") is carried to the final audit as unresolved evidence."
                    record_nonblocking_failure "$(basename "$repair_source")" 'repair is disabled; the failure remains unresolved'
                    record_test_failure_disposition || true
                    # A failed test review or driver check comes before the checklists, which are how the application is actually
                    # observed: they still run, and their rows go to the audit with the failure. Anything later (the checklist's
                    # own report) has had them already.
                    case "$(basename "$repair_source")" in
                        TEST_REVIEW.md|green-check.md)
                            if [[ -e "$STATE_DIR/checklist-ran" ]]; then set_state FINAL_AUDIT; else set_state MANUAL_CHECKLIST; fi ;;
                        *) set_state FINAL_AUDIT ;;
                    esac
                    continue
                fi
                echo 'Automatic repair is not eligible for this failure.'
                echo "Only $WORKFLOW_AUTO_REPAIR_ATTEMPTS driver green-check source/test repair(s) are automatic (WORKFLOW_AUTO_REPAIR_ATTEMPTS). Checklist, test-review, and other canonical report failures remain stopped for an explicit owner decision."
                exit 1
            fi
            # A run that reached REPAIR before the current test-review JSON
            # was ingested should recover on resume as well.  The fallback
            # report is an implementation-owned documentation gap, so no
            # source repair can make this acceptance result pass.
            if [[ ! -e "$STATE_DIR/test-evidence-handoff-attempted" ]] && [[ "$(green_regressions "$GREEN_CLASS")" -eq 0 ]] \
                && python3 -B "$ROOT/scripts/lib/test_review_route.py" "$STATE_DIR/documents/TEST_REVIEW.json" "$STATE_DIR/documents/AUTOMATED_TEST_REPORT.json"; then
                touch "$STATE_DIR/test-evidence-handoff-attempted" "$STATE_DIR/test-evidence-reconcile"
                echo 'Repair reclassified as incomplete test-evidence handoff; returning to implementation-owned report reconciliation.'
                set_state IMPLEMENT
                continue
            fi
            if [[ ! -e "$STATE_DIR/test-mutation-evidence-attempted" ]] && [[ "$(green_regressions "$GREEN_CLASS")" -eq 0 ]] \
                && [[ "${WORKFLOW_MUTATION_EVIDENCE_REPAIR:-0}" == 1 ]] \
                && python3 -B "$ROOT/scripts/lib/test_review_route.py" --mutation-evidence-gap "$STATE_DIR/documents/TEST_REVIEW.json"; then
                touch "$STATE_DIR/test-mutation-evidence-attempted" "$STATE_DIR/test-evidence-reconcile"
                echo 'Repair reclassified as missing mutation evidence; running one implementation-owned evidence reconciliation.'
                set_state IMPLEMENT
                continue
            fi
            verify_approval .uncle/docs/UPDATED_PROJECT_PLAN.md UPDATED_PROJECT_PLAN
            require_file "$STATE_DIR/repair-source"
            repair_count="$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 0)"
            case "$repair_count" in
                ''|*[!0-9]*) echo "Invalid repair-count; inspect $STATE_DIR/repair-count."; exit 1 ;;
            esac
            if [[ ${#repair_count} -gt 3 ]]; then
                echo "Invalid repair-count; inspect $STATE_DIR/repair-count."
                exit 1
            fi
            repair_count=$((10#$repair_count))
            plan_status=0
            if plan_executability_enabled && [[ -s "$STATE_DIR/plan-recovery.json" ]] && grep -qE '"phase": "(WAIT_LIVE|VERIFYING|DESIGN|AUTHORITY)"' "$STATE_DIR/plan-recovery.json"; then
                plan_before_write repair-resume || plan_status=$?
                case "$plan_status" in 22) ;; 10) continue ;; *) exit 1 ;; esac
            fi
            if [[ "$plan_status" != 22 ]]; then
                ensure_repair_capacity "$repair_count" || { triage_stop_reason "$STATE_DIR" human; exit 1; }
                repair_count=$((repair_count + 1))
                plan_before_write "repair-$repair_count" || plan_status=$?
                case "$plan_status" in 0|22) ;; 10) continue ;; *) exit 1 ;; esac
            fi
            PREVIOUS_VERIFICATION_SNAPSHOT="$(cat "$STATE_DIR/verification-snapshot" 2>/dev/null || true)"
            if [[ "$plan_status" != 22 ]]; then
                printf '%s\n' "$repair_count" > "$STATE_DIR/repair-count"
                repair_begin || exit 1
                run_stage REPAIR
                repair_status=0
                repair_judge || repair_status=$?
                case "$repair_status" in
                    0)
                        # A repair triggered by test review has changed the
                        # evidence base the review judged.  Never validate the
                        # old verdict again: discard both its JSON authority
                        # and Markdown view, rerun driver verification, then
                        # rebuild the review from the repaired tree.
                        if [[ "$(cat "$STATE_DIR/repair-source")" == .uncle/docs/TEST_REVIEW.md ]]; then
                            echo 'Repair changed the test-review evidence base; invalidating review and rerunning verification.'
                            rm -f .uncle/docs/TEST_REVIEW.md "$STATE_DIR/documents/TEST_REVIEW.json" \
                                "$STATE_DIR/documents/TEST_REVIEW_WORKERS.json"
                            plan_after_write || exit 1
                            verify_approval .uncle/docs/UPDATED_PROJECT_PLAN.md UPDATED_PROJECT_PLAN
                            capture_verification_inputs
                            run_green_check_auto || true
                            check_verification_inputs
                            set_state TEST_REVIEW
                            continue
                        fi
                        # A NOT_READY final audit sent here (see
                        # WAIT_AUDIT_OVERRIDE) judged the pre-repair tree. Its
                        # canonical packet, verdict, and dispositions all
                        # describe findings this repair was meant to fix;
                        # serving any of them again -- the FINAL_AUDIT state's
                        # own fast path included -- would silently re-approve
                        # or re-litigate evidence from before the fix. Clear
                        # them and replay the whole post-implementation
                        # pipeline, same as a GREEN_MD-sourced repair.
                        if [[ "$(cat "$STATE_DIR/repair-source")" == .uncle/docs/FINAL_AUDIT.md ]]; then
                            echo 'Repair changed the tree a NOT READY final audit judged; invalidating that audit and rerunning verification.'
                            rm -f .uncle/docs/FINAL_AUDIT.md "$STATE_DIR/documents/FINAL_AUDIT.json" \
                                "$STATE_DIR/documents/FINAL_AUDIT_WORKERS.json" \
                                "$VERDICT_FILE" "$STATE_DIR/audit-verdict.original" "$AUDIT_OVERRIDE_FILE"
                        fi
                        ;;
                    3|5) continue ;;
                    6) set_state "$(test_review_next_stage)"; continue ;;
                    *) exit 1 ;;
                esac
            fi
            plan_status=0
            plan_after_write || plan_status=$?
            case "$plan_status" in 0) ;; 27) continue ;; 10) plan_revise; continue ;; *) exit 1 ;; esac
            verify_approval "$PLAN_DOC" "$PLAN_DOC_NAME"
            capture_verification_inputs
            run_green_check_auto || true
            plan_delivery_summary
            check_verification_inputs
            rm -f "$STATE_DIR/checklist-ran"    # the tree changed: the checklists must observe it again
            set_state WAIT_IMPLEMENT_APPROVAL
            ;;

        MANUAL_CHECKLIST)
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi
            green_wait_final || { echo 'Driver verification did not publish final evidence before MANUAL_CHECKLIST.' >&2; exit 1; }
            runtime_ready_rc=0
            route_unrunnable_application || runtime_ready_rc=$?
            if [[ "$runtime_ready_rc" == 2 ]]; then continue; fi
            [[ "$runtime_ready_rc" == 0 ]] || exit 1
            # The checklist is written against what this machine was proved to
            # do, not against what the plan hoped for.
            snapshot_preflight_capabilities
            run_stage MANUAL_CHECKLIST
            set_state VALIDATE_MANUAL_CHECKLIST
            ;;

        VALIDATE_MANUAL_CHECKLIST)
            # The panel is advisory about which observations look useful.
            # Before execution, remove rows the driver can prove from its
            # completed command record or deterministic environment facts.
            # This also covers the single-reviewer fallback path.
            validate_status=0
            checklist_validate_manual_checklist MANUAL_CHECKLIST 1 \
                "The preceding MANUAL_CHECKLIST.json was rejected only for this required format.
Write a new complete manual checklist; every entry needs id, exact_action, and expected_result.
This is a new response: write the complete document now. A reply that refers back to a previous turn leaves this artifact empty and fails the same check again." \
                || validate_status=$?
            [[ "$validate_status" != 2 ]] || continue
            set_state EXECUTE_CHECKLIST
            ;;

        EXECUTE_CHECKLIST)
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi
            require_file "$STATE_DIR/verification.manifest"
            EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
            check_verification_inputs
            # Green evidence is a prerequisite. Execute workers consume its
            # canonical result and never repeat unit/build/browser checks the
            # driver already ran.
            green_wait_final || { echo 'Driver verification did not publish final evidence before EXECUTE_CHECKLIST.' >&2; exit 1; }
            runtime_ready_rc=0
            route_unrunnable_application || runtime_ready_rc=$?
            if [[ "$runtime_ready_rc" == 2 ]]; then continue; fi
            [[ "$runtime_ready_rc" == 0 ]] || exit 1
            plan_delivery_summary
            check_verification_inputs
            # New applications may have no commits. A historical-baseline
            # checklist row is an invalid contract, so regenerate it rather
            # than misclassifying that normal state as blocked setup.
            python3 "$ROOT/scripts/lib/checklist_document.py" --validate-json "$STATE_DIR/documents/MANUAL_CHECKLIST.json" || exit 1
            if python3 - "$STATE_DIR/documents/MANUAL_CHECKLIST.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding='utf-8'))
raise SystemExit(0 if payload.get('checks') == [] else 1)
PY
            then
                echo 'Manual checklist has no additional checks; recording an empty canonical execution report.'
                python3 "$ROOT/scripts/lib/execute_checklist_reports.py" --empty . || exit 1
                set_state VALIDATE_CHECKLIST
                continue
            fi
            snapshot_checklist_checks
            snapshot_checklist_groups
            ensure_checklist_runner execute-checklist || exit 1
            # Execute once, after the complete checklist is collated.  A
            # partial streamed checklist commits browser/resource rows into
            # early serial lanes and prevents the final scheduler from seeing
            # the full parallel fan-out.
            run_stage EXECUTE_CHECKLIST
            check_verification_inputs
            # Execution and report validation are separate durable steps. A
            # malformed table must not replay browser checks on every resume.
            set_state VALIDATE_CHECKLIST
            ;;

        VALIDATE_CHECKLIST)
            : > "$STATE_DIR/checklist-ran"      # every route out of here has had the checklist run (see test_review_next_stage)
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi
            require_file "$STATE_DIR/verification.manifest"
            EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
            check_verification_inputs
            echo "Validating saved checklist reports; checks will not be rerun."
            echo "Correct report errors in place, then resume this validation step."
            if [[ ! -s "$STATE_DIR/documents/EXECUTE_CHECKLIST.json" ]]; then
                # In gated mode a delivered but malformed report gets the
                # existing bounded format retry before fallback can replace
                # its evidence. A missing report still gets no model retry.
                if [[ "${WORKFLOW_POSTFLIGHT_GREEN_CHECK:-1}" != 1 && -s .uncle/docs/VERIFICATION_REPORT.md ]]; then
                    ensure_rc=0
                    ensure_acceptance_canonical .uncle/docs/VERIFICATION_REPORT.md || ensure_rc=$?
                    if [[ "$ensure_rc" == 2 ]]; then continue; fi
                    require_file "$STATE_DIR/documents/VERIFICATION_REPORT.json"
                fi
                echo 'Checklist reports missing; recording incomplete evidence automatically.'
                python3 "$ROOT/scripts/lib/checklist_report_fallback.py" --project . --missing-only || exit 1
            fi
            # A format defect just recorded as a degenerate placeholder (the
            # marker checklist_report_fallback.py leaves behind) must not be
            # rendered back over .uncle/docs/VERIFICATION_REPORT.md -- that
            # would overwrite the real report a person needs to see and fix
            # with a blank-id placeholder, destroying the evidence of what
            # went wrong.
            if [[ ! -e "$STATE_DIR/documents/.execute-checklist-malformed" ]]; then
                python3 -c "import importlib.util; s=importlib.util.spec_from_file_location('r','$ROOT/scripts/lib/checklist_report_fallback.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.render_from_json('.')" || exit 1
            fi
            require_file "$STATE_DIR/documents/EXECUTE_CHECKLIST.json"
            if [[ "${WORKFLOW_POSTFLIGHT_GREEN_CHECK:-1}" == 1 ]]; then
                # Restored by explicit operator decision, consistent with the
                # FAIL->REPAIR decision above: a real driver-level test
                # regression is a defect regardless of what the checklist's
                # own acceptance JSON says, so it is checked first and takes
                # precedence over the checklist's classification entirely
                # (an otherwise-PASS checklist does not excuse a failing
                # driver suite, and neither does a BLOCKED-HUMAN/BLOCKED-
                # SETUP/BLOCKED-IMPOSSIBLE/UNKNOWN row -- those are about the
                # checklist's own rows, not about whether the tree actually
                # works). This is the same GREEN_CHECK==1 && green_regressions>0
                # condition, and the same exhaustion/waiver handling, the
                # legacy (non-postflight) branch below already used for this
                # exact purpose before postflight-only became the default;
                # postflight mode had never consulted it at all. repair-source
                # is $GREEN_MD, exactly as the legacy branch uses -- already
                # safe here (unlike the FAIL case's VERIFICATION_REPORT.md):
                # it neither matches the REPAIR state's "older installed
                # drivers" VERIFICATION_REPORT.md-specific demotion shim, nor
                # needs adding to the ATTEMPTS-gate allowlist, since $GREEN_MD
                # is already one of its allowed values.
                green_ids="$(green_failed_ids "$GREEN_CLASS" "$GREEN_CMDS")"
                if [[ "$GREEN_CHECK" == 1 && -s "$GREEN_CLASS" ]] \
                    && [[ "$(green_regressions "$GREEN_CLASS")" -gt 0 ]] \
                    && ! { [[ -n "${green_ids// /}" ]] && waived_ids $green_ids; }; then
                    if [[ "$(green_failure_route "$WORKFLOW_CONTINUE_ON_TEST_FAILURE" \
                            "$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 0)" \
                            "$WORKFLOW_AUTO_REPAIR_ATTEMPTS")" == continue ]]; then
                        echo 'Driver verification still fails and no automatic repair remains; continuing to final audit with the failure recorded as unresolved evidence.'
                        record_nonblocking_failure green-check 'driver verification failed after the checklist; automatic repair not available'
                        record_test_failure_disposition
                        set_state FINAL_AUDIT
                        continue
                    fi
                    echo 'Driver verification shows a real regression; repairing before final audit, regardless of the checklist acceptance result.'
                    printf '%s\n' "$GREEN_MD" > "$STATE_DIR/repair-source"
                    set_state REPAIR
                    continue
                fi
                checklist_acceptance="$(python3 -B "$ROOT/scripts/lib/acceptance_json.py" "$STATE_DIR/documents/VERIFICATION_REPORT.json")"
                # UNKNOWN means the report could not even be classified
                # (missing/duplicate IDs, an unparseable row) -- a format
                # defect, not a judged outcome. Every other acceptance
                # document in this file gets a one-shot format-only retry
                # before failing closed (ensure_acceptance_canonical); a
                # checklist report in postflight-only mode skipped that
                # entirely and would otherwise sail on to FINAL_AUDIT with no
                # record that nobody could classify it. Give it the same
                # one-shot retry here, then stop for a person.
                if [[ "$checklist_acceptance" == UNKNOWN ]]; then
                    # A degenerate placeholder canonical artifact was just
                    # written for this unclassifiable attempt (the only way
                    # require_file above had something non-empty to find).
                    # Left in place, "already have EXECUTE_CHECKLIST.json" at
                    # the top of this state would keep reading that same
                    # placeholder forever -- on the retry below, and again on
                    # a later resume after a person edits
                    # .uncle/docs/VERIFICATION_REPORT.md by hand -- instead of
                    # ever re-deriving from what is actually on disk now.
                    rm -f "$STATE_DIR/documents/EXECUTE_CHECKLIST.json" \
                          "$STATE_DIR/documents/VERIFICATION_REPORT.json" \
                          "$STATE_DIR/documents/DEFECTS.json" \
                          "$STATE_DIR/documents/.execute-checklist-malformed"
                    checklist_format_retry_marker="$STATE_DIR/execute-checklist-format-retry.md"
                    if [[ ! -e "$checklist_format_retry_marker" ]]; then
                        {
                            echo 'The preceding .uncle/docs/VERIFICATION_REPORT.md was rejected: its rows could not be classified (missing/duplicate IDs, missing evidence, or no parseable required row).'
                            echo 'Write a new complete VERIFICATION_REPORT.md with exactly one final "## Acceptance gate" section: a header, separator, and one row per plain checklist ID, each with required, status, and evidence.'
                            echo 'Preserve every substantive finding, status, and evidence. Never change FAIL or BLOCKED merely to make the table parse.'
                        } > "$checklist_format_retry_marker"
                        echo 'Checklist acceptance report could not be classified (format defect); retrying execute-checklist once with the format diagnostic.'
                        set_state EXECUTE_CHECKLIST
                        continue
                    fi
                    supervision_validation_failed acceptance "$STATE_DIR/documents/VERIFICATION_REPORT.json" "Checklist acceptance report remained unclassifiable after one retry"
                    echo 'Checklist acceptance report could not be classified after one retry; stopping for correction.' >&2
                    exit 1
                fi
                # FAIL is a judged defect, not an ambiguous or merely
                # unreviewed finding -- unlike BLOCKED-SETUP/BLOCKED-HUMAN/
                # BLOCKED-IMPOSSIBLE (a real but non-code-fixable outcome) or
                # UNKNOWN (a format defect, handled above), a required check
                # someone/something actually ran and marked FAIL means the
                # tree has a known, repairable problem right now. Postflight-
                # only mode originally forwarded every non-PASS/non-UNKNOWN
                # result here uniformly as nonblocking evidence for
                # FINAL_AUDIT to judge; that silently relaxed "a checklist
                # defect enters REPAIR" (still true for every other acceptance
                # document in this file, and true here before postflight-only
                # became the default) without anyone deciding it should be.
                # Restored by explicit operator decision, not a judgment call
                # made in isolation here: a checklist FAIL routes to REPAIR
                # the same way a green-check regression a few lines below
                # does. acceptance_json.py's result() already classifies a
                # FAIL row as the literal string "REPAIR" (not "FAIL") -- the
                # same vocabulary acceptance_transition's REPAIR) case
                # switches on.
                #
                # Deliberately NOT repair-source=.uncle/docs/VERIFICATION_REPORT.md:
                # the REPAIR state's own "older installed drivers" compat shim
                # a little further up this file demotes that exact value back
                # to nonblocking/FINAL_AUDIT whenever the driver's green check
                # already passed -- it exists to neutralize exactly the old
                # pre-postflight behavior this fix is restoring, for runs that
                # saved a repair-source before postflight-only existed. A
                # distinct tag routes a freshly-decided FAIL through REPAIR's
                # ordinary (untagged) path instead of through that shim.
                if [[ "$checklist_acceptance" == REPAIR && "$WORKFLOW_REPAIR" != 1 ]]; then
                    echo 'Checklist acceptance report recorded a FAIL. Repair is disabled for new application builds; the failing rows go to the final audit as unresolved evidence.'
                    record_nonblocking_failure checklist-fail 'checklist acceptance recorded a FAIL; repair is disabled'
                    set_state FINAL_AUDIT
                    continue
                fi
                if [[ "$checklist_acceptance" == REPAIR ]]; then
                    echo 'Checklist acceptance report recorded a FAIL; repairing before final audit.'
                    printf '%s\n' checklist-fail > "$STATE_DIR/repair-source"
                    set_state REPAIR
                    continue
                fi
                if [[ "$checklist_acceptance" != PASS ]]; then
                    record_nonblocking_failure VERIFICATION_REPORT.json "checklist acceptance $checklist_acceptance after completed driver verification"
                fi
                echo 'Checklist evidence recorded against the completed driver verification result.'
                set_state FINAL_AUDIT
                continue
            fi
            # A checklist may expose the implementation fallback after a
            # passing driver suite. That is stale evidence, not a code defect
            # and never belongs in REPAIR. Reconcile the implementation-owned
            # JSON once, then rerun the checklist against the fresh handoff.
            if [[ ! -e "$STATE_DIR/checklist-evidence-handoff-attempted" ]] \
               && [[ "$(green_regressions "$GREEN_CLASS")" -eq 0 ]] \
               && python3 -B "$ROOT/scripts/lib/test_review_route.py" --report-stale \
                    "$STATE_DIR/documents/AUTOMATED_TEST_REPORT.json"; then
                touch "$STATE_DIR/checklist-evidence-handoff-attempted" "$STATE_DIR/test-evidence-reconcile"
                echo 'Checklist found a stale implementation test handoff after a passing green check; reconciling reports before rerunning checklist.'
                set_state IMPLEMENT
                continue
            fi
            green_ids="$(green_failed_ids "$GREEN_CLASS" "$GREEN_CMDS")"
            if [[ "$GREEN_CHECK" == 1 && -s "$GREEN_CLASS" ]] \
                && [[ "$(green_regressions "$GREEN_CLASS")" -gt 0 ]] \
                && ! { [[ -n "${green_ids// /}" ]] && waived_ids $green_ids; }; then
                # The checklist has already run. When no automatic repair is
                # left, REPAIR's "continue" path returns to MANUAL_CHECKLIST,
                # which regenerates and re-executes the whole checklist and
                # lands back here: a loop that never reaches the audit. Carry
                # the failing check to the audit instead, as unresolved
                # evidence, exactly as the earlier gates do.
                if [[ "$(green_failure_route "$WORKFLOW_CONTINUE_ON_TEST_FAILURE" \
                        "$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 0)" \
                        "$WORKFLOW_AUTO_REPAIR_ATTEMPTS")" == continue ]]; then
                    echo 'Driver verification still fails and no automatic repair remains; continuing to final audit with the failure recorded as unresolved evidence.'
                    record_nonblocking_failure green-check 'driver verification failed after the checklist; automatic repair not available'
                    record_test_failure_disposition
                    record_nonblocking_failure VERIFICATION_REPORT.json 'checklist ran; failing driver check carried to final audit'
                    set_state FINAL_AUDIT
                    continue
                fi
                printf '%s\n' "$GREEN_MD" > "$STATE_DIR/repair-source"
                set_state REPAIR
            else
                ensure_rc=0
                ensure_acceptance_canonical .uncle/docs/VERIFICATION_REPORT.md || ensure_rc=$?
                if [[ "$ensure_rc" == 2 ]]; then continue; fi
                checklist_acceptance="$(python3 -B "$ROOT/scripts/lib/acceptance_json.py" "$STATE_DIR/documents/VERIFICATION_REPORT.json")"
                # A checklist can report a missing human-only observation or
                # an evidence/coverage concern after the driver has already
                # proven the executable verification suite passes.  Repairing
                # source for that does not make a browser-only observation
                # available and creates an expensive loop.  Preserve every
                # failing row for final audit, but continue in the same mode
                # that already permits a failing green-check to be delivered
                # with an explicit disposition.
                # UNKNOWN is excluded: that is a format defect (malformed or
                # missing canonical JSON, the retry above already spent its
                # one attempt), not a real, judged acceptance outcome -- it
                # must still stop through acceptance_transition's own path
                # below, not be waved through as nonblocking evidence.
                if [[ "$WORKFLOW_CONTINUE_ON_TEST_FAILURE" == "1" ]] \
                    && [[ "$(green_regressions "$GREEN_CLASS")" -eq 0 ]] \
                    && [[ "$checklist_acceptance" != PASS && "$checklist_acceptance" != UNKNOWN ]]; then
                    echo 'Checklist findings are recorded as nonblocking evidence; continuing to final audit.'
                    record_nonblocking_failure VERIFICATION_REPORT.json "checklist acceptance $checklist_acceptance after passing driver green check"
                    set_state FINAL_AUDIT
                else
                    acceptance_transition .uncle/docs/VERIFICATION_REPORT.md FINAL_AUDIT
                fi
            fi
            ;;

        FINAL_AUDIT)
            if [[ "${WORKFLOW_POSTFLIGHT_GREEN_CHECK:-1}" != 1 ]]; then
                # Legacy gated behavior remains available for operators who
                # explicitly opt out of postflight-only verification.
                continue_nonblocking_test_review FINAL_AUDIT || \
                    acceptance_transition .uncle/docs/TEST_REVIEW.md FINAL_AUDIT 'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS'
                [[ "$(get_state)" == FINAL_AUDIT ]] || continue
                if has_nonblocking_failure VERIFICATION_REPORT.json; then
                    echo 'Checklist finding was already recorded as nonblocking evidence; final audit will assess the canonical report without reopening repair.'
                else
                    acceptance_transition .uncle/docs/VERIFICATION_REPORT.md FINAL_AUDIT
                fi
                [[ "$(get_state)" == FINAL_AUDIT ]] || continue
            fi
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi
            require_file "$STATE_DIR/verification.manifest"
            EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
            check_verification_inputs
            # TEST_REVIEW is the first synchronization point (its workers
            # must judge real evidence, never a PENDING placeholder); this is
            # the last. Verification almost always finished long ago by here
            # -- unless REPAIR changed the tree since, in which case this is
            # a real rerun and a real wait, correctly. Either way, final
            # audit receives the finished result as evidence rather than
            # using it to reopen the workflow.
            run_green_check_auto || true
            green_wait_final || {
                echo 'Driver postflight verification did not publish final evidence.' >&2
                exit 1
            }
            # `WORKFLOW_CONTINUE_ON_TEST_FAILURE` applies to evidence such as
            # a failing assertion in an otherwise usable app.  It must never
            # waive a compiler/module/server failure discovered only by this
            # deliberately late postflight check.  Route that concrete defect
            # through the bounded implementation retry before asking an audit
            # model to describe a page that cannot render.
            runtime_ready_rc=0
            route_unrunnable_application || runtime_ready_rc=$?
            if [[ "$runtime_ready_rc" == 2 ]]; then continue; fi
            [[ "$runtime_ready_rc" == 0 ]] || exit 1
            # Removed first so run_codex_review's require_file cannot read a
            # previous run's audit as this one's output.
            rm -f .uncle/docs/FINAL_AUDIT.md
            run_stage FINAL_AUDIT

            set_state VALIDATE_AUDIT
            ;;

        VALIDATE_AUDIT)
            if [[ "$DIFF_GATE" == "1" ]]; then verify_implementation_review; fi
            require_file "$STATE_DIR/verification.manifest"
            EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
            check_verification_inputs
            echo "Validating saved audit; the reviewer will not be rerun."
            # Shared with change-workflow.sh (uncle consolidation item 2): see
            # final_audit_validate/final_audit_route_verdict in
            # scripts/lib/audit-verdict.sh.
            audit_validate_status=0
            final_audit_validate require_artifact "-" || audit_validate_status=$?
            [[ "$audit_validate_status" != 2 ]] || continue
            final_audit_route_verdict "$FINAL_AUDIT_CLASS"
            ;;

        WAIT_AUDIT_OVERRIDE)
            require_file "$VERDICT_FILE"
            audit_class="$(verdict_file_field "$VERDICT_FILE" audit_class)"

            # Shared with change-workflow.sh (uncle consolidation item 2): see
            # final_audit_override_recovery/final_audit_override_gate in
            # scripts/lib/audit-verdict.sh. stagegate.sh keeps its unattended
            # repair-before-waiver route (enable_unattended_repair_route=1);
            # change-workflow.sh's original had no such route (see that
            # function's header comment).
            audit_recovery_status=0
            final_audit_override_recovery "$audit_class" "-" 1 || audit_recovery_status=$?
            [[ "$audit_recovery_status" != 0 ]] || continue

            final_audit_override_gate "$audit_class" review_and_approve \
                "  printf '%s\\n' IMPLEMENT > $STATE_FILE
  ./scripts/stagegate.sh" \
                build
            ;;

        COMPLETE)
            echo
            if green_pending; then
                echo "Verification commands are still running in the background; $GREEN_MD is replaced with their results when they finish."
            fi
            if [[ -s "$STATE_DIR/delivery-summary.tsv" ]] && grep -q $'\tWAIVED\t' "$STATE_DIR/delivery-summary.tsv"; then
                echo "Workflow complete with waived acceptance."
            else
                echo "Workflow complete."
            fi
            if [[ -s "$VERDICT_FILE" ]]; then
                echo "Build verdict: $(completed_verdict)"
            fi
            echo
            echo "Artifacts:"
            echo "  .uncle/docs/REQUIREMENTS_INTERPRETATION.md"
            echo "  .uncle/docs/PROJECT_PLAN.md"
            echo "  .uncle/docs/ADVERSARIAL_REVIEW.md"
            echo "  .uncle/docs/UPDATED_PROJECT_PLAN.md"
            echo "  .uncle/docs/IMPLEMENTATION_NOTES.md"
            echo "  .uncle/docs/AUTOMATED_TEST_REPORT.md"
            echo "  .uncle/docs/MANUAL_CHECKLIST.md"
            echo "  .uncle/docs/VERIFICATION_REPORT.md"
            echo "  .uncle/docs/FINAL_AUDIT.md"
            echo "  $DIFF_FILE"

            # An overridden check is not a passed check. Whatever else this
            # summary says, it says that first.
            if [[ -s "$GREEN_OVERRIDE_FILE" ]]; then
                echo
                echo "Completed with a failing green check, by human override:"
                sed 's/^/  /' "$GREEN_OVERRIDE_FILE"
                echo "  Detail: $GREEN_MD"
            fi

            if [[ -s "$AUDIT_OVERRIDE_FILE" ]]; then
                echo
                echo "Completed over a failing final audit, by human override:"
                sed 's/^/  /' "$AUDIT_OVERRIDE_FILE"
            fi

            # An unattended run reached the end; it did not earn the same
            # sentence as one a person signed off. Say how many judgments were
            # skipped and where they are written down, so "complete" is read
            # with the qualifier it needs.
            if [[ -s "$UNATTENDED_FILE" ]]; then
                echo
                echo "Unattended run: $(wc -l < "$UNATTENDED_FILE" | tr -d ' ') gate(s) passed with no human review."
                cut -f2,3 "$UNATTENDED_FILE" | sed 's/^/  /'
                echo "  Ledger: $UNATTENDED_FILE"
                if [[ -d "$STATE_DIR/waivers" ]]; then
                    echo "  Waivers: $STATE_DIR/waivers"
                fi
                echo "Waived checks were not performed. They are not passes, and this"
                echo "summary is the only place that says so out loud."
            fi
            triage_print_actions "$STATE_DIR"
            if [[ "$UNATTENDED" == 1 ]]; then
                echo
                finished_build_line "$(completed_verdict)"
            fi
            finished_extras print --kind new --reason not-applicable ${UNATTENDED:+$([[ "$UNATTENDED" == 1 ]] && echo --unattended)}

            exit 0
            ;;

        *)
            echo "Unknown workflow state: $state"
            exit 1
            ;;
    esac
done

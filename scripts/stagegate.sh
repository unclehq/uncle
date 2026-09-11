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
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="${UNCLE_PROJECT_ROOT:-$ROOT}"
if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "Project root does not exist: $PROJECT_ROOT" >&2
    exit 1
fi
cd "$PROJECT_ROOT"
PROJECT_ROOT="$PWD"
export DOCUMENT_BUDGET_SOURCE=REQUIREMENTS.md

# Prompt files are named relative to the uncle install, but the cwd is now the
# project. Resolve them the way gates are resolved: the project's own copy
# wins, otherwise the prompt that shipped with uncle. An absolute path or a
# path that exists in the project is returned untouched, which is what keeps
# composed prompts under .uncle/workflow working.
resolve_prompt() {
    local p="$1"
    if [[ -e "$p" ]]; then
        printf '%s' "$p"
    else
        printf '%s' "$ROOT/$p"
    fi
}

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

STATE_DIR=".uncle/workflow"
APPROVAL_DIR="$STATE_DIR/approvals"
LOG_DIR="$STATE_DIR/logs"
SPEC_DIR="$STATE_DIR/speculative"
STATE_FILE="$STATE_DIR/state"

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

# Run the stage that follows a human gate in the background while the human is
# still reading. Set to 0 to make every stage strictly serial again.
#
# Token cost: a speculative stage that gets discarded was paid for and thrown
# away. Discards only happen when the reviewer edits the gated file or declines
# the gate, so the expected waste is low — but if tokens matter more than wall
# clock, or you habitually edit documents during review, set this to 0.
WORKFLOW_SPECULATE="${WORKFLOW_SPECULATE:-1}"

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
DEFAULT_MODEL="opus"
DEFAULT_EFFORT="medium"

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
# implementation. AUTOMATED_TEST_REPORT.md is the implementing agent's account
# of checks the implementing agent ran; this runs them with no agent in the
# path. The commands come from UPDATED_PROJECT_PLAN.md, which the operator has
# already approved.
#
# Set to 0 to return to trusting the report.
GREEN_CHECK="${WORKFLOW_GREEN_CHECK:-1}"

# Refuse to reach COMPLETE on an audit that did not say the build is ready.
# Finishing anyway takes an explicit, recorded human override.
#
# Set to 0 to complete on any verdict, as before.
AUDIT_GATE="${WORKFLOW_AUDIT_GATE:-1}"

# The FINAL_AUDIT.md verdict classifier, the independent verification run, and
# the generated document the post-implementation gate shows. Sourced
# self-relative so the driver still runs from any CWD.
#
# state.sh is here for context_exhausted, which run_codex_review has always
# called and this driver never defined: the recovery hint after a reviewer runs
# out of tokens could not print, because the test for it failed as a missing
# command.
. "$ROOT/scripts/lib/state.sh"
. "$ROOT/scripts/lib/audit-verdict.sh"
. "$ROOT/scripts/lib/green-check.sh"
. "$ROOT/scripts/lib/implementation-review.sh"
. "$ROOT/scripts/lib/gates.sh"
. "$ROOT/scripts/lib/stage-config.sh"
. "$ROOT/scripts/lib/acceptance.sh"
. "$ROOT/scripts/lib/repair-limit.sh"
. "$ROOT/scripts/lib/checklist-capability.sh"
. "$ROOT/scripts/lib/human-input.sh"
. "$ROOT/scripts/lib/verification-integrity.sh"
. "$ROOT/scripts/lib/performance.sh"

. "$ROOT/scripts/lib/sha256.sh"

# A repair always comes back through the independent checks and human diff
# gate. Bound retries across restarts so an unfixable defect cannot spin.
MAX_REPAIRS="${WORKFLOW_MAX_REPAIRS:-2}"
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

# A required row that no environment can satisfy is a dead end unless someone
# can say so on the record. A waiver is that record: an operator's typed reason
# for one id, kept with the run. It never turns a row into a PASS -- the report
# still says the check was not performed -- it only stops the driver treating
# an impossible check as a reason to abandon the run.
waive_file() { printf '%s/waivers/%s' "$STATE_DIR" "$1"; }
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
record_unattended_gate() {
    local what="$1" detail="$2"
    mkdir -p "$STATE_DIR" 2>/dev/null || true
    printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$what" "$detail" \
        >> "$UNATTENDED_FILE" 2>/dev/null || true
}

waived_ids() {
    local id
    for id in "$@"; do
        [[ -s "$(waive_file "$id")" ]] || return 1
    done
    return 0
}

record_waiver() {
    local report="$1" reason
    shift
    local ids=("$@")

    # Unattended: there is nobody to type a reason, so the reason is the flag
    # itself. This is deliberately the least flattering wording available --
    # the waiver is what the audit reads, and it should not be mistakable for
    # someone having considered the check and decided it was fine.
    if [[ "${UNATTENDED:-0}" == 1 ]]; then
        reason="Waived by an unattended run; no person assessed this check."
        write_waivers "$report" "$reason" "${ids[@]}" || return 1
        record_unattended_gate "waiver" "$report: ${ids[*]}"
        return 0
    fi

    # A popup, when there is a terminal to draw one on. Waiving a required
    # check is the most consequential thing an operator does at this gate, and
    # it should look like a decision rather than another line of log output.
    #
    # Exit 2 means there was no terminal -- a piped or scripted run -- and the
    # text prompt below still has to work: a run that cannot draw a window
    # must still be able to decline.
    local popup="$ROOT/scripts/lib/waiver-popup.py" out status=2
    if [[ -f "$popup" ]] && python3 -c pass > /dev/null 2>&1; then
        out="$(mktemp)" || out=""
        if [[ -n "$out" ]]; then
            status=0
            python3 "$popup" --report "$report" --out "$out" "${ids[@]}" || status=$?
            if [[ "$status" == 0 ]]; then
                reason="$(cat "$out")"
                rm -f "$out"
                if [[ -n "$reason" ]]; then
                    write_waivers "$report" "$reason" "${ids[@]}" || return 1
                    return 0
                fi
                status=1
            fi
            rm -f "$out"
        fi
    fi
    if [[ "$status" == 1 ]]; then
        echo 'No waiver recorded; the run remains pending.'
        return 1
    fi

    echo
    echo "These required checks cannot be performed in this environment:"
    local id
    for id in "${ids[@]}"; do
        printf '  %s\n' "$id"
    done
    echo
    echo "Effort will not clear them -- amending $report's plan or the"
    echo "requirement behind it is the real fix, and is what should normally"
    echo "happen here. A waiver is the other option: it records why a required"
    echo "check cannot be performed and lets the run continue to its audit."
    echo "It does not make the check pass, and the report keeps saying so."
    gate_prompt "Type a reason to waive these checks for this run, or Enter to stop and amend the plan: "
    if ! IFS= read -r reason || [[ -z "$reason" ]]; then
        echo 'No waiver recorded; the run remains pending.'
        return 1
    fi
    write_waivers "$report" "$reason" "${ids[@]}"
}

# One writer for both the popup and the prompt: a waiver recorded one way must
# be indistinguishable from one recorded the other.
write_waivers() {
    local report="$1" reason="$2" id
    shift 2
    mkdir -p "$STATE_DIR/waivers" || return 1
    for id in "$@"; do
        {
            printf 'id: %s\n' "$id"
            printf 'report: %s\n' "$report"
            printf 'recorded: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
            printf 'reason: %s\n' "$reason"
        } > "$(waive_file "$id")" || return 1
    done
    echo "Waiver recorded for $# check(s); it is kept in $STATE_DIR/waivers."
    return 0
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
        if ! IFS= read -r choice; then
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
# does not change PREFLIGHT_REPORT.md, which is the agent's document and stays
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
    ids="$(acceptance_blocked_ids PREFLIGHT_REPORT.md BLOCKED-SETUP)"
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
    local plan="$1" commands
    commands="$(mktemp)" || return 0
    if ! verify_commands "$plan" > "$commands" || [[ ! -s "$commands" ]]; then
        rm -f "$commands"
        printf 'no Verification commands block'
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
    return 1
}

acceptance_setup_pause() {
    local report="$1"
    echo
    echo "Acceptance BLOCKED-SETUP: $report."
    echo "Outstanding setup, one action each:"
    acceptance_blocked_ids "$report" BLOCKED-SETUP | sed 's/^/  /'
    echo "Do them and rerun; each is doable in this environment."
    echo "The current stage remains pending; no acceptance pass was recorded."
}

# Waiting on a person is what this workflow is for, not a fault. Everything a
# machine could check has been checked, so the run goes on to its audit, which
# reads the report and decides.
acceptance_human_continue() {
    local report="$1" next="$2"
    echo
    echo "Awaiting human sign-off in $report:"
    acceptance_blocked_ids "$report" BLOCKED-HUMAN | sed 's/^/  /'
    echo "Nothing else is outstanding. Continuing to $next, which reads the"
    echo "report and judges it; the run cannot complete on an unsigned"
    echo "required check."
    set_state "$next"
}

# A waiver settles the check it names and nothing else. Whatever is still
# outstanding is still outstanding -- otherwise accepting one check no machine
# can perform would quietly skip the checks a machine could have performed
# after one commit.
acceptance_after_waiver() {
    local report="$1" next="$2"
    if [[ -n "$(acceptance_blocked_ids "$report" BLOCKED-SETUP)" ]]; then
        acceptance_setup_pause "$report"
        exit 1
    fi
    if [[ -n "$(acceptance_blocked_ids "$report" BLOCKED-HUMAN)" ]]; then
        acceptance_human_continue "$report" "$next"
        return 0
    fi
    set_state "$next"
}

acceptance_transition() {
    local report="$1" next="$2" result ids
    python3 "$ROOT/scripts/lib/repair-acceptance.py" "$report" || return 1
    result="$(acceptance_result "$report" "${3:-}")"
    case "$result" in
        PASS) set_state "$next" ;;
        REPAIR)
            printf '%s\n' "$report" > "$STATE_DIR/repair-source"
            set_state REPAIR
            ;;
        BLOCKED-HUMAN)
            acceptance_human_continue "$report" "$next"
            ;;
        BLOCKED-SETUP)
            # "Do them and rerun" needs someone to do them. Unattended, that
            # someone never arrives, so the choice is a waiver or a run that
            # never ends -- and a waiver at least says what went unchecked.
            if [[ "${UNATTENDED:-0}" == 1 ]]; then
                ids="$(acceptance_blocked_ids "$report" BLOCKED-SETUP)"
                # Not acceptance_after_waiver: that re-reads the report, which
                # still says BLOCKED-SETUP for the rows just waived, and would
                # pause on them again. A waiver settles the row, not the file.
                # shellcheck disable=SC2086
                if [[ -n "$ids" ]] && record_waiver "$report" $ids; then
                    if [[ -n "$(acceptance_blocked_ids "$report" BLOCKED-HUMAN)" ]]; then
                        acceptance_human_continue "$report" "$next"
                    else
                        set_state "$next"
                    fi
                    return 0
                fi
            fi
            acceptance_setup_pause "$report"
            exit 1
            ;;
        BLOCKED-IMPOSSIBLE)
            ids="$(acceptance_blocked_ids "$report" BLOCKED-IMPOSSIBLE)"
            if [[ -z "$ids" ]]; then
                echo "Acceptance $result: $report, but no required check names itself impossible."
                echo "The current stage remains pending; no acceptance pass was recorded."
                exit 1
            fi
            # shellcheck disable=SC2086
            if waived_ids $ids; then
                echo
                echo "Required check(s) $(printf '%s' "$ids" | tr '\n' ' ')waived for this run; see $STATE_DIR/waivers."
            # shellcheck disable=SC2086
            elif ! record_waiver "$report" $ids; then
                echo "The current stage remains pending; no acceptance pass was recorded."
                exit 1
            fi
            acceptance_after_waiver "$report" "$next"
            ;;
        *)
            echo "Acceptance $result: $report."
            if [[ "$result" == UNKNOWN ]]; then
                acceptance_problem "$report" | sed 's/^/  /'
            else
                echo "Resolve its prerequisites or report errors and rerun."
            fi
            echo "The current stage remains pending; no acceptance pass was recorded."
            exit 1
            ;;
    esac
}

verification_integrity_failure() {
    {
        echo '## Verification input changes'
        echo
        echo 'Verification changed protected inputs or could not establish their integrity.'
        echo 'Repair the tests or runner explicitly; do not accept regenerated expectations.'
        echo 'Record each test change and its requirement-based justification in IMPLEMENTATION_NOTES.md.'
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
    local snapshot digest file
    verification_paths UPDATED_PROJECT_PLAN.md > "$STATE_DIR/verification.paths" \
        || { echo 'Missing Protected verification paths in approved plan.' > "$STATE_DIR/verification-integrity.log"; verification_integrity_failure; }
    if ! verification_manifest "$STATE_DIR/verification.paths" \
        > "$STATE_DIR/verification.manifest" 2> "$STATE_DIR/verification-integrity.log"; then
        verification_integrity_failure
    fi
    EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
    [[ -n "$EXPECTED_VERIFICATION" ]] || verification_integrity_failure
    # Keep actual earlier assertions, not just their hashes or the repair
    # agent's description. New snapshots never overwrite prior evidence.
    snapshot="$(mktemp -d "$STATE_DIR/verification-snapshot.XXXXXX")"
    while IFS=$'\t' read -r digest file; do
        [[ "$digest" != DIRECTORY ]] || continue
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
    local actual started="$SECONDS"
    if ! actual="$(verification_manifest "$STATE_DIR/verification.paths" 2> "$STATE_DIR/verification-integrity.log")"; then
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
upper() {
    printf '%s' "$1" | tr '[:lower:]' '[:upper:]'
}

# ...nor ${var,,}.
lower() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

# One bold prompt line. `read -p` suppresses its prompt when stdin is not a
# terminal, so the text is printed separately. Escapes are emitted only for a
# real terminal: piped captures and TERM=dumb stay free of control bytes.
gate_prompt() {
    if [[ -t 1 && "${TERM:-}" != "dumb" ]]; then
        printf '%s%s%s' $'\033[1m' "$1" $'\033[0m'
    else
        printf '%s' "$1"
    fi
}

# The gate used to require the words APPROVE/ACKNOWLEDGE. Automation that still
# pipes them now declines; say so, so the break is visible in the output rather
# than silent.
legacy_word_notice() {
    case "$(upper "$1")" in
        APPROVE|ACKNOWLEDGE)
            echo "This gate now requires 'y' to approve."
            ;;
    esac
}

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
# than passing none. Only cline needs to be told, and it is told explicitly.
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
    local fallback="$DEFAULT_MODEL"
    case "$1" in
        requirements|execute-checklist) fallback="kimi" ;;
    esac
    if uncle_has_config || [[ -n "${UNCLE_RESOLVED_RUNNER:-}" ]]; then
        fallback="$(uncle_stage_model "$1" "${UNCLE_RESOLVED_RUNNER-$(uncle_stage_runner "$1")}")"
    fi
    stage_setting_opt MODEL "$1" "$fallback"
}

# Which CLI runs one stage. An explicit variable always wins over the config
# file — a driver invoked with WORKFLOW_AGENT_CMD set means it — and the
# built-in default applies only when the project has no config at all.
stage_agent_cmd() {
    local var
    var="WORKFLOW_AGENT_CMD_$(printf '%s' "$1" | tr '[:lower:]-.' '[:upper:]__')"
    if [[ -n "${!var:-}" ]]; then
        printf '%s' "${!var}"
    elif [[ -n "${WORKFLOW_AGENT_CMD:-}" ]]; then
        printf '%s' "$WORKFLOW_AGENT_CMD"
    else
        uncle_stage_cmd "$1" "${UNCLE_RESOLVED_RUNNER-$(uncle_stage_runner "$1")}"
    fi
}

stage_reviewer_cmd() {
    local var
    var="WORKFLOW_REVIEWER_CMD_$(printf '%s' "$1" | tr '[:lower:]-.' '[:upper:]__')"
    if [[ -n "${!var:-}" ]]; then
        printf '%s' "${!var}"
    elif [[ -n "${WORKFLOW_REVIEWER_CMD:-}" ]]; then
        printf '%s' "$WORKFLOW_REVIEWER_CMD"
    else
        uncle_stage_cmd "$1" "${UNCLE_RESOLVED_RUNNER-$(uncle_stage_runner "$1")}"
    fi
}

stage_effort() {
    uncle_effective_stage_effort "$1"
}

# Turn caps bound the worst case — a stage looping on a broken command — and
# nothing else. They are set well above what a healthy stage uses, because
# tripping one throws away the whole stage and the replay costs more than the
# cap saved. A document stage that needs 40 turns has already gone wrong;
# implementation and checklist execution legitimately run long.
stage_turns() {
    local fallback=40
    case "$1" in
        implementation) fallback=200 ;;
        execute-checklist) fallback=120 ;;
    esac
    stage_setting TURNS "$1" "$fallback"
}

# Tool grants are also a token lever. An agent holding Bash will shell out to
# explore the tree even when Glob and Grep would answer the question, and
# TodoWrite re-sends the whole list on every update — pure overhead for a stage
# whose entire output is one document.
stage_tools() {
    local fallback="Read,Glob,Grep,Write"
    case "$1" in
        updated-plan)
            fallback="Read,Glob,Grep,Write,Edit" ;;
        implementation|execute-checklist|preflight)
            fallback="Read,Glob,Grep,Write,Edit,TodoWrite,Bash"
            ;;
    esac
    stage_setting TOOLS "$1" "$fallback"
}

# New application pipeline stage order, used to report "stage N/M" to the TUI.
# Matches run_stage's case arms.
STATUS_STAGE_SEQ="requirements project-plan adversarial-review updated-plan preflight implementation test-review manual-checklist execute-checklist final-audit"

# Report the current stage to the TUI status channel. The exports feed the
# agent shims' own status writes; the start event written here covers every
# stage directly, including runners with no shim (plain claude, reviewers).
status_stage_context() {
    local log_name="$1"
    local model="${2:-(runner default)}"
    local mode="${3:-act}"
    local s i=1 index=0 n=0
    for s in $STATUS_STAGE_SEQ; do
        n=$((n + 1))
        if [[ "$s" == "$log_name" ]]; then
            index=$i
        fi
        i=$((i + 1))
    done
    local turns
    turns="$(stage_turns "$log_name")"
    export UNCLE_STATUS_STAGE="$log_name"
    export UNCLE_STATUS_STAGE_INDEX="$index"
    export UNCLE_STATUS_STAGE_TOTAL="$n"
    export UNCLE_STATUS_STAGE_TURNS="$turns"
    # Read per stage, like every other setting: an operator who discovers at a
    # gate that verification needs a local server can turn it on there.
    UNCLE_STAGE_NETWORK="$(uncle_stage_network "$log_name")"
    export UNCLE_STAGE_NETWORK
    if [[ -n "${UNCLE_STATUS_FILE:-}" ]]; then
        printf '{"event":"start","model":"%s","mode":"%s","stage":"%s","stage_index":%s,"stage_total":%s,"stage_turns":%s}\n' \
            "$model" "$mode" "$log_name" "$index" "$n" "$turns" \
            >> "$UNCLE_STATUS_FILE"
    fi
}

set_state() {
    printf '%s\n' "$1" > "$STATE_FILE"
}

get_state() {
    if [[ -s "$STATE_FILE" ]]; then
        cat "$STATE_FILE"
    else
        echo "REQUIREMENTS"
    fi
}

require_file() {
    if [[ ! -s "$1" ]]; then
        echo "Required file is missing or empty: $1"
        exit 1
    fi
}

# Used after an agent stage: a missing artifact here usually means a denied
# tool, not a refusal to work.
require_artifact() {
    if [[ ! -s "$1" ]]; then
        echo
        echo "Stage produced no artifact: $1"
        echo "Check the log for '[tool ERROR]' lines — a denied Write is the"
        echo "most common cause. A '[done] error_max_turns' line means the"
        echo "turn cap was too low; raise it with WORKFLOW_TURNS_<STAGE>."
        echo "State has not advanced, so the stage replays cleanly."
        exit 1
    fi
    check_document_budget "$1" || exit 1
}

verify_approval() {
    local file="$1"
    local name="$2"
    local approval="$APPROVAL_DIR/${name}.sha256"

    require_file "$file"
    require_file "$approval"

    local expected
    local actual

    expected="$(cat "$approval")"
    actual="$(hash_file "$file")"

    if [[ "$expected" != "$actual" ]]; then
        echo "$file changed after approval."
        echo "Review and approve it again."
        exit 1
    fi
}

review_and_approve() {
    local gate_start="$SECONDS"
    local file="$1"
    local name="$2"
    local wording
    wording="$(lower "${3:-approve}")"

    require_file "$file"

    local before
    local response

    # Unattended: record the approval against the bytes on disk, and record in
    # the run's own ledger that nobody read them. The digest still has to be
    # real -- later stages compare against it, and an approval attesting to
    # nothing would let a document change underneath them unnoticed.
    if [[ "${UNATTENDED:-0}" == 1 ]]; then
        before="$(hash_file "$file")"
        printf '%s\n' "$before" > "$APPROVAL_DIR/${name}.sha256"
        printf '%s\n' "$([[ "${UNATTENDED:-0}" == 1 ]] && printf unattended || printf '%s' "${UNCLE_APPROVAL_NAME:-}")" > "$APPROVAL_DIR/${name}.approved-by"
        record_unattended_gate "$name" "$wording $file without human review"
        echo "Unattended: recorded $wording of $file with no human review."
        if declare -f perf_record > /dev/null; then perf_record approval "$name" "$((SECONDS-gate_start))" 0; fi
        return 0
    fi

    while true; do
        before="$(hash_file "$file")"

        echo
        echo "=================================================="
        echo "HUMAN REVIEW REQUIRED: $file"
        echo "=================================================="
        echo
        echo "Review in another terminal with:"
        echo
        echo "  less $file"
        echo
        echo "or:"
        echo
        echo "  code $file"
        echo

        # Closed stdin here would abort the driver under `set -e` before the
        # Y/N prompt, so EOF is routed to the same decline path as any other
        # non-answer.
        if ! read -r -p "Press ENTER after reviewing the file..."; then
            if declare -f perf_record > /dev/null; then perf_record approval "$name" "$((SECONDS-gate_start))" 1; fi
            echo
            echo "Gate not accepted. Workflow paused."
            exit 0
        fi

        echo
        gate_prompt "Ready to $wording $file? [Y/N] "
        # IFS= keeps surrounding whitespace, so " y" is not an approval.
        # `|| true` keeps EOF from tripping `set -e` before the decline path
        # runs.
        response=""
        IFS= read -r response || true

        case "$response" in
            y|Y) ;;
            *)
                if declare -f perf_record > /dev/null; then perf_record approval "$name" "$((SECONDS-gate_start))" 1; fi
                echo "Gate not accepted. Workflow paused."
                legacy_word_notice "$response"
                exit 0
                ;;
        esac

        # The approval must attest to the bytes that were actually read. If the
        # file moved during review — a human edit, or a speculative stage that
        # ignored its instructions and wrote here — re-open the gate instead of
        # recording an approval for content nobody reviewed.
        if [[ "$(hash_file "$file")" == "$before" ]]; then
            break
        fi

        echo
        echo "$file changed while you were reviewing it."
        echo "Re-opening the gate so the approval covers what you read."
        cancel_speculation
    done

    # `before` is the digest that was just validated against the file, so it is
    # what gets recorded. Re-hashing here would attest to bytes that could have
    # landed after the check.
    printf '%s\n' "$before" > "$APPROVAL_DIR/${name}.sha256"
    printf '%s\n' "$([[ "${UNATTENDED:-0}" == 1 ]] && printf unattended || printf '%s' "${UNCLE_APPROVAL_NAME:-}")" > "$APPROVAL_DIR/${name}.approved-by"
    echo "Recorded approval for $file"
    if declare -f perf_record > /dev/null; then perf_record approval "$name" "$((SECONDS-gate_start))" 0; fi
}

# Render the stream-json event feed as readable progress lines.
# Non-JSON lines (startup warnings) are dropped rather than fataling jq.
format_claude_stream() {
    jq -R -r --unbuffered '
        (fromjson? // empty) as $e
        | if $e.type == "assistant" then
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

run_claude() {
    local prompt_file
    prompt_file="$(resolve_prompt "$1")"
    local log_name="$2"
    case "$log_name" in
        requirements|project-plan|baseline|change-spec|change-plan)
            python3 "$ROOT/scripts/lib/early-prerequisites.py" "$DOCUMENT_BUDGET_SOURCE" || exit $? ;;
    esac

    local tools="${3:-$(stage_tools "$log_name")}"
    local model
    local effort
    local turns
    local cmd
    local UNCLE_RESOLVED_RUNNER
    uncle_resolve_stage_runner "$log_name" AGENT || return 1

    cmd="$(stage_agent_cmd "$log_name")" || return 1
    model="$(stage_model "$log_name")"
    effort="$(stage_effort "$log_name")"
    turns="$(stage_turns "$log_name")"
    local -a client_cmd=("$cmd")
    case "${cmd##*/}" in
        claude|codex) client_cmd=(env -u UNCLE_STATUS_FILE -u UNCLE_PROJECT_ROOT -u UNCLE_CONFIG -u STAGEGATE_RUN_ID -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u DOCUMENT_BUDGET_SOURCE "$cmd") ;;
    esac

    require_file "$prompt_file"
    status_stage_context "$log_name" "${model:-}" act

    while true; do
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
        local -a model_args=()
        [[ -n "$model" ]] && model_args=(--model "$model")
        local started="$SECONDS"
        "${client_cmd[@]}" -p \
            "${model_args[@]+"${model_args[@]}"}" \
            --effort "$effort" \
            --strict-mcp-config \
            --max-turns "$turns" \
            --output-format stream-json \
            --verbose \
            --allowedTools "$tools" \
            < "$effective_prompt" \
            2>&1 \
            | tee "$LOG_DIR/${log_name}.jsonl" \
            | format_claude_stream || status=$?
        perf_record agent "$log_name" "$((SECONDS-started))" "$status" \
            "$LOG_DIR/${log_name}.jsonl" "$cmd" "$model" "$effort"

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
            fi
            echo "Agent ($cmd) exited with status $status."
            echo "Raw event log: $log"
            exit "$status"
        fi

        break
    done
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
    prompt_file="$(gated_prompt "$prompt_file" "$log_name" reviewer)"
    if [[ "$log_name" == test-review ]]; then
        local evidence_prompt="$LOG_DIR/test-review.evidence-prompt.md"
        cat "$prompt_file" > "$evidence_prompt"
        python3 "$ROOT/scripts/lib/test-review-context.py" "$PWD" "$STATE_DIR" >> "$evidence_prompt" || return 1
        prompt_file="$evidence_prompt"
    fi

    local review_key
    review_key="$(review_input_key "$output_file" "$prompt_file" "$cmd" "$model" "$effort" "$log_name")"
    if restore_plan_review "$output_file" "$review_key"; then
        finish_review_budget "$output_file" "$cmd" "$model" "$effort" "$log_name" || { [[ "$log_name" != adversarial-review ]] || exit 42; exit 1; }
        save_plan_review "$output_file" "$review_key"
        return 0
    fi

    echo
    echo "Launching reviewer ($cmd): $log_name"
    [[ -z "$model" ]] || echo "Model: $model"
    status_stage_context "$log_name" "${model:-}" review
    local status=0
    local started retry_answer
    while true; do
        started="$SECONDS"
        # stdin is the operator's gate-answer channel, not stage input: codex
        # appends a non-TTY stdin to the prompt and would block on it forever.
        # Project dirs need not be git repos; the read-only sandbox is the boundary.
        "${client_cmd[@]}" exec \
            --ephemeral \
            --skip-git-repo-check \
            --sandbox read-only \
            "${model_args[@]+"${model_args[@]}"}" \
            --output-last-message "$output_file" \
            "$(cat "$prompt_file")" \
            < /dev/null 2>&1 | tee "$LOG_DIR/${log_name}.log" || status=$?
        perf_record reviewer "$log_name" "$((SECONDS-started))" "$status" \
            "$LOG_DIR/${log_name}.log" "$cmd" "$model" "$effort"

        if [[ "$status" -ne 0 || ! -s "$output_file" ]] && context_exhausted "$LOG_DIR/${log_name}.log"; then
            echo
            echo "The reviewer ran out of context/tokens."
            echo "Change the reviewer model (Configure → reviewer) and re-run to resume this stage."
        fi

        [[ "$status" != 0 ]] || break
        gate_prompt "Reviewer $log_name failed (exit $status). Retry this reviewer stage? [Y/N]"
        if ! IFS= read -r retry_answer; then return "$status"; fi
        case "$retry_answer" in y|Y) status=0 ;; *) return "$status" ;; esac
    done
    require_file "$output_file"
    # Do not reuse results if inputs changed while the reviewer was reading them.
    if [[ -n "$review_key" && "$review_key" == "$(review_input_key "$output_file" "$prompt_file" "$cmd" "$model" "$effort" "$log_name")" ]]; then
        save_plan_review "$output_file" "$review_key"
    else
        review_key=""
    fi
    finish_review_budget "$output_file" "$cmd" "$model" "$effort" "$log_name" || { [[ "$log_name" != adversarial-review ]] || exit 42; exit 1; }
    save_plan_review "$output_file" "$review_key"
}

# Every stage's actual work, with no state transitions and no approval checks,
# so a stage can be run either in the foreground or speculatively.
run_stage() {
    case "$1" in
        REQUIREMENTS)
            run_claude prompts/requirements.md requirements
            require_artifact REQUIREMENTS_INTERPRETATION.md
            ;;
        PROJECT_PLAN)
            run_claude prompts/project-plan.md project-plan
            require_artifact PROJECT_PLAN.md
            ;;
        ADVERSARIAL_REVIEW)
            run_codex_review \
                prompts/adversarial-review.md \
                ADVERSARIAL_REVIEW.md \
                adversarial-review
            ;;
        UPDATED_PLAN)
            run_claude prompts/updated-plan.md updated-plan
            require_artifact UPDATED_PROJECT_PLAN.md
            ;;
        IMPLEMENT)
            run_claude prompts/implement.md implementation
            require_artifact IMPLEMENTATION_NOTES.md
            require_artifact AUTOMATED_TEST_REPORT.md
            ;;
        PREFLIGHT)
            rm -f PREFLIGHT_REPORT.md
            run_claude prompts/preflight.md preflight
            require_artifact PREFLIGHT_REPORT.md
            ;;
        TEST_REVIEW)
            # Preserve the previous findings for the next review and repairs.
            if [[ -s TEST_REVIEW.md ]]; then
                cp TEST_REVIEW.md "$STATE_DIR/previous-test-review.md"
            fi
            rm -f TEST_REVIEW.md
            run_codex_review prompts/test-review.md TEST_REVIEW.md test-review
            ;;
        REPAIR)
            run_claude prompts/repair.md implementation
            require_artifact IMPLEMENTATION_NOTES.md
            require_artifact AUTOMATED_TEST_REPORT.md
            ;;
        MANUAL_CHECKLIST)
            run_codex_review \
                prompts/manual-checklist.md \
                MANUAL_CHECKLIST.md \
                manual-checklist
            ;;
        EXECUTE_CHECKLIST)
            rm -f VERIFICATION_REPORT.md
            run_claude prompts/execute-checklist.md execute-checklist
            ;;
        FINAL_AUDIT)
            run_codex_review \
                prompts/final-audit.md \
                FINAL_AUDIT.md \
                final-audit
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
# The list comes from UPDATED_PROJECT_PLAN.md and nowhere else: the driver
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
            echo "the plan's verification commands, so AUTOMATED_TEST_REPORT.md"
            echo "below is the implementing agent's unverified account of them."
        } > "$GREEN_MD"
        return 0
    fi

    verify_commands UPDATED_PROJECT_PLAN.md > "$GREEN_CMDS"
    if ! verify_parallel_groups UPDATED_PROJECT_PLAN.md "$GREEN_CMDS" > "$STATE_DIR/green-check.groups"; then
        echo 'Invalid Parallel verification groups. Amend the plan and renew approval.'
        parallel_groups_format_hint
        exit 1
    fi

    if [[ ! -s "$GREEN_CMDS" ]]; then
        : > "$GREEN_CLASS"
        green_report "$GREEN_CLASS" "$GREEN_MD" UPDATED_PROJECT_PLAN.md \
            "$LOG_DIR/green-check.log" 0
        echo
        echo "Green check NOT RUN: UPDATED_PROJECT_PLAN.md has no fenced block"
        echo "under a 'Verification commands' heading, so the driver has no"
        echo "approved commands to run."
        return 0
    fi

    echo
    echo "Re-running the plan's verification commands from the driver:"
    local execution_status=0
    green_run "$GREEN_CMDS" "$GREEN_CUR" "$LOG_DIR/green-check.log" \
        check_verification_inputs "$STATE_DIR/green-check.groups" || execution_status=$?
    [[ "$execution_status" == 0 ]] || exit "$execution_status"

    # No baseline file: green_classify treats every failure as a regression,
    # which is the correct reading for a new application.
    green_classify "$STATE_DIR/green-check.no-baseline" "$GREEN_CUR" > "$GREEN_CLASS"
    green_report "$GREEN_CLASS" "$GREEN_MD" UPDATED_PROJECT_PLAN.md \
        "$LOG_DIR/green-check.log" 0

    local failures
    failures="$(green_regressions "$GREEN_CLASS")"

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

# Rebuilt from the working tree every time the gate opens, so the approval
# digest attests to the tree rather than to a file somebody could edit.
build_implementation_review() {
    write_change_diff "$DIFF_FILE"
    write_implementation_review "$REVIEW_FILE" "$DIFF_FILE" "$GREEN_MD" \
        IMPLEMENTATION_NOTES.md AUTOMATED_TEST_REPORT.md \
        "$STATE_DIR/verification.paths" "$STATE_DIR/verification.manifest" \
        "$STATE_DIR/verification-snapshot" "$STATE_DIR/TEST_CHANGES.diff"
}

# Regenerate the document and compare it with what was approved. A mismatch
# means the code moved after the operator read it, so the gate re-opens on the
# current tree rather than the pipeline carrying a stale approval forward.
verify_implementation_review() {
    local approval="$APPROVAL_DIR/IMPLEMENTATION_REVIEW.sha256"

    require_file "$approval"
    build_implementation_review

    if [[ "$(hash_file "$REVIEW_FILE")" != "$(cat "$approval")" ]]; then
        echo
        echo "The working tree changed after the implementation was approved."
        echo "$REVIEW_FILE has been rebuilt from the current tree."
        set_state WAIT_IMPLEMENT_APPROVAL
        echo "Re-run the driver to review and approve what is there now."
        exit 0
    fi
}

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
# CLAUDE.md forbids starting it before UPDATED_PROJECT_PLAN.md is approved.

spec_pid=""
spec_stage=""

cancel_speculation() {
    if [[ -n "$spec_pid" ]] && kill -0 "$spec_pid" 2>/dev/null; then
        echo "Cancelling speculative $spec_stage..."
        kill "$spec_pid" 2>/dev/null || true
        wait "$spec_pid" 2>/dev/null || true
    fi
    spec_pid=""
    spec_stage=""
}

trap cancel_speculation EXIT

speculate() {
    local stage="$1"
    local gate_file="$2"

    [[ "$WORKFLOW_SPECULATE" == "1" ]] || return 0
    [[ -z "$spec_pid" ]] || return 0
    [[ -s "$gate_file" ]] || return 0

    hash_file "$gate_file" > "$SPEC_DIR/${stage}.input"

    echo "Starting $stage in the background while you review."
    echo "Its output is only used if $gate_file is unchanged at approval."

    # Fully detached from this terminal: the gate prompt owns stdin, and stage
    # output would otherwise interleave with it.
    UNCLE_SPECULATIVE=true run_stage "$stage" > "$LOG_DIR/${stage}.speculative.log" 2>&1 < /dev/null &
    spec_pid=$!
    spec_stage="$stage"
}

# Succeeds when a usable speculative artifact is in place, in which case the
# caller skips the stage.
adopt_speculation() {
    local stage="$1"
    local gate_file="$2"
    local artifact="$3"
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
        echo "Speculative $stage failed (status $status). Running it again."
        echo "Log: $LOG_DIR/${stage}.speculative.log"
        return 1
    fi

    if [[ "$(cat "$SPEC_DIR/${stage}.input")" != "$(hash_file "$gate_file")" ]]; then
        echo "$gate_file changed during review. Discarding speculative $stage."
        rm -f "$artifact"
        return 1
    fi

    if [[ ! -s "$artifact" ]]; then
        echo "Speculative $stage produced no artifact. Running it again."
        return 1
    fi

    echo "Adopted speculative $stage — inputs unchanged since it started."
    echo "Log: $LOG_DIR/${stage}.speculative.log"
    return 0
}

# Run a stage, using the speculative result when one is valid.
run_gated_stage() {
    local stage="$1"
    local gate_file="$2"
    local artifact="$3"

    adopt_speculation "$stage" "$gate_file" "$artifact" && return 0
    run_stage "$stage"
}

python3 "$ROOT/scripts/lib/session-totals.py" "$STATE_DIR" REQUIREMENTS.md \
    "${STAGEGATE_ORIGIN_REPO:-}#${STAGEGATE_ORIGIN_ISSUE:-}" || true

while true; do
    state="$(get_state)"

    echo
    echo "Current workflow state: $state"

    case "$state" in
        REQUIREMENTS)
            run_stage REQUIREMENTS
            set_state WAIT_REQUIREMENTS_APPROVAL
            ;;

        WAIT_REQUIREMENTS_APPROVAL)
            speculate PROJECT_PLAN REQUIREMENTS_INTERPRETATION.md
            review_and_approve \
                REQUIREMENTS_INTERPRETATION.md \
                REQUIREMENTS_INTERPRETATION \
                approve
            set_state PROJECT_PLAN
            ;;

        PROJECT_PLAN)
            verify_approval \
                REQUIREMENTS_INTERPRETATION.md \
                REQUIREMENTS_INTERPRETATION
            run_gated_stage PROJECT_PLAN \
                REQUIREMENTS_INTERPRETATION.md \
                PROJECT_PLAN.md
            set_state WAIT_PLAN_APPROVAL
            ;;

        WAIT_PLAN_APPROVAL)
            speculate ADVERSARIAL_REVIEW PROJECT_PLAN.md
            review_and_approve PROJECT_PLAN.md PROJECT_PLAN approve
            set_state ADVERSARIAL_REVIEW
            ;;

        ADVERSARIAL_REVIEW)
            verify_approval PROJECT_PLAN.md PROJECT_PLAN
            run_gated_stage ADVERSARIAL_REVIEW \
                PROJECT_PLAN.md \
                ADVERSARIAL_REVIEW.md
            set_state WAIT_REVIEW_ACKNOWLEDGEMENT
            ;;

        WAIT_REVIEW_ACKNOWLEDGEMENT)
            speculate UPDATED_PLAN ADVERSARIAL_REVIEW.md
            review_and_approve \
                ADVERSARIAL_REVIEW.md \
                ADVERSARIAL_REVIEW \
                acknowledge
            set_state UPDATED_PLAN
            ;;

        UPDATED_PLAN)
            verify_approval PROJECT_PLAN.md PROJECT_PLAN
            verify_approval \
                ADVERSARIAL_REVIEW.md \
                ADVERSARIAL_REVIEW
            run_gated_stage UPDATED_PLAN \
                ADVERSARIAL_REVIEW.md \
                UPDATED_PROJECT_PLAN.md
            set_state WAIT_UPDATED_PLAN_APPROVAL
            ;;

        WAIT_UPDATED_PLAN_APPROVAL)
            # Reject a structurally incomplete plan before asking anyone to
            # read it. Approving a plan the next state will refuse wastes the
            # one thing this workflow cannot generate more of.
            plan_problem="$(plan_structure_problem UPDATED_PROJECT_PLAN.md)" && {
                echo
                echo "UPDATED_PROJECT_PLAN.md has $plan_problem."
                plan_headings UPDATED_PROJECT_PLAN.md
                if [[ "$plan_problem" == 'invalid Parallel verification groups' ]]; then
                    parallel_groups_format_hint
                elif [[ "$plan_problem" == 'no Protected verification paths block' ]]; then
                    echo 'Expected: a heading with the words "protected" and "paths", then'
                    echo 'one fenced block of repository-relative paths, one per line.'
                elif [[ "$plan_problem" == 'no Verification commands block' ]]; then
                    echo 'Expected: ## Verification commands with one fenced block of'
                    echo 'commands, one per line, and nothing else in it.'
                fi
                echo "The driver reads that block to run and protect verification,"
                echo "so amend the plan before approving it; you are not being asked"
                echo "to approve a plan that the next stage would reject."
                exit 1
            }
            # No speculation here: IMPLEMENT writes source code, and it may not
            # start before this approval exists.
            review_and_approve \
                UPDATED_PROJECT_PLAN.md \
                UPDATED_PROJECT_PLAN \
                approve
            set_state PREFLIGHT
            ;;

        PREFLIGHT)
            verify_approval UPDATED_PROJECT_PLAN.md UPDATED_PROJECT_PLAN
            verify_commands UPDATED_PROJECT_PLAN.md > "$GREEN_CMDS"
            if [[ ! -s "$GREEN_CMDS" ]]; then
                echo "No Verification commands in UPDATED_PROJECT_PLAN.md. Amend the plan and renew its approval."
                exit 1
            fi
            if ! verify_parallel_groups UPDATED_PROJECT_PLAN.md "$GREEN_CMDS" > "$STATE_DIR/green-check.groups"; then
                echo 'Invalid Parallel verification groups. Amend the plan and renew approval.'
                parallel_groups_format_hint
                exit 1
            fi
            if ! verification_paths UPDATED_PROJECT_PLAN.md > /dev/null; then
                echo "Missing Protected verification paths in UPDATED_PROJECT_PLAN.md."
                echo "The heading needs the words 'protected' and 'paths', followed by"
                echo "one fenced block of repository-relative paths. Its headings are:"
                plan_headings UPDATED_PROJECT_PLAN.md
                echo "Amend the plan and renew its approval."
                exit 1
            fi
            run_stage PREFLIGHT
            preflight_result="$(acceptance_result PREFLIGHT_REPORT.md)"
            case "$preflight_result" in
                PASS) human_input_reset "$STATE_DIR" ;;
                BLOCKED-HUMAN)
                    human_input_reset "$STATE_DIR"
                    echo
                    echo "Prerequisites await a person, not an arrangement:"
                    acceptance_blocked_ids PREFLIGHT_REPORT.md BLOCKED-HUMAN | sed 's/^/  /'
                    echo "Implementation does not consume a signature, so the run continues."
                    echo "Verification does: these must be signed before the checklist can"
                    echo "pass, and the gates there will say so again."
                    ;;
                BLOCKED-SETUP)
                    echo "Prerequisites BLOCKED-SETUP: see PREFLIGHT_REPORT.md."
                    echo "Outstanding, one action each:"
                    acceptance_blocked_ids PREFLIGHT_REPORT.md BLOCKED-SETUP | sed 's/^/  /'
                    # Offer to take them here. A prerequisite that is waiting
                    # on a person is waiting on the person sitting at this
                    # gate, and hand-editing markdown between runs is how its
                    # path ends up spelled two ways.
                    blocked_ids="$(acceptance_blocked_ids PREFLIGHT_REPORT.md BLOCKED-SETUP)"
                    # Unattended: nobody is sitting at this gate to supply the
                    # prerequisite, so asking is the one thing that cannot
                    # work. Waive them and go on -- the rows stay blocked in
                    # the report, so implementation proceeds knowing an input
                    # it expected is not there, which is a worse position than
                    # a person providing it and an honest one.
                    if [[ "${UNATTENDED:-0}" == 1 ]]; then
                        # shellcheck disable=SC2086
                        if [[ -z "$blocked_ids" ]] \
                            || ! record_waiver PREFLIGHT_REPORT.md $blocked_ids; then
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
                        preflight_blocked_gate PREFLIGHT_REPORT.md BLOCKED-SETUP $blocked_ids
                    fi
                    ;;
                *)
                    echo "Prerequisites $preflight_result: see PREFLIGHT_REPORT.md."
                    if [[ "$preflight_result" == UNKNOWN ]]; then
                        # UNKNOWN means the table did not parse. Name the line:
                        # the verdict alone leaves an operator guessing which of
                        # a dozen rules the report missed.
                        acceptance_problem PREFLIGHT_REPORT.md | sed 's/^/  /'
                        echo "Resolve and rerun."
                        exit 1
                    fi
                    if [[ "$preflight_result" == BLOCKED-IMPOSSIBLE && "${UNATTENDED:-0}" != 1 ]]; then
                        impossible_ids="$(acceptance_blocked_ids PREFLIGHT_REPORT.md BLOCKED-IMPOSSIBLE)"
                        if [[ -n "$impossible_ids" ]]; then
                            # Effort will not clear these, but the answer is
                            # still a choice: review, provide out-of-band,
                            # skip on the record, or decline and amend.
                            # shellcheck disable=SC2086
                            preflight_blocked_gate PREFLIGHT_REPORT.md BLOCKED-IMPOSSIBLE $impossible_ids
                        fi
                    fi
                    echo "Resolve and rerun."
                    exit 1
                    ;;
            esac
            hash_file UPDATED_PROJECT_PLAN.md > "$STATE_DIR/preflight-plan.sha256"
            set_state IMPLEMENT
            ;;

        IMPLEMENT)
            verify_approval \
                UPDATED_PROJECT_PLAN.md \
                UPDATED_PROJECT_PLAN
            if [[ ! -s "$STATE_DIR/preflight-plan.sha256" ]] \
                || [[ "$(cat "$STATE_DIR/preflight-plan.sha256")" != "$(hash_file UPDATED_PROJECT_PLAN.md)" ]] \
                || ! preflight_settled "$(acceptance_result PREFLIGHT_REPORT.md)"; then
                set_state PREFLIGHT
                continue
            fi
            # Taken before the agent runs, so a file that was already sitting
            # in the directory is not read as something this build produced.
            if [[ ! -e "$UNTRACKED_BASELINE" ]]; then
                snapshot_untracked "$UNTRACKED_BASELINE"
            fi

            run_stage IMPLEMENT
            verify_approval UPDATED_PROJECT_PLAN.md UPDATED_PROJECT_PLAN
            PREVIOUS_VERIFICATION_SNAPSHOT=""
            capture_verification_inputs

            # Independent of the agent that just claimed its checks passed.
            # The result is carried to the gate rather than ending the run: a
            # failure is for the operator to weigh against the diff, and
            # killing the run here would throw away the stage that produced it.
            run_green_check || true
            check_verification_inputs

            set_state WAIT_IMPLEMENT_APPROVAL
            ;;

        WAIT_IMPLEMENT_APPROVAL)
            green_failed="$(green_regressions "$GREEN_CLASS")"

            if [[ "$DIFF_GATE" != "1" ]]; then
                if [[ "$green_failed" -gt 0 ]]; then
                    echo
                    echo "Refusing to continue: $green_failed verification"
                    echo "check(s) failed, and WORKFLOW_DIFF_GATE=0 leaves no"
                    echo "human gate to weigh that against the diff."
                    echo "Fix the failure, or re-enable the gate."
                    exit 1
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
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi
            require_file "$STATE_DIR/verification.manifest"
            EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
            check_verification_inputs
            run_stage TEST_REVIEW
            check_verification_inputs
            if [[ "$GREEN_CHECK" != 1 || ! -s "$GREEN_CLASS" ]]; then
                echo "Acceptance BLOCKED: the driver must run the approved verification suite."
                echo "Enable WORKFLOW_GREEN_CHECK and rerun IMPLEMENT to capture its results."
                exit 1
            fi
            if [[ "$(green_regressions "$GREEN_CLASS")" -gt 0 ]] \
                && [[ "$(acceptance_result TEST_REVIEW.md 'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS')" == PASS ]]; then
                printf '%s\n' "$GREEN_MD" > "$STATE_DIR/repair-source"
                set_state REPAIR
            else
                acceptance_transition TEST_REVIEW.md MANUAL_CHECKLIST 'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS'
            fi
            ;;

        REPAIR)
            verify_approval UPDATED_PROJECT_PLAN.md UPDATED_PROJECT_PLAN
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
            ensure_repair_capacity "$repair_count" || exit 1
            repair_count=$((repair_count + 1))
            printf '%s\n' "$repair_count" > "$STATE_DIR/repair-count"
            PREVIOUS_VERIFICATION_SNAPSHOT="$(cat "$STATE_DIR/verification-snapshot" 2>/dev/null || true)"
            run_stage REPAIR
            verify_approval UPDATED_PROJECT_PLAN.md UPDATED_PROJECT_PLAN
            capture_verification_inputs
            run_green_check || true
            check_verification_inputs
            set_state WAIT_IMPLEMENT_APPROVAL
            ;;

        MANUAL_CHECKLIST)
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi
            # The checklist is written against what this machine was proved to
            # do, not against what the plan hoped for.
            snapshot_preflight_capabilities
            run_stage MANUAL_CHECKLIST
            set_state EXECUTE_CHECKLIST
            ;;

        EXECUTE_CHECKLIST)
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi
            require_file "$STATE_DIR/verification.manifest"
            EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
            check_verification_inputs
            run_green_check || true
            check_verification_inputs
            snapshot_checklist_checks
            snapshot_checklist_groups
            ensure_checklist_runner execute-checklist || exit 1
            run_stage EXECUTE_CHECKLIST
            check_verification_inputs
            # Execution and report validation are separate durable steps. A
            # malformed table must not replay browser checks on every resume.
            set_state VALIDATE_CHECKLIST
            ;;

        VALIDATE_CHECKLIST)
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi
            require_file "$STATE_DIR/verification.manifest"
            EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
            check_verification_inputs
            echo "Validating saved checklist reports; checks will not be rerun."
            echo "Correct report errors in place, then resume this validation step."
            require_file VERIFICATION_REPORT.md
            require_file DEFECTS.md
            check_document_budget VERIFICATION_REPORT.md || exit 1
            check_document_budget DEFECTS.md || exit 1
            if [[ "$GREEN_CHECK" == 1 && -s "$GREEN_CLASS" ]] && [[ "$(green_regressions "$GREEN_CLASS")" -gt 0 ]]; then
                printf '%s\n' "$GREEN_MD" > "$STATE_DIR/repair-source"
                set_state REPAIR
            else
                acceptance_transition VERIFICATION_REPORT.md FINAL_AUDIT
            fi
            ;;

        FINAL_AUDIT)
            # Use the same decisions as the preceding gates: human blockers
            # and recorded waivers reach audit without becoming PASS. Testing
            # only for PASS here sent those reports back around the pipeline.
            acceptance_transition TEST_REVIEW.md FINAL_AUDIT 'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS'
            [[ "$(get_state)" == FINAL_AUDIT ]] || continue
            acceptance_transition VERIFICATION_REPORT.md FINAL_AUDIT
            [[ "$(get_state)" == FINAL_AUDIT ]] || continue
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi
            require_file "$STATE_DIR/verification.manifest"
            EXPECTED_VERIFICATION="$(cat "$STATE_DIR/verification.manifest")"
            check_verification_inputs
            # Removed first so run_codex_review's require_file cannot read a
            # previous run's audit as this one's output.
            rm -f FINAL_AUDIT.md
            run_stage FINAL_AUDIT

            audit_class="$(classify_audit_verdict FINAL_AUDIT.md)"
            printf '%s\t%s\n' "$audit_class" "$(hash_file FINAL_AUDIT.md)" \
                > "$VERDICT_FILE"
            echo
            echo "Audit verdict: $audit_class"

            # The audit's conclusion decides whether the run finishes. A
            # NOT READY verdict, or one whose last line cannot be read as a
            # verdict at all, is not a pass.
            case "$audit_class" in
                READY|READY_WITH_NON_BLOCKING_ISSUES)
                    set_state COMPLETE
                    ;;
                *)
                    if [[ "$AUDIT_GATE" == "1" ]]; then
                        set_state WAIT_AUDIT_OVERRIDE
                    else
                        echo "Audit gate disabled (WORKFLOW_AUDIT_GATE=0);" \
                             "completing on a $audit_class verdict."
                        set_state COMPLETE
                    fi
                    ;;
            esac
            ;;

        WAIT_AUDIT_OVERRIDE)
            require_file "$VERDICT_FILE"
            audit_class="$(awk -F'\t' 'NR == 1 {print $1}' "$VERDICT_FILE")"

            # Recover an interruption after saving READY but before COMPLETE.
            if [[ "$audit_class" == READY ]]; then
                [[ "$(awk -F'\t' 'NR == 1 {print $2}' "$VERDICT_FILE")" == "$(hash_file FINAL_AUDIT.md)" ]] || exit 1
                python3 "$ROOT/scripts/lib/audit-findings.py" FINAL_AUDIT.md "$STATE_DIR" --check || exit 1
                set_state COMPLETE
                continue
            fi

            if [[ "$audit_class" == NOT_READY ]]; then
                audit_hash="$(hash_file FINAL_AUDIT.md)"
                if [[ "$(classify_audit_verdict FINAL_AUDIT.md)" != NOT_READY ]] \
                    || [[ "$(awk -F'\t' 'NR == 1 {print $2}' "$VERDICT_FILE")" != "$audit_hash" ]]; then
                    echo "The audit changed since its verdict was recorded; rerun FINAL_AUDIT."
                    exit 1
                fi
                # Each finding needs an explicit decision, including in an
                # unattended run. EOF leaves the saved review pending.
                python3 "$ROOT/scripts/lib/audit-findings.py" FINAL_AUDIT.md "$STATE_DIR" || exit 1
                [[ "$(hash_file FINAL_AUDIT.md)" == "$audit_hash" ]] || exit 1
                cp "$VERDICT_FILE" "$STATE_DIR/audit-verdict.original"
                printf '%s\t%s\n' "READY" "$audit_hash" > "$VERDICT_FILE"
                if [[ -f "$AUDIT_OVERRIDE_FILE" ]]; then
                    mv "$AUDIT_OVERRIDE_FILE" "$AUDIT_OVERRIDE_FILE.previous"
                fi
                set_state COMPLETE
                continue
            fi

            echo
            echo "=================================================="
            echo "FINAL AUDIT: $audit_class"
            echo "=================================================="
            echo

            if [[ "$audit_class" == "NOT_READY" ]]; then
                echo "The independent auditor says this build is not ready."
            else
                echo "FINAL_AUDIT.md does not end in one of the three verdict"
                echo "phrases, so the auditor's conclusion could not be read."
                echo "An unreadable verdict is not a pass."
            fi

            echo
            echo "This run does not finish on that by itself. Either fix what"
            echo "the audit found and re-run the implementation stage:"
            echo
            echo "  printf '%s\\n' IMPLEMENT > $STATE_FILE"
            echo "  ./scripts/stagegate.sh"
            echo
            echo "or record an explicit decision to finish anyway. An override"
            echo "is written to $AUDIT_OVERRIDE_FILE and reported at COMPLETE."

            review_and_approve FINAL_AUDIT.md FINAL_AUDIT_OVERRIDE override

            printf '%s\t%s\t%s\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
                "$audit_class" \
                "$(hash_file FINAL_AUDIT.md)" \
                > "$AUDIT_OVERRIDE_FILE"

            set_state COMPLETE
            ;;

        COMPLETE)
            echo
            echo "Workflow complete."
            if [[ -s "$VERDICT_FILE" ]]; then
                echo "Build verdict: $(awk -F'\t' 'NR == 1 {print $1}' "$VERDICT_FILE")"
            fi
            echo
            echo "Artifacts:"
            echo "  REQUIREMENTS_INTERPRETATION.md"
            echo "  PROJECT_PLAN.md"
            echo "  ADVERSARIAL_REVIEW.md"
            echo "  UPDATED_PROJECT_PLAN.md"
            echo "  IMPLEMENTATION_NOTES.md"
            echo "  AUTOMATED_TEST_REPORT.md"
            echo "  MANUAL_CHECKLIST.md"
            echo "  VERIFICATION_REPORT.md"
            echo "  FINAL_AUDIT.md"
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

            exit 0
            ;;

        *)
            echo "Unknown workflow state: $state"
            exit 1
            ;;
    esac
done

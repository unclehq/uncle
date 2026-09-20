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
export DOCUMENT_BUDGET_SOURCE=CHANGE_REQUEST.md

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
# The PR attestation reads these rather than guessing from the cwd.
export UNCLE_VERSION="$STAGEGATE_VERSION"
export UNCLE_LIB_DIR="$ROOT/scripts/lib"

usage() {
    cat <<'EOF'
Usage: change-workflow.sh [-h|--help] [--version] [--unattended]

Run the human-gated existing-code change workflow from CHANGE_REQUEST.md. The
driver is a resumable state machine; re-run it to continue from the current
stage.

--unattended runs with nobody at the terminal: every gate that would wait for
a person is auto-approved and recorded, and the run reports how many judgments
no one made. A regressed check or a failing audit still stops the run; those
wait on a result, not on a person.

Takes no positional arguments; all configuration is via WORKFLOW_* environment
variables (see scripts/README.md). Seed CHANGE_REQUEST.md from a GitHub issue
with ./scripts/from-issue.sh.
EOF
}

# Opt-in only, never inferred from a missing terminal: a piped run is still a
# run someone is watching, and only the flag says otherwise.
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

# Serialize both workflow families before mutable initialization.
if [[ "${UNCLE_DRIVER_SUPERVISED:-}" != 1 ]] || ! python3 "$ROOT/scripts/lib/plan-executability.py" lock-child "$$" "$PPID" 2>/dev/null; then
    driver_args=(bash "${BASH_SOURCE[0]}")
    [[ "$UNATTENDED" != 1 ]] || driver_args+=(--unattended)
    exec python3 "$ROOT/scripts/lib/plan-executability.py" lock-run "${driver_args[@]}"
fi
python3 "$ROOT/scripts/lib/workflow_family.py" change
unset UNCLE_NEW_WORKFLOW
. "$ROOT/scripts/lib/project-git.sh"
uncle_ensure_project_git || exit 1
. "$ROOT/scripts/lib/plan-recovery.sh"

STATE_DIR=".uncle/workflow"
export UNCLE_RUNNER_POOL_OWNER_PID="${UNCLE_RUNNER_POOL_OWNER_PID:-$$}"
APPROVAL_DIR="$STATE_DIR/approvals"
# Every gate an unattended run passed without a person, dated. The whole cost
# of the flag in one file.
UNATTENDED_FILE="$STATE_DIR/unattended-gates"

record_unattended_gate() {
    local what="$1" detail="$2"
    mkdir -p "$STATE_DIR" 2>/dev/null || true
    printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$what" "$detail" \
        >> "$UNATTENDED_FILE" 2>/dev/null || true
}
LOG_DIR="$STATE_DIR/logs"
STATE_FILE="$STATE_DIR/state"
SESSION_FILE="$STATE_DIR/session-head"
LEDGER_FILE="$STATE_DIR/cost.tsv"
LOCK_DIR="$STATE_DIR/lock"
ORIGIN_FILE="$STATE_DIR/origin"
VERDICT_FILE="$STATE_DIR/audit-verdict"
MARKER_FILE="$STATE_DIR/issue-closed"

# Post-implementation gate: the generated document the operator reads, and the
# diff it is built from.
REVIEW_FILE="$STATE_DIR/IMPLEMENTATION_REVIEW.md"
DIFF_FILE="$STATE_DIR/change.diff"

# Green check: the approved command list, the statuses from before and after
# the change, their classification, and the table shown at the gate.
GREEN_CMDS="$STATE_DIR/green-check.commands"
GREEN_BASE="$STATE_DIR/green-check.baseline.tsv"
GREEN_CUR="$STATE_DIR/green-check.current.tsv"
GREEN_CLASS="$STATE_DIR/green-check.tsv"
GREEN_MD="$STATE_DIR/green-check.md"
GREEN_SOURCE="$STATE_DIR/green-check.source"

# Records of a human choosing to finish over a failing check.
GREEN_OVERRIDE_FILE="$STATE_DIR/green-check-override"
AUDIT_OVERRIDE_FILE="$STATE_DIR/audit-override"

# Untracked paths that existed before implementation started. Read by
# change_diff_files, so both the scope check and the review diff ignore work
# that was already in the checkout.
UNTRACKED_BASELINE="$STATE_DIR/untracked-before.txt"
WORKFLOW_UNTRACKED_BASELINE="$UNTRACKED_BASELINE"

mkdir -p "$APPROVAL_DIR" "$LOG_DIR"

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# Stage models. Opus is reserved for the two stages where a wrong answer is
# expensive to undo: the plan everything else hangs off, and the implementation
# itself. The stages that were on Sonnet now run on kimi, which is cheaper
# again: BASELINE and EXECUTE_CHECKLIST carry the largest contexts in the
# pipeline (whole-repo reads, full test output) and are mostly read-and-record
# work, and CHANGE_SPEC/UPDATED_PLAN transcribe decisions already made.
#
# `kimi` routes through scripts/agent-kimi.sh; `kimi:<alias>` picks a specific
# model from ~/.kimi-code/config.toml. Set any of these back to `sonnet` to
# return that one stage to Claude.
# Each is keyed by the stage's log name first, because that is what `uncle`
# writes and what stagegate.sh already uses; the older key stays as a fallback
# so an existing environment keeps working. A variable that is *set and empty*
# means "pass no model": claude, kimi, and codex have their own defaults, and
# only cline needs to be told which model to run.
MODEL_CHANGE_PLAN="${WORKFLOW_MODEL_CHANGE_PLAN-opus}"
MODEL_BASELINE="${WORKFLOW_MODEL_BASELINE-${MODEL_CHANGE_PLAN}}"
MODEL_CHANGE_SPEC="${WORKFLOW_MODEL_CHANGE_SPEC-kimi}"
MODEL_UPDATED_PLAN="${WORKFLOW_MODEL_UPDATED_CHANGE_PLAN-${WORKFLOW_MODEL_UPDATED_PLAN-kimi}}"
MODEL_IMPLEMENT="${WORKFLOW_MODEL_IMPLEMENTATION-${WORKFLOW_MODEL_IMPLEMENT-opus}}"
MODEL_EXECUTE="${WORKFLOW_MODEL_EXECUTE_CHECKLIST-${WORKFLOW_MODEL_EXECUTE-kimi}}"

EFFORT_CHANGE_SPEC="${WORKFLOW_EFFORT_CHANGE_SPEC:-medium}"
EFFORT_UPDATED_PLAN="${WORKFLOW_EFFORT_UPDATED_CHANGE_PLAN:-${WORKFLOW_EFFORT_UPDATED_PLAN:-medium}}"
EFFORT_EXECUTE="${WORKFLOW_EFFORT_EXECUTE_CHECKLIST:-${WORKFLOW_EFFORT_EXECUTE:-medium}}"

# Per-stage stop-loss, in dollars. This is a runaway guard, not a target: the
# cap is checked between turns, so a stage stops shortly after crossing it
# rather than being preempted mid-turn. Raise a cap rather than lowering the
# work if a legitimate stage trips it.
BUDGET_BASELINE="${WORKFLOW_BUDGET_BASELINE:-10}"
BUDGET_CHANGE_SPEC="${WORKFLOW_BUDGET_CHANGE_SPEC:-5}"
BUDGET_CHANGE_PLAN="${WORKFLOW_BUDGET_CHANGE_PLAN:-12}"
BUDGET_UPDATED_PLAN="${WORKFLOW_BUDGET_UPDATED_PLAN:-5}"
BUDGET_IMPLEMENT="${WORKFLOW_BUDGET_IMPLEMENT:-40}"
BUDGET_EXECUTE="${WORKFLOW_BUDGET_EXECUTE:-20}"

# Codex reasoning effort. The two judgement stages think; the two checklist
# stages transcribe an approved specification into checks.
CODEX_EFFORT_REVIEW="${WORKFLOW_CODEX_EFFORT_REVIEW:-high}"
CODEX_EFFORT_CHECKLIST="${WORKFLOW_CODEX_EFFORT_CHECKLIST:-low}"
CODEX_EFFORT_AUDIT="${WORKFLOW_CODEX_EFFORT_AUDIT:-high}"

# Carry one forked conversation across the Claude stages. Off by default:
# a forked stage inherits the entire transcript that produced the upstream
# artifacts and re-sends it on every turn, so cost grows with the pipeline.
# The artifacts on disk are a compressed form of that same context. Set to 1
# to trade the money back for latency.
SESSION_REUSE="${WORKFLOW_SESSION_REUSE:-0}"

# Run implementation as one invocation per step of CHANGE_PLAN.md's
# implementation sequence, each with a fresh context, instead of one long run.
#
# Nothing is evicted from a context, so cost is turns x context and the last
# turns of a 200-turn run are the most expensive tokens in the pipeline.
# Splitting resets the accumulated tool output at each step; the plan and the
# spec are re-read per step, so the fixed part is paid N times while the
# growing part is paid once per step instead of once per run.
#
# Auto mode uses the approved plan's own sequence only when it is detailed
# enough to provide safe handoff boundaries. Small changes keep one context;
# larger changes stop carrying every tool result through the entire stage.
# Set 0 to force one context or 1 to force one invocation per plan step.
STEPWISE_IMPLEMENT="${WORKFLOW_STEPWISE_IMPLEMENT:-auto}"

stepwise_implementation_enabled() {
    case "$STEPWISE_IMPLEMENT" in
        1|true|yes|on) return 0 ;;
        0|false|no|off) return 1 ;;
        auto)
            local count
            count="$(plan_steps CHANGE_PLAN.md 2>/dev/null | grep -c . || true)"
            [[ "${count:-0}" -ge 8 ]]
            ;;
        *)
            echo "Invalid WORKFLOW_STEPWISE_IMPLEMENT: $STEPWISE_IMPLEMENT (expected auto, 0, or 1)" >&2
            return 1
            ;;
    esac
}

# Write the Codex verification checklist concurrently with implementation.
# Set to 0 to fall back to the serial single-shot checklist stage.
PARALLEL_CHECKLIST="${WORKFLOW_PARALLEL_CHECKLIST:-1}"

# Independent checklist rows fan out through per-run temporary handoffs. The
# normal execution stage remains the only canonical report writer. Set to 0
# only to opt out of agent fan-out.
PARALLEL_CHECKLIST_WORKERS="${WORKFLOW_PARALLEL_CHECKLIST_WORKERS:-1}"

# Stop after implementation and show the operator the actual diff, the green
# check, and the agent's own notes, before anything downstream reads them.
#
# Every other gate in this pipeline is a gate on prose. Without this one the
# person who approved the plan never sees the code that plan produced: the
# implementation, the checklist, the verification report, and the audit all run
# unattended between the plan gate and COMPLETE.
#
# Set to 0 only when something else reviews the diff — a pull request, a
# reviewer, a second pair of eyes. The driver then refuses to continue past a
# green-check regression, because no human gate is left to weigh it.
DIFF_GATE="${WORKFLOW_DIFF_GATE:-1}"

# Re-run the project's own verification commands from the driver, once before
# implementation and once after, and compare.
#
# CHANGE_TEST_REPORT.md is the implementing agent's account of checks the
# implementing agent ran. Everything downstream reads that account instead of
# the checks. This runs them with no agent in the path.
#
# Set to 0 to return to trusting the report.
GREEN_CHECK="${WORKFLOW_GREEN_CHECK:-1}"

# Refuse to reach COMPLETE on an audit that did not say the change is ready.
#
# The verdict was already classified and recorded; it just did not gate
# anything, so a NOT READY audit and an unreadable one both finished the run
# looking like a success. Finishing anyway now takes an explicit, recorded
# human override, and never closes the originating issue.
#
# Set to 0 to restore the old behavior: classify, print, and complete.
AUDIT_GATE="${WORKFLOW_AUDIT_GATE:-1}"

# Agent/reviewer CLI commands. Defaults are `claude` and `codex`. Swap either
# for a compatible CLI or a wrapper script. The agent CLI must accept the same
# flags as `claude -p` (model, effort, max-turns, output-format stream-json,
# allowedTools, stdin prompt). The reviewer CLI must accept the same flags as
# `codex exec` (ephemeral, sandbox read-only, model, output-last-message).
AGENT_CMD="${WORKFLOW_AGENT_CMD:-$ROOT/scripts/agent-kimi.sh}"

# Which CLI runs one stage, and that stage's own reasoning effort. `uncle`
# exports one variable per stage so a run can put different runners on
# different stages; the global command stays the fallback for a driver invoked
# without the launcher.
stage_var() {
    printf 'WORKFLOW_%s_%s' "$1" \
        "$(printf '%s' "$2" | tr '[:lower:]' '[:upper:]' | tr -c 'A-Z0-9' '_')"
}

# Precedence, for every per-stage setting: an explicit WORKFLOW_* variable
# wins, then the project's .uncle/config, then what the call site asked for.
# The config file is read at the moment the stage starts, so an edit made at a
# human gate applies to the stages after it.
# An explicit variable always wins over the config file; the built-in default
# applies only when the project has no config at all.
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

stage_command_overridden() {
    local side="$1" stage="$2" var global
    var="WORKFLOW_${side}_CMD_$(printf '%s' "$stage" | tr '[:lower:]-.' '[:upper:]__')"
    global="WORKFLOW_${side}_CMD"
    [[ -n "${!var:-}" || -n "${!global:-}" ]]
}

stage_effort_for() {
    uncle_effective_stage_effort "$1"
}

stage_model_for() {
    local var fallback="$2"
    if uncle_has_config || [[ -n "${UNCLE_RESOLVED_RUNNER:-}" ]]; then
        fallback="$(uncle_stage_model "$1" "${UNCLE_RESOLVED_RUNNER-$(uncle_stage_runner "$1")}")"
    fi
    if ! uncle_has_config; then
        case "$1" in
            updated-change-plan) fallback="${WORKFLOW_MODEL_UPDATED_PLAN-$fallback}" ;;
            implementation) fallback="${WORKFLOW_MODEL_IMPLEMENT-$fallback}" ;;
            execute-checklist) fallback="${WORKFLOW_MODEL_EXECUTE-$fallback}" ;;
        esac
        if [[ "$(uncle_stage_side "$1")" == reviewer ]]; then
            fallback="${CODEX_MODEL-$fallback}"
        fi
    fi
    var="$(stage_var MODEL "$1")"
    eval "printf '%s' \"\${$var-$fallback}\""
}
REVIEWER_CMD="${WORKFLOW_REVIEWER_CMD:-codex}"

# Close the originating GitHub issue on reaching COMPLETE with a READY verdict.
# Set to 0 for an immediate, no-deploy kill switch: behavior reverts to closing
# only from from-issue.sh's post-run check.
CLOSE_ISSUE="${WORKFLOW_CLOSE_ISSUE:-1}"

# `$AGENT_CMD -p` is non-interactive, so a normal permission prompt can never be
# answered. Explicitly grant the tools needed by the analysis, writing, build,
# and verification stages. This is an allowlist, not a permission bypass.
CLAUDE_TOOLS="Read,Glob,Grep,Write,Edit,TodoWrite,Bash"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

. "$ROOT/scripts/lib/sha256.sh"

# One bold prompt line. `read -p` suppresses its prompt when stdin is not a
# terminal, so the text is printed separately. Escapes are emitted only for a
# real terminal: piped captures and TERM=dumb stay free of control bytes.
gate_prompt() {
    if declare -f supervision_gate_open > /dev/null; then supervision_gate_open "$1"; fi
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
    case "$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')" in
        APPROVE|ACKNOWLEDGE)
            echo "This gate now requires 'y' to approve."
            ;;
    esac
}

# Pure FINAL_AUDIT.md verdict classifier, shared with scripts/tests/. Sourced
# self-relative so the driver still runs from any CWD.
. "$ROOT/scripts/lib/audit-verdict.sh"

# .uncle/workflow/state grammar, and the shared INV-3 close gate.
. "$ROOT/scripts/lib/state.sh"
. "$ROOT/scripts/lib/plan-scope.sh"
. "$ROOT/scripts/lib/progress.sh"
. "$ROOT/scripts/lib/issue-close.sh"
. "$ROOT/scripts/lib/change-pr.sh"

# The independent verification run, and the generated document the
# post-implementation gate shows.
. "$ROOT/scripts/lib/green-check.sh"
. "$ROOT/scripts/lib/implementation-review.sh"
. "$ROOT/scripts/lib/gates.sh"
. "$ROOT/scripts/lib/waivers.sh"
. "$ROOT/scripts/lib/checklist-capability.sh"
. "$ROOT/scripts/lib/performance.sh"
. "$ROOT/scripts/lib/stage-config.sh"
. "$ROOT/scripts/lib/parallel-implement.sh"
. "$ROOT/scripts/lib/triage.sh"

# The implementation stage can end with acceptance rows the agent could not
# deliver. Exiting there is right when someone is about to go fix it, and wrong
# when nobody is: the run stops, the issue stays open, and the operator is left
# to work out which files to edit and how to resume. Offer the decision instead.
#
# Retry and stop are the honest answers. Waive is the third, for a row no
# further attempt can deliver -- and it never becomes a pass: the rejected rows
# stay in implementation-completion.txt, the waiver records who accepted what,
# and the final audit reads both.
implementation_incomplete_choice() {
    local completion="$STATE_DIR/implementation-completion.txt" ids="" answer
    echo
    echo "The implementation did not deliver every acceptance row."
    if [[ -s "$completion" ]]; then
        echo "Rejected rows:"
        sed 's/^/  /' "$completion"
        # Format errors cannot be waived as acceptance rows.
        if ! grep -qvE '^AC-[0-9]+: requires IMPLEMENTED,' "$completion"; then
            ids="$(awk -F: '{ printf "%s ", $1 }' "$completion")"
        fi
    fi
    echo
    while true; do
        UNCLE_GATE_CLASS="sensitive:waiver"
        gate_prompt "Retry the implementation, waive the rows above, or stop? [retry/waive/stop]: "
        UNCLE_GATE_CLASS=""
        if ! { if declare -f gate_read > /dev/null; then gate_read answer; else IFS= read -r answer; fi; }; then
            echo
            echo "No answer; the run remains pending at IMPLEMENT."
            return 1
        fi
        case "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')" in
            r|retry)
                # Clearing the digest is what lets the repair path run again for
                # this plan; without it the next pass repeats the same refusal.
                rm -f "$STATE_DIR/implementation-completion-repair"
                if plan_executability_enabled; then plan_tool retry; fi
                echo "Retrying implementation."
                return 0
                ;;
            w|waive)
                if [[ -z "${ids// /}" ]]; then
                    echo "No row ids to waive; edit the plan or retry instead."
                    continue
                fi
                # shellcheck disable=SC2086
                if record_waiver "$completion" $ids; then
                    echo "Waived. The rows stay rejected on the record; the audit still reads them."
                    return 2
                fi
                ;;
            s|stop|'')
                echo "Run remains pending at IMPLEMENT."
                return 1
                ;;
            *) echo "Answer retry, waive, or stop." ;;
        esac
    done
}


require_file() {
    if [[ ! -s "$1" ]]; then
        supervision_validation_failed require_file "$1" "Required file missing or empty: $1"
        echo "Required file missing or empty: $1"
        exit 1
    fi
}

# The issue number written into .uncle/workflow/state is informational only;
# .uncle/workflow/origin stays the sole identity source (INV-1).
current_issue() {
    if [[ -n "${STAGEGATE_ORIGIN_ISSUE:-}" ]]; then
        printf '%s' "$STAGEGATE_ORIGIN_ISSUE"
    else
        origin_field "$ORIGIN_FILE" 2
    fi
}

. "$ROOT/scripts/lib/terminal-title.sh"

# One EXIT hook for the whole run. The cleanup list used to be re-declared at
# each trap site and one of them dropped the lock release; every site now
# names this function. The exit status is read first and handed to the triage
# hook, which writes the failure bundle for anything that is not a decline,
# a cancel, or a stop a person chose.
on_exit() {
    local rc=$?
    if declare -f progress_end > /dev/null; then progress_end; fi
    if declare -f cleanup_bg > /dev/null; then cleanup_bg; fi
    if declare -f release_lock > /dev/null; then release_lock; fi
    uncle_title_end
    triage_on_exit "$rc"
}
trap on_exit EXIT
trap 'uncle_cancel 130' INT
trap 'uncle_cancel 143' TERM
if [[ -n "${STAGEGATE_ORIGIN_REPO:-$(origin_field "$ORIGIN_FILE" 1)}" ]]; then
    uncle_title_begin "$(current_issue)"
fi

set_state() {
    state_write "$STATE_FILE" "$1" "$(current_issue)"
}

get_state() {
    state_read "$STATE_FILE" DERIVE_BRIEF
}

# --- Single-writer lock -----------------------------------------------------
# One run owns a checkout's .uncle/workflow/ for its whole lifetime. mkdir is atomic,
# so it is the lock primitive; the pid file only exists to detect a lock left
# behind by a killed run.

LOCK_HELD=0

release_lock() {
    if [[ "$LOCK_HELD" == "1" ]]; then
        LOCK_HELD=0
        rm -rf "$LOCK_DIR"
    fi
}

acquire_lock() {
    local attempt holder
    for attempt in 1 2; do
        if mkdir "$LOCK_DIR" 2>/dev/null; then
            printf '%s\n' "$$" > "$LOCK_DIR/pid"
            LOCK_HELD=1
            trap on_exit EXIT
            return 0
        fi

        holder=""
        if [[ -s "$LOCK_DIR/pid" ]]; then
            holder="$(cat "$LOCK_DIR/pid")"
        fi

        if [[ -n "$holder" ]] && kill -0 "$holder" 2>/dev/null; then
            echo "Refusing to start: another change-workflow.sh run (pid $holder) holds this checkout."
            echo "Wait for it to finish, or remove $LOCK_DIR if that process is gone."
            exit 1
        fi

        echo "Clearing stale lock $LOCK_DIR (pid ${holder:-unknown} is not running)."
        rm -rf "$LOCK_DIR"
    done

    echo "Refusing to start: could not acquire $LOCK_DIR."
    exit 1
}

# --- Origin binding ---------------------------------------------------------
# .uncle/workflow/origin binds in-flight state to one (repo, issue) so a resumed run
# cannot act on — or later close — a different issue's work. Enforced only when
# the driver was launched by from-issue.sh, which exports STAGEGATE_ORIGIN_*; a
# human running the driver by hand is unaffected.

origin_preflight() {
    local repo="${STAGEGATE_ORIGIN_REPO:-}"
    local issue="${STAGEGATE_ORIGIN_ISSUE:-}"
    local state owner

    # Corruption check first: a state file bound to one issue next to an origin
    # naming another is not resolvable in either file's favour, and the check
    # does not depend on this invocation being origin-bound.
    state_origin_agree "$STATE_FILE" "$ORIGIN_FILE" || exit 1

    if [[ -z "$repo" || -z "$issue" ]]; then
        return 0
    fi

    state="$(get_state)"

    # A COMPLETE state belonging to a different issue is the previous run's
    # residue. Leaving it in place would send this invocation straight to the
    # COMPLETE branch, which prints "Change workflow complete" and offers to
    # close an issue whose work never started. Rebind to this issue at ANALYZE
    # and drop the finished run's per-run records so nothing carries over.
    # An unprefixed COMPLETE was written by an older driver and cannot be shown
    # to belong to a different issue, so it is left alone — the same rule
    # state_origin_agree applies to a missing prefix.
    local finished_issue
    finished_issue="$(state_issue "$STATE_FILE")"
    if [[ "$state" == "COMPLETE" && -n "$finished_issue" && "$finished_issue" != "$issue" ]]; then
        echo "Previous run for issue $finished_issue is COMPLETE;" \
             "starting $repo#$issue."
        rm -f "$VERDICT_FILE" "$MARKER_FILE" "$SESSION_FILE" \
              "$GREEN_OVERRIDE_FILE" "$AUDIT_OVERRIDE_FILE" \
              "$GREEN_BASE" "$GREEN_CUR" "$GREEN_CLASS" "$GREEN_SOURCE" \
              "$GREEN_MD" "$GREEN_CMDS" "$UNTRACKED_BASELINE"
        rm -f "$APPROVAL_DIR/IMPLEMENTATION_REVIEW.sha256" \
              "$APPROVAL_DIR/FINAL_AUDIT_OVERRIDE.sha256"
        state_write "$STATE_FILE" ANALYZE "$issue"
        return 0
    fi

    if [[ ! -s "$STATE_FILE" || "$state" == "COMPLETE" ]]; then
        return 0
    fi

    if [[ ! -s "$ORIGIN_FILE" ]]; then
        echo "Refusing to resume: state is '$state' but $ORIGIN_FILE does not exist,"
        echo "so that state cannot be proven to belong to $repo#$issue."
        exit 1
    fi

    owner="$(head -n 1 "$ORIGIN_FILE")"
    if [[ "$(origin_field "$ORIGIN_FILE" 1)" != "$repo" \
        || "$(origin_field "$ORIGIN_FILE" 2)" != "$issue" ]]; then
        echo "Refusing to resume: this checkout is mid-run (state '$state') for another issue."
        echo "  $ORIGIN_FILE owner: $owner"
        echo "  this invocation:    $(printf '%s\t%s' "$repo" "$issue")"
        exit 1
    fi
}

write_origin() {
    local repo="${STAGEGATE_ORIGIN_REPO:-}" issue="${STAGEGATE_ORIGIN_ISSUE:-}"
    local fetch=""

    if [[ -z "$repo" || -z "$issue" ]]; then
        return 0
    fi

    # The driver never fetches an issue, so it can never originate a `gh`
    # provenance claim. It only carries forward the one from-issue.sh recorded
    # for this same binding; anything else is left absent, which reads as
    # `curl` and fails closed at the close gate.
    if [[ "$(origin_field "$ORIGIN_FILE" 1)" == "$repo" \
        && "$(origin_field "$ORIGIN_FILE" 2)" == "$issue" ]]; then
        fetch="$(origin_field "$ORIGIN_FILE" 3)"
    fi

    if [[ -n "$fetch" ]]; then
        printf '%s\t%s\t%s\n' "$repo" "$issue" "$fetch" > "$ORIGIN_FILE"
    else
        printf '%s\t%s\n' "$repo" "$issue" > "$ORIGIN_FILE"
    fi
}

# stage, seconds, usd, input, output, cache_read, cache_write
record_cost() {
    if [[ ! -s "$LEDGER_FILE" ]]; then
        printf 'stage\tsecs\tusd\tin\tout\tcache_r\tcache_w\n' > "$LEDGER_FILE"
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$@" >> "$LEDGER_FILE"
}

ledger_total() {
    if [[ -s "$LEDGER_FILE" ]]; then
        awk -F'\t' 'NR>1 && $3 != "-" {t += $3} END {printf "%.2f", t}' "$LEDGER_FILE"
    else
        printf '0.00'
    fi
}

show_spend() {
    echo "  Reported stage cost so far (partial): \$$(ledger_total); estimates: uncle --performance"
}

verify_approval() {
    local file="$1"
    local approval_name="$2"
    local approval="$APPROVAL_DIR/${approval_name}.sha256"

    require_file "$file"
    if [[ ! -s "$approval" ]]; then
        # State that presupposes an approval nobody recorded: send the run to
        # the gate rather than stopping on a file the operator never heard of.
        echo "$file has no approval on record."
        echo "Review and approve it."
        triage_reopen_gate "$approval_name"
        require_file "$approval"
    fi

    local expected
    local actual

    expected="$(cat "$approval")"
    actual="$(hash_file "$file")"

    if [[ "$expected" != "$actual" ]]; then
        echo "$file changed after approval."
        echo "Review and approve the new contents."
        triage_reopen_gate "$approval_name"
        exit 1
    fi
}

# --- Envelopes (Issue 59) ----------------------------------------------------
#
# Every claim about a stage is written here, by the driver, from validator
# exit codes, gate records and its own hashing. scripts/lib/envelope.py owns
# the format; these wrappers keep each call site to one line.
envelope_py() {
    python3 "$ROOT/scripts/lib/envelope.py" "$@"
}

envelope_write() {
    envelope_py write --state "$STATE_DIR" "$@" || exit 1
}

envelope_invalidate() {
    envelope_py invalidate --state "$STATE_DIR" "$@" || exit 1
}

# The artifact digest: working files minus the workflow's own state and
# documents (change-pr.sh `artifact`). Empty without a Git HEAD.
change_artifact() {
    local out
    if git rev-parse --verify HEAD >/dev/null 2>&1; then
        if out="$(change_pr_engine artifact 2>/dev/null)"; then
            printf '%s' "$out"
        fi
    fi
}

# The green check's own numbers, in the row format the PR block has always used.
green_summary() {
    awk -F'\t' '
        NF && $1 != "" { total++ }
        $1 == "PASS" || $1 == "FIXED" { pass++ }
        $1 == "PREEXISTING" { pre++ }
        $1 == "REGRESSION" { reg++ }
        END { printf "%d commands: %d pass, %d pre-existing, %d regressed", total + 0, pass + 0, pre + 0, reg + 0 }
    ' "$GREEN_CLASS"
}

write_verification_envelope() {
    local result reason artifact
    artifact="$(change_artifact)"
    if [[ "$GREEN_CHECK" != "1" ]]; then
        result=unavailable
        reason='WORKFLOW_GREEN_CHECK=0: the driver did not re-run the checks'
    elif [[ ! -s "$GREEN_CLASS" ]]; then
        result=unavailable
        reason='no green-check results'
    elif [[ "$(green_regressions "$GREEN_CLASS")" -gt 0 ]]; then
        result=fail
        reason="$(green_summary)"
    else
        result=pass
        reason="$(green_summary)"
    fi
    envelope_write --stage verification --result "$result" --reason "$reason" \
        ${artifact:+--input "artifact=$artifact"} \
        --evidence "$STATE_DIR/green-check.tsv" CHANGE_TEST_REPORT.md
}

write_implementation_envelope() {
    local result="$1" reason="${2:-}" artifact
    artifact="$(change_artifact)"
    envelope_write --stage implementation --result "$result" ${reason:+--reason "$reason"} \
        ${artifact:+--artifact "$artifact"} --approval IMPLEMENTATION_REVIEW \
        --evidence IMPLEMENTATION_NOTES.md CHANGE_TEST_REPORT.md "$REVIEW_FILE" \
        --producer-stage implementation --producer-kind agent
}

write_review_envelope() {
    local input=()
    [[ -f CHANGE_PLAN.md ]] && input=(--input "plan=$(hash_file CHANGE_PLAN.md)")
    envelope_write --stage review --result pass --evidence ADVERSARIAL_REVIEW.md \
        --findings ADVERSARIAL_REVIEW.md ${input[@]+"${input[@]}"} \
        --producer-stage adversarial-review --producer-kind reviewer
}

# Around each implementation agent run: envelopes are driver-owned, so a
# write there by the agent is reverted from the snapshot, logged, and ends
# the run.
envelope_guard_begin() {
    envelope_py snapshot --state "$STATE_DIR" || exit 1
}

envelope_guard_end() {
    envelope_py restore --state "$STATE_DIR" || exit 1
}

# An approved document that changed -- by hand, or by a triage action the
# operator selected -- sends the run back to the gate that approved it, so
# the new bytes are read and approved by a keystroke. Nothing is written
# under approvals/ here; the stale digest stays until the operator answers.
# A document with no gate of its own keeps the plain exit 1 above.
triage_reopen_gate() {
    local gate=""
    case "$1" in
        CHANGE_PLAN)
            gate=WAIT_PLAN_APPROVAL
            case "$(cat "$STATE_DIR/approval-route" 2>/dev/null || true)" in
                WAIT_UPDATED_PLAN_APPROVAL) gate=WAIT_UPDATED_PLAN_APPROVAL ;;
            esac
            ;;
        ADVERSARIAL_REVIEW) gate=WAIT_PLAN_APPROVAL ;;
        CHANGE_SPEC|BASELINE_REPORT) gate=WAIT_ANALYSIS_APPROVAL ;;
    esac
    [[ -n "$gate" ]] || return 0
    # Every claim downstream of the changed document is withdrawn with it.
    envelope_invalidate "$1"
    set_state "$gate"
    echo "Reopening $gate: re-run the driver to review and approve what is there now."
    exit 0
}

# One gate can cover several documents. Each document is still hashed and
# approved individually; batching only removes the round-trip of stopping the
# pipeline twice for two documents that are read together anyway.
#
# Usage: human_gate ACTION file1 approval_name1 [file2 approval_name2 ...]
human_gate() {
    local gate_start="$SECONDS"
    local action="$1"
    shift

    local -a files=()
    local -a names=()
    local gate_by

    while [[ "$#" -gt 0 ]]; do
        require_file "$1"
        files+=("$1")
        names+=("$2")
        shift 2
    done

    # Unattended: record each approval against the bytes on disk and log that
    # nobody read them. The digests must still be real -- later stages compare
    # against them to catch a document changing underneath an approval.
    if [[ "${UNATTENDED:-0}" == 1 ]]; then
        local j act
        act="$(printf '%s' "$action" | tr '[:upper:]' '[:lower:]')"
        for j in "${!files[@]}"; do
            printf '%s\n' "$(hash_file "${files[$j]}")" > "$APPROVAL_DIR/${names[$j]}.sha256"
            gate_by="$(if declare -f supervision_approved_by > /dev/null; then supervision_approved_by; elif [[ "${UNATTENDED:-0}" == 1 ]]; then printf unattended; else printf '%s' "${UNCLE_APPROVAL_NAME:-}"; fi)"
            # A human name goes to `.approved-by`; `unattended` and supervisor
            # receipts go to `.delegated-by` with `.approved-by` left empty, so
            # nothing downstream reads a delegated answer as a keystroke.
            # `.gate-action` records what the gate asked for (Issue 59).
            case "$gate_by" in
                unattended|supervisor:*)
                    printf '%s\n' "$gate_by" > "$APPROVAL_DIR/${names[$j]}.delegated-by"
                    printf '\n' > "$APPROVAL_DIR/${names[$j]}.approved-by"
                    ;;
                *)
                    printf '%s\n' "$gate_by" > "$APPROVAL_DIR/${names[$j]}.approved-by"
                    printf '\n' > "$APPROVAL_DIR/${names[$j]}.delegated-by"
                    ;;
            esac
            printf '%s\n' "$action" > "$APPROVAL_DIR/${names[$j]}.gate-action"
            record_unattended_gate "${names[$j]}" "$act ${files[$j]} without human review"
        done
        echo "Unattended: recorded $act of ${files[*]} with no human review."
        if declare -f perf_record > /dev/null; then perf_record approval "${names[*]}" "$((SECONDS-gate_start))" 0; fi
        return 0
    fi

    echo
    echo "=================================================="
    echo "HUMAN REVIEW REQUIRED"
    local f
    for f in "${files[@]}"; do
        echo "  $f"
    done
    echo "=================================================="
    echo
    echo "Review with:"
    echo "  less ${files[*]}"
    echo
    echo "Edit with:"
    echo "  code ${files[*]}"
    echo
    echo "Edits you make now are picked up by the next stage."
    show_spend
    echo

    # Digests are captured before the prompt and recorded afterwards, so each
    # approval attests to the bytes the operator was shown.
    local -a digests=()
    local i
    for i in "${!files[@]}"; do
        digests+=("$(hash_file "${files[$i]}")")
    done

    local verb targets response=""
    verb="$(printf '%s' "$action" | tr '[:upper:]' '[:lower:]')"
    targets="$(printf '%s, ' "${files[@]}")"
    targets="${targets%, }"

    echo
    UNCLE_GATE_FILE="${files[0]}"
    gate_prompt "Ready to $verb $targets? [Y/N] "
    UNCLE_GATE_FILE=""
    # IFS= keeps surrounding whitespace, so " y" is not an approval. `|| true`
    # keeps EOF from tripping `set -e` before the decline path runs. The
    # wrapper attributes the line (human, or a supervisor receipt) and closes
    # the gate; the answer itself is validated exactly as before.
    if declare -f gate_read > /dev/null; then gate_read response || true; else IFS= read -r response || true; fi

    case "$response" in
        y|Y) ;;
        *)
            if declare -f perf_record > /dev/null; then perf_record approval "${names[*]}" "$((SECONDS-gate_start))" 1; fi
            echo "Gate not accepted. Workflow remains paused."
            legacy_word_notice "$response"
            exit 0
            ;;
    esac

    # Every file is re-checked before any approval is written, so a mutated
    # document cannot leave a half-approved gate behind.
    for i in "${!files[@]}"; do
        if [[ "$(hash_file "${files[$i]}")" != "${digests[$i]}" ]]; then
            if declare -f perf_record > /dev/null; then perf_record approval "${names[*]}" "$((SECONDS-gate_start))" 1; fi
            echo "${files[$i]} changed after it was shown for approval."
            echo "Gate not accepted. Workflow remains paused."
            exit 0
        fi
    done

    for i in "${!files[@]}"; do
        printf '%s\n' "${digests[$i]}" > "$APPROVAL_DIR/${names[$i]}.sha256"
        gate_by="$(if declare -f supervision_approved_by > /dev/null; then supervision_approved_by; elif [[ "${UNATTENDED:-0}" == 1 ]]; then printf unattended; else printf '%s' "${UNCLE_APPROVAL_NAME:-}"; fi)"
        # A human name goes to `.approved-by`; `unattended` and supervisor
        # receipts go to `.delegated-by` with `.approved-by` left empty, so
        # nothing downstream reads a delegated answer as a keystroke.
        # `.gate-action` records what the gate asked for (Issue 59).
        case "$gate_by" in
            unattended|supervisor:*)
                printf '%s\n' "$gate_by" > "$APPROVAL_DIR/${names[$i]}.delegated-by"
                printf '\n' > "$APPROVAL_DIR/${names[$i]}.approved-by"
                ;;
            *)
                printf '%s\n' "$gate_by" > "$APPROVAL_DIR/${names[$i]}.approved-by"
                printf '\n' > "$APPROVAL_DIR/${names[$i]}.delegated-by"
                ;;
        esac
        printf '%s\n' "$action" > "$APPROVAL_DIR/${names[$i]}.gate-action"
        echo "Recorded approval for ${files[$i]}"
    done
    if declare -f perf_record > /dev/null; then perf_record approval "${names[*]}" "$((SECONDS-gate_start))" 0; fi
}

# Render Claude's streaming JSON event feed as readable progress. Startup
# warnings and other non-JSON lines are ignored rather than making jq fail.
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
              "\n[done] \($e.subtype) — \($e.num_turns) turns, \(if ($e.duration_ms | type) == "number" then (($e.duration_ms / 1000 | floor | tostring) + "s") else "time unknown" end), \(if $e.total_cost_usd == null then "cost unknown" else "$" + ($e.total_cost_usd | .*100 | round / 100 | tostring) end)\(if $e.error_detail then "\n  cause: \($e.error_detail)" else "" end)"
          else empty end
    '
}

# Compose the implementation prompt with the plan's own change-impact table
# resolved into a file list. The prompt already said "go straight to the files
# named in the frozen scope"; without this the agent had to find them, which
# meant reading the plan for navigation and re-exploring the repository when
# that was ambiguous. Printed into the prompt, the scope costs a few hundred
# tokens once instead of a search that is re-sent on every later turn.
compose_implementation_prompt() {
    local base out="$2"
    base="$(resolve_prompt "$1")"
    local files
    files="$(plan_scope_files CHANGE_PLAN.md)"

    cat "$base" > "$out"

    if [[ -z "$files" ]]; then
        echo "Warning: no change-impact table found in CHANGE_PLAN.md;" \
             "implementation runs without a resolved scope." >&2
        return 0
    fi

    {
        echo
        echo "## Frozen scope"
        echo
        echo "CHANGE_PLAN.md's change-impact table names these files. This list"
        echo "is generated from it, so it is the plan's own commitment, not a"
        echo "summary of it:"
        echo
        printf -- '- %s\n' $files
        echo
        echo "Open these directly. Do not search the repository for the change"
        echo "surface; it is above."
        echo
        echo "Changing a file outside this list is allowed but is a deviation:"
        echo "name the file and the reason in IMPLEMENTATION_NOTES.md. The"
        echo "driver checks the diff against this list and fails the stage on an"
        echo "unrecorded one."
    } >> "$out"
}

# Rule 9 of the implementation prompt requires every material deviation to be
# recorded. That was unenforced, so the change surface could grow silently: on
# issue #4 the diff touched app/config.py, app/records/models.py and a new
# migration, none of which the change-impact table named.
#
# Going outside the plan is legitimate — a review disposition routinely
# requires it. Doing so without writing it down is not.
check_scope_deviations() {
    local changed extra missing=""

    # The same file set the operator is shown at the implementation gate:
    # staged, unstaged, and files the agent created. `git diff` alone reports
    # only tracked changes, so a brand-new file — the largest kind of scope
    # creep there is — went unexamined.
    changed="$(change_diff_files)"
    [[ -n "$changed" ]] || return 0

    if [[ -z "$(plan_scope_files CHANGE_PLAN.md)" ]]; then
        echo
        echo "Warning: CHANGE_PLAN.md has no change-impact table, so the diff" \
             "could not be checked against a frozen scope."
        return 0
    fi

    extra="$(plan_out_of_scope CHANGE_PLAN.md $changed)"
    [[ -n "$extra" ]] || return 0

    local f
    while IFS= read -r f; do
        [[ -n "$f" ]] || continue
        if ! grep -qF "$f" IMPLEMENTATION_NOTES.md 2>/dev/null; then
            missing="$missing$f"$'\n'
        fi
    done <<< "$extra"

    echo
    echo "Files changed outside CHANGE_PLAN.md's change-impact table:"
    printf '%s\n' "$extra" | sed 's/^/  /'

    if [[ -n "$missing" ]]; then
        echo
        echo "Not recorded as deviations in IMPLEMENTATION_NOTES.md:"
        printf '%s' "$missing" | sed 's/^/  /'
        echo
        echo "Every file outside the frozen scope must be named there with its"
        echo "reason. Add them, or revert the unintended edits, then re-run."
        exit 1
    fi

    echo "  (all recorded in IMPLEMENTATION_NOTES.md)"
}

# --- Green check ------------------------------------------------------------
# The driver runs the project's checks itself, before and after the change.
#
# The command list is only ever taken from BASELINE_REPORT.md, and only after
# the operator has approved it at the ANALYZE gate: the driver executes these
# commands with its own privileges, so what it runs has to be something a human
# signed off on, not something an agent wrote and nobody read.

# Run the approved commands against the unmodified tree. Everything that is
# already failing here is this repository's problem, not this change's, and is
# not allowed to block the gate later.
capture_green_baseline() {
    if [[ "$GREEN_CHECK" != "1" ]]; then
        return 0
    fi

    # Recorded per BASELINE_REPORT.md digest: a resumed run must not re-run the
    # suite, and an edited baseline report must not silently keep the old one.
    if [[ -s "$GREEN_BASE" && -s "$GREEN_SOURCE" \
        && "$(cat "$GREEN_SOURCE")" == "$(hash_file BASELINE_REPORT.md)" ]]; then
        return 0
    fi

    verify_commands BASELINE_REPORT.md > "$GREEN_CMDS"

    if [[ ! -s "$GREEN_CMDS" ]]; then
        echo
        echo "Warning: BASELINE_REPORT.md has no fenced command block under its"
        echo "'build and test commands' section, so the driver cannot re-run"
        echo "this project's checks itself. The implementation stage's own"
        echo "report will be the only evidence that they passed, and the"
        echo "implementation gate will say so."
        rm -f "$GREEN_BASE" "$GREEN_SOURCE"
        return 0
    fi

    echo
    echo "Recording the green-check baseline before anything changes."
    echo "Commands from the BASELINE_REPORT.md you approved:"
    sed 's/^/  /' "$GREEN_CMDS"
    echo

    resolve_baseline_parallel_groups BASELINE_REPORT.md "$GREEN_CMDS" "$STATE_DIR/green-check.groups" || exit $?
    green_run "$GREEN_CMDS" "$GREEN_BASE" "$LOG_DIR/green-check-baseline.log" "" "$STATE_DIR/green-check.groups" || exit $?
    hash_file BASELINE_REPORT.md > "$GREEN_SOURCE"
}

# The baseline suite, run beside the planning stages instead of in front of them.
#
# capture_green_baseline executes the approved command list against the
# unmodified tree. On this repository that is about three minutes of test suite,
# and nothing reads its results until the green check compares them after
# implementation -- with change-plan, adversarial-review and updated-change-plan
# in between. Waiting for it before planning spends that time twice.
#
# Two properties it must keep. It still runs against the *unmodified* tree, so
# it is joined before IMPLEMENT, the first stage that writes code. And a failure
# still stops the run: the result is checked at the join, not discarded.
#
# WORKFLOW_BASELINE_BACKGROUND=0 restores the blocking behaviour.
BASELINE_BACKGROUND="${WORKFLOW_BASELINE_BACKGROUND:-1}"
BASELINE_BG_PID=""

start_green_baseline_bg() {
    if [[ "$BASELINE_BACKGROUND" != "1" || "$GREEN_CHECK" != "1" ]] \
       || [[ -z "$(verify_commands BASELINE_REPORT.md 2>/dev/null)" ]]; then
        # Nothing to run takes no time to run; with no command block the
        # warning is the whole result and belongs on screen now.
        capture_green_baseline
        return 0
    fi
    echo
    echo "Recording the green-check baseline in the background while planning runs."
    echo "Log: $LOG_DIR/green-check-baseline.log"
    ( capture_green_baseline ) > "$LOG_DIR/green-baseline.bg.log" 2>&1 < /dev/null &
    BASELINE_BG_PID=$!
}

# Joined before anything writes code. A failure here is fatal, exactly as it was
# when this ran in the foreground: without a baseline there is nothing for the
# green check to compare against, and proceeding would quietly drop the
# comparison rather than make it.
wait_green_baseline_bg() {
    [[ -n "$BASELINE_BG_PID" ]] || return 0
    local status=0 pid="$BASELINE_BG_PID"
    BASELINE_BG_PID=""
    echo
    echo "Waiting for the baseline suite started during planning..."
    wait "$pid" || status=$?
    sed 's/^/  /' "$LOG_DIR/green-baseline.bg.log" 2>/dev/null || true
    if [[ "$status" -ne 0 ]]; then
        echo "Baseline capture failed (status $status); the green check has nothing"
        echo "to compare against. Log: $LOG_DIR/green-check-baseline.log"
        printf '%s\n' "baseline: capture failed with status $status" > "$STATE_DIR/stop-reason"
        exit "$status"
    fi
    return 0
}

# Run the same commands against the changed tree and classify each against its
# baseline. Returns non-zero when something that passed before now fails.
#
# It reports; it does not decide. A regression turns the implementation gate
# from an approval into an explicit override, so the decision stays with the
# operator and is recorded either way.
run_green_check() {
    if [[ "$GREEN_CHECK" != "1" ]]; then
        {
            echo "## Green check"
            echo
            echo "DISABLED (\`WORKFLOW_GREEN_CHECK=0\`). The driver did not"
            echo "re-run this project's checks, so CHANGE_TEST_REPORT.md below"
            echo "is the implementing agent's unverified account of them."
        } > "$GREEN_MD"
        return 0
    fi

    if [[ ! -s "$GREEN_CMDS" ]]; then
        : > "$GREEN_CLASS"
        green_report "$GREEN_CLASS" "$GREEN_MD" BASELINE_REPORT.md \
            "$LOG_DIR/green-check.log"
        echo
        echo "Green check NOT RUN: no commands were found in BASELINE_REPORT.md."
        return 0
    fi

    echo
    echo "Re-running this project's checks from the driver:"
    resolve_baseline_parallel_groups BASELINE_REPORT.md "$GREEN_CMDS" "$STATE_DIR/green-check.groups" || exit $?
    green_run "$GREEN_CMDS" "$GREEN_CUR" "$LOG_DIR/green-check.log" "" "$STATE_DIR/green-check.groups" || exit $?
    green_classify "$GREEN_BASE" "$GREEN_CUR" > "$GREEN_CLASS"
    green_report "$GREEN_CLASS" "$GREEN_MD" BASELINE_REPORT.md \
        "$LOG_DIR/green-check.log"

    local regressions
    regressions="$(green_regressions "$GREEN_CLASS")"

    if [[ "$regressions" -gt 0 ]]; then
        echo
        echo "$regressions check(s) passed before this change and fail now:"
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
    echo "Green check: no regressions."
    return 0
}

# --- Background green check for the checklist stage -------------------------
#
# At EXECUTE_CHECKLIST the green check's exit status was already discarded
# (`run_green_check || true`): nothing there gates on it. What it cost was
# wall-clock -- on this repo, re-running the whole shell suite before the
# checklist agent could start, with no output while it ran, which reads as a
# hang. So it runs alongside the stage instead of in front of it.
#
# The result is still consumed. A failure goes to triage exactly as a
# foreground failure would; a pass is ignored, because a pass at this call site
# never fed a decision.
#
# The one thing this gives up is stated rather than hidden: the checklist agent
# is told the driver checks are still running, so it cannot cite them as fresh
# evidence and verifies those items itself. snapshot_checklist_checks refuses
# to present a previous run's log as fresh, and that stays true here.
GREEN_BG_PID=""

start_green_check_bg() {
    if [[ "$GREEN_CHECK" != "1" || ! -s "$GREEN_CMDS" ]]; then
        return 0
    fi
    echo
    echo "Re-running this project's checks in the background while the checklist runs."
    echo "Log: $LOG_DIR/green-check.log"
    ( run_green_check ) > "$LOG_DIR/green-check.bg.log" 2>&1 < /dev/null &
    GREEN_BG_PID=$!
}

# Consume the background result: triage a failure, ignore a pass.
wait_green_check_bg() {
    [[ -n "$GREEN_BG_PID" ]] || return 0
    local status=0 pid="$GREEN_BG_PID"
    GREEN_BG_PID=""
    echo
    echo "Collecting the background check results..."
    wait "$pid" || status=$?
    sed 's/^/  /' "$LOG_DIR/green-check.bg.log" 2>/dev/null || true
    if [[ "$status" -eq 0 ]]; then
        echo "Background checks: no regressions."
        return 0
    fi
    # Surfaced, not fatal -- the same status the foreground call discarded with
    # `|| true`. A regression here is the operator's to weigh at the gate and
    # override on the record; stopping the run would delete that choice, and
    # green-check.md and the final audit still carry the failure either way.
    echo
    echo "Background checks reported regressions (status $status)."
    echo "They are recorded, not silently dropped: the gate and the final audit"
    echo "both see them, and completing over one requires an explicit override."
    echo "Detail: $GREEN_MD"
    return 0
}

# Run only the rows that the independent checklist reviewer explicitly placed
# together.  Each worker owns a private evidence file; it never writes the
# canonical reports or product files.  Groups remain barriers, so a row that
# depends on an earlier group cannot start early.  A worker failure is evidence
# for the synthesizer, not a reason to throw away results from its siblings.
run_parallel_checklist_workers() {
    local groups="$PROJECT_ROOT/$STATE_DIR/checklist-groups/groups.txt"
    # Runner adapters may rebuild .uncle while they start. Worker handoffs are
    # outside the project entirely, so no workflow cleanup can race them.
    local directory="" group id prompt evidence
    local worker_count=0 worker_cap synthesis_cap failed=0 status pid jobs
    local -a ids pids pid_ids

    [[ "$PARALLEL_CHECKLIST_WORKERS" == 1 && -s "$groups" ]] || return 0
    jobs="${WORKFLOW_VERIFY_JOBS:-4}"
    [[ "$jobs" =~ ^[1-8]$ ]] || jobs=4
    while IFS= read -r group; do
        set -- $group
        [[ $# -gt 1 ]] && worker_count=$((worker_count + $#))
    done < "$groups"
    [[ "$worker_count" -gt 1 ]] || return 0

    # Reserve half of the existing stage cap for reconciliation and split the
    # other half among workers. This bounds a fan-out to the old stage budget
    # instead of multiplying it by the number of independent checks.
    synthesis_cap="$BUDGET_EXECUTE"
    worker_cap="$BUDGET_EXECUTE"
    if [[ -n "$BUDGET_EXECUTE" ]]; then
        synthesis_cap="$(awk -v cap="$BUDGET_EXECUTE" 'BEGIN { printf "%.2f", cap / 2 }')"
        worker_cap="$(awk -v cap="$BUDGET_EXECUTE" -v n="$worker_count" 'BEGIN { printf "%.2f", cap / (2 * n) }')"
    fi
    CHECKLIST_SYNTHESIS_BUDGET="$synthesis_cap"

    directory="$(mktemp -d "${TMPDIR:-/tmp}/uncle-checklist-workers.XXXXXX")" || return 1
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
    # MANUAL_CHECKLIST.md and both READMEs from scratch just to execute one
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
    local n batches chunk start end i batch_index batch_size
    while IFS= read -r group; do
        read -r -a ids <<< "$group"
        n="${#ids[@]}"
        [[ "$n" -gt 1 ]] || continue
        batches=$(( n < jobs ? n : jobs ))
        chunk=$(( (n + batches - 1) / batches ))
        i=0
        batch_index=0
        while [[ "$i" -lt "$n" ]]; do
            batch_index=$((batch_index + 1))
            prompt="$directory/prompts/batch-$batch_index.md"
            cp "$ROOT/prompts/change/execute-checklist-worker.md" "$prompt"
            printf '\n## Assigned checks\n\n' >> "$prompt"
            end=$(( i + chunk < n ? i + chunk : n ))
            for ((start = i; start < end; start++)); do
                id="${ids[$start]}"
                evidence="$directory/$id.md"
                printf -- '- Execute `%s`. Write its evidence to `%s`.\n' "$id" "$evidence" >> "$prompt"
                # Backticks are Markdown here, not shell command substitution.
                printf '%s\n' "- $id: \`$evidence\`" >> "$directory/README.md"
            done
            i="$end"
        done
    done < "$groups"

    while IFS= read -r group; do
        read -r -a ids <<< "$group"
        n="${#ids[@]}"
        [[ "$n" -gt 1 ]] || continue
        batches=$(( n < jobs ? n : jobs ))
        chunk=$(( (n + batches - 1) / batches ))
        echo "Checklist worker group: $group ($batches batch(es))"
        pids=()
        pid_ids=()
        i=0
        for ((batch_index = 1; batch_index <= batches; batch_index++)); do
            end=$(( i + chunk < n ? i + chunk : n ))
            batch_size=$(( end - i ))
            i="$end"
            prompt="$directory/prompts/batch-$batch_index.md"
            (
                SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 \
                    run_claude "$prompt" "execute-checklist-worker-batch-$batch_index" \
                        "$MODEL_EXECUTE" "$EFFORT_EXECUTE" 80 \
                        "$(awk -v cap="$worker_cap" -v n="$batch_size" 'BEGIN { printf "%.2f", cap * n }')"
            ) > "$LOG_DIR/execute-checklist-worker-batch-$batch_index.log" 2>&1 &
            pids+=("$!")
            pid_ids+=("batch-$batch_index")
        done
        # Batches per group are already bounded at `jobs`, so every batch in
        # a group launches together; the barrier is only between groups.
        for ((status = 0; status < ${#pids[@]}; status++)); do
            pid="${pids[$status]}"
            if ! wait "$pid"; then
                echo "Worker ${pid_ids[$status]} did not complete; reconciliation will run its assigned rows." >&2
                failed=1
            fi
        done
    done < "$groups"
    [[ "$failed" == 0 ]] || printf '\nSome workers failed; their IDs require reconciliation.\n' >> "$directory/README.md"
    CHECKLIST_EXECUTE_PROMPT="$directory/execute-checklist-synthesis.md"
    cp "$ROOT/prompts/change/execute-change-checklist.md" "$CHECKLIST_EXECUTE_PROMPT"
    printf '\n## Parallel worker handoff\n\nRead `%s` and every listed evidence file before reconciling reports.\n' \
        "$directory/README.md" >> "$CHECKLIST_EXECUTE_PROMPT"
    return 0
}

# --- Post-implementation review document ------------------------------------

# Rebuilt from the working tree every time the gate opens, so the approval
# digest attests to the tree rather than to a file somebody could edit.
build_implementation_review() {
    write_change_diff "$DIFF_FILE"
    write_implementation_review "$REVIEW_FILE" "$DIFF_FILE" "$GREEN_MD" \
        IMPLEMENTATION_NOTES.md CHANGE_TEST_REPORT.md
    WORKFLOW_UNTRACKED_BASELINE="$WORKFLOW_UNTRACKED_BASELINE" python3 -B "$ROOT/scripts/lib/approval_snapshot.py" prepare "$STATE_DIR"

}

# Regenerate the document and compare it with what was approved. A mismatch
# means the code moved after the operator read it, so the gate re-opens on the
# current tree rather than the pipeline carrying a stale approval forward.
verify_implementation_review() {
    local approval="$APPROVAL_DIR/IMPLEMENTATION_REVIEW.sha256"

    require_file "$approval"
    if [[ -f "$APPROVAL_DIR/IMPLEMENTATION_REVIEW.inputs.json" ]]; then
        if WORKFLOW_UNTRACKED_BASELINE="$WORKFLOW_UNTRACKED_BASELINE" python3 -B "$ROOT/scripts/lib/approval_snapshot.py" check "$STATE_DIR"; then
            return 0
        fi
        build_implementation_review
        set_state WAIT_IMPLEMENT_APPROVAL
        echo "Approved inputs changed; review the current implementation again."
        exit 0
    fi
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

# Run plan-declared independent implementation steps in temporary worktrees.
# The supervisor's schedule is intentionally mechanical: it may only use the
# approved plan's Owns:/Depends on: data.  The driver, not the model, creates,
# merges and removes worktrees.
run_supervised_parallel_implementation() {
    local base="$1" groups group step prompt cmd model effort result
    groups="$(parallel_groups CHANGE_PLAN.md "$ROOT/scripts/lib")" || return 2
    [[ -n "$groups" ]] || return 2
    [[ ! -s "$STATE_DIR/implement-step-done" ]] || return 2

    uncle_resolve_stage_runner implementation AGENT || return 1
    cmd="$(stage_agent_cmd implementation)" || return 1
    model="$(stage_model_for implementation "$MODEL_IMPLEMENT")"
    effort="$(stage_effort_for implementation)"
    export PARALLEL_AGENT_CMD="$cmd" PARALLEL_AGENT_MODEL="$model"
    export PARALLEL_AGENT_EFFORT="$effort" PARALLEL_AGENT_BUDGET="$BUDGET_IMPLEMENT"
    export PARALLEL_AGENT_TOOLS="$CLAUDE_TOOLS"

    mkdir -p "$STATE_DIR/parallel/prompts" "$STATE_DIR/parallel/notes"
    export PARALLEL_PROMPT_DIR="$PWD/$STATE_DIR/parallel/prompts"
    while IFS= read -r group; do
        [[ -n "$group" ]] || continue
        for step in $group; do
            prompt="$STATE_DIR/parallel/prompts/step-$step.md"
            compose_implementation_prompt "$base" "$prompt"
            {
                echo
                echo "## Isolated parallel implementation step $step"
                sed -n "${step}p" "$STATE_DIR/implement-steps.txt"
                echo
                echo "Work only on this approved step and its declared owned files."
                echo "Do not edit workflow documents in the project root. Append a"
                echo "concise handoff with changed files and exact checks to"
                echo ".uncle/workflow/parallel/notes/step-$step.md. Do not write"
                echo "CHANGE_TEST_REPORT.md; the driver reconciles it after merging."
                echo "Finish in at most 12 tool actions. Read only the named files,"
                echo "make the smallest edit, run one narrow check, write the handoff,"
                echo "and stop; do not investigate unrelated failures or repeat probes."
            } >> "$prompt"
        done
        echo "Supervisor schedule: isolated parallel steps $group."
        result="$(parallel_run_group "$ROOT/scripts/lib" "$LOG_DIR" CHANGE_PLAN.md $group)" || return $?
        PARALLEL_RESULT="$result" python3 - "$group" <<'PY'
import json, os, sys
group = sys.argv[1]
data = json.loads(os.environ['PARALLEL_RESULT'])
elapsed = float(data.get('elapsed_seconds', 0))
total = sum(float(v) for v in (data.get('step_seconds') or {}).values())
saved = max(0.0, total - elapsed)
files = len(data.get('files') or [])
print('Parallel group %s complete: %.1fs wall time; %.1fs worker time; '
      'estimated %.1fs saved; %d files merged; worktrees %s.' %
      (group, elapsed, total, saved, files, data.get('worktrees', 'preserved')))
PY
        for step in $group; do
            require_file "$STATE_DIR/parallel/notes/step-$step.md"
            cat "$STATE_DIR/parallel/notes/step-$step.md" >> IMPLEMENTATION_NOTES.md
            printf '%s\n' "$step" > "$STATE_DIR/implement-step-done"
        done
    done <<< "$groups"
    rm -rf "$STATE_DIR/parallel"
    return 0
}

# One invocation per implementation-sequence step, each starting cold.
#
# IMPLEMENTATION_NOTES.md is the handoff: every step appends to it, and the
# next step reads it instead of inheriting a transcript. The code already
# written is on disk, which is the other half of the handoff.
run_stepwise_implementation() {
    local base="$1"
    local steps_file="$STATE_DIR/implement-steps.txt"
    local done_file="$STATE_DIR/implement-step-done"
    local report_done_file="$STATE_DIR/implement-report-done"

    plan_steps CHANGE_PLAN.md > "$steps_file"

    local total
    total="$(grep -c . "$steps_file" || true)"

    if [[ "${total:-0}" -lt 2 ]]; then
        echo "CHANGE_PLAN.md has no usable implementation sequence;" \
             "running implementation as a single stage."
        compose_implementation_prompt "$base" "$STATE_DIR/implement-change.resolved.md"
        run_claude "$STATE_DIR/implement-change.resolved.md" implementation \
            "$MODEL_IMPLEMENT" "" 200 "$BUDGET_IMPLEMENT"
        return 0
    fi

    # Parallel execution is the default and only starts when the approved plan
    # explicitly partitions ownership. A resume remains serial: preserving a
    # failed worktree for inspection is safer than recreating it on top of a
    # partial delivery.
    if run_supervised_parallel_implementation "$base"; then
        check_document_budget IMPLEMENTATION_NOTES.md || exit 1
    else
        local parallel_status=$?
        [[ "$parallel_status" == 2 ]] || return "$parallel_status"
    fi

    # Split the single stage's cap across the steps rather than multiplying it.
    # The final code step and its change report are deliberately separate cold
    # invocations. Some runners cap a session independently of --max-turns;
    # making a completed implementation also reconcile a whole report can then
    # turn a successful code change into a failed stage at that runner cap.
    local report_turns=12 final_turns=38 turns=50 step_turns
    if [[ "$total" -gt 1 ]]; then
        turns=$(( 150 / (total - 1) ))
        [[ "$turns" -lt 8 ]] && turns=8
        [[ "$turns" -gt 50 ]] && turns=50
    fi

    local completed=0
    if [[ -s "$done_file" ]]; then
        completed="$(head -n 1 "$done_file")"
        echo "Resuming implementation after step $completed of $total."
    fi

    local i=0 step prompt
    while IFS= read -r step; do
        [[ -n "$step" ]] || continue
        i=$(( i + 1 ))
        [[ "$i" -le "$completed" ]] && continue

        prompt="$STATE_DIR/implement-step-$i.md"
        compose_implementation_prompt "$base" "$prompt"

        {
            echo
            echo "## This invocation: step $i of $total"
            echo
            echo "$step"
            echo
            echo "Implement this step only. The earlier steps are already done"
            echo "and their code is on disk; IMPLEMENTATION_NOTES.md records"
            echo "what they changed and why. Read it first. Do not redo, revise"
            echo "or review their work, and do not start a later step."
            echo
            echo "Append your rows to IMPLEMENTATION_NOTES.md; do not rewrite"
            echo "the rows already there. Run the narrowest test target that"
            echo "covers this step."
            echo
            echo "## Runtime completion bound (binding)"
            echo
            echo "This runner can end a session after 21 tool iterations. Finish"
            echo "this step in at most 12 tool actions: read the named files once,"
            echo "make the smallest edit, run the one named/narrow test, append the"
            echo "handoff, and stop. Do not investigate unrelated failures, repeat"
            echo "probes, review earlier steps, or broaden the test run. If a narrow"
            echo "check exposes an unrelated pre-existing issue, record it in the"
            echo "handoff and finish this step rather than diagnosing it."
            if [[ "$i" -ne "$total" ]]; then
                echo
                echo "Do not run the full suite; the final step does that once."
            else
                echo
                echo "This is the final code step. Run only the narrow checks"
                echo "needed for this code and append their result to"
                echo "IMPLEMENTATION_NOTES.md. Do not write CHANGE_TEST_REPORT.md:"
                echo "a fresh report-only invocation will reconcile it from the"
                echo "on-disk notes and evidence. The driver runs the full"
                echo "regression block once after that invocation."
            fi
        } >> "$prompt"

        echo
        echo "Implementation step $i/$total: ${step:0:70}"
        plan_assess || return $?
        step_turns="$turns"
        [[ "$i" -eq "$total" ]] && step_turns="$final_turns"
        run_claude "$prompt" "implementation-step-$i" \
            "$MODEL_IMPLEMENT" "" "$step_turns" "$BUDGET_IMPLEMENT"

        check_document_budget IMPLEMENTATION_NOTES.md || exit 1
        printf '%s\n' "$i" > "$done_file"
    done < "$steps_file"

    # This is intentionally its own cold stage, rather than a postscript to
    # the last code step. It is a checkpointed recovery boundary: if report
    # synthesis hits a runner limit, resume retries only this small stage and
    # never redoes a successfully checkpointed implementation step.
    if [[ ! -f "$report_done_file" ]]; then
        prompt="$STATE_DIR/implement-report.md"
        compose_implementation_prompt "$base" "$prompt"
        {
            echo
            echo "## Report-only invocation (no code changes)"
            echo
            echo "All implementation steps are complete and checkpointed. Do"
            echo "not inspect unrelated code, change source files, rerun tests,"
            echo "or review the implementation. Read IMPLEMENTATION_NOTES.md and"
            echo "the existing targeted-test evidence only. Then replace"
            echo "CHANGE_TEST_REPORT.md with its required concise, authoritative"
            echo "whole-change report. Report only checks that actually ran; mark"
            echo "anything absent as NOT RUN. Finish immediately after writing it."
        } >> "$prompt"

        echo
        echo "Implementation report: reconciling checkpointed step evidence."
        plan_assess || return $?
        run_claude "$prompt" "implementation-step-report" \
            "$MODEL_IMPLEMENT" "" "$report_turns" "$BUDGET_IMPLEMENT"
        check_document_budget CHANGE_TEST_REPORT.md || exit 1
        touch "$report_done_file"
    fi

    rm -f "$done_file"
    rm -f "$report_done_file"
}

# Count checks as they stream past and drive the pinned status line.
#
# The denominator is the distinct MC ids in MANUAL_CHECKLIST.md; the numerator
# is the distinct ids seen in the stage's own output. That is a progress
# estimate, not a completion record: an id counts the first time the stage
# mentions it, which may be when it starts a check rather than when it
# finishes. VERIFICATION_REPORT.md remains the only authority on what actually
# ran. Lines pass through untouched, so the log is unchanged.
progress_tap() {
    local total="$1" label="$2"
    local seen="" count=0 line id

    if [[ "$total" -le 0 ]]; then
        cat
        return 0
    fi

    progress_begin
    progress_update 0 "$total" "$label"
    while IFS= read -r line; do
        printf '%s\n' "$line"
        case "$line" in
            *MC-*)
                for id in $(printf '%s' "$line" | grep -oE 'MC-[0-9]+' | sort -u); do
                    case " $seen " in
                        *" $id "*) ;;
                        *)
                            seen="$seen $id"
                            count=$(( count + 1 ))
                            progress_update "$count" "$total" "$label"
                            ;;
                    esac
                done
                ;;
        esac
    done
    progress_end
}

# Change-request pipeline stage order, used to report "stage N/M" to the TUI.
# Dynamic log names (implementation-step-N, manual-checklist-base/delta) are
# normalized to the base stage before lookup.
STATUS_STAGE_SEQ="change-plan adversarial-review updated-change-plan implementation manual-checklist execute-checklist final-audit"

# Report the current stage to the TUI status channel. The exports feed the
# agent shims' own status writes; the start event written here covers every
# stage directly, including runners with no shim (plain claude, reviewers).
status_stage_context() {
    local log_name="$1"
    local turns="${2:-0}"
    local model="${3:-(runner default)}"
    local mode="${4:-act}"
    local base="${log_name%%-step-*}"     # implementation-step-3 -> implementation
    base="${base%-base}"                   # manual-checklist-base -> manual-checklist
    base="${base%-delta}"                  # manual-checklist-delta -> manual-checklist
    local s i=1 index=0 n=0
    for s in $STATUS_STAGE_SEQ; do
        n=$((n + 1))
        if [[ "$s" == "$base" ]]; then
            index=$i
        fi
        i=$((i + 1))
    done
    export UNCLE_STATUS_STAGE="$log_name"
    export UNCLE_STATUS_STAGE_INDEX="$index"
    export UNCLE_STATUS_STAGE_TOTAL="$n"
    export UNCLE_STATUS_STAGE_TURNS="$turns"
    # Keyed on the normalized name, so a -step-/-base/-delta variant inherits
    # the setting its parent stage was configured with.
    UNCLE_STAGE_NETWORK="$(uncle_stage_network "$base")"
    export UNCLE_STAGE_NETWORK
    if [[ -n "${UNCLE_STATUS_FILE:-}" ]]; then
        printf '{"event":"start","model":"%s","mode":"%s","stage":"%s","stage_index":%s,"stage_total":%s,"stage_turns":%s}\n' \
            "$model" "$mode" "$log_name" "$index" "$n" "$turns" \
            >> "$UNCLE_STATUS_FILE"
    fi
}

run_claude() {
    local prompt_file
    prompt_file="$(resolve_prompt "$1")"
    local log_name="$2"
    case "$log_name" in
        requirements|project-plan|change-plan)
            python3 "$ROOT/scripts/lib/early-prerequisites.py" "$DOCUMENT_BUDGET_SOURCE" || exit $? ;;
    esac

    local model="$3"
    local effort="${4:-}"
    local max_turns="${5:-80}"
    local budget="${6:-}"
    local cmd
    local UNCLE_RESOLVED_RUNNER
    uncle_resolve_stage_runner "$log_name" AGENT || return 1

    cmd="$(stage_agent_cmd "$log_name")" || return 1
    local -a client_cmd=("$cmd")
    case "${cmd##*/}" in
        claude|codex) client_cmd=(env -u UNCLE_STATUS_FILE -u UNCLE_PROJECT_ROOT -u UNCLE_CONFIG -u STAGEGATE_RUN_ID -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u DOCUMENT_BUDGET_SOURCE "$cmd") ;;
    esac
    if [[ -n "${UNCLE_RESOLVED_RUNNER:-}" && "$UNCLE_RESOLVED_RUNNER" != self-hosted ]] \
       && { [[ "${UNCLE_STEERING:-}" == 1 ]] \
            || { [[ "${UNCLE_RUNNER_REUSE:-1}" != 0 ]] && ! stage_command_overridden AGENT "$log_name"; }; }; then
        client_cmd=(python3 "$ROOT/scripts/lib/native_stage.py" --runner "$UNCLE_RESOLVED_RUNNER" --side agent --stage "$log_name" --)
    fi
    # A stage configured in `uncle` overrides what the call site asked for.
    model="$(stage_model_for "$log_name" "$model")"
    effort="$(stage_effort_for "$log_name")"

    require_file "$prompt_file"

    local turns_retried=""
    while true; do
        status_stage_context "$log_name" "$max_turns" "${model:-}" act
        local -a flags=(
            -p
            --max-turns "$max_turns"
            --output-format stream-json
            --verbose
            --strict-mcp-config
            --exclude-dynamic-system-prompt-sections
            --allowedTools "$CLAUDE_TOOLS"
        )

        if [[ -n "$model" ]]; then
            flags+=(--model "$model")
        fi

        if [[ -n "$effort" ]]; then
            flags+=(--effort "$effort")
        fi

        if [[ -n "$budget" ]]; then
            flags+=(--max-budget-usd "$budget")
        fi

        # Forking inherits the previous stage's whole transcript. That is faster
        # but costs more every turn, so it is off unless asked for. Forking leaves
        # the parent session untouched, so a failed stage retries from the same
        # point.
        local head=""
        if [[ "$SESSION_REUSE" == "1" && -s "$SESSION_FILE" ]]; then
            head="$(cat "$SESSION_FILE")"
            flags+=(--resume "$head" --fork-session)
        fi

        echo
        echo "Launching agent ($cmd): $log_name"
        echo "Model: ${model:-(runner default)}${effort:+  Effort: $effort}${budget:+  Cap: \$$budget}"
        if [[ -n "$head" ]]; then
            echo "Forking session: $head"
        fi
        echo

        # Use stdin for the prompt because --allowedTools is variadic and can
        # otherwise consume a trailing positional prompt. Streaming also makes a
        # long-running stage visibly active instead of buffering until completion.
        local start="$SECONDS"
        local status=0
        local effective_prompt
        effective_prompt="$(gated_prompt "$prompt_file" "$log_name")"
        supervision_prompt "$effective_prompt" "$log_name" "$LOG_DIR/${log_name}.jsonl"
        effective_prompt="$SUPERVISION_PROMPT"
        ( "${client_cmd[@]}" "${flags[@]}" \
            < "$effective_prompt" \
            2>&1 \
            | perf_stream "$log_name" | tee "$LOG_DIR/${log_name}.jsonl" \
            | progress_tap "${PROGRESS_TOTAL:-0}" "${PROGRESS_LABEL:-stage}" \
            | format_claude_stream ) &
        wait "$!" || status=$?
        progress_end

        local elapsed="$((SECONDS - start))"
        local log="$LOG_DIR/${log_name}.jsonl"
        perf_record agent "$log_name" "$elapsed" "$status" "$log" "$cmd" "$model" "$effort"
        supervision_stage_end "$log_name" "$status" "$log"

        # The final result event, if the run produced one.
        local result
        result="$(jq -R -c 'fromjson? | select(type == "object") | select(.type == "result")' < "$log" | tail -n 1)"

        if [[ -n "$result" ]]; then
            record_cost "agent:$log_name" "$elapsed" \
                "$(printf '%s' "$result" | jq -r '.total_cost_usd // "-"')" \
                "$(printf '%s' "$result" | jq -r '.usage.input_tokens // 0')" \
                "$(printf '%s' "$result" | jq -r '.usage.output_tokens // 0')" \
                "$(printf '%s' "$result" | jq -r '.usage.cache_read_input_tokens // 0')" \
                "$(printf '%s' "$result" | jq -r '.usage.cache_creation_input_tokens // 0')"
        else
            record_cost "agent:$log_name" "$elapsed" - - - - -
        fi

        if [[ "$status" -ne 0 ]]; then
            # A step whose scope needs more turns than its automatically
            # divided share (150 turns split across the plan's steps) is not
            # stuck or wrong -- a real run had correctly diagnosed the exact
            # fix needed and was mid-way through applying it across several
            # files when the runner exited nonzero on hitting this limit
            # (this is not the exit-0-with-a-failed-result-event case the
            # comment below assumes every stop condition takes). Unlike a
            # model choice, a turn count is not a decision an operator needs
            # to make; double it once, the same bounded-retry shape
            # self_hosted.py already uses for an output-token ceiling.
            if [[ -z "$turns_retried" ]] && grep -qiE 'maximum number of turns|max.?turns' "$log"; then
                turns_retried=1
                local larger_turns=$((max_turns * 2))
                [[ "$larger_turns" -le 200 ]] || larger_turns=200
                if [[ "$larger_turns" -gt "$max_turns" ]]; then
                    echo "Stage $log_name reached its turn limit ($max_turns) mid-task; retrying once with $larger_turns."
                    max_turns="$larger_turns"
                    continue
                fi
            fi
            echo "Agent ($cmd) exited with status $status."
            echo "Raw event log: $log"
            exit "$status"
        fi

        # A budget breach, a turn-limit stop, and an API failure all exit 0 and
        # report themselves only inside the result event. Without this check the
        # stage would look like a success and the pipeline would advance on a
        # partial artifact.
        if [[ -z "$result" ]]; then
            echo "No result event in $log; treating $log_name as failed."
            exit 1
        fi

        local is_error subtype
        is_error="$(printf '%s' "$result" | jq -r '.is_error // false')"
        subtype="$(printf '%s' "$result" | jq -r '.subtype // "unknown"')"

        if [[ "$is_error" == "true" ]]; then
            echo
            echo "Stage $log_name reported failure: $subtype"
            local error_detail
            error_detail="$(printf '%s' "$result" | jq -r '.error_detail // empty')"
            if [[ -n "$error_detail" ]]; then
                echo "Cause: $error_detail"
            fi
            if [[ "$subtype" == "context_length_exceeded" ]]; then
                echo "The model ran out of context/tokens."
                echo
                printf '%s' "Enter a new model id to retry this stage (or Enter to stop): "
                local new_model
                if read -r new_model && [[ -n "$new_model" ]]; then
                    model="$(printf '%s' "$new_model" | tr -d '[:space:]')"
                    continue
                fi
                echo
                triage_stop_reason "$STATE_DIR" human
            fi
            # A step whose scope needs more turns than its automatically
            # divided share (150 turns split across the plan's steps) is not
            # stuck or wrong -- a real run had correctly diagnosed the exact
            # fix needed and was mid-way through applying it across several
            # files when it hit this. Unlike a model choice, a turn count is
            # not a decision an operator needs to make; double it once, the
            # same bounded-retry shape self_hosted.py already uses for an
            # output-token ceiling, before ever treating this as a real stop.
            if [[ -z "$turns_retried" ]] && printf '%s' "$error_detail$subtype" | grep -qiE 'maximum number of turns|max.?turns'; then
                turns_retried=1
                local larger_turns=$((max_turns * 2))
                [[ "$larger_turns" -le 200 ]] || larger_turns=200
                if [[ "$larger_turns" -gt "$max_turns" ]]; then
                    echo "Stage $log_name reached its turn limit ($max_turns) mid-task; retrying once with $larger_turns."
                    max_turns="$larger_turns"
                    continue
                fi
            fi
            if [[ "$subtype" == *budget* ]]; then
                echo "The \$$budget cap for this stage was reached."
                echo "Raise it with the matching WORKFLOW_BUDGET_* variable and re-run."
            fi
            echo "Raw event log: $log"
            show_spend
            exit 1
        fi

        show_spend
        break
    done

    if [[ "$SESSION_REUSE" == "1" ]]; then
        local next
        next="$(printf '%s' "$result" | jq -r '.session_id // empty')"
        if [[ -n "$next" ]]; then
            printf '%s\n' "$next" > "$SESSION_FILE"
        else
            echo "Warning: no session id in $log_name; next stage cold-starts."
        fi
    fi
}

# Codex reports token usage on its last line but never a dollar figure, so the
# ledger records tokens for Codex stages and a dash for cost.
record_codex_cost() {
    local log_name="$1"
    local elapsed="$2"
    local log="$LOG_DIR/${log_name}.log"
    local tokens="-"

    if [[ -s "$log" ]]; then
        tokens="$(awk '/tokens used/ {getline; gsub(/[^0-9]/, "", $0); if ($0 != "") t = $0} END {print (t == "" ? "-" : t)}' "$log")"
    fi

    local result
    result="$(jq -R -c 'fromjson? | select(type == "object") | select(.type == "result")' "$log" | tail -n 1)"
    if [[ -n "$result" ]]; then
        record_cost "reviewer:$log_name" "$elapsed" \
            "$(printf '%s' "$result" | jq -r '.total_cost_usd // "-"')" \
            "$(printf '%s' "$result" | jq -r '.usage.input_tokens // "-"')" \
            "$(printf '%s' "$result" | jq -r '.usage.output_tokens // "-"')" \
            "$(printf '%s' "$result" | jq -r '.usage.cache_read_input_tokens // "-"')" \
            "$(printf '%s' "$result" | jq -r '.usage.cache_creation_input_tokens // "-"')"
    else
        record_cost "reviewer:$log_name" "$elapsed" - - - - "$tokens"
    fi
}

run_codex() {
    local prompt_file
    prompt_file="$(resolve_prompt "$1")"
    local output_file="$2"
    local log_name="$3"
    local effort="${4:-}"
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
    effort="$(stage_effort_for "$log_name")"
    local -a model_args=()
    local model
    model="$(stage_model_for "$log_name" "${CODEX_MODEL:-}")"
    [[ -n "$model" ]] && model_args=(-m "$model")

    require_file "$prompt_file"
    # The reviewer writes a document a human reads, so it gets the output
    # rules the same way an agent stage does.
    if [[ "$log_name" != plan-executability ]]; then
        prompt_file="$(gated_prompt "$prompt_file" "$log_name" reviewer)"
        supervision_prompt "$prompt_file" "$log_name" "$LOG_DIR/${log_name}.log"
        prompt_file="$SUPERVISION_PROMPT"
    fi

    local review_key
    review_key="$(review_input_key "$output_file" "$prompt_file" "$cmd" "$model" "$effort" "$log_name")"
    if restore_plan_review "$output_file" "$review_key"; then
        if [[ "$log_name" != adversarial-review ]]; then
        finish_review_budget "$output_file" "$cmd" "$model" "$effort" "$log_name" || exit 1
    fi
        save_plan_review "$output_file" "$review_key"
        return 0
    fi

    local -a flags=(
        exec
        --ephemeral
        # Project dirs need not be git repos; the read-only sandbox is the boundary.
        --skip-git-repo-check
        --sandbox read-only
        "${model_args[@]+"${model_args[@]}"}"
        --output-last-message "$output_file"
    )

    if [[ -n "$effort" ]]; then
        flags+=(-c "model_reasoning_effort=$effort")
    fi

    echo
    echo "Launching reviewer ($cmd): $log_name${effort:+  Effort: $effort}${model:+  Model: $model}"
    status_stage_context "$log_name" 0 "${model:-}" review

    local start="$SECONDS" empty_retried=""
    local status=0
    while true; do
        start="$SECONDS"
        # stdin is the operator's gate-answer channel, not stage input: codex
        # appends a non-TTY stdin to the prompt and would block on it forever.
        ( "${client_cmd[@]}" "${flags[@]}" "$(cat "$prompt_file")" \
            < /dev/null 2>&1 | perf_stream "$log_name" | tee "$LOG_DIR/${log_name}.log" ) &
        wait "$!" || status=$?

        record_codex_cost "$log_name" "$((SECONDS - start))"
        perf_record reviewer "$log_name" "$((SECONDS-start))" "$status" \
            "$LOG_DIR/${log_name}.log" "$cmd" "$model" "$effort"
        supervision_stage_end "$log_name" "$status" "$LOG_DIR/${log_name}.log"

        if [[ "$status" -ne 0 || ! -s "$output_file" ]] && context_exhausted "$LOG_DIR/${log_name}.log"; then
            echo
            echo "The reviewer ran out of context/tokens."
            echo "Change the reviewer model (Configure → reviewer) and re-run to resume this stage."
        fi

        # A reviewer that exits successfully but writes nothing -- a
        # conversational summary asking for guidance instead of the document
        # -- is not done, whatever its own transcript claims. Left alone, this
        # used to reach a later validation state that only checks what this
        # stage already produced, with no path back to re-running it: "resume"
        # alone could never recover. One bounded, silent retry with the same
        # prompt plus a note of what happened.
        if [[ "$status" == 0 && ! -s "$output_file" && -z "$empty_retried" ]]; then
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
        break
    done

    [[ "$status" == 0 ]] || return "$status"
    require_file "$output_file"
    [[ "$log_name" != plan-executability ]] || return 0
    # Do not reuse results if inputs changed while the reviewer was reading them.
    if [[ -n "$review_key" && "$review_key" == "$(review_input_key "$output_file" "$prompt_file" "$cmd" "$model" "$effort" "$log_name")" ]]; then
        save_plan_review "$output_file" "$review_key"
    else
        review_key=""
    fi
    if [[ "$log_name" != adversarial-review ]]; then
        finish_review_budget "$output_file" "$cmd" "$model" "$effort" "$log_name" || exit 1
    fi
    save_plan_review "$output_file" "$review_key"
}

# Focused read-only review workers broaden coverage without granting them the
# canonical review artifact. Failures are advisory: the primary reviewer still
# receives the original evidence and produces the only binding verdict.
run_adversarial_review_panel() {
    local directory="$STATE_DIR/adversarial-review-panel" lens prompt output pid status
    local -a pids=()
    [[ "${WORKFLOW_ADVERSARIAL_REVIEW_PANEL:-1}" == 1 ]] || return 0
    rm -rf "$directory"
    mkdir -p "$directory/prompts"
    for lens in requirements regression security testability; do
        prompt="$directory/prompts/$lens.md"
        output="$directory/$lens.md"
        cp "$ROOT/prompts/change/adversarial-review-worker.md" "$prompt"
        printf '\n## Assigned review lens\n\nFocus only on **%s**.\n' "$lens" >> "$prompt"
        (
            run_codex "$prompt" "$output" "adversarial-review-worker-$lens" \
                "$CODEX_EFFORT_REVIEW"
        ) > "$LOG_DIR/adversarial-review-worker-$lens.log" 2>&1 &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do
        wait "$pid" || echo "Adversarial review panel worker failed; primary review will continue." >&2
    done
    ADVERSARIAL_REVIEW_PROMPT="$directory/adversarial-review-synthesis.md"
    cp "$ROOT/prompts/change/adversarial-review.md" "$ADVERSARIAL_REVIEW_PROMPT"
    printf '\n## Specialist review packets\n\nRead every available packet in `%s`. Treat them as leads, verify their evidence yourself, and write the only canonical `ADVERSARIAL_REVIEW.md`.\n' \
        "$directory" >> "$ADVERSARIAL_REVIEW_PROMPT"
}

run_updated_change_plan_panel() {
    local directory="$STATE_DIR/updated-plan-panel" lens prompt output pid
    local -a pids=()
    # Keep the older knob as a fallback, while allowing the change workflow to
    # be controlled independently from the new-project updated-plan panel.
    [[ "${WORKFLOW_UPDATED_CHANGE_PLAN_PANEL:-${WORKFLOW_UPDATED_PLAN_PANEL:-1}}" == 1 ]] || return 0
    echo "Updated-change-plan review panel: launching 4 workers in parallel."
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    for lens in dispositions ownership verification scope; do
        prompt="$directory/prompts/$lens.md"; output="$directory/$lens.md"
        cp "$ROOT/prompts/change/updated-plan-review-worker.md" "$prompt"
        printf '\n## Assigned review lens\n\nFocus only on **%s**.\n' "$lens" >> "$prompt"
        ( run_codex "$prompt" "$output" "updated-change-plan-review-worker-$lens" "$CODEX_EFFORT_REVIEW" ) > "$LOG_DIR/updated-plan-worker-$lens.log" 2>&1 &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do wait "$pid" || echo 'Updated-change-plan panel worker failed; plan writer will continue.' >&2; done
    echo "Updated-change-plan review panel: worker packets collected; launching synthesis."
    UPDATED_PLAN_PROMPT="$directory/synthesis.md"
    cp "$ROOT/prompts/change/updated-change-plan.md" "$UPDATED_PLAN_PROMPT"
    printf '\n## Specialist plan-review packets\n\nRead available packets in `%s`, verify them, and write the sole canonical revised plan.\n' "$directory" >> "$UPDATED_PLAN_PROMPT"
}

run_final_audit_panel() {
    local directory="$STATE_DIR/final-audit-panel" lens prompt output pid
    local -a pids=()
    [[ "${WORKFLOW_FINAL_AUDIT_PANEL:-1}" == 1 ]] || return 0
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    for lens in verification scope regression waivers; do
        prompt="$directory/prompts/$lens.md"; output="$directory/$lens.md"
        cp "$ROOT/prompts/change/final-audit-review-worker.md" "$prompt"
        printf '\n## Assigned audit lens\n\nFocus only on **%s**.\n' "$lens" >> "$prompt"
        ( run_codex "$prompt" "$output" "final-audit-review-worker-$lens" "$CODEX_EFFORT_AUDIT" ) > "$LOG_DIR/final-audit-worker-$lens.log" 2>&1 &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do wait "$pid" || echo 'Final-audit panel worker failed; auditor will continue.' >&2; done
    FINAL_AUDIT_PROMPT="$directory/synthesis.md"
    cp "$ROOT/prompts/change/final-audit.md" "$FINAL_AUDIT_PROMPT"
    printf '\n## Specialist audit packets\n\nRead available packets in `%s`, verify them, and write the sole canonical final audit and verdict.\n' "$directory" >> "$FINAL_AUDIT_PROMPT"
}

run_checklist_panel() {
    local kind="$1" source="$2" directory="$STATE_DIR/checklist-$1-panel" lens prompt output pid
    local -a pids=()
    [[ "${WORKFLOW_MANUAL_CHECKLIST_PANEL:-1}" == 1 ]] || { CHECKLIST_PANEL_PROMPT="$source"; return 0; }
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    for lens in coverage invariants resources regressions; do
        prompt="$directory/prompts/$lens.md"; output="$directory/$lens.md"
        cp "$ROOT/prompts/change/manual-checklist-review-worker.md" "$prompt"
        printf '\n## Assigned checklist lens\n\nFocus only on **%s** for the %s pass.\n' "$lens" "$kind" >> "$prompt"
        ( run_codex "$prompt" "$output" "manual-checklist-review-worker-$kind-$lens" "$CODEX_EFFORT_CHECKLIST" ) > "$LOG_DIR/manual-checklist-$kind-worker-$lens.log" 2>&1 &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do wait "$pid" || echo 'Checklist panel worker failed; checklist reviewer will continue.' >&2; done
    CHECKLIST_PANEL_PROMPT="$directory/synthesis.md"
    cp "$source" "$CHECKLIST_PANEL_PROMPT"
    printf '\n## Specialist checklist packets\n\nRead available packets in `%s`, verify them, and write the sole canonical checklist.\n' "$directory" >> "$CHECKLIST_PANEL_PROMPT"
}

BG_PID=""
BG_LABEL=""
BG_START=0
BG_CMD=""
BG_MODEL=""
BG_EFFORT=""

cleanup_bg() {
    # A baseline suite must not outlive the run that started it.
    if [[ -n "${BASELINE_BG_PID:-}" ]] && kill -0 "$BASELINE_BG_PID" 2>/dev/null; then
        echo "Stopping the baseline suite"
        kill "$BASELINE_BG_PID" 2>/dev/null || true
        wait "$BASELINE_BG_PID" 2>/dev/null || true
        BASELINE_BG_PID=""
    fi
    if [[ -n "${GREEN_BG_PID:-}" ]] && kill -0 "$GREEN_BG_PID" 2>/dev/null; then
        echo "Stopping background checks"
        kill "$GREEN_BG_PID" 2>/dev/null || true
        wait "$GREEN_BG_PID" 2>/dev/null || true
        GREEN_BG_PID=""
    fi
    if [[ -n "$BG_PID" ]] && kill -0 "$BG_PID" 2>/dev/null; then
        echo "Stopping background stage: $BG_LABEL"
        bash "$ROOT/scripts/lib/terminal-title.sh" --stop-tree "$BG_PID" include-root
        wait "$BG_PID" 2>/dev/null || true
    fi
}
trap on_exit EXIT

start_codex_bg() {
    # panel_kind/panel_source (args 5/6): when set, arg 1 is ignored and the
    # panel's own lens-worker fan-out (run_checklist_panel) runs inside this
    # same background job instead of synchronously before it. Those workers
    # used to finish, blocking, before this function was even called -- so
    # "manual-checklist-base" only ever backgrounded its own synthesis pass,
    # not the specialist packets that pass reads. Implementation and the
    # checklist-base panel (workers and synthesis alike) now start together.
    local prompt_file="$1"
    local output_file="$2"
    local log_name="$3"
    local effort="${4:-}"
    local panel_kind="${5:-}"
    local panel_source="${6:-}"
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
    effort="$(stage_effort_for "$log_name")"
    local -a model_args=()
    local model
    model="$(stage_model_for "$log_name" "${CODEX_MODEL:-}")"
    [[ -n "$model" ]] && model_args=(-m "$model")

    if [[ -z "$panel_kind" ]]; then
        prompt_file="$(resolve_prompt "$prompt_file")"
        require_file "$prompt_file"
        # The reviewer writes a document a human reads, so it gets the output
        # rules the same way an agent stage does.
        if [[ "$log_name" != plan-executability ]]; then
            prompt_file="$(gated_prompt "$prompt_file" "$log_name" reviewer)"
        fi
    fi
    rm -f "$output_file"
    status_stage_context "$log_name" 0 "${model:-}" review

    local -a flags=(
        exec
        --ephemeral
        # Project dirs need not be git repos; the read-only sandbox is the boundary.
        --skip-git-repo-check
        --sandbox read-only
        "${model_args[@]+"${model_args[@]}"}"
        --output-last-message "$output_file"
    )

    if [[ -n "$effort" ]]; then
        flags+=(-c "model_reasoning_effort=$effort")
    fi

    echo
    echo "Starting background reviewer ($cmd) stage: $log_name${effort:+  Effort: $effort}${model:+  Model: $model}"
    echo "Log: $LOG_DIR/${log_name}.log"

    (
        cd "$PROJECT_ROOT"
        local started="$SECONDS" status=0 child=""
        trap 'if [[ -n "$child" ]]; then kill "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi; exit 130' INT TERM
        if [[ -n "$panel_kind" ]]; then
            run_checklist_panel "$panel_kind" "$panel_source"
            prompt_file="$(resolve_prompt "$CHECKLIST_PANEL_PROMPT")"
            require_file "$prompt_file"
            prompt_file="$(gated_prompt "$prompt_file" "$log_name" reviewer)"
        fi
        "${client_cmd[@]}" "${flags[@]}" "$(cat "$prompt_file")" \
            < /dev/null > "$LOG_DIR/${log_name}.log" 2>&1 &
        child=$!
        wait "$child" || status=$?
        child=""
        UNCLE_SPECULATIVE=true perf_record reviewer "$log_name" "$((SECONDS-started))" "$status" \
            "$LOG_DIR/${log_name}.log" "$cmd" "$model" "$effort"
        exit "$status"
    ) &

    BG_PID=$!
    BG_CMD="$cmd"
    BG_MODEL="$model"
    BG_EFFORT="$effort"
    BG_LABEL="$log_name"
    BG_START="$SECONDS"
}

wait_codex_bg() {
    local output_file="$1"

    if [[ -z "$BG_PID" ]]; then
        return 0
    fi

    echo
    echo "Waiting for background Codex stage: $BG_LABEL"

    local pid="$BG_PID"
    local label="$BG_LABEL"
    local status=0
    wait "$pid" || status=$?
    BG_PID=""

    record_codex_cost "$label" "$((SECONDS - BG_START))"

    if [[ "$status" -ne 0 ]]; then
        if context_exhausted "$LOG_DIR/${label}.log"; then
            echo "Background Codex stage $label ran out of context/tokens."
            echo "Change the reviewer model (Configure → reviewer) and re-run to resume this stage."
        else
            echo "Background Codex stage $label failed with status $status."
        fi
        echo "Log: $LOG_DIR/${label}.log"
        exit "$status"
    fi

    require_file "$output_file"
    finish_review_budget "$output_file" "$BG_CMD" "$BG_MODEL" "$BG_EFFORT" "$label" || exit 1
    echo "Background Codex stage complete: $label"
}

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

# The shared supervisor owns the permanent lock.
origin_preflight

# A stop reason belongs to the run that recorded it. Left in place, a
# previous "human" stop would silence the triage bundle on this run's failure.
rm -f "$STATE_DIR/stop-reason"

# Whether this invocation can prove it owns .uncle/workflow/origin, rather than having
# found a leftover one on disk. Computed once here, before this run performs any
# state write, so a run that only *becomes* issue-bound mid-run cannot later
# read as resumed.
ORIGIN_BOUND=0
if [[ -n "$(state_issue "$STATE_FILE")" ]]; then
    ORIGIN_BOUND=1
fi
if [[ -n "${STAGEGATE_ORIGIN_REPO:-}" && -n "${STAGEGATE_ORIGIN_ISSUE:-}" ]]; then
    ORIGIN_BOUND=1
fi

python3 "$ROOT/scripts/lib/session-totals.py" "$STATE_DIR" CHANGE_REQUEST.md \
    "${STAGEGATE_ORIGIN_REPO:-}#${STAGEGATE_ORIGIN_ISSUE:-}" || true

VERDICT_WRITTEN_THIS_RUN=0

# Bind the draft plan to exactly the specification and baseline shown at the
# existing analysis gate. Editing any of them requires a fresh plan afterward.
change_plan_draft_key() {
    local file
    for file in CHANGE_REQUEST.md BASELINE_REPORT.md CHANGE_SPEC.md CHANGE_PLAN.md; do
        [[ -s "$file" ]] || return 1
        hash_file "$file" || return 1
    done
}

# --- Planning, with documents as checkpoints --------------------------------
#
# The combined stage writes BASELINE_REPORT.md, CHANGE_SPEC.md and
# CHANGE_PLAN.md in one context so the plan is written by the model that did
# the baseline. On a large repository that context can run out while the agent
# is still reading: Claude compacts, the model takes the compaction summary for
# a question, answers "what did we do so far", and the turn ends with nothing
# on disk. Three such passes cost twenty minutes and 600k tokens on one issue.
#
# So the stage is judged by the documents it left, not by its exit. Whatever
# was written is kept; a second pass writes only what is missing, in a fresh
# context, with a note saying what happened. Two passes that write nothing
# stop with the cause, which is the request pointing at too much repository.
PLANNING_CONTEXT_LIMIT="${WORKFLOW_CONTEXT_EXHAUSTED_TOKENS:-150000}"

planning_context_used() {
    jq -R -s '[split("\n")[] | fromjson? | select(type == "object" and .type == "result")]
        | (last // {}) | (.usage // {})
        | ((.input_tokens // 0) + (.cache_read_input_tokens // 0) + (.cache_creation_input_tokens // 0))' \
        "$1" 2>/dev/null || printf 0
}

planning_documents_complete() {
    [[ -s BASELINE_REPORT.md && -s CHANGE_SPEC.md && -s CHANGE_PLAN.md ]]
}

# run_planning_pass with-baseline|spec-and-plan [note-file]
run_planning_pass() {
    local prompt="$LOG_DIR/change-planning.prompt.md"
    {
        if [[ "$1" == with-baseline ]]; then
            printf '# Combined baseline, change specification, and planning\n\n'
            printf 'In this single stage and the same model and context, first establish the baseline by running verification commands and write BASELINE_REPORT.md, then write CHANGE_SPEC.md, then use it to write CHANGE_PLAN.md. These are drafts for the existing approval gates. Do not implement source changes.\n\n'
        else
            printf '# Combined change specification and planning\n\n'
            printf 'BASELINE_REPORT.md is already written; read it and do not redo the baseline. In this single stage and the same context, write CHANGE_SPEC.md, then use it to write CHANGE_PLAN.md. These are drafts for the existing approval gates. Do not implement source changes.\n\n'
        fi
        printf 'Write each document to disk the moment its inputs are in hand -- BASELINE_REPORT.md before any reading for the specification, CHANGE_SPEC.md before any reading for the plan. A document on disk survives a context that runs out; work still in progress does not. Grep for the symbols CHANGE_REQUEST.md names and read the surrounding lines; never read a large file end to end.\n\n'
        if [[ -n "${2:-}" && -s "$2" ]]; then
            cat "$2"
            printf '\n\n'
        fi
        if [[ "$1" == with-baseline ]]; then
            cat "$(resolve_prompt prompts/change/baseline.md)"
            printf '\n\n# Then specify the change\n\n'
        fi
        cat "$(resolve_prompt prompts/change/change-spec.md)"
        printf '\n\n# Then plan the specified change\n\n'
        cat "$(resolve_prompt prompts/change/change-plan.md)"
    } > "$prompt"
    UNCLE_COMBINED_CHANGE_PLAN=1 run_claude "$prompt" change-plan \
        "$MODEL_CHANGE_PLAN" "" 120 "$BUDGET_CHANGE_PLAN"
}

run_planning_stage() {
    local pass used missing f note="$STATE_DIR/planning-context-note.md"
    rm -f "$note"
    for pass in 1 2; do
        if [[ -s BASELINE_REPORT.md ]]; then
            run_planning_pass spec-and-plan "$note" || return $?
        else
            run_planning_pass with-baseline "$note" || return $?
        fi
        planning_documents_complete && break
        missing=""
        for f in BASELINE_REPORT.md CHANGE_SPEC.md CHANGE_PLAN.md; do
            [[ -s "$f" ]] || missing="$missing$f "
        done
        used="$(planning_context_used "$LOG_DIR/change-plan.jsonl")"
        case "$used" in ''|*[!0-9]*) used=0 ;; esac
        echo
        if [[ "$used" -ge "$PLANNING_CONTEXT_LIMIT" ]]; then
            echo "The planning stage ran out of context ($used tokens) before writing: $missing"
            echo "Reading a large repository end to end spends the whole context on exploring."
        else
            echo "The planning stage ended without writing: $missing"
        fi
        if [[ "$pass" == 1 ]]; then
            echo "Whatever it wrote is kept; the rest is written in a fresh context."
            {
                printf '## Context note from the driver\n\n'
                printf 'The previous pass of this stage ended after %s tokens without writing: %s\n' "$used" "$missing"
                printf 'Documents already on disk are kept and are not rewritten; write only the missing ones.\n'
                printf 'Grep for the symbols CHANGE_REQUEST.md names instead of reading large files end to end,\n'
                printf 'and write each document as soon as its inputs are in hand.\n'
            } > "$note"
        fi
    done
    rm -f "$note"
    if ! planning_documents_complete; then
        echo "Planning did not complete in two passes. Narrow CHANGE_REQUEST.md, or name the files"
        echo "the change touches so the baseline can go straight to them, then re-run."
        supervision_validation_failed change-plan BASELINE_REPORT.md \
            "planning stage ended twice without completing its documents (context used: $used tokens)" 1 || true
        return 1
    fi
    check_document_budget BASELINE_REPORT.md || return 1
    check_document_budget CHANGE_SPEC.md || return 1
    check_document_budget CHANGE_PLAN.md || return 1
    change_plan_draft_key > "$STATE_DIR/change-plan.draft-key"
}

implementation_complete() {
    verify_approval CHANGE_SPEC.md CHANGE_SPEC
    verify_approval CHANGE_PLAN.md CHANGE_PLAN
    local completion="$STATE_DIR/implementation-completion.txt" line id waiver
    if python3 "$ROOT/scripts/lib/implementation-completion.py" \
        CHANGE_SPEC.md IMPLEMENTATION_NOTES.md > "$completion"; then
        return 0
    fi
    supervision_validation_failed implementation_completion IMPLEMENTATION_NOTES.md \
        "$(head -n 3 "$completion" 2>/dev/null | tr '\n' ' ')" 0
    # Keep rejection evidence intact. Only explicitly waived delivery rows may
    # advance; structural errors, missing IDs, and unrelated waivers still fail.
    [[ -s "$completion" ]] || return 1
    while IFS= read -r line; do
        [[ "$line" =~ ^(AC-[0-9]+):\ requires\ IMPLEMENTED, ]] || return 1
        id="${BASH_REMATCH[1]}"
        waiver="$(waive_file "$id")"
        [[ -s "$waiver" ]] || return 1
        grep -qxF "id: $id" "$waiver" || return 1
        grep -qxF "report: $completion" "$waiver" || return 1
        grep -q '^reason: .*[^[:space:]]' "$waiver" || return 1
    done < "$completion"
    echo "Continuing with recorded implementation waivers; rejected rows remain on record."
    return 0
}

# Claim the PR head branch as a local ref before any stage runs (Issue 60).
# Only a ref is created, never a commit or push; the engine skips unborn or
# detached HEAD and no-remote checkouts, and a name collision stops the build
# here, before the first stage.
change_pr_engine start || exit 1

while true; do
    python3 "$ROOT/scripts/lib/rerun_stage.py" change || exit 1
    state="$(get_state)"
    if declare -f perf_stage >/dev/null; then perf_stage "$state"; fi

    echo
    echo "Current state: $state"

    # Older drivers could advance despite an explicitly partial delivery.
    case "$state" in
        WAIT_IMPLEMENT_APPROVAL|CHECKLIST|EXECUTE_CHECKLIST|VALIDATE_CHECKLIST|FINAL_AUDIT|VALIDATE_AUDIT)
            if ! implementation_complete; then
                echo "Incomplete acceptance delivery; returning to IMPLEMENT."
                cat "$STATE_DIR/implementation-completion.txt"
                rm -f "$APPROVAL_DIR/IMPLEMENTATION_REVIEW.sha256"
                set_state IMPLEMENT
                continue
            fi
            ;;
    esac

    case "$state" in
        DERIVE_BRIEF)
            require_file CHANGE_REQUEST.md
            # A request a human wrote is not ours to rewrite. Derivation runs
            # only when the prerequisite check says rows are still unfilled,
            # which is exactly the seeded-from-an-issue case.
            if python3 "$ROOT/scripts/lib/early-prerequisites.py" \
                    "$DOCUMENT_BUDGET_SOURCE" >/dev/null 2>&1; then
                echo "$DOCUMENT_BUDGET_SOURCE is already stated; skipping derivation."
                set_state ANALYZE
                continue
            fi
            run_claude prompts/derive-brief.md derive-brief \
                "$MODEL_BASELINE" "" 60 "$BUDGET_CHANGE_SPEC"
            require_file CHANGE_REQUEST.md
            set_state WAIT_DERIVE_APPROVAL
            ;;

        WAIT_DERIVE_APPROVAL)
            human_gate APPROVE \
                CHANGE_REQUEST.md DERIVED_BRIEF
            set_state ANALYZE
            ;;

        ANALYZE)
            require_file CHANGE_REQUEST.md
            # A fresh run legitimately claims this checkout for its issue.
            write_origin

            run_planning_stage || exit 1

            set_state WAIT_ANALYSIS_APPROVAL
            ;;

        WAIT_ANALYSIS_APPROVAL)
            human_gate APPROVE \
                BASELINE_REPORT.md BASELINE_REPORT \
                CHANGE_SPEC.md CHANGE_SPEC
            # A newly approved specification starts the evidence chain over.
            envelope_invalidate CHANGE_SPEC
            envelope_write --stage requirements --result pass \
                --evidence BASELINE_REPORT.md CHANGE_SPEC.md \
                --approval BASELINE_REPORT CHANGE_SPEC \
                --producer-stage change-spec --producer-kind agent
            set_state PLAN
            ;;

        PLAN)
            verify_approval BASELINE_REPORT.md BASELINE_REPORT
            verify_approval CHANGE_SPEC.md CHANGE_SPEC

            # First point in the pipeline where the command list has been
            # approved and the tree is still untouched, which is the only
            # window in which a baseline means anything.
            start_green_baseline_bg

            if [[ -s "$STATE_DIR/change-plan.draft-key" ]] && \
                    [[ "$(cat "$STATE_DIR/change-plan.draft-key")" == "$(change_plan_draft_key)" ]]; then
                echo 'Using the plan drafted with the approved change specification.'
            else
                # Legacy resume, or edits made while approving the specification.
                run_claude prompts/change/change-plan.md change-plan \
                    "$MODEL_CHANGE_PLAN" "" 120 "$BUDGET_CHANGE_PLAN"
                require_file CHANGE_PLAN.md
                check_document_budget CHANGE_PLAN.md || exit 1
            fi

            envelope_invalidate CHANGE_PLAN
            envelope_write --stage plan --result pass \
                --evidence CHANGE_PLAN.md \
                --producer-stage change-plan --producer-kind agent
            set_state ADVERSARIAL_REVIEW
            ;;

        ADVERSARIAL_REVIEW)

            # Written before the reviewer runs: a reviewer that never returns
            # leaves the reason nothing was verified, and blocks release.
            envelope_write --stage review --result unavailable --reason 'reviewer did not complete'
            run_adversarial_review_panel
            run_codex \
                "${ADVERSARIAL_REVIEW_PROMPT:-prompts/change/adversarial-review.md}" \
                ADVERSARIAL_REVIEW.md \
                adversarial-review \
                "$CODEX_EFFORT_REVIEW"

            set_state VALIDATE_ADVERSARIAL_REVIEW
            ;;

        VALIDATE_ADVERSARIAL_REVIEW)
            verify_approval BASELINE_REPORT.md BASELINE_REPORT
            verify_approval CHANGE_SPEC.md CHANGE_SPEC
            validation_error="$(python3 "$ROOT/scripts/lib/adversarial-context.py" --validate ADVERSARIAL_REVIEW.md 2>&1)" || {
                # A shape the repairer can settle on its own is not worth a
                # stopped run. It only fixes deviations with one reading -- a
                # leaked preamble, a bold label that should be a heading -- and
                # refuses anything needing judgment, so a real defect still
                # stops here. Re-validate after; the repair is not trusted.
                if python3 "$ROOT/scripts/lib/repair_document_format.py" ADVERSARIAL_REVIEW.md; then
                    if validation_error="$(python3 "$ROOT/scripts/lib/adversarial-context.py" --validate ADVERSARIAL_REVIEW.md 2>&1)"; then
                        echo "Repaired the review format; continuing."
                        rm -f "$STATE_DIR/validation-error.txt"
                        check_document_budget ADVERSARIAL_REVIEW.md || exit 1
                        write_review_envelope
                        set_state WAIT_PLAN_APPROVAL
                        continue
                    fi
                fi
                envelope_write --stage review --result fail --reason "validation: ${validation_error%%$'\n'*}"
                printf '%s\n' "$validation_error" >&2
                printf '%s\n' "$validation_error" > "$STATE_DIR/validation-error.txt"
                printf '%s\n' "validation: $validation_error" > "$STATE_DIR/stop-reason"
                supervision_validation_failed adversarial-review ADVERSARIAL_REVIEW.md "$validation_error"
                exit 1
            }
            rm -f "$STATE_DIR/validation-error.txt"
            check_document_budget ADVERSARIAL_REVIEW.md || exit 1
            write_review_envelope
            set_state WAIT_PLAN_APPROVAL
            ;;

        WAIT_PLAN_APPROVAL)
            # One gate for the plan and the review of it: UPDATED_PLAN verifies
            # both approvals, and the reopen map sends either document here.
            printf '%s\n' WAIT_PLAN_APPROVAL > "$STATE_DIR/approval-route"
            human_gate ACKNOWLEDGE \
                CHANGE_PLAN.md CHANGE_PLAN \
                ADVERSARIAL_REVIEW.md ADVERSARIAL_REVIEW
            set_state UPDATED_PLAN
            ;;

        UPDATED_PLAN)
            verify_approval BASELINE_REPORT.md BASELINE_REPORT
            verify_approval CHANGE_SPEC.md CHANGE_SPEC
            verify_approval CHANGE_PLAN.md CHANGE_PLAN
            verify_approval ADVERSARIAL_REVIEW.md ADVERSARIAL_REVIEW

            # The review response revises CHANGE_PLAN.md in place rather than
            # writing a second plan. A separate UPDATED_CHANGE_PLAN.md restated
            # every section of the plan it superseded, and five later stages
            # then carried the longer copy in context. Snapshot the approved
            # pre-review text first: nothing reads it, so it costs no tokens,
            # and it keeps the record of what the review actually changed.
            cp CHANGE_PLAN.md "$STATE_DIR/CHANGE_PLAN.pre-review.md"

            run_updated_change_plan_panel
            run_claude "${UPDATED_PLAN_PROMPT:-prompts/change/updated-change-plan.md}" updated-change-plan \
                "$MODEL_UPDATED_PLAN" "$EFFORT_UPDATED_PLAN" 60 \
                "$BUDGET_UPDATED_PLAN"
            set_state VALIDATE_UPDATED_PLAN
            ;;

        VALIDATE_UPDATED_PLAN)
            # Probe only: would code written from the pre-review plan have
            # survived the review? The snapshot above already holds that plan,
            # so this costs a diff. Acts on nothing, cannot fail the stage.
            if [[ -s "$STATE_DIR/CHANGE_PLAN.pre-review.md" && -s CHANGE_PLAN.md ]]; then
                python3 -B "$ROOT/scripts/lib/plan_drift.py" \
                    "$STATE_DIR/CHANGE_PLAN.pre-review.md" CHANGE_PLAN.md \
                    "$STATE_DIR/plan-drift.json" 2>/dev/null || true
            fi
            verify_approval BASELINE_REPORT.md BASELINE_REPORT
            verify_approval CHANGE_SPEC.md CHANGE_SPEC
            verify_approval ADVERSARIAL_REVIEW.md ADVERSARIAL_REVIEW
            require_file CHANGE_PLAN.md
            check_document_budget CHANGE_PLAN.md || exit 1

            set_state WAIT_UPDATED_PLAN_APPROVAL
            ;;

        WAIT_UPDATED_PLAN_APPROVAL)
            plan_status=0
            plan_assess || plan_status=$?
            case "$plan_status" in 0) ;; 10) continue ;; *) exit 1 ;; esac
            # The review response revised CHANGE_PLAN.md in place, so the
            # ACKNOWLEDGE hash taken at WAIT_PLAN_APPROVAL names text that no
            # longer exists. Without this gate IMPLEMENT finds the plan
            # "changed after approval", reopens WAIT_PLAN_APPROVAL, the plan is
            # revised again, and the run loops. Re-approving here records the
            # hash of the text implementation will run against.
            # The gate does not open while a blocking review finding has no
            # disposition row in the revised plan.
            envelope_py plan-gate ADVERSARIAL_REVIEW.md CHANGE_PLAN.md || exit 1
            printf '%s\n' WAIT_UPDATED_PLAN_APPROVAL > "$STATE_DIR/approval-route"
            human_gate APPROVE \
                CHANGE_PLAN.md CHANGE_PLAN
            plan_review_input=()
            [[ -f ADVERSARIAL_REVIEW.md ]] && plan_review_input=(--input "review=$(hash_file ADVERSARIAL_REVIEW.md)")
            envelope_write --stage plan --result pass \
                --evidence CHANGE_PLAN.md ADVERSARIAL_REVIEW.md \
                --dispositions CHANGE_PLAN.md ${plan_review_input[@]+"${plan_review_input[@]}"} \
                --approval CHANGE_PLAN ADVERSARIAL_REVIEW --reapprovals \
                --producer-stage updated-change-plan --producer-kind agent
            set_state IMPLEMENT
            ;;

        IMPLEMENT)
            # Before a single line of code is written: the baseline only means
            # anything against the unmodified tree.
            wait_green_baseline_bg
            verify_approval CHANGE_PLAN.md CHANGE_PLAN
            verify_approval CHANGE_SPEC.md CHANGE_SPEC
            plan_status=0
            plan_before_write || plan_status=$?
            case "$plan_status" in 0|22) ;; 10) continue ;; *) exit 1 ;; esac

            # Re-entering implementation withdraws every claim made about
            # the previous one; the directory itself turns attestation on.
            envelope_invalidate IMPLEMENT

            # Taken before the agent runs, so an untracked file that was
            # already sitting in the operator's checkout is not read as
            # something this change created.
            # Preserve the original baseline across incomplete-delivery resumes;
            # files the first attempt created must remain part of the review.
            if [[ ! -e "$UNTRACKED_BASELINE" ]]; then
                snapshot_untracked "$UNTRACKED_BASELINE"
            fi

            # The verification checklist is derived from the frozen, approved
            # artifacts, so it can be written while the implementation runs
            # instead of after it. Its prompt forbids reading source, which
            # would otherwise race Claude's in-flight edits; anything that
            # genuinely depends on the implementation is added by the delta
            # pass in the CHECKLIST state.
            if [[ "$PARALLEL_CHECKLIST" == "1" ]]; then
                start_codex_bg \
                    "" \
                    "$STATE_DIR/MANUAL_CHECKLIST.base.md" \
                    manual-checklist-base \
                    "$CODEX_EFFORT_CHECKLIST" \
                    base prompts/change/manual-checklist-base.md
            fi

            if [[ -s IMPLEMENTATION_NOTES.md ]] && implementation_has_changes && implementation_complete; then
                echo "Existing implementation delivery accepted; continuing to verification."
            elif [[ "$plan_status" == 22 ]]; then
                echo 'Verification-only resume finished; checking delivery.'
            elif [[ "$(cat "$STATE_DIR/implementation-completion-repair" 2>/dev/null || true)" == "$(hash_file CHANGE_PLAN.md)" ]]; then
                echo 'Implementation remains incomplete; automatic repair already attempted for this plan.'
            elif stepwise_implementation_enabled && { ! plan_executability_enabled || ! grep -q '"verdict": "DECISION"' "$PLAN_ASSESS_DIR/assessment.json"; }; then
                step_status=0
                envelope_guard_begin
                run_stepwise_implementation prompts/change/implement-change.md || step_status=$?
                envelope_guard_end
                case "$step_status" in 0) ;; 10) plan_revise; continue ;; *) exit 1 ;; esac
            else
                compose_implementation_prompt \
                    prompts/change/implement-change.md \
                    "$STATE_DIR/implement-change.resolved.md"

                envelope_guard_begin
                run_claude "$STATE_DIR/implement-change.resolved.md" implementation \
                    "$MODEL_IMPLEMENT" "" 200 "$BUDGET_IMPLEMENT"
                envelope_guard_end
            fi
            plan_status=0
            plan_after_write || plan_status=$?
            case "$plan_status" in 0) ;; 27) continue ;; 10) plan_revise; continue ;; *) exit 1 ;; esac
            require_file IMPLEMENTATION_NOTES.md
            require_file CHANGE_TEST_REPORT.md
            check_document_budget IMPLEMENTATION_NOTES.md || exit 1
            check_document_budget CHANGE_TEST_REPORT.md || exit 1

            if ! implementation_has_changes || ! implementation_complete; then
                repair_digest="$(hash_file CHANGE_PLAN.md)"
                if [[ "$(cat "$STATE_DIR/implementation-completion-repair" 2>/dev/null || true)" == "$repair_digest" ]]; then
                    echo "Implementation remains incomplete; automatic repair already attempted for this plan."
                    echo "See IMPLEMENTATION_NOTES.md and $STATE_DIR/implementation-completion.txt; resume after resolving the blockers."
                    choice_status=0
                    implementation_incomplete_choice || choice_status=$?
                    case "$choice_status" in
                        0) continue ;;
                        2) ;;
                        *) triage_stop_reason "$STATE_DIR" human; exit 1 ;;
                    esac
                else
                    echo "Implementation is incomplete. Attempting repair once."
                    printf '%s\n' "$repair_digest" > "$STATE_DIR/implementation-completion-repair"
                    compose_implementation_prompt prompts/change/implement-change.md "$STATE_DIR/implementation-repair.md"
                    cat >> "$STATE_DIR/implementation-repair.md" <<'REPAIR'

The previous implementation did not deliver all required acceptance criteria.
Read IMPLEMENTATION_NOTES.md and resolve routine implementation choices within
the approved scope, then implement the requested behavior and its tests.
Do not treat writing reports or rerunning baseline tests as implementation.
Do not bypass a genuine unresolved approval requirement: explain the precise
decision needed if you cannot proceed. The driver will keep IMPLEMENT pending
if no change is delivered. Update the implementation notes and test report.
Read .uncle/workflow/implementation-completion.txt when present for rejected
acceptance rows. Deliver the missing behavior, not merely a changed status.
Missing credentials for live verification do not prevent independent coding
and mocked tests. Complete those first; report any remaining live check as
BLOCKED without claiming acceptance. Do not change approved scope or protected
tests without the required approval.
REPAIR
                    plan_status=0
                    plan_before_write repair || plan_status=$?
                    case "$plan_status" in 0) ;; 27) continue ;; 10) plan_revise; continue ;; *) exit 1 ;; esac
                    envelope_guard_begin
                    run_claude "$STATE_DIR/implementation-repair.md" implementation \
                        "$MODEL_IMPLEMENT" "" 200 "$BUDGET_IMPLEMENT"
                    envelope_guard_end
                    plan_status=0
                    plan_after_write || plan_status=$?
                    case "$plan_status" in 0) ;; 27) continue ;; 10) plan_revise; continue ;; *) exit 1 ;; esac
                    if ! implementation_has_changes || ! implementation_complete; then
                        echo "Implementation remains incomplete: required delivery is missing."
                        echo "Resolve the blockers in IMPLEMENTATION_NOTES.md and CHANGE_PLAN.md, then resume."
                        echo "The workflow remains at IMPLEMENT; it cannot advance to final audit."
                        choice_status=0
                        implementation_incomplete_choice || choice_status=$?
                        case "$choice_status" in
                            0) continue ;;
                            2) ;;
                            *) triage_stop_reason "$STATE_DIR" human; exit 1 ;;
                        esac
                    fi
                    require_file IMPLEMENTATION_NOTES.md
                    require_file CHANGE_TEST_REPORT.md
                    check_document_budget IMPLEMENTATION_NOTES.md || exit 1
                    check_document_budget CHANGE_TEST_REPORT.md || exit 1
                fi
            fi

            check_scope_deviations

            # Whitespace tidying is cosmetic. Under `set -e` a bare call
            # made a nonzero status kill the driver between a successful
            # stage and the record of it, leaving no stop reason and no
            # completion marker -- a stage that had worked looked like a
            # crash. Report it and continue; the gate still sees the diff.
            python3 "$ROOT/scripts/lib/fix-report-whitespace.py" || \
                echo "Whitespace tidy reported issues; continuing."
            git diff --stat > "$STATE_DIR/change-stat.txt"

            # Independent of the agent that just claimed its checks passed.
            # The result is carried to the gate rather than ending the run: a
            # regression is for the operator to weigh against the diff, and
            # killing the run here would throw away the stage that produced it.
            run_green_check || true

            # Probe only: records what a parallel implementation would have
            # done and whether the plan's file ownership matched the tree.
            # Runs nothing in parallel and cannot fail the stage.
            python3 -B "$ROOT/scripts/lib/step_groups.py" CHANGE_PLAN.md . \
                > "$STATE_DIR/step-groups.json" 2>/dev/null || true
            write_verification_envelope
            plan_delivery_summary

            # Waited for before the gate, not after: declining the gate exits
            # the driver, and cleanup_bg would kill a checklist run that is
            # already nearly paid for.
            if [[ "$PARALLEL_CHECKLIST" == "1" ]]; then
                wait_codex_bg "$STATE_DIR/MANUAL_CHECKLIST.base.md"
            fi

            set_state WAIT_IMPLEMENT_APPROVAL
            ;;

        WAIT_IMPLEMENT_APPROVAL)
            green_regressed="$(green_regressions "$GREEN_CLASS")"

            if [[ "$DIFF_GATE" != "1" ]]; then
                if [[ "$green_regressed" -gt 0 ]]; then
                    echo
                    echo "Refusing to continue: $green_regressed verification"
                    echo "check(s) regressed, and WORKFLOW_DIFF_GATE=0 leaves no"
                    echo "human gate to weigh that against the diff."
                    echo "Fix the regression, or re-enable the gate."
                    exit 1
                fi
                echo
                echo "Implementation gate disabled (WORKFLOW_DIFF_GATE=0);" \
                     "no human reads the diff."
                # Recorded as a required gate nobody answered: the attestation
                # cannot say a person read this diff.
                mkdir -p "$APPROVAL_DIR"
                printf 'SKIPPED\n' > "$APPROVAL_DIR/IMPLEMENTATION_REVIEW.gate-action"
                printf 'disabled:WORKFLOW_DIFF_GATE=0\n' > "$APPROVAL_DIR/IMPLEMENTATION_REVIEW.delegated-by"
                printf '\n' > "$APPROVAL_DIR/IMPLEMENTATION_REVIEW.approved-by"
                write_implementation_envelope unavailable 'WORKFLOW_DIFF_GATE=0: no human read the diff'
                set_state CHECKLIST
                continue
            fi

            build_implementation_review

            gate_action=APPROVE
            if [[ "$green_regressed" -gt 0 ]]; then
                gate_action=OVERRIDE
                echo
                echo "=================================================="
                echo "GREEN CHECK FAILED: $green_regressed regression(s)"
                echo "=================================================="
                echo
                echo "Commands that passed before this change now fail. They are"
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

            human_gate "$gate_action" "$REVIEW_FILE" IMPLEMENTATION_REVIEW
            WORKFLOW_UNTRACKED_BASELINE="$WORKFLOW_UNTRACKED_BASELINE" python3 -B "$ROOT/scripts/lib/approval_snapshot.py" record "$STATE_DIR" || exit 1
            write_implementation_envelope pass

            if [[ "$green_regressed" -gt 0 ]]; then
                printf '%s\t%s\n' \
                    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
                    "$green_regressed regression(s) overridden" \
                    > "$GREEN_OVERRIDE_FILE"
            else
                rm -f "$GREEN_OVERRIDE_FILE"
            fi

            set_state CHECKLIST
            ;;

        CHECKLIST)
            if [[ "$DIFF_GATE" == "1" ]]; then
                verify_implementation_review
            fi

            if [[ "$PARALLEL_CHECKLIST" == "1" ]]; then
                require_file "$STATE_DIR/MANUAL_CHECKLIST.base.md"
                run_checklist_panel delta prompts/change/manual-checklist-delta.md
                run_codex \
                    "$CHECKLIST_PANEL_PROMPT" \
                    MANUAL_CHECKLIST.md \
                    manual-checklist-delta \
                    "$CODEX_EFFORT_CHECKLIST"
            else
                run_codex \
                    prompts/change/manual-checklist.md \
                    MANUAL_CHECKLIST.md \
                    manual-checklist \
                    "$CODEX_EFFORT_CHECKLIST"
            fi
            set_state VALIDATE_MANUAL_CHECKLIST
            ;;

        VALIDATE_MANUAL_CHECKLIST)
            python3 "$ROOT/scripts/lib/checklist_document.py" MANUAL_CHECKLIST.md || exit 1
            set_state EXECUTE_CHECKLIST
            ;;

        EXECUTE_CHECKLIST)
            if ! python3 "$ROOT/scripts/lib/checklist_document.py" MANUAL_CHECKLIST.md; then
                set_state VALIDATE_MANUAL_CHECKLIST
                exit 1
            fi
            start_green_check_bg
            plan_delivery_summary
            snapshot_checklist_groups
            snapshot_checklist_checks
            ensure_checklist_runner execute-checklist || exit 1
            run_parallel_checklist_workers
            PROGRESS_TOTAL="$(grep -oE 'MC-[0-9]+' MANUAL_CHECKLIST.md 2>/dev/null \
                | sort -u | grep -c . || echo 0)"
            PROGRESS_LABEL="checklist"
            run_claude "${CHECKLIST_EXECUTE_PROMPT:-prompts/change/execute-change-checklist.md}" execute-checklist \
                "$MODEL_EXECUTE" "$EFFORT_EXECUTE" 200 "${CHECKLIST_SYNTHESIS_BUDGET:-$BUDGET_EXECUTE}"
            PROGRESS_TOTAL=0
            wait_green_check_bg || exit $?
            set_state VALIDATE_CHECKLIST
            ;;

        VALIDATE_CHECKLIST)
            echo "Validating saved checklist reports; checks will not be rerun."
            require_file VERIFICATION_REPORT.md
            check_document_budget VERIFICATION_REPORT.md || exit 1
            if [[ -e DEFECTS.md ]]; then
                check_document_budget DEFECTS.md || exit 1
            fi
            set_state FINAL_AUDIT
            ;;

        FINAL_AUDIT)
            # Remove any prior audit first: run_codex's require_file then treats
            # the file's existence as proof this invocation produced it, so a
            # reviewer call that exits 0 without writing cannot be read as fresh.
            envelope_invalidate FINAL_AUDIT
            envelope_write --stage audit --result unavailable --reason 'reviewer did not complete'
            if git rev-parse --verify HEAD >/dev/null 2>&1; then change_pr_engine freeze || exit 1; fi
            rm -f FINAL_AUDIT.md
            run_final_audit_panel
            run_codex \
                "${FINAL_AUDIT_PROMPT:-prompts/change/final-audit.md}" \
                FINAL_AUDIT.md \
                final-audit \
                "$CODEX_EFFORT_AUDIT"

            set_state VALIDATE_AUDIT
            ;;

        VALIDATE_AUDIT)
            echo "Validating saved audit; the reviewer will not be rerun."
            require_file FINAL_AUDIT.md
            python3 "$ROOT/scripts/lib/final-audit-context.py" --validate FINAL_AUDIT.md || {
                envelope_write --stage audit --result fail --reason 'audit format invalid'
                exit 1
            }
            audit_class="$(classify_audit_verdict FINAL_AUDIT.md)"
            printf '%s\t%s\t%s\n' \
                "${STAGEGATE_RUN_ID:--}" \
                "$audit_class" \
                "$(hash_file FINAL_AUDIT.md)" \
                > "$VERDICT_FILE"
            if git rev-parse --verify HEAD >/dev/null 2>&1; then change_pr_engine bind || exit 1; fi
            # The audit claim: pass only for a READY verdict. An override
            # recorded later never rewrites it; release reads this file.
            audit_result=fail
            case "$audit_class" in READY|READY_WITH_NON_BLOCKING_ISSUES) audit_result=pass ;; esac
            audit_artifact="$(change_artifact)"
            envelope_write --stage audit --result "$audit_result" --reason "$audit_class" \
                ${audit_artifact:+--input "artifact=$audit_artifact"} \
                --evidence FINAL_AUDIT.md VERIFICATION_REPORT.md \
                --producer-stage final-audit --producer-kind reviewer
            echo "Audit verdict: $audit_class"
            VERDICT_WRITTEN_THIS_RUN=1

            # The verdict was already computed here; it just did not decide
            # anything. A run that ends on NOT READY — or on an audit whose
            # last line cannot be read as a verdict at all — reached COMPLETE
            # and reported success.
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
            audit_class="$(awk -F'\t' 'NR == 1 {print $2}' "$VERDICT_FILE")"

            # Recover an interruption after saving READY but before COMPLETE.
            if [[ "$audit_class" == READY ]]; then
                [[ "$(awk -F'\t' 'NR == 1 {print $3}' "$VERDICT_FILE")" == "$(hash_file FINAL_AUDIT.md)" ]] || exit 1
                python3 "$ROOT/scripts/lib/audit-findings.py" FINAL_AUDIT.md "$STATE_DIR" --check || exit 1
                set_state COMPLETE
                continue
            fi

            if [[ "$audit_class" == NOT_READY ]]; then
                audit_hash="$(hash_file FINAL_AUDIT.md)"
                if [[ "$(classify_audit_verdict FINAL_AUDIT.md)" != NOT_READY ]] \
                    || [[ "$(awk -F'\t' 'NR == 1 {print $3}' "$VERDICT_FILE")" != "$audit_hash" ]]; then
                    echo "The audit changed since its verdict was recorded; rerun FINAL_AUDIT."
                    exit 1
                fi
                # Each finding needs an explicit decision, including in an
                # unattended run. EOF leaves the saved review pending.
                python3 "$ROOT/scripts/lib/audit-findings.py" FINAL_AUDIT.md "$STATE_DIR" || exit 1
                [[ "$(hash_file FINAL_AUDIT.md)" == "$audit_hash" ]] || exit 1
                cp "$VERDICT_FILE" "$STATE_DIR/audit-verdict.original"
                printf '%s\t%s\t%s\n' "${STAGEGATE_RUN_ID:--}" "READY" "$audit_hash" > "$VERDICT_FILE"
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
                echo "The independent auditor says this change is not ready."
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
            echo "  ./scripts/change-workflow.sh"
            echo
            echo "or record an explicit decision to finish anyway. An override"
            echo "is written to $AUDIT_OVERRIDE_FILE, reported at COMPLETE, and"
            echo "never closes the originating issue."

            human_gate OVERRIDE FINAL_AUDIT.md FINAL_AUDIT_OVERRIDE

            printf '%s\t%s\t%s\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
                "$audit_class" \
                "$(hash_file FINAL_AUDIT.md)" \
                > "$AUDIT_OVERRIDE_FILE"

            set_state COMPLETE
            ;;

        COMPLETE)
            echo
            if [[ -s "$STATE_DIR/delivery-summary.tsv" ]] && grep -q $'\tWAIVED\t' "$STATE_DIR/delivery-summary.tsv"; then
                echo "Change workflow complete with waived acceptance."
            else
                echo "Change workflow complete."
            fi
            if [[ -s "$VERDICT_FILE" ]]; then
                echo "Build verdict: $(awk -F'\t' 'NR == 1 {print $2}' "$VERDICT_FILE")"
            fi
            echo
            echo "Review:"
            echo "  CHANGE_TEST_REPORT.md"
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
                echo "  The originating issue was not closed."
            fi
            if [[ -s "$LEDGER_FILE" ]]; then
                echo
                echo "Cost ledger ($LEDGER_FILE):"
                column -t -s "$(printf '\t')" < "$LEDGER_FILE" | sed 's/^/  /'
                echo
                echo "  Total Claude spend: \$$(ledger_total)"
                echo "  (Codex stages report tokens only; see the cache_w column.)"
            fi
            # An unattended run reached the end; it did not earn the same
            # sentence as one a person signed off. Say how many judgments were
            # skipped and where they are recorded.
            if [[ -s "$UNATTENDED_FILE" ]]; then
                echo
                echo "Unattended run: $(wc -l < "$UNATTENDED_FILE" | tr -d ' ') gate(s) passed with no human review."
                cut -f2,3 "$UNATTENDED_FILE" | sed 's/^/  /'
                echo "  Ledger: $UNATTENDED_FILE"
                echo "Waived checks were not performed. They are not passes, and this"
                echo "summary is the only place that says so out loud."
            fi
            triage_print_actions "$STATE_DIR"
            if git rev-parse --verify HEAD >/dev/null 2>&1; then
                change_pr_complete
            elif [[ -s "$ORIGIN_FILE" ]]; then
                echo "Build complete without a commit. PR publication requires an existing base commit; the issue remains open."
            else
                echo "Build complete without a commit. PR publication requires an existing base commit; no PR was created."
            fi
            exit 0
            ;;

        *)
            echo "Unknown workflow state: $state"
            echo "Delete $STATE_FILE to restart from the beginning."
            exit 1
            ;;
    esac
done

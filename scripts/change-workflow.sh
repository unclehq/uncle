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

STATE_DIR=".uncle/workflow"
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
MODEL_BASELINE="${WORKFLOW_MODEL_BASELINE-kimi}"
MODEL_CHANGE_SPEC="${WORKFLOW_MODEL_CHANGE_SPEC-kimi}"
MODEL_CHANGE_PLAN="${WORKFLOW_MODEL_CHANGE_PLAN-opus}"
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
# Off by default: it changes how the most consequential stage runs, and a step
# boundary in the wrong place costs coherence, which is worth more than tokens.
STEPWISE_IMPLEMENT="${WORKFLOW_STEPWISE_IMPLEMENT:-0}"

# Write the Codex verification checklist concurrently with implementation.
# Set to 0 to fall back to the serial single-shot checklist stage.
PARALLEL_CHECKLIST="${WORKFLOW_PARALLEL_CHECKLIST:-1}"

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
    local var fallback
    if [[ -n "${WORKFLOW_AGENT_CMD:-}" ]]; then
        fallback="$WORKFLOW_AGENT_CMD"
    elif uncle_has_config; then
        fallback="$(uncle_stage_cmd "$1")"
    else
        fallback="$AGENT_CMD"
    fi
    var="$(stage_var AGENT_CMD "$1")"
    eval "printf '%s' \"\${$var:-$fallback}\""
}

stage_reviewer_cmd() {
    local var fallback
    if [[ -n "${WORKFLOW_REVIEWER_CMD:-}" ]]; then
        fallback="$WORKFLOW_REVIEWER_CMD"
    elif uncle_has_config; then
        fallback="$(uncle_stage_cmd "$1")"
    else
        fallback="$REVIEWER_CMD"
    fi
    var="$(stage_var REVIEWER_CMD "$1")"
    eval "printf '%s' \"\${$var:-$fallback}\""
}

stage_effort_for() {
    uncle_effective_stage_effort "$1"
}

stage_model_for() {
    local var fallback="$2"
    uncle_has_config && fallback="$(uncle_stage_model "$1")"
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
. "$ROOT/scripts/lib/checklist-capability.sh"
. "$ROOT/scripts/lib/performance.sh"
. "$ROOT/scripts/lib/stage-config.sh"

require_file() {
    if [[ ! -s "$1" ]]; then
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

set_state() {
    state_write "$STATE_FILE" "$1" "$(current_issue)"
}

get_state() {
    state_read "$STATE_FILE" ANALYZE
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
            trap 'cleanup_bg; release_lock' EXIT
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

# --- Driver-side issue close (BEH-D) ----------------------------------------
# Fires when this process produced the verdict record, or — on a rerun that
# lands on COMPLETE with no close marker — when the record names this same
# concrete run id. A recorded '-' is the unset-run-id sentinel: it must never
# be read as matching an unset STAGEGATE_RUN_ID, so it never enables the retry.

close_origin_issue_if_ready() {
    local recorded owns=0

    if [[ ! -s "$ORIGIN_FILE" || -e "$MARKER_FILE" ]]; then
        return 0
    fi

    # Closing the issue tells everyone watching it that a person accepted this
    # change. On an unattended run nobody did, and the claim would be visible
    # outside the repository where it cannot be taken back quietly. Leave it
    # open; the marker is not written, so a later attended run still closes it.
    if [[ -s "$UNATTENDED_FILE" ]]; then
        echo "Unattended run: leaving the originating issue open for a human to close."
        return 0
    fi

    if [[ "$VERDICT_WRITTEN_THIS_RUN" == "1" ]]; then
        owns=1
    elif [[ -s "$VERDICT_FILE" ]]; then
        recorded="$(head -n 1 "$VERDICT_FILE" | awk -F'\t' '{printf "%s", $1}')"
        if [[ -n "$recorded" && "$recorded" != "-" \
            && "$recorded" == "${STAGEGATE_RUN_ID:-}" ]]; then
            owns=1
        fi
    fi

    if [[ "$owns" != "1" ]]; then
        return 0
    fi

    # A failed close never fails the run: the change itself completed, and the
    # missing marker leaves a later rerun eligible to retry.
    issue_close_if_ready \
        "${STAGEGATE_RUN_ID:--}" \
        "$(origin_field "$ORIGIN_FILE" 1)" \
        "$(origin_field "$ORIGIN_FILE" 2)" \
        "$VERDICT_FILE" "$ORIGIN_FILE" FINAL_AUDIT.md "$MARKER_FILE" \
        "$CLOSE_ISSUE" "$ORIGIN_BOUND" "$owns" \
        "$(origin_fetch_method "$ORIGIN_FILE")" || true
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
    require_file "$approval"

    local expected
    local actual

    expected="$(cat "$approval")"
    actual="$(hash_file "$file")"

    if [[ "$expected" != "$actual" ]]; then
        echo "$file changed after approval."
        echo "Review and approve the new contents."
        exit 1
    fi
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
            printf '%s\n' "$([[ "${UNATTENDED:-0}" == 1 ]] && printf unattended || printf '%s' "${UNCLE_APPROVAL_NAME:-}")" > "$APPROVAL_DIR/${names[$j]}.approved-by"
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

    # Closed stdin here would abort the driver under `set -e` before the Y/N
    # prompt, so EOF is routed to the same decline path as any other non-answer.
    local prompt="Press ENTER after reviewing..."
    if [[ "${#files[@]}" -gt 1 ]]; then
        prompt="Press ENTER after reviewing all documents above..."
    fi
    # read -p hides the prompt on the TUI's piped stdin. Emit it explicitly
    # so the TUI can open its review dialog before the approval question.
    printf '%s' "$prompt"
    if ! read -r; then
        if declare -f perf_record > /dev/null; then perf_record approval "${names[*]}" "$((SECONDS-gate_start))" 1; fi
        echo
        echo "Gate not accepted. Workflow remains paused."
        exit 0
    fi

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
    gate_prompt "Ready to $verb $targets? [Y/N] "
    # IFS= keeps surrounding whitespace, so " y" is not an approval. `|| true`
    # keeps EOF from tripping `set -e` before the decline path runs.
    IFS= read -r response || true

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
        printf '%s\n' "$([[ "${UNATTENDED:-0}" == 1 ]] && printf unattended || printf '%s' "${UNCLE_APPROVAL_NAME:-}")" > "$APPROVAL_DIR/${names[$i]}.approved-by"
        echo "Recorded approval for ${files[$i]}"
    done
    if declare -f perf_record > /dev/null; then perf_record approval "${names[*]}" "$((SECONDS-gate_start))" 0; fi
}

# Render Claude's streaming JSON event feed as readable progress. Startup
# warnings and other non-JSON lines are ignored rather than making jq fail.
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

    if ! verify_parallel_groups BASELINE_REPORT.md "$GREEN_CMDS" > "$STATE_DIR/green-check.groups"; then
        echo 'Invalid Parallel verification groups in BASELINE_REPORT.md.'
        parallel_groups_format_hint
        exit 1
    fi
    green_run "$GREEN_CMDS" "$GREEN_BASE" "$LOG_DIR/green-check-baseline.log" "" "$STATE_DIR/green-check.groups" || exit $?
    hash_file BASELINE_REPORT.md > "$GREEN_SOURCE"
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
    if ! verify_parallel_groups BASELINE_REPORT.md "$GREEN_CMDS" > "$STATE_DIR/green-check.groups"; then
        echo 'Invalid Parallel verification groups in BASELINE_REPORT.md.'
        parallel_groups_format_hint
        exit 1
    fi
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

# --- Post-implementation review document ------------------------------------

# Rebuilt from the working tree every time the gate opens, so the approval
# digest attests to the tree rather than to a file somebody could edit.
build_implementation_review() {
    write_change_diff "$DIFF_FILE"
    write_implementation_review "$REVIEW_FILE" "$DIFF_FILE" "$GREEN_MD" \
        IMPLEMENTATION_NOTES.md CHANGE_TEST_REPORT.md
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

# One invocation per implementation-sequence step, each starting cold.
#
# IMPLEMENTATION_NOTES.md is the handoff: every step appends to it, and the
# next step reads it instead of inheriting a transcript. The code already
# written is on disk, which is the other half of the handoff.
run_stepwise_implementation() {
    local base="$1"
    local steps_file="$STATE_DIR/implement-steps.txt"
    local done_file="$STATE_DIR/implement-step-done"

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

    # Split the single stage's caps across the steps rather than multiplying
    # them: the point is to spend fewer tokens, not to authorise more.
    local turns=$(( 200 / total ))
    [[ "$turns" -lt 40 ]] && turns=40

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
            if [[ "$i" -eq "$total" ]]; then
                echo
                echo "This is the final step. After it, run the full gate from"
                echo "CHANGE_PLAN.md's automated-test strategy and write"
                echo "CHANGE_TEST_REPORT.md covering the whole change, not only"
                echo "this step."
            else
                echo
                echo "Do not run the full suite; the final step does that once."
            fi
        } >> "$prompt"

        echo
        echo "Implementation step $i/$total: ${step:0:70}"
        run_claude "$prompt" "implementation-step-$i" \
            "$MODEL_IMPLEMENT" "" "$turns" "$BUDGET_IMPLEMENT"

        check_document_budget IMPLEMENTATION_NOTES.md || exit 1
        if [[ "$i" -eq "$total" ]]; then
            check_document_budget CHANGE_TEST_REPORT.md || exit 1
        fi
        printf '%s\n' "$i" > "$done_file"
    done < "$steps_file"

    rm -f "$done_file"
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
STATUS_STAGE_SEQ="baseline change-spec change-plan adversarial-review updated-change-plan implementation manual-checklist execute-checklist final-audit"

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
        requirements|project-plan|baseline|change-spec|change-plan)
            python3 "$ROOT/scripts/lib/early-prerequisites.py" "$DOCUMENT_BUDGET_SOURCE" || exit $? ;;
    esac

    local model="$3"
    local effort="${4:-}"
    local max_turns="${5:-80}"
    local budget="${6:-}"
    local cmd

    cmd="$(stage_agent_cmd "$log_name")"
    local -a client_cmd=("$cmd")
    case "${cmd##*/}" in
        claude|codex) client_cmd=(env -u UNCLE_STATUS_FILE -u UNCLE_PROJECT_ROOT -u UNCLE_CONFIG -u STAGEGATE_RUN_ID -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u DOCUMENT_BUDGET_SOURCE "$cmd") ;;
    esac
    # A stage configured in `uncle` overrides what the call site asked for.
    model="$(stage_model_for "$log_name" "$model")"
    effort="$(stage_effort_for "$log_name")"

    require_file "$prompt_file"

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
        "${client_cmd[@]}" "${flags[@]}" \
            < "$effective_prompt" \
            2>&1 \
            | tee "$LOG_DIR/${log_name}.jsonl" \
            | progress_tap "${PROGRESS_TOTAL:-0}" "${PROGRESS_LABEL:-stage}" \
            | format_claude_stream || status=$?
        progress_end

        local elapsed="$((SECONDS - start))"
        local log="$LOG_DIR/${log_name}.jsonl"
        perf_record agent "$log_name" "$elapsed" "$status" "$log" "$cmd" "$model" "$effort"

        # The final result event, if the run produced one.
        local result
        result="$(jq -R -c 'fromjson? | select(.type == "result")' < "$log" | tail -n 1)"

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
    result="$(jq -R -c 'fromjson? | select(.type == "result")' "$log" | tail -n 1)"
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
    cmd="$(stage_reviewer_cmd "$log_name")"
    local -a client_cmd=("$cmd")
    case "${cmd##*/}" in
        claude|codex) client_cmd=(env -u UNCLE_STATUS_FILE -u UNCLE_PROJECT_ROOT -u UNCLE_CONFIG -u STAGEGATE_RUN_ID -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u DOCUMENT_BUDGET_SOURCE "$cmd") ;;
    esac
    effort="$(stage_effort_for "$log_name")"
    local -a model_args=()
    local model
    model="$(stage_model_for "$log_name" "${CODEX_MODEL:-}")"
    [[ -n "$model" ]] && model_args=(-m "$model")

    require_file "$prompt_file"
    # The reviewer writes a document a human reads, so it gets the output
    # rules the same way an agent stage does.
    prompt_file="$(gated_prompt "$prompt_file" "$log_name" reviewer)"

    local review_key
    review_key="$(review_input_key "$output_file" "$prompt_file" "$cmd" "$model" "$effort" "$log_name")"
    if restore_plan_review "$output_file" "$review_key"; then
        finish_review_budget "$output_file" "$cmd" "$model" "$effort" "$log_name" || { [[ "$log_name" != adversarial-review ]] || exit 42; exit 1; }
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

    local start="$SECONDS"
    local status=0
    # stdin is the operator's gate-answer channel, not stage input: codex
    # appends a non-TTY stdin to the prompt and would block on it forever.
    "${client_cmd[@]}" "${flags[@]}" "$(cat "$prompt_file")" \
        < /dev/null 2>&1 | tee "$LOG_DIR/${log_name}.log" || status=$?

    record_codex_cost "$log_name" "$((SECONDS - start))"
    perf_record reviewer "$log_name" "$((SECONDS-start))" "$status" \
        "$LOG_DIR/${log_name}.log" "$cmd" "$model" "$effort"

    if [[ "$status" -ne 0 || ! -s "$output_file" ]] && context_exhausted "$LOG_DIR/${log_name}.log"; then
        echo
        echo "The reviewer ran out of context/tokens."
        echo "Change the reviewer model (Configure → reviewer) and re-run to resume this stage."
    fi

    [[ "$status" == 0 ]] || return "$status"
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

BG_PID=""
BG_LABEL=""
BG_START=0
BG_CMD=""
BG_MODEL=""
BG_EFFORT=""

cleanup_bg() {
    if [[ -n "$BG_PID" ]] && kill -0 "$BG_PID" 2>/dev/null; then
        echo "Stopping background stage: $BG_LABEL"
        kill "$BG_PID" 2>/dev/null || true
        wait "$BG_PID" 2>/dev/null || true
    fi
}
trap 'progress_end; cleanup_bg' EXIT

start_codex_bg() {
    local prompt_file
    prompt_file="$(resolve_prompt "$1")"
    local output_file="$2"
    local log_name="$3"
    local effort="${4:-}"
    local cmd
    cmd="$(stage_reviewer_cmd "$log_name")"
    local -a client_cmd=("$cmd")
    case "${cmd##*/}" in
        claude|codex) client_cmd=(env -u UNCLE_STATUS_FILE -u UNCLE_PROJECT_ROOT -u UNCLE_CONFIG -u STAGEGATE_RUN_ID -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u DOCUMENT_BUDGET_SOURCE "$cmd") ;;
    esac
    effort="$(stage_effort_for "$log_name")"
    local -a model_args=()
    local model
    model="$(stage_model_for "$log_name" "${CODEX_MODEL:-}")"
    [[ -n "$model" ]] && model_args=(-m "$model")

    require_file "$prompt_file"
    # The reviewer writes a document a human reads, so it gets the output
    # rules the same way an agent stage does.
    prompt_file="$(gated_prompt "$prompt_file" "$log_name" reviewer)"
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

acquire_lock
origin_preflight

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

while true; do
    state="$(get_state)"

    echo
    echo "Current state: $state"

    case "$state" in
        ANALYZE)
            require_file CHANGE_REQUEST.md
            # A fresh run legitimately claims this checkout for its issue.
            write_origin

            run_claude prompts/change/baseline.md baseline \
                "$MODEL_BASELINE" "" 120 "$BUDGET_BASELINE"
            require_file BASELINE_REPORT.md
            check_document_budget BASELINE_REPORT.md || exit 1

            run_claude prompts/change/change-spec.md change-spec \
                "$MODEL_CHANGE_SPEC" "$EFFORT_CHANGE_SPEC" 60 \
                "$BUDGET_CHANGE_SPEC"
            require_file CHANGE_SPEC.md
            check_document_budget CHANGE_SPEC.md || exit 1

            set_state WAIT_ANALYSIS_APPROVAL
            ;;

        WAIT_ANALYSIS_APPROVAL)
            human_gate APPROVE \
                BASELINE_REPORT.md BASELINE_REPORT \
                CHANGE_SPEC.md CHANGE_SPEC
            set_state PLAN
            ;;

        PLAN)
            verify_approval BASELINE_REPORT.md BASELINE_REPORT
            verify_approval CHANGE_SPEC.md CHANGE_SPEC

            # First point in the pipeline where the command list has been
            # approved and the tree is still untouched, which is the only
            # window in which a baseline means anything.
            capture_green_baseline

            run_claude prompts/change/change-plan.md change-plan \
                "$MODEL_CHANGE_PLAN" "" 120 "$BUDGET_CHANGE_PLAN"
            require_file CHANGE_PLAN.md
            check_document_budget CHANGE_PLAN.md || exit 1

            run_codex \
                prompts/change/adversarial-review.md \
                ADVERSARIAL_REVIEW.md \
                adversarial-review \
                "$CODEX_EFFORT_REVIEW"

            set_state WAIT_PLAN_APPROVAL
            ;;

        WAIT_PLAN_APPROVAL)
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

            run_claude prompts/change/updated-change-plan.md updated-change-plan \
                "$MODEL_UPDATED_PLAN" "$EFFORT_UPDATED_PLAN" 60 \
                "$BUDGET_UPDATED_PLAN"
            require_file CHANGE_PLAN.md
            check_document_budget CHANGE_PLAN.md || exit 1

            set_state WAIT_UPDATED_PLAN_APPROVAL
            ;;

        WAIT_UPDATED_PLAN_APPROVAL)
            # Re-approving CHANGE_PLAN overwrites the ACKNOWLEDGE hash taken
            # before the revision, so the recorded approval always names the
            # text implementation will run against.
            human_gate APPROVE \
                CHANGE_PLAN.md CHANGE_PLAN
            set_state IMPLEMENT
            ;;

        IMPLEMENT)
            verify_approval CHANGE_PLAN.md CHANGE_PLAN

            # Taken before the agent runs, so an untracked file that was
            # already sitting in the operator's checkout is not read as
            # something this change created.
            snapshot_untracked "$UNTRACKED_BASELINE"

            # The verification checklist is derived from the frozen, approved
            # artifacts, so it can be written while the implementation runs
            # instead of after it. Its prompt forbids reading source, which
            # would otherwise race Claude's in-flight edits; anything that
            # genuinely depends on the implementation is added by the delta
            # pass in the CHECKLIST state.
            if [[ "$PARALLEL_CHECKLIST" == "1" ]]; then
                start_codex_bg \
                    prompts/change/manual-checklist-base.md \
                    "$STATE_DIR/MANUAL_CHECKLIST.base.md" \
                    manual-checklist-base \
                    "$CODEX_EFFORT_CHECKLIST"
            fi

            if [[ "$STEPWISE_IMPLEMENT" == "1" ]]; then
                run_stepwise_implementation prompts/change/implement-change.md
            else
                compose_implementation_prompt \
                    prompts/change/implement-change.md \
                    "$STATE_DIR/implement-change.resolved.md"

                run_claude "$STATE_DIR/implement-change.resolved.md" implementation \
                    "$MODEL_IMPLEMENT" "" 200 "$BUDGET_IMPLEMENT"
            fi
            require_file IMPLEMENTATION_NOTES.md
            require_file CHANGE_TEST_REPORT.md
            check_document_budget IMPLEMENTATION_NOTES.md || exit 1
            check_document_budget CHANGE_TEST_REPORT.md || exit 1

            check_scope_deviations

            python3 "$ROOT/scripts/lib/fix-report-whitespace.py"
            git diff --stat > "$STATE_DIR/change-stat.txt"

            # Independent of the agent that just claimed its checks passed.
            # The result is carried to the gate rather than ending the run: a
            # regression is for the operator to weigh against the diff, and
            # killing the run here would throw away the stage that produced it.
            run_green_check || true

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
                run_codex \
                    prompts/change/manual-checklist-delta.md \
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
            set_state EXECUTE_CHECKLIST
            ;;

        EXECUTE_CHECKLIST)
            run_green_check || true
            snapshot_checklist_groups
            snapshot_checklist_checks
            ensure_checklist_runner execute-checklist || exit 1
            PROGRESS_TOTAL="$(grep -oE 'MC-[0-9]+' MANUAL_CHECKLIST.md 2>/dev/null \
                | sort -u | grep -c . || echo 0)"
            PROGRESS_LABEL="checklist"
            run_claude prompts/change/execute-change-checklist.md execute-checklist \
                "$MODEL_EXECUTE" "$EFFORT_EXECUTE" 200 "$BUDGET_EXECUTE"
            PROGRESS_TOTAL=0
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
            if [[ -e .git ]]; then change_pr_engine freeze || exit 1; fi
            rm -f FINAL_AUDIT.md
            run_codex \
                prompts/change/final-audit.md \
                FINAL_AUDIT.md \
                final-audit \
                "$CODEX_EFFORT_AUDIT"

            audit_class="$(classify_audit_verdict FINAL_AUDIT.md)"
            printf '%s\t%s\t%s\n' \
                "${STAGEGATE_RUN_ID:--}" \
                "$audit_class" \
                "$(hash_file FINAL_AUDIT.md)" \
                > "$VERDICT_FILE"
            if [[ -e .git ]]; then change_pr_engine bind || exit 1; fi
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
            echo "Change workflow complete."
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
            if [[ -e .git ]]; then
                change_pr_complete
            else
                close_origin_issue_if_ready
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

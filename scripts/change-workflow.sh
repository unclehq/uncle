#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STAGEGATE_VERSION="0.1.0"

usage() {
    cat <<'EOF'
Usage: change-workflow.sh [-h|--help] [--version]

Run the human-gated existing-code change workflow from CHANGE_REQUEST.md. The
driver is a resumable state machine; re-run it to continue from the current
stage.

Takes no positional arguments; all configuration is via WORKFLOW_* environment
variables (see scripts/README.md). Seed CHANGE_REQUEST.md from a GitHub issue
with ./scripts/from-issue.sh.
EOF
}

case "$#:${1:-}" in
    0:)                 ;;
    1:-h|1:--help)      usage; exit 0 ;;
    1:--version)        printf '%s\n' "$STAGEGATE_VERSION"; exit 0 ;;
    *)                  printf 'Unknown argument: %s\n' "${1:-}" >&2; usage >&2; exit 1 ;;
esac

STATE_DIR=".workflow"
APPROVAL_DIR="$STATE_DIR/approvals"
LOG_DIR="$STATE_DIR/logs"
STATE_FILE="$STATE_DIR/state"
SESSION_FILE="$STATE_DIR/session-head"
LEDGER_FILE="$STATE_DIR/cost.tsv"
LOCK_DIR="$STATE_DIR/lock"
ORIGIN_FILE="$STATE_DIR/origin"
VERDICT_FILE="$STATE_DIR/audit-verdict"
MARKER_FILE="$STATE_DIR/issue-closed"

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
MODEL_BASELINE="${WORKFLOW_MODEL_BASELINE:-kimi}"
MODEL_CHANGE_SPEC="${WORKFLOW_MODEL_CHANGE_SPEC:-kimi}"
MODEL_CHANGE_PLAN="${WORKFLOW_MODEL_CHANGE_PLAN:-opus}"
MODEL_UPDATED_PLAN="${WORKFLOW_MODEL_UPDATED_PLAN:-kimi}"
MODEL_IMPLEMENT="${WORKFLOW_MODEL_IMPLEMENT:-opus}"
MODEL_EXECUTE="${WORKFLOW_MODEL_EXECUTE:-kimi}"

EFFORT_CHANGE_SPEC="${WORKFLOW_EFFORT_CHANGE_SPEC:-medium}"
EFFORT_UPDATED_PLAN="${WORKFLOW_EFFORT_UPDATED_PLAN:-medium}"
EFFORT_EXECUTE="${WORKFLOW_EFFORT_EXECUTE:-medium}"

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

# Agent/reviewer CLI commands. Defaults are `claude` and `codex`. Swap either
# for a compatible CLI or a wrapper script. The agent CLI must accept the same
# flags as `claude -p` (model, effort, max-turns, output-format stream-json,
# allowedTools, stdin prompt). The reviewer CLI must accept the same flags as
# `codex exec` (ephemeral, sandbox read-only, model, output-last-message).
AGENT_CMD="${WORKFLOW_AGENT_CMD:-$ROOT/scripts/agent-kimi.sh}"
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

hash_file() {
    shasum -a 256 "$1" | awk '{print $1}'
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
    case "$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')" in
        APPROVE|ACKNOWLEDGE)
            echo "This gate now requires 'y' to approve."
            ;;
    esac
}

# Pure FINAL_AUDIT.md verdict classifier, shared with scripts/tests/. Sourced
# self-relative so the driver still runs from any CWD.
. "$ROOT/scripts/lib/audit-verdict.sh"

# .workflow/state grammar, and the shared INV-3 close gate.
. "$ROOT/scripts/lib/state.sh"
. "$ROOT/scripts/lib/plan-scope.sh"
. "$ROOT/scripts/lib/progress.sh"
. "$ROOT/scripts/lib/issue-close.sh"

require_file() {
    if [[ ! -s "$1" ]]; then
        echo "Required file missing or empty: $1"
        exit 1
    fi
}

# The issue number written into .workflow/state is informational only;
# .workflow/origin stays the sole identity source (INV-1).
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
# One run owns a checkout's .workflow/ for its whole lifetime. mkdir is atomic,
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
# .workflow/origin binds in-flight state to one (repo, issue) so a resumed run
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
        rm -f "$VERDICT_FILE" "$MARKER_FILE" "$SESSION_FILE"
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
    echo "  Stage cost so far: \$$(ledger_total)"
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
    if ! read -r -p "$prompt"; then
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
            echo "Gate not accepted. Workflow remains paused."
            legacy_word_notice "$response"
            exit 0
            ;;
    esac

    # Every file is re-checked before any approval is written, so a mutated
    # document cannot leave a half-approved gate behind.
    for i in "${!files[@]}"; do
        if [[ "$(hash_file "${files[$i]}")" != "${digests[$i]}" ]]; then
            echo "${files[$i]} changed after it was shown for approval."
            echo "Gate not accepted. Workflow remains paused."
            exit 0
        fi
    done

    for i in "${!files[@]}"; do
        printf '%s\n' "${digests[$i]}" > "$APPROVAL_DIR/${names[$i]}.sha256"
        echo "Recorded approval for ${files[$i]}"
    done
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
              "\n[done] \($e.subtype) — \($e.num_turns) turns, \($e.duration_ms / 1000 | floor)s, $\($e.total_cost_usd // 0 | .*100 | round / 100)"
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
    local base="$1" out="$2"
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

    changed="$(git diff --name-only; git diff --cached --name-only)"
    changed="$(printf '%s\n' "$changed" | sort -u | grep -v '^$' || true)"
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

run_claude() {
    local prompt_file="$1"
    local log_name="$2"
    local model="$3"
    local effort="${4:-}"
    local max_turns="${5:-80}"
    local budget="${6:-}"

    require_file "$prompt_file"

    while true; do
        local -a flags=(
            -p
            --model "$model"
            --max-turns "$max_turns"
            --output-format stream-json
            --verbose
            --strict-mcp-config
            --exclude-dynamic-system-prompt-sections
            --allowedTools "$CLAUDE_TOOLS"
        )

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
        echo "Launching agent ($AGENT_CMD): $log_name"
        echo "Model: $model${effort:+  Effort: $effort}${budget:+  Cap: \$$budget}"
        if [[ -n "$head" ]]; then
            echo "Forking session: $head"
        fi
        echo

        # Use stdin for the prompt because --allowedTools is variadic and can
        # otherwise consume a trailing positional prompt. Streaming also makes a
        # long-running stage visibly active instead of buffering until completion.
        local start="$SECONDS"
        local status=0
        "$AGENT_CMD" "${flags[@]}" \
            < "$prompt_file" \
            2>&1 \
            | tee "$LOG_DIR/${log_name}.jsonl" \
            | progress_tap "${PROGRESS_TOTAL:-0}" "${PROGRESS_LABEL:-stage}" \
            | format_claude_stream || status=$?
        progress_end

        local elapsed="$((SECONDS - start))"
        local log="$LOG_DIR/${log_name}.jsonl"

        # The final result event, if the run produced one.
        local result
        result="$(jq -R -c 'fromjson? | select(.type == "result")' < "$log" | tail -n 1)"

        if [[ -n "$result" ]]; then
            record_cost "agent:$log_name" "$elapsed" \
                "$(printf '%s' "$result" | jq -r '.total_cost_usd // 0')" \
                "$(printf '%s' "$result" | jq -r '.usage.input_tokens // 0')" \
                "$(printf '%s' "$result" | jq -r '.usage.output_tokens // 0')" \
                "$(printf '%s' "$result" | jq -r '.usage.cache_read_input_tokens // 0')" \
                "$(printf '%s' "$result" | jq -r '.usage.cache_creation_input_tokens // 0')"
        else
            record_cost "agent:$log_name" "$elapsed" - - - - -
        fi

        if [[ "$status" -ne 0 ]]; then
            echo "Agent ($AGENT_CMD) exited with status $status."
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

    record_cost "reviewer:$log_name" "$elapsed" - - - - "$tokens"
}

run_codex() {
    local prompt_file="$1"
    local output_file="$2"
    local log_name="$3"
    local effort="${4:-}"

    require_file "$prompt_file"

    local -a flags=(
        exec
        --ephemeral
        --sandbox read-only
        --output-last-message "$output_file"
    )

    if [[ -n "$effort" ]]; then
        flags+=(-c "model_reasoning_effort=$effort")
    fi

    echo
    echo "Launching reviewer ($REVIEWER_CMD): $log_name${effort:+  Effort: $effort}"

    local start="$SECONDS"
    local status=0
    "$REVIEWER_CMD" "${flags[@]}" "$(cat "$prompt_file")" \
        2>&1 | tee "$LOG_DIR/${log_name}.log" || status=$?

    record_codex_cost "$log_name" "$((SECONDS - start))"

    if [[ "$status" -ne 0 || ! -s "$output_file" ]] && context_exhausted "$LOG_DIR/${log_name}.log"; then
        echo
        echo "The reviewer ran out of context/tokens."
        echo "Change the reviewer model (Configure → reviewer) and re-run to resume this stage."
    fi

    require_file "$output_file"
}

BG_PID=""
BG_LABEL=""
BG_START=0

cleanup_bg() {
    if [[ -n "$BG_PID" ]] && kill -0 "$BG_PID" 2>/dev/null; then
        echo "Stopping background stage: $BG_LABEL"
        kill "$BG_PID" 2>/dev/null || true
        wait "$BG_PID" 2>/dev/null || true
    fi
}
trap 'progress_end; cleanup_bg' EXIT

start_codex_bg() {
    local prompt_file="$1"
    local output_file="$2"
    local log_name="$3"
    local effort="${4:-}"

    require_file "$prompt_file"
    rm -f "$output_file"

    local -a flags=(
        exec
        --ephemeral
        --sandbox read-only
        --output-last-message "$output_file"
    )

    if [[ -n "$effort" ]]; then
        flags+=(-c "model_reasoning_effort=$effort")
    fi

    echo
    echo "Starting background reviewer ($REVIEWER_CMD) stage: $log_name${effort:+  Effort: $effort}"
    echo "Log: $LOG_DIR/${log_name}.log"

    "$REVIEWER_CMD" "${flags[@]}" "$(cat "$prompt_file")" \
        > "$LOG_DIR/${log_name}.log" 2>&1 &

    BG_PID=$!
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
    echo "Background Codex stage complete: $label"
}

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

acquire_lock
origin_preflight

# Whether this invocation can prove it owns .workflow/origin, rather than having
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

            run_claude prompts/change/change-spec.md change-spec \
                "$MODEL_CHANGE_SPEC" "$EFFORT_CHANGE_SPEC" 60 \
                "$BUDGET_CHANGE_SPEC"
            require_file CHANGE_SPEC.md

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

            run_claude prompts/change/change-plan.md change-plan \
                "$MODEL_CHANGE_PLAN" "" 120 "$BUDGET_CHANGE_PLAN"
            require_file CHANGE_PLAN.md

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

            check_scope_deviations

            git diff --check
            git diff --stat > "$STATE_DIR/change-stat.txt"
            git diff > "$STATE_DIR/change.diff"

            if [[ "$PARALLEL_CHECKLIST" == "1" ]]; then
                wait_codex_bg "$STATE_DIR/MANUAL_CHECKLIST.base.md"
            fi

            set_state CHECKLIST
            ;;

        CHECKLIST)
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
            PROGRESS_TOTAL="$(grep -oE 'MC-[0-9]+' MANUAL_CHECKLIST.md 2>/dev/null \
                | sort -u | grep -c . || echo 0)"
            PROGRESS_LABEL="checklist"
            run_claude prompts/change/execute-change-checklist.md execute-checklist \
                "$MODEL_EXECUTE" "$EFFORT_EXECUTE" 200 "$BUDGET_EXECUTE"
            PROGRESS_TOTAL=0
            require_file VERIFICATION_REPORT.md
            set_state FINAL_AUDIT
            ;;

        FINAL_AUDIT)
            # Remove any prior audit first: run_codex's require_file then treats
            # the file's existence as proof this invocation produced it, so a
            # reviewer call that exits 0 without writing cannot be read as fresh.
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
            echo "Audit verdict: $audit_class"
            VERDICT_WRITTEN_THIS_RUN=1

            set_state COMPLETE
            ;;

        COMPLETE)
            echo
            echo "Change workflow complete."
            echo
            echo "Review:"
            echo "  CHANGE_TEST_REPORT.md"
            echo "  VERIFICATION_REPORT.md"
            echo "  FINAL_AUDIT.md"
            echo "  .workflow/change.diff"
            if [[ -s "$LEDGER_FILE" ]]; then
                echo
                echo "Cost ledger ($LEDGER_FILE):"
                column -t -s "$(printf '\t')" < "$LEDGER_FILE" | sed 's/^/  /'
                echo
                echo "  Total Claude spend: \$$(ledger_total)"
                echo "  (Codex stages report tokens only; see the cache_w column.)"
            fi
            close_origin_issue_if_ready
            exit 0
            ;;

        *)
            echo "Unknown workflow state: $state"
            echo "Delete $STATE_FILE to restart from the beginning."
            exit 1
            ;;
    esac
done

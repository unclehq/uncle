#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STAGEGATE_VERSION="0.1.0"

usage() {
    cat <<'EOF'
Usage: stagegate.sh [-h|--help] [--version]

Run the human-gated new-application workflow from REQUIREMENTS.md. The driver
is a resumable state machine; re-run it to continue from the current stage.

Takes no positional arguments; all configuration is via WORKFLOW_* environment
variables (see scripts/README.md). Approvals are recorded with
./scripts/workflow.sh.
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
SPEC_DIR="$STATE_DIR/speculative"
STATE_FILE="$STATE_DIR/state"

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
DEFAULT_EFFORT="high"

hash_file() {
    shasum -a 256 "$1" | awk '{print $1}'
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

stage_model() {
    local fallback="$DEFAULT_MODEL"
    case "$1" in
        requirements|execute-checklist) fallback="kimi" ;;
    esac
    stage_setting MODEL "$1" "$fallback"
}

stage_effort() {
    local fallback="$DEFAULT_EFFORT"
    case "$1" in
        requirements|execute-checklist) fallback="medium" ;;
    esac
    stage_setting EFFORT "$1" "$fallback"
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
        implementation|execute-checklist)
            fallback="Read,Glob,Grep,Write,Edit,TodoWrite,Bash"
            ;;
    esac
    stage_setting TOOLS "$1" "$fallback"
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
    local file="$1"
    local name="$2"
    local wording
    wording="$(lower "${3:-approve}")"

    require_file "$file"

    local before
    local response

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
    echo "Recorded approval for $file"
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
              "\n[done] \($e.subtype) — \($e.num_turns) turns, \($e.duration_ms / 1000 | floor)s"
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
    local prompt_file="$1"
    local log_name="$2"
    local tools="${3:-$(stage_tools "$log_name")}"
    local model
    local effort
    local turns

    model="$(stage_model "$log_name")"
    effort="$(stage_effort "$log_name")"
    turns="$(stage_turns "$log_name")"

    require_file "$prompt_file"

    while true; do
        echo
        echo "Launching agent ($AGENT_CMD): $log_name"
        echo "Model: $model (effort: $effort, max turns: $turns)"
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
        "$AGENT_CMD" -p \
            --model "$model" \
            --effort "$effort" \
            --strict-mcp-config \
            --max-turns "$turns" \
            --output-format stream-json \
            --verbose \
            --allowedTools "$tools" \
            < "$prompt_file" \
            2>&1 \
            | tee "$LOG_DIR/${log_name}.jsonl" \
            | format_claude_stream || status=$?

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
            echo "Agent ($AGENT_CMD) exited with status $status."
            echo "Raw event log: $log"
            exit "$status"
        fi

        break
    done
}

run_codex_review() {
    local prompt_file="$1"
    local output_file="$2"
    local log_name="$3"

    require_file "$prompt_file"

    echo
    echo "Launching reviewer ($REVIEWER_CMD): $log_name"

    # Keep the reviewer read-only. The shell writes the reviewer's final
    # message into the designated review artifact.
    local model_args=()
    local model
    model="$(stage_setting MODEL "$log_name" "${CODEX_MODEL:-}")"
    if [[ -n "$model" ]]; then
        model_args=(-m "$model")
        echo "Model: $model"
    fi

    local status=0
    "$REVIEWER_CMD" exec \
        --ephemeral \
        --sandbox read-only \
        "${model_args[@]+"${model_args[@]}"}" \
        --output-last-message "$output_file" \
        "$(cat "$prompt_file")" \
        2>&1 | tee "$LOG_DIR/${log_name}.log" || status=$?

    if [[ "$status" -ne 0 || ! -s "$output_file" ]] && context_exhausted "$LOG_DIR/${log_name}.log"; then
        echo
        echo "The reviewer ran out of context/tokens."
        echo "Change the reviewer model (Configure → reviewer) and re-run to resume this stage."
    fi

    require_file "$output_file"
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
            require_artifact AUTOMATED_TEST_REPORT.md
            ;;
        MANUAL_CHECKLIST)
            run_codex_review \
                prompts/manual-checklist.md \
                MANUAL_CHECKLIST.md \
                manual-checklist
            ;;
        EXECUTE_CHECKLIST)
            run_claude prompts/execute-checklist.md execute-checklist
            require_artifact VERIFICATION_REPORT.md
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
    run_stage "$stage" > "$LOG_DIR/${stage}.speculative.log" 2>&1 < /dev/null &
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
            # No speculation here: IMPLEMENT writes source code, and it may not
            # start before this approval exists.
            review_and_approve \
                UPDATED_PROJECT_PLAN.md \
                UPDATED_PROJECT_PLAN \
                approve
            set_state IMPLEMENT
            ;;

        IMPLEMENT)
            verify_approval \
                UPDATED_PROJECT_PLAN.md \
                UPDATED_PROJECT_PLAN
            run_stage IMPLEMENT
            set_state MANUAL_CHECKLIST
            ;;

        MANUAL_CHECKLIST)
            run_stage MANUAL_CHECKLIST
            set_state EXECUTE_CHECKLIST
            ;;

        EXECUTE_CHECKLIST)
            run_stage EXECUTE_CHECKLIST
            set_state FINAL_AUDIT
            ;;

        FINAL_AUDIT)
            run_stage FINAL_AUDIT
            set_state COMPLETE
            ;;

        COMPLETE)
            echo
            echo "Workflow complete."
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
            exit 0
            ;;

        *)
            echo "Unknown workflow state: $state"
            exit 1
            ;;
    esac
done

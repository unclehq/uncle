#!/usr/bin/env bash
# Reviewer-CLI shim that puts the adversarial review stages on `claude`.
#
# The drivers call $REVIEWER_CMD with `codex exec` flags. claude is not
# flag-compatible with those, so this translates:
#
#   exec                        dropped
#   --ephemeral                 dropped (claude -p is already single-shot)
#   --sandbox read-only         --allowedTools with no write or exec tool
#   -m MODEL                    --model MODEL
#   -c model_reasoning_effort=X --effort X
#   --output-last-message FILE  the run's final assistant text, written to FILE
#   <prompt>                    trailing positional, moved to stdin
#
# Read-only is enforced by the tool allowlist, not by a sandbox flag: the
# reviewer is given Read, Glob and Grep and nothing that can write a file or
# run a command. That is the property the workflow depends on — a reviewer that
# could edit the plan it is reviewing, or write its own verdict artifact
# directly, would not be an independent check.
#
# bash 3.2 compatible: no associative arrays, no ${var^^}.
set -euo pipefail

CLAUDE_CMD="${WORKFLOW_REVIEWER_CLAUDE_CMD:-claude}"
DEFAULT_MODEL="${WORKFLOW_REVIEWER_CLAUDE_MODEL:-opus}"
MAX_TURNS="${WORKFLOW_REVIEWER_CLAUDE_TURNS:-80}"
TOOLS="${WORKFLOW_REVIEWER_CLAUDE_TOOLS:-Read,Glob,Grep}"

model="$DEFAULT_MODEL"
effort=""
output_file=""
prompt=""

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        exec|--ephemeral|--json|--skip-git-repo-check)
            shift
            ;;
        --sandbox)
            # The allowlist below is the enforcement; the value is advisory.
            shift 2
            ;;
        -m|--model)
            model="$2"
            shift 2
            ;;
        --output-last-message)
            output_file="$2"
            shift 2
            ;;
        -c)
            # codex config pairs; the drivers only ever set the effort.
            case "$2" in
                model_reasoning_effort=*) effort="${2#model_reasoning_effort=}" ;;
            esac
            shift 2
            ;;
        *)
            prompt="$1"
            shift
            ;;
    esac
done

if [[ -z "$prompt" ]]; then
    echo "reviewer-claude.sh: no prompt argument" >&2
    exit 2
fi

# `CODEX_MODEL` and the per-stage WORKFLOW_MODEL_* overrides can still name a
# reviewer model from the Codex era. Anything that is not a Claude tier would
# be rejected by claude with an unhelpful error, so fall back instead of
# failing the stage. This is an allowlist on purpose: a denylist of known
# non-Claude names would miss the next one.
case "$model" in
    claude*|opus*|sonnet*|haiku*) ;;
    *)
        echo "reviewer-claude.sh: '$model' is not a Claude tier; using $DEFAULT_MODEL" >&2
        model="$DEFAULT_MODEL"
        ;;
esac

stream="$(mktemp)"
trap 'rm -f "$stream"' EXIT

echo "--------"
echo "reviewer: $CLAUDE_CMD"
echo "model: $model${effort:+  effort: $effort}"
echo "tools: $TOOLS (read-only)"
echo "--------"

claude_flags=(
    -p
    --model "$model"
    --max-turns "$MAX_TURNS"
    --output-format stream-json
    --verbose
    --strict-mcp-config
    --exclude-dynamic-system-prompt-sections
    --allowedTools "$TOOLS"
)

if [[ -n "$effort" ]]; then
    claude_flags+=(--effort "$effort")
fi

# Render progress to stdout the way codex does — the drivers tee this to the
# stage log — while keeping the raw events for the extraction below.
set +e
printf '%s' "$prompt" \
    | "$CLAUDE_CMD" "${claude_flags[@]}" \
    | tee "$stream" \
    | jq -R -r --unbuffered '
        (fromjson? // empty) as $e
        | if $e.type == "assistant" then
              ($e.message.content[]?
               | if .type == "text" then .text
                 elif .type == "tool_use" then "  [tool] \(.name)"
                 else empty end)
          else empty end
      '
claude_pipe=( "${PIPESTATUS[@]}" )
set -e

status="${claude_pipe[1]}"

result="$(jq -R -c 'fromjson? | select(.type == "result")' < "$stream" | tail -n 1)"
# Preserve usage even if this review subsequently fails.
[[ -z "$result" ]] || printf '%s\n' "$result"

if [[ "$status" -ne 0 ]]; then
    echo "reviewer-claude.sh: $CLAUDE_CMD exited with status $status" >&2
    exit "$status"
fi

# Same rule the drivers apply to the agent CLI: a stream with no terminal
# result event is a failed stage, not a silent success.
if [[ -z "$result" ]]; then
    echo "reviewer-claude.sh: no result event; treating the review as failed" >&2
    exit 1
fi

if [[ "$(printf '%s' "$result" | jq -r '.is_error // false')" == "true" ]]; then
    echo "reviewer-claude.sh: review failed: $(printf '%s' "$result" | jq -r '.subtype // "unknown"')" >&2
    exit 1
fi

review="$(printf '%s' "$result" | jq -r '.result // empty')"

if [[ -z "$review" ]]; then
    echo "reviewer-claude.sh: the review produced no final message" >&2
    exit 1
fi

# Only written on success: the drivers `require_file` this afterwards, so a
# failed review must not leave a file behind for the next run to mistake for a
# fresh one.
if [[ -n "$output_file" ]]; then
    printf '%s\n' "$review" > "$output_file"
fi

# record_codex_cost reads the digits on the line after "tokens used".
echo
printf 'tokens used\n%s\n' \
    "$(printf '%s' "$result" | jq -r '
        (.usage.input_tokens // 0)
        + (.usage.output_tokens // 0)
        + (.usage.cache_read_input_tokens // 0)
        + (.usage.cache_creation_input_tokens // 0)')"

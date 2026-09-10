#!/usr/bin/env bash
# Agent-CLI shim that runs `codex exec` for the drivers' agent stages.
#
# codex already runs the reviewer stages, where it is held to
# `--sandbox read-only`. This is the other half: the same CLI driving a stage
# that has to write code, which means `--sandbox workspace-write`.
#
# The drivers call $AGENT_CMD with `claude -p` flags and the prompt on stdin.
# codex is not flag-compatible, so this translates:
#   -p, --verbose, --strict-mcp-config,
#   --exclude-dynamic-system-prompt-sections, --fork-session   dropped
#   --model X                                 -> -m X (omitted when empty)
#   --effort X                                -> -c model_reasoning_effort=X
#   --max-turns, --max-budget-usd, --resume,
#   --output-format, --mcp-config             consumed and dropped
#   --allowedTools LIST                       consumed and dropped
#   prompt on stdin                           -> codex reads stdin
#
# Two of those droppings matter, and neither is this shim's to fix:
#
#   --max-turns / --max-budget-usd: codex exec has no turn or spend cap, so a
#   stage on this runner has no ceiling but the driver's own patience.
#   --allowedTools: codex has no tool allowlist. The sandbox mode is the only
#   restriction available, so a document stage on codex can still run
#   commands. Pick the runner accordingly.
#
# codex streams its own JSONL (`--json`): thread.started, turn.started,
# item.completed (one per agent message, command, or file change), and
# turn.completed carrying usage. This rewrites those into the Claude
# stream-json schema the drivers' format_claude_stream renders, and
# synthesizes the terminal `result` event they use for success/failure
# detection and cost accounting.
set -euo pipefail

CODEX_CMD="${WORKFLOW_CODEX_CMD:-codex}"

model=""
effort=""
skip_value=0
pending=""
for arg in "$@"; do
    if [[ "$skip_value" == "1" ]]; then
        case "$pending" in
            model)  model="$arg" ;;
            effort) effort="$arg" ;;
        esac
        skip_value=0
        pending=""
        continue
    fi
    case "$arg" in
        --model)  skip_value=1; pending="model" ;;
        --effort) skip_value=1; pending="effort" ;;
        --max-turns|--max-budget-usd|--allowedTools|--output-format|--resume|--mcp-config)
            skip_value=1; pending="" ;;
        -p|--verbose|--strict-mcp-config|--fork-session|\
        --exclude-dynamic-system-prompt-sections)
            ;;
        *) ;;
    esac
done

# A tier name from the driver's built-in defaults is not a codex model id.
# Treat it as "no model given" so codex uses the model it is configured with,
# which is the same rule the cline shim follows.
case "$model" in
    opus|sonnet|kimi|kimi:*) model="" ;;
esac
if [[ -n "${UNCLE_CODEX_MODEL:-}" ]]; then
    model="$UNCLE_CODEX_MODEL"
fi

prompt="$(cat)"
if [[ -z "$prompt" ]]; then
    echo "agent-codex.sh: no prompt on stdin" >&2
    exit 2
fi

# workspace-write, not read-only: this is an implementing stage. Not
# --dangerously-bypass-approvals-and-sandbox — the whole point of this
# workflow is that an agent stays inside a boundary.
args=(exec --json --ephemeral --skip-git-repo-check --sandbox workspace-write)

# workspace-write denies network access unless codex is configured otherwise,
# and that denial covers binding a loopback port -- so a stage that has to
# serve the site it is verifying cannot start its own server. The driver sets
# this from <stage>.network, which is false unless an operator turned it on.
if [[ "${UNCLE_STAGE_NETWORK:-false}" == "true" ]]; then
    args+=(-c sandbox_workspace_write.network_access=true)
fi
if [[ -n "$model" ]]; then
    args+=(-m "$model")
fi
if [[ -n "$effort" ]]; then
    args+=(-c "model_reasoning_effort=$effort")
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
raw="$work/events.jsonl"
status_file="${UNCLE_STATUS_FILE:-}"

stage="${UNCLE_STATUS_STAGE:-}"
stage_index="${UNCLE_STATUS_STAGE_INDEX:-0}"
stage_total="${UNCLE_STATUS_STAGE_TOTAL:-0}"
stage_turns="${UNCLE_STATUS_STAGE_TURNS:-0}"

if [[ -n "$status_file" ]]; then
    printf '{"event":"start","model":"%s","effort":"%s","mode":"act","stage":"%s","stage_index":%s,"stage_total":%s,"stage_turns":%s}\n' \
        "${model:-codex default}" "$effort" "$stage" "$stage_index" "$stage_total" "$stage_turns" \
        >> "$status_file"
fi

# item.completed is the only event that carries content. An agent_message is
# text; reasoning is internal and dropped; anything else is work the agent did
# (a command, a patch) and is rendered as a tool line under its own name, so a
# new item type shows up as itself rather than vanishing.
translate() {
    jq -R -r --unbuffered '
        (fromjson? // empty) as $e
        | if $e.type == "item.completed" then
              ($e.item // {}) as $i
              | if $i.type == "agent_message" then
                    {type: "assistant",
                     message: {content: [{type: "text", text: ($i.text // "")}]}} | tojson
                elif $i.type == "reasoning" then empty
                else
                    {type: "assistant",
                     message: {content: [{type: "tool_use", name: ($i.type // "item")}]}} | tojson
                end
          else empty end
    '
}

set +e
if [[ -n "$status_file" ]]; then
    printf '%s' "$prompt" | env -u UNCLE_STATUS_FILE -u UNCLE_PROJECT_ROOT -u UNCLE_CONFIG -u STAGEGATE_RUN_ID -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u DOCUMENT_BUDGET_SOURCE "$CODEX_CMD" "${args[@]}" \
        | tee "$raw" \
        | tee >(jq -R -r --unbuffered --arg model "${model:-codex default}" --arg stage "$stage" '
            (fromjson? // empty) as $e
            | if $e.type == "turn.completed" then
                  {event:"usage", stage:$stage, model:$model, mode:"act", input_includes_cache:true,
                   usage:{input_tokens:$e.usage.input_tokens,output_tokens:$e.usage.output_tokens,
                          cache_read_input_tokens:$e.usage.cached_input_tokens,cache_creation_input_tokens:($e.usage.cache_write_input_tokens // 0)},
                   total_tokens: (($e.usage.input_tokens // 0)
                                + ($e.usage.output_tokens // 0))} | tojson
              else empty end
          ' >> "$status_file") \
        | translate
    codex_status="${PIPESTATUS[1]}"
else
    printf '%s' "$prompt" | env -u UNCLE_STATUS_FILE -u UNCLE_PROJECT_ROOT -u UNCLE_CONFIG -u STAGEGATE_RUN_ID -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u DOCUMENT_BUDGET_SOURCE "$CODEX_CMD" "${args[@]}" \
        | tee "$raw" \
        | translate
    codex_status="${PIPESTATUS[1]}"
fi
set -e

# codex has no terminal result event, so the result is synthesized from its
# exit status and the last turn's usage. A run that produced no turn at all is
# a failure even when the process exited 0: the drivers treat a missing result
# as a failed stage, and a stage that said nothing did not do the work.
result="$(jq -R -s -c --argjson exit "$codex_status" --arg model "$model" '
  [split("\n")[] | fromjson? // empty] as $events
  | ($events | map(select(.type == "turn.completed")) | .[-1]) as $t
  | ($events | map(select(.type == "turn.started")) | length) as $turns
  | (if $exit == 0 and $t != null then true else false end) as $ok
  | {type:"result", model:$model,
     subtype: (if $ok then "success" else "error_during_execution" end),
     is_error: (if $ok then "false" else "true" end),
     num_turns: (if $turns > 0 then $turns else 1 end),
     duration_ms: 0,
     total_cost_usd: null,
     input_includes_cache: true,
     usage: {input_tokens: ($t.usage.input_tokens // 0),
             output_tokens: ($t.usage.output_tokens // 0),
             cache_read_input_tokens: ($t.usage.cached_input_tokens // 0),
             cache_creation_input_tokens: ($t.usage.cache_write_input_tokens // 0)}}
' "$raw")"

# Context exhaustion is recoverable: name it so the driver can offer a
# different model and replay the stage.
if [[ "$(printf '%s' "$result" | jq -r '.is_error // "true"')" == "true" ]] \
    && grep -qiE 'context (length|window)|maximum context|out of (tokens|context)|token limit|too many tokens|context_length_exceeded' "$raw"; then
    result="$(printf '%s' "$result" | jq -c '.subtype = "context_length_exceeded"')"
fi

printf '%s\n' "$result"

if [[ "$codex_status" -ne 0 ]]; then
    exit "$codex_status"
fi
if [[ "$(printf '%s' "$result" | jq -r '.is_error // "true"')" == "true" ]]; then
    exit 1
fi
exit 0

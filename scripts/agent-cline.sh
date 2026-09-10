#!/usr/bin/env bash
# Agent-CLI shim that runs `cline` for the drivers' agent stages.
#
# The drivers call $AGENT_CMD with `claude -p` flags and the prompt on stdin.
# cline is not flag-compatible, so this translates:
#   -p, --verbose, --strict-mcp-config,
#   --exclude-dynamic-system-prompt-sections              dropped
#   --model X / --effort X                                captured (effort -> --thinking)
#   --max-turns, --max-budget-usd, --allowedTools,
#   --output-format, --resume, --fork-session, --mcp-config  consumed and dropped
#   prompt on stdin                                       cline positional prompt, act mode
#
# cline streams its own NDJSON. This rewrites the final text of each assistant
# block into the Claude stream-json schema the drivers' format_claude_stream
# renders, and synthesizes the terminal `result` event the drivers use for
# success/failure detection and cost accounting. A failed run also carries the
# agent's own last failure line as `error_detail` so the operator sees the
# cause, not just a subtype.
set -euo pipefail

CLINE_CMD="${WORKFLOW_CLINE_CMD:-cline}"

model=""
effort=""
prompt_extra=""
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
        -p|--verbose|--strict-mcp-config|--exclude-dynamic-system-prompt-sections|--fork-session)
            ;;
        -*) ;;
        *) prompt_extra="$arg" ;;
    esac
done

# `uncle` exports these when the user picks a model / performance; they win over
# the driver's per-stage flags. Invoked without them, the shim honors the
# driver's --model/--effort as a fallback.
# A cline model id carried by the driver's --model (from WORKFLOW_MODEL_<STAGE>)
# wins over the global pick; a tier name (opus/kimi/sonnet) falls back to the
# global pick, then cline's own default.
case "$model" in
    ""|opus|sonnet|kimi|kimi:*)
        model="${UNCLE_CLINE_MODEL:-}"
        ;;
    *) ;;
esac
if [[ -n "${UNCLE_CLINE_EFFORT+x}" ]]; then
    effort="$UNCLE_CLINE_EFFORT"
fi
if [[ -z "$effort" ]]; then
    effort="medium"
fi

# cline requires a model id in `modelType/model` form (e.g. cline-pass/kimi-k3).
# A bare display name — from a hand-edited .uncle/config, or a picker entry that
# offered a label instead of an id — is only rejected by cline itself, one turn
# into the stage and after the driver has already announced it. Fail here, where
# the offending value can be named.
if [[ -n "$model" && "$model" != */* ]]; then
    printf '%s: invalid cline model id: %s\n' "agent-cline.sh" "$model" >&2
    printf '  cline expects modelType/model, e.g. cline-pass/deepseek-v4-pro.\n' >&2
    printf '  Fix it in .uncle/config, or in uncle -> Configure.\n' >&2
    exit 2
fi

prompt="$(cat)"
if [[ -z "$prompt" ]]; then
    prompt="$prompt_extra"
fi
if [[ -z "$prompt" ]]; then
    echo "agent-cline.sh: no prompt on stdin" >&2
    exit 2
fi

# Without an explicit mode Cline inherits its saved planActMode, even though
# CLI help describes act as the default. Agent stages must write artifacts.
args=(--act --json --auto-approve true)
if [[ -n "$model" ]]; then
    args+=(-m "$model")
fi
args+=(--thinking "$effort")

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
raw="$work/events.ndjson"
status_file="${UNCLE_STATUS_FILE:-}"

# The workflow script exports the current stage context (name, its 1-based
# index, the total stage count, and that stage's turn cap) so the status bar
# can show "stage N/M" and a within-stage completion estimate. Names are
# workflow-controlled identifiers (e.g. implementation, change-plan), so the
# shell-injected values never need JSON escaping.
stage="${UNCLE_STATUS_STAGE:-}"
stage_index="${UNCLE_STATUS_STAGE_INDEX:-0}"
stage_total="${UNCLE_STATUS_STAGE_TOTAL:-0}"
stage_turns="${UNCLE_STATUS_STAGE_TURNS:-0}"

# Announce the stage to the TUI status channel (model + mode + stage context,
# zero tokens) so the status bar flips to the right model/mode before any
# usage event lands.
if [[ -n "$status_file" ]]; then
    printf '{"event":"start","model":"%s","effort":"%s","mode":"act","stage":"%s","stage_index":%s,"stage_total":%s,"stage_turns":%s}\n' \
        "$model" "$effort" "$stage" "$stage_index" "$stage_total" "$stage_turns" >> "$status_file"
fi

# Stream cline's NDJSON through a translator that emits one Claude `assistant`
# event per completed text block, while tee keeps the raw feed for the result
# event synthesized below. When a status channel is configured, a second tee
# mirrors cline's cumulative `usage` events into it for live token accounting.
set +e
if [[ -n "$status_file" ]]; then
    env -u UNCLE_STATUS_FILE -u UNCLE_PROJECT_ROOT -u UNCLE_CONFIG -u STAGEGATE_RUN_ID -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u DOCUMENT_BUDGET_SOURCE "$CLINE_CMD" "${args[@]}" "$prompt" \
        | tee "$raw" \
        | tee >(jq -R -r --unbuffered --arg model "$model" --arg stage "$stage" '
            (fromjson? // empty) as $e
            | if $e.type == "agent_event" and $e.event.type == "usage" then
                  {event:"usage", stage:$stage, model:$model, mode:"act",
                   total_cost_usd:($e.event.totalCost // null), input_includes_cache:true,
                   usage:{input_tokens:$e.event.totalInputTokens,output_tokens:$e.event.totalOutputTokens,
                          cache_read_input_tokens:$e.event.totalCacheReadTokens,cache_creation_input_tokens:$e.event.totalCacheWriteTokens},
                   total_tokens: (($e.event.totalInputTokens // 0)
                                + ($e.event.totalOutputTokens // 0))} | tojson
              else empty end
          ' >> "$status_file") \
        | jq -R -r --unbuffered '
            (fromjson? // empty) as $e
            | if $e.type == "agent_event" and $e.event.type == "content_end"
                  and $e.event.contentType == "text" then
                  {type: "assistant", message: {content: [{type: "text", text: $e.event.text}]}} | tojson
              else empty end
          '
    cline_status="${PIPESTATUS[0]}"
else
    env -u UNCLE_STATUS_FILE -u UNCLE_PROJECT_ROOT -u UNCLE_CONFIG -u STAGEGATE_RUN_ID -u STAGEGATE_ORIGIN_REPO -u STAGEGATE_ORIGIN_ISSUE -u DOCUMENT_BUDGET_SOURCE "$CLINE_CMD" "${args[@]}" "$prompt" \
        | tee "$raw" \
        | jq -R -r --unbuffered '
            (fromjson? // empty) as $e
            | if $e.type == "agent_event" and $e.event.type == "content_end"
                  and $e.event.contentType == "text" then
                  {type: "assistant", message: {content: [{type: "text", text: $e.event.text}]}} | tojson
              else empty end
          '
    cline_status="${PIPESTATUS[0]}"
fi
set -e

# Synthesize the terminal result event from cline's run_result (or fail loudly).
result="$(jq -R -s -c '
  [split("\n")[] | fromjson? // empty] as $events
  | ($events | map(select(.type == "run_result")) | .[-1]) as $r
  | if $r == null then
      {type:"result", subtype:"error_during_execution", is_error:"true",
       num_turns:1, duration_ms:0, total_cost_usd:null,
       usage:{input_tokens:0, output_tokens:0,
              cache_read_input_tokens:0, cache_creation_input_tokens:0}}
    else
      {type:"result",
       subtype: (if $r.finishReason == "completed" then "success" else "error_during_execution" end),
       is_error: (if $r.finishReason == "completed" then "false" else "true" end),
       num_turns: ($r.iterations // 1),
       duration_ms: ($r.durationMs // 0),
       total_cost_usd: ($r.usage.totalCost // null),
       input_includes_cache: true,
       usage: {input_tokens: ($r.usage.inputTokens // 0),
               output_tokens: ($r.usage.outputTokens // 0),
               cache_read_input_tokens: ($r.usage.cacheReadTokens // 0),
               cache_creation_input_tokens: ($r.usage.cacheWriteTokens // 0)}}
    end
' "$raw")"
# A context/token exhaustion is a distinct, recoverable failure: surface it as
# its own subtype so the driver can offer to change the model and retry.
#
# Matched against the failure text only, never the whole stream. cline's
# run_result carries a catalogue of available models, and those descriptions
# say things like "Frontier reasoning and coding with 1M context window" -- so
# scanning the transcript labelled every cline failure context exhaustion,
# a weekly billing limit included, and sent the operator to change models when
# the fix was to change providers or wait. Assistant text is out of scope for
# the same reason: a stage that writes the words "token limit" into its own
# output must not thereby change how its failure is classified.
cline_failure_text="$(jq -R -r '
    (fromjson? // empty) as $e
    | if $e.type == "error" then ($e.message // "")
      elif $e.type == "run_result" then ($e.text // "")
      elif $e.type == "agent_event" and $e.event.type == "done" then ($e.event.text // "")
      else empty end
' "$raw" 2>/dev/null || true)"
if [[ "$(printf '%s' "$result" | jq -r '.is_error // "true"')" == "true" ]]; then
    if printf '%s' "$cline_failure_text" | grep -qiE 'context (length|window)|maximum context|out of (tokens|context)|token limit|too many tokens|context_length_exceeded'; then
        result="$(printf '%s' "$result" | jq -c '.subtype = "context_length_exceeded"')"
    fi
    # Attach the last failure line so the driver can show the real cause --
    # "session not found: ..." when cline's hub daemon dies mid-stage, say --
    # instead of a bare subtype. One line, capped: a failure can run long.
    error_detail="$(printf '%s' "$cline_failure_text" | grep -v '^[[:space:]]*$' | tail -n 1 | cut -c1-300 || true)"
    if [[ -n "$error_detail" ]]; then
        result="$(printf '%s' "$result" | jq -c --arg detail "$error_detail" '. + {error_detail: $detail}')"
    fi
fi

printf '%s\n' "$result"

if [[ "$cline_status" -ne 0 ]]; then
    exit "$cline_status"
fi
if [[ "$(printf '%s' "$result" | jq -r '.is_error // "true"')" == "true" ]]; then
    exit 1
fi
exit 0

#!/usr/bin/env bash
# Agent-CLI shim that routes per-stage between `claude` and `kimi`.
#
# The drivers call one $AGENT_CMD for every stage and select the tier with
# --model, so swapping the whole command would move the opus stages too. This
# shim dispatches instead: no model or a kimi tier runs on kimi; an explicit
# non-Kimi model is passed through to claude untouched.
#
# kimi is not flag-compatible with `claude -p`, so the kimi path translates:
# the prompt moves from stdin to -p, claude-only flags are dropped, and kimi's
# event stream is rewritten into the schema format_claude_stream expects.
set -euo pipefail

CLAUDE_CMD="${WORKFLOW_CLAUDE_CMD:-claude}"
KIMI_CMD="${WORKFLOW_KIMI_CMD:-kimi}"
KIMI_MODEL="${WORKFLOW_KIMI_MODEL:-moonshot-ai/kimi-k2.7-code-highspeed}"

# Find --model without disturbing the argument list.
model="kimi"
prev=""
for arg in "$@"; do
    if [[ "$prev" == "--model" ]]; then
        model="$arg"
        break
    fi
    prev="$arg"
done

# Anything that is not a kimi tier stays on claude, flags and stdin intact.
case "$model" in
    kimi|kimi:*) ;;
    *) exec "$CLAUDE_CMD" "$@" ;;
esac

# `kimi:<alias>` names a model from config.toml explicitly; bare `kimi` takes
# the configured default tier.
if [[ "$model" == kimi:* ]]; then
    resolved="${model#kimi:}"
else
    resolved="$KIMI_MODEL"
fi

# Drop the claude-only surface. Value-taking flags consume their argument so it
# is not mistaken for a positional prompt.
kimi_args=()
skip_value=0
for arg in "$@"; do
    if [[ "$skip_value" == "1" ]]; then
        skip_value=0
        continue
    fi
    case "$arg" in
        --model|--max-turns|--effort|--max-budget-usd|--allowedTools|\
        --resume|--output-format|--mcp-config)
            skip_value=1
            ;;
        -p|--verbose|--strict-mcp-config|--fork-session|\
        --exclude-dynamic-system-prompt-sections)
            ;;
        *)
            kimi_args+=("$arg")
            ;;
    esac
done

# The drivers feed the prompt on stdin; kimi needs it as a -p value.
prompt="$(cat)"

# kimi emits OpenAI-shaped events and no result/usage event. Rewrite the two
# the drivers render, drop meta and tool results, and pass non-JSON lines
# through so startup errors stay visible in the log.
# bash 3.2 under `set -u` errors on "${arr[@]}" when arr is empty.
# Stall guard. kimi talks to a remote API; a connection can go established but
# silent, and the process then sits in a socket read at 0% CPU forever. The
# drivers cannot catch that: this shim drops --max-turns and --max-budget-usd
# because kimi does not accept them, so a stalled stage has no cap of any kind
# and parks the pipeline indefinitely.
#
# The bound is on *silence*, not on total runtime. EXECUTE_CHECKLIST legitimately
# runs for many minutes, so a wall-clock cap would kill healthy stages; a stage
# that has produced no output at all for this long is not working.
IDLE_TIMEOUT="${WORKFLOW_KIMI_IDLE_TIMEOUT:-300}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
fifo="$work/stream"
beat="$work/heartbeat"
mkfifo "$fifo"
: > "$beat"

mtime_of() {
    stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || echo 0
}

start="$SECONDS"
set +e

# Job control gives the background job its own process group, so the watchdog
# can signal the whole tree. Killing only kimi leaves its children holding the
# fifo's write end open, and the reader below then blocks on a stream that will
# never reach EOF -- a different hang in place of the one being fixed.
set -m
"$KIMI_CMD" --print -p "$prompt" -m "$resolved" --output-format stream-json \
    ${kimi_args[@]+"${kimi_args[@]}"} > "$fifo" 2>&1 &
kimi_pid=$!
set +m

# Watchdog: kill kimi once the stream has been quiet for IDLE_TIMEOUT. It exits
# on its own when kimi does, so a healthy run leaves nothing behind.
(
    while kill -0 "$kimi_pid" 2>/dev/null; do
        sleep 10
        kill -0 "$kimi_pid" 2>/dev/null || break
        quiet=$(( $(date +%s) - $(mtime_of "$beat") ))
        if [[ "$quiet" -ge "$IDLE_TIMEOUT" ]]; then
            echo "agent-kimi.sh: no output for ${quiet}s (limit ${IDLE_TIMEOUT}s); stopping kimi." >&2
            kill -TERM -"$kimi_pid" 2>/dev/null || kill -TERM "$kimi_pid" 2>/dev/null
            sleep 5
            kill -KILL -"$kimi_pid" 2>/dev/null || kill -KILL "$kimi_pid" 2>/dev/null
            break
        fi
    done
) &
watchdog_pid=$!

# The reader marks the heartbeat per line, so "quiet" means the stream is quiet
# rather than the process merely being slow between tokens.
{
    while IFS= read -r -t "$(( IDLE_TIMEOUT + 30 ))" line; do
        printf '%s\n' "$line"
        : > "$beat"
    done < "$fifo"
} | jq -R -r --unbuffered '
        . as $line
        | (fromjson? // null) as $e
        | if $e == null then $line
          elif $e.role == "assistant" and ($e.content? // "") != "" then
              {type: "assistant", message: {content: [{type: "text", text: $e.content}]}} | tojson
          elif $e.role == "assistant" and ($e.tool_calls? | length) > 0 then
              {type: "assistant", message: {content: [$e.tool_calls[] | {type: "tool_use", name: .function.name}]}} | tojson
          else empty end
      '
# The reader/jq pipeline is what just finished; kimi is the background job.
jq_status="${PIPESTATUS[1]}"
wait "$kimi_pid"
kimi_status=$?
kill "$watchdog_pid" 2>/dev/null
wait "$watchdog_pid" 2>/dev/null
set -e

# A watchdog kill surfaces as a signal status (128+n). Report it as this shim's
# failure rather than as a mysterious agent crash.
if [[ "$kimi_status" -gt 128 ]]; then
    echo "agent-kimi.sh: kimi was stopped after ${IDLE_TIMEOUT}s of silence." >&2
fi

status=0
if [[ "$kimi_status" -ne 0 ]]; then
    status="$kimi_status"
elif [[ "$jq_status" -ne 0 ]]; then
    status="$jq_status"
fi

# Close the stream the way the drivers require. A missing `result` event is
# read as stage failure, and rightly so for claude: a budget breach or a
# turn-limit stop exits 0 and confesses only inside that event, so its absence
# cannot be taken for success. kimi never emits one, which made every kimi
# stage fail no matter how well it went. Synthesizing it here keeps the check
# meaningful for claude instead of relaxing it for both.
#
# kimi reports neither a turn count nor a spend figure, so those fields are
# zero rather than invented; the ledger already reads them with `// 0`.
if [[ "$status" -eq 0 ]]; then
    subtype="success"
    is_error="false"
else
    subtype="error_during_execution"
    is_error="true"
fi

printf '{"type":"result","subtype":"%s","is_error":%s,"num_turns":0,"duration_ms":%d,"total_cost_usd":0}\n' \
    "$subtype" "$is_error" "$(( (SECONDS - start) * 1000 ))"

exit "$status"

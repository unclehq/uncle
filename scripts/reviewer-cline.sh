#!/usr/bin/env bash
# Reviewer-CLI shim that runs `cline` in plan mode (read-only) for the drivers'
# adversarial-review / checklist / audit stages.
#
# The drivers call $REVIEWER_CMD with `codex exec` flags; cline is not
# flag-compatible, so this translates:
#   exec, --ephemeral, --json, --skip-git-repo-check   dropped
#   --sandbox read-only     -> cline -p (plan mode enforces read-only)
#   -m/--model MODEL        -> cline -m MODEL
#   -c model_reasoning_effort=X  -> cline --thinking X
#   --output-last-message FILE   -> write the final review text to FILE
#   <prompt> (trailing positional) -> cline prompt
#
# Read-only is enforced by plan mode, not by a tool allowlist: a reviewer that
# could edit the plan it is reviewing would not be an independent check.
set -euo pipefail

CLINE_CMD="${WORKFLOW_CLINE_CMD:-cline}"

model=""
effort=""
output_file=""
prompt=""
skip_value=0
pending=""
for arg in "$@"; do
    if [[ "$skip_value" == "1" ]]; then
        case "$pending" in
            model) model="$arg" ;;
            effort)
                case "$arg" in
                    model_reasoning_effort=*) effort="${arg#model_reasoning_effort=}" ;;
                esac
                ;;
            output) output_file="$arg" ;;
        esac
        skip_value=0
        pending=""
        continue
    fi
    case "$arg" in
        exec|--ephemeral|--json|--skip-git-repo-check) ;;
        --sandbox) skip_value=1; pending="sandbox" ;;
        -m|--model) skip_value=1; pending="model" ;;
        -c) skip_value=1; pending="effort" ;;
        --output-last-message) skip_value=1; pending="output" ;;
        -*) ;;
        *) prompt="$arg" ;;
    esac
done

# `uncle` exports these when the user picks a model / performance; they win over
# the driver's per-stage flags.
# Dedicated reviewer model (config `reviewer` key) > global pick > driver -m.
if [[ -n "${UNCLE_CLINE_REVIEWER_MODEL:-}" ]]; then
    model="$UNCLE_CLINE_REVIEWER_MODEL"
elif [[ -n "${UNCLE_CLINE_MODEL+x}" ]]; then
    model="$UNCLE_CLINE_MODEL"
fi
if [[ -n "${UNCLE_CLINE_EFFORT+x}" ]]; then
    effort="$UNCLE_CLINE_EFFORT"
fi
if [[ -z "$effort" ]]; then
    effort="medium"
fi

if [[ -z "$prompt" ]]; then
    echo "reviewer-cline.sh: no prompt argument" >&2
    exit 2
fi

args=(--json -p)
if [[ -n "$model" ]]; then
    args+=(-m "$model")
fi
args+=(--thinking "$effort")

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
raw="$work/events.ndjson"
status_file="${UNCLE_STATUS_FILE:-}"

if [[ -n "$status_file" ]]; then
    printf '{"event":"start","model":"%s","mode":"plan"}\n' "$model" >> "$status_file"
fi

set +e
"$CLINE_CMD" "${args[@]}" "$prompt" > "$raw" 2>&1
status=$?
set -e

review="$(jq -R -s -r '
  [split("\n")[] | fromjson? // empty] as $events
  | ($events | map(select(.type == "run_result")) | .[-1] | .text // null) as $rr
  | ($events | map(select(.type == "agent_event" and .event.type == "done")) | .[-1] | .event.text // null) as $dn
  | ($rr // $dn // "")
' "$raw")"

tokens="$(jq -R -s -r '
  [split("\n")[] | fromjson? // empty]
  | map(select(.type == "run_result")) | .[-1]
  | ((.usage.inputTokens // 0) + (.usage.outputTokens // 0)
     + (.usage.cacheReadTokens // 0) + (.usage.cacheWriteTokens // 0) | tostring)
' "$raw")"

if [[ -n "$status_file" ]]; then
    jq -R -s -r --arg model "$model" '
      [split("\n")[] | fromjson? // empty]
      | map(select(.type == "run_result")) | .[-1] as $r
      | {event:"usage", model:$model, mode:"plan",
         total_tokens: (($r.usage.totalInputTokens // 0)
                      + ($r.usage.totalOutputTokens // 0)
                      + ($r.usage.totalCacheReadTokens // 0)
                      + ($r.usage.totalCacheWriteTokens // 0))} | tojson
    ' "$raw" >> "$status_file"
fi

if [[ "$status" -ne 0 ]]; then
    echo "reviewer-cline.sh: $CLINE_CMD exited with status $status" >&2
    exit "$status"
fi

if [[ -z "$review" ]]; then
    echo "reviewer-cline.sh: no final text produced by the review" >&2
    exit 1
fi

if [[ -n "$output_file" ]]; then
    printf '%s\n' "$review" > "$output_file"
fi

# Print the review to stdout (landing in the stage log for debugging), then the
# token line record_codex_cost reads.
printf '%s\n' "$review"
printf 'tokens used\n%s\n' "${tokens:-0}"
exit 0

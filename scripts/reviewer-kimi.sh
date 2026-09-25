#!/usr/bin/env bash
# Translate the driver's Codex reviewer contract to Kimi's custom read-only agent.
set -euo pipefail
if [[ -n "${UNCLE_RUNTIME_ROOT:-}" && -d "$UNCLE_RUNTIME_ROOT/scripts" ]]; then
    ROOT="$(cd -L "$UNCLE_RUNTIME_ROOT" && pwd -L)"
else
    ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
model=kimi
output_file=""
prompt=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        exec|--ephemeral|--json|--skip-git-repo-check) shift ;;
        --sandbox|-c) [[ $# -ge 2 ]] || exit 2; shift 2 ;;
        -m|--model) [[ $# -ge 2 ]] || exit 2; model="$2"; shift 2 ;;
        --output-last-message) [[ $# -ge 2 ]] || exit 2; output_file="$2"; shift 2 ;;
        -*) echo "Unsupported reviewer flag: $1" >&2; exit 2 ;;
        *) prompt="$1"; shift ;;
    esac
done
[[ -n "$prompt" && -n "$output_file" ]] || exit 2
# A failed attempt must not expose a previous review as fresh evidence.
rm -f -- "$output_file"
case "$model" in kimi|kimi:*) ;; *) model="kimi:$model" ;; esac
stream=$(mktemp)
agent_file="$ROOT/lib/kimi/reviewer.md"
delivery_profile=""
if [[ -n "${UNCLE_ARTIFACT_DELIVERY:-}" ]]; then
    delivery_profile=$(mktemp)
    # Only this profile exception grants Write, and the driver prompt names
    # the sole allowed target.  Human Markdown reviews remain read-only.
    sed '/  - Grep/a\  - Write' "$agent_file" > "$delivery_profile"
    agent_file="$delivery_profile"
fi
trap 'rm -f "$stream" "$delivery_profile"' EXIT
# Legacy human reviews use the fixed read-only profile. JSON packets receive
# the short-lived profile above solely to create their delivery file.
printf '%s' "$prompt" | "$ROOT/scripts/agent-kimi.sh" --model "$model" \
    --agent-file "$agent_file" | tee "$stream"
# Use the last assistant text, not intermediate reasoning or tool-call messages.
review=$(jq -rs '[.[] | select(.type == "assistant") |
    [.message.content[]? | select(.type == "text") | .text] | join("") |
    select(length > 0)] | last // empty' "$stream")
if [[ -n "${UNCLE_ARTIFACT_DELIVERY:-}" && -s "$UNCLE_ARTIFACT_DELIVERY" ]]; then
    review="$(cat "$UNCLE_ARTIFACT_DELIVERY")"
fi
[[ -n "$review" ]] || { echo "Kimi produced no review." >&2; exit 1; }
# Non-empty is not the same as a document: a model can end its turn having only
# announced the work. Fail here, where the reason is still visible.
review="$(printf '%s' "$review" | python3 "$ROOT/scripts/lib/reviewer_output.py" --artifact "$output_file" kimi)" || exit 1
printf '%s\n' "$review" > "$output_file"

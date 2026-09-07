#!/usr/bin/env bash
# Translate the driver's Codex reviewer contract to Kimi's custom read-only agent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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
trap 'rm -f "$stream"' EXIT
# The fixed tool allowlist grants no shell, writes, delegation, or inherited tools.
printf '%s' "$prompt" | "$ROOT/scripts/agent-kimi.sh" --model "$model" \
    --agent-file "$ROOT/lib/kimi/reviewer.md" | tee "$stream"
# Use the last assistant text, not intermediate reasoning or tool-call messages.
review=$(jq -rs '[.[] | select(.type == "assistant") |
    [.message.content[]? | select(.type == "text") | .text] | join("") |
    select(length > 0)] | last // empty' "$stream")
[[ -n "$review" ]] || { echo "Kimi produced no review." >&2; exit 1; }
printf '%s\n' "$review" > "$output_file"

#!/usr/bin/env bash
# Shared reviewer prompt helpers, sourced by stagegate.sh and change-workflow.sh.
#
# Contract (fixed for callers):
#   reviewer_prompt_guard NAME KIND FILE
#   reviewer_report_launch_failure NAME STATUS LOG [PACKET]

# Linux caps one argv element at 131072 bytes; stay below it.
REVIEWER_PROMPT_ARGV_LIMIT=120000

# reviewer_prompt_guard NAME KIND FILE
#   KIND: "file" (client takes --prompt-file: python3 running self_hosted.py or
#         native_stage.py) or "argv" (every other reviewer command).
#   Fails (returns 1) iff KIND is argv and FILE is strictly larger than
#   REVIEWER_PROMPT_ARGV_LIMIT bytes (wc -c). FILE must be the exact final
#   argv element content, including any prefix/suffix wrapper text.
#   Returns 2 on a usage error.
reviewer_prompt_guard() {
  local name="${1:-}" kind="${2:-}" file="${3:-}" size
  if [ -z "$name" ] || [ -z "$file" ]; then
    echo "reviewer_prompt_guard: usage: NAME KIND FILE" >&2
    return 2
  fi
  case "$kind" in
    file) return 0 ;;
    argv) ;;
    *)
      echo "reviewer_prompt_guard: unknown KIND '$kind' for $name (expected file or argv)" >&2
      return 2
      ;;
  esac
  if [ ! -r "$file" ]; then
    echo "reviewer_prompt_guard: prompt file not readable for $name: $file" >&2
    return 2
  fi
  size=$(wc -c < "$file" | tr -d '[:space:]')
  if [ "$size" -gt "$REVIEWER_PROMPT_ARGV_LIMIT" ]; then
    echo "Reviewer $name: prompt is $size bytes, over Linux's 131,072-byte per-argument limit (guard $REVIEWER_PROMPT_ARGV_LIMIT); this reviewer command cannot read the prompt from a file. Shorten the prompt or use a file-capable reviewer (self_hosted.py / native_stage.py)." >&2
    return 1
  fi
  return 0
}

# reviewer_report_launch_failure NAME STATUS LOG [PACKET]
#   Returns 0 (and prints a message) only when the reviewer failed to launch:
#     (a) STATUS is 126 or 127 and no packet was written, or
#     (b) STATUS is nonzero, LOG contains 'Argument list too long', and no
#         packet was written.
#   Returns 1 otherwise. STATUS 0 or a non-empty PACKET is never a launch failure.
reviewer_report_launch_failure() {
  local name="${1:-}" status="${2:-}" log="${3:-}" packet="${4:-}"
  case "$status" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ "$status" -ne 0 ] || return 1
  if [ -n "$packet" ] && [ -s "$packet" ]; then
    return 1
  fi
  if [ "$status" -eq 126 ] || [ "$status" -eq 127 ]; then
    echo "Reviewer $name: launch failed (exit $status); the reviewer command did not start." >&2
    return 0
  fi
  if [ -n "$log" ] && [ -r "$log" ] && grep -q 'Argument list too long' "$log"; then
    echo "Reviewer $name: launch failed (exit $status): argument list too long." >&2
    return 0
  fi
  return 1
}

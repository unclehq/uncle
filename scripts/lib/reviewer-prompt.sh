#!/usr/bin/env bash
# Shared reviewer prompt helpers, sourced by stagegate.sh and change-workflow.sh.
#
# Contract (fixed for callers):
#   reviewer_prompt_guard NAME KIND FILE
#   reviewer_report_launch_failure NAME STATUS LOG [PACKET]
#   reviewer_prompt_kind CMD...   prints "file" or "argv", always returns 0.
#     Positional match: only element 0, or element 1 when element 0's basename
#     is an interpreter (python3, python, bash, sh). That element's basename
#     must be self_hosted.py, native_stage.py or reviewer-self-hosted.sh
#     (the wrapper only when its resolved dir is ${UNCLE_RUNTIME_ROOT}/scripts)
#     to print "file". No arguments, empty strings, or later look-alike
#     arguments print "argv". stagegate.sh additionally treats a python3-first
#     command as file (decision D1); change-workflow.sh uses the helper alone (D2).

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

# reviewer_prompt_kind CMD...
reviewer_prompt_kind() {
  local el="${1:-}" base dir want got
  if [ -n "$el" ]; then
    case "${el##*/}" in
      python3|python|bash|sh) el="${2:-}" ;;
    esac
  fi
  [ -n "$el" ] || { echo argv; return 0; }
  base="${el##*/}"
  case "$base" in
    self_hosted.py|native_stage.py) echo file; return 0 ;;
    reviewer-self-hosted.sh)
      case "$el" in
        */*)
          if [ -n "${UNCLE_RUNTIME_ROOT:-}" ]; then
            dir=$(cd -P "$(dirname "$el")" 2>/dev/null && pwd -P) || dir=""
            want=$(cd -P "${UNCLE_RUNTIME_ROOT}/scripts" 2>/dev/null && pwd -P) || want=""
            if [ -n "$dir" ] && [ "$dir" = "$want" ]; then
              echo file
              return 0
            fi
          fi
          ;;
      esac
      ;;
  esac
  echo argv
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

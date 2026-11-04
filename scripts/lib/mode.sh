#!/usr/bin/env bash
# Single resolver for attended/unattended mode. Sourced by the launcher and
# every driver; owns every mode string. Notices and refusals go to stderr only.
#
# API
#   uncle_capture_tty            capture isatty(0) once -> UNCLE_STDIN_TTY (1/0)
#   uncle_resolve_mode "$@"      sets UNATTENDED, UNCLE_UNATTENDED (0/1),
#                                UNCLE_MODE_RESOLVED=1, UNCLE_MODE_SOURCE
#                                (flag|env|inherited|resume|default).
#                                Returns 1 after a refusal. Writes no state.
#                                UNCLE_MODE_DIR (optional) names the
#                                .uncle/workflow dir consulted for resume.
#   uncle_write_mode_file DIR M  atomic write of DIR/mode (owner drivers only)
#   uncle_mode_banner            print the banner for the resolved mode

uncle_msg_banner_unattended='Mode: unattended (default). Approval gates are delegated to the agent; use --attended to approve each gate yourself.'
uncle_msg_banner_attended='Mode: attended. Each approval gate waits for your decision.'
uncle_msg_refuse_contradict='uncle: --attended and --unattended contradict each other; choose one.'
uncle_msg_refuse_no_tty='uncle: attended mode needs an interactive terminal on stdin, or stdin left free to answer gates (not consumed by a bare --application, bare --issue or --change-request).'
uncle_msg_refuse_inherited='uncle: attended mode was requested but this run was already resolved as unattended; start a new run with --attended.'
uncle_msg_notice_flag='uncle: --unattended is deprecated; unattended is now the default. Use --attended to approve gates yourself.'

uncle_msg_banner_resumed() { printf 'Mode: %s (resumed from .uncle/workflow/mode).' "$1"; }
uncle_msg_notice_env() { printf 'uncle: %s=1 is deprecated; unattended is now the default. Use UNCLE_ATTENDED=1 to approve gates yourself.' "$1"; }
uncle_msg_refuse_mode_file() { printf 'uncle: %s is not a regular file containing exactly "attended" or "unattended"; fix or remove it.' "$1"; }
uncle_msg_notice_mode_missing() { printf 'uncle: %s is missing for this existing run; it predates the mode file and resumes attended.' "$1"; }

uncle_capture_tty() {
  if [ -z "${UNCLE_STDIN_TTY:-}" ]; then
    if [ -t 0 ]; then UNCLE_STDIN_TTY=1; else UNCLE_STDIN_TTY=0; fi
  fi
  export UNCLE_STDIN_TTY
}

uncle__err() { printf '%s\n' "$1" >&2; }

uncle__tty_ok() {
  [ "${UNCLE_ATTENDED_STDIN:-}" = 1 ] && return 0
  uncle_capture_tty
  [ "$UNCLE_STDIN_TTY" = 1 ]
}

# Prints attended|unattended|none|missing; returns 1 on an invalid mode file.
uncle__recorded_mode() {
  local dir=$1 f="$1/mode" entry content have=0
  [ -d "$dir" ] || { echo none; return 0; }
  for entry in "$dir"/* "$dir"/.[!.]*; do
    [ -e "$entry" ] || [ -L "$entry" ] || continue
    [ "$entry" = "$f" ] && continue
    # Written by the launcher before the driver resolves the mode (issue seed,
    # lock, performance log); they do not mean a prior run exists.
    case "${entry##*/}" in driver.lock|family|origin|origin.bound|performance) continue ;; esac
    have=1; break
  done
  if [ ! -e "$f" ] && [ ! -L "$f" ]; then
    if [ "$have" = 1 ]; then echo missing; else echo none; fi
    return 0
  fi
  [ "$have" = 1 ] || { echo none; return 0; }   # stale file, no run state
  if [ -L "$f" ] || [ ! -f "$f" ]; then return 1; fi
  content=$(cat "$f"; printf x); content=${content%x}
  case "$content" in
    attended|"attended
") echo attended ;;
    unattended|"unattended
") echo unattended ;;
    *) return 1 ;;
  esac
}

uncle_resolve_mode() {
  local arg a_flag=0 u_flag=0 want_attended=0 name mode source rec dir
  local legacy=()
  for arg in "$@"; do
    case "$arg" in
      --attended) a_flag=1 ;;
      --unattended) u_flag=1 ;;
    esac
  done
  if [ "$a_flag" = 1 ] && [ "$u_flag" = 1 ]; then
    uncle__err "$uncle_msg_refuse_contradict"; return 1
  fi
  if [ "$a_flag" = 1 ] || [ "${UNCLE_ATTENDED:-}" = 1 ]; then want_attended=1; fi

  if [ "${UNCLE_MODE_RESOLVED:-}" = 1 ]; then
    if [ "${UNCLE_UNATTENDED:-}" = 1 ]; then mode=unattended; else mode=attended; fi
    if [ "$mode" = unattended ] && [ "$want_attended" = 1 ]; then
      uncle__err "$uncle_msg_refuse_inherited"; return 1
    fi
    source=inherited
  else
    [ "$u_flag" = 1 ] && legacy+=("--unattended")
    for name in UNCLE_UNATTENDED WORKFLOW_UNATTENDED UNCLE_HOUSEKEEPING_UNATTENDED; do
      [ "${!name:-}" = 1 ] && legacy+=("$name")
    done
    dir=${UNCLE_MODE_DIR:-}
    rec=none
    if [ -n "$dir" ]; then
      if ! rec=$(uncle__recorded_mode "$dir"); then
        uncle__err "$(uncle_msg_refuse_mode_file "$dir/mode")"; return 1
      fi
    fi
    if [ "$want_attended" = 1 ]; then
      mode=attended; source=flag
      [ "$a_flag" = 1 ] || source=env
    elif [ "${#legacy[@]}" -gt 0 ]; then
      mode=unattended; source=env
      [ "$u_flag" = 1 ] && source=flag
    elif [ "$rec" = attended ] || [ "$rec" = unattended ]; then
      mode=$rec; source=resume
    elif [ "$rec" = missing ]; then
      mode=attended; source=resume
    else
      mode=unattended; source=default
    fi
    if [ "$mode" = attended ] && ! uncle__tty_ok; then
      uncle__err "$uncle_msg_refuse_no_tty"; return 1
    fi
    if [ "$rec" = missing ] && [ "$source" = resume ]; then
      uncle__err "$(uncle_msg_notice_mode_missing "$dir/mode")"
    fi
    if [ -z "${UNCLE_MODE_NOTICED:-}" ]; then
      for name in ${legacy[@]+"${legacy[@]}"}; do
        if [ "$name" = "--unattended" ]; then uncle__err "$uncle_msg_notice_flag"
        else uncle__err "$(uncle_msg_notice_env "$name")"; fi
      done
      UNCLE_MODE_NOTICED=1
    fi
  fi
  if [ "$source" = inherited ] && [ "$mode" = attended ] && ! uncle__tty_ok; then
    uncle__err "$uncle_msg_refuse_no_tty"; return 1
  fi

  if [ "$mode" = unattended ]; then UNATTENDED=1; else UNATTENDED=0; fi
  UNCLE_UNATTENDED=$UNATTENDED
  UNCLE_MODE_RESOLVED=1
  UNCLE_MODE_SOURCE=$source
  UNCLE_MODE=$mode
  export UNATTENDED UNCLE_UNATTENDED UNCLE_MODE_RESOLVED UNCLE_MODE_SOURCE UNCLE_MODE
  return 0
}

uncle_mode_banner() {
  if [ "${UNCLE_MODE_SOURCE:-}" = resume ]; then
    uncle__err "$(uncle_msg_banner_resumed "$UNCLE_MODE")"
  elif [ "${UNCLE_MODE:-}" = attended ]; then
    uncle__err "$uncle_msg_banner_attended"
  else
    uncle__err "$uncle_msg_banner_unattended"
  fi
}

uncle_write_mode_file() {
  local dir=$1 mode=$2 f tmp
  f="$dir/mode"
  if [ -L "$f" ] || { [ -e "$f" ] && [ ! -f "$f" ]; }; then
    uncle__err "$(uncle_msg_refuse_mode_file "$f")"; return 1
  fi
  mkdir -p "$dir" || return 1
  tmp=$(mktemp "$dir/.mode.XXXXXX") || return 1
  printf '%s\n' "$mode" >"$tmp" && mv -f "$tmp" "$f" || { rm -f "$tmp"; return 1; }
}

#!/usr/bin/env bash
# Driver-side supervision hooks: status events for validators, and retained
# corrections appended to a stage prompt on a permitted retry.
#
# Everything here is active by default; `supervision.enabled false` in the
# project's .uncle/config disables it. Events are additive JSON lines on the status
# channel the TUI already reads; with no UNCLE_STATUS_FILE nothing is written.
# The prompt a stage reads is byte-identical to today's unless supervision is
# enabled and a note for this exact run and state exists.
#
# bash 3.2 compatible: no associative arrays, no ${var^^}.

SUPERVISION_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

supervision_config_file() {
    printf '%s' "${UNCLE_CONFIG:-${PROJECT_ROOT:-$PWD}/.uncle/config}"
}

# supervision_enabled -- enabled by default, with an explicit config opt-out.
supervision_enabled() {
    local file line
    file="$(supervision_config_file)"
    [[ -s "$file" ]] || return 0
    while IFS= read -r line; do
        line="${line%%#*}"
        line="$(printf '%s' "$line" | tr -s '[:space:]' ' ')"
        line="${line# }"
        line="${line% }"
        case "$line" in
            'supervision.enabled false') return 1 ;;
            'supervision.enabled true') return 0 ;;
        esac
    done < "$file"
    return 0
}

# supervision_event <event> [key=value ...] -- one status line; never fails the caller.
supervision_event() {
    [[ -n "${UNCLE_STATUS_FILE:-}" ]] || return 0
    python3 "$SUPERVISION_LIB_DIR/supervisor.py" event --file "$UNCLE_STATUS_FILE" --event "$@" 2>/dev/null || true
}

# supervision_validation_failed <validator> <artifact> <diagnostic> [exit]
# Emitted before the existing handling of a validator failure; the outcome
# of that handling is unchanged.
supervision_validation_failed() {
    supervision_event validation_failed "stage=${UNCLE_STATUS_STAGE:-}" "validator=$1" "artifact=$2" \
        "diagnostic=$3" "exit=${4:-1}" "state=$(supervision_state)"
}

supervision_state() {
    local file="${STATE_FILE:-${STATE_DIR:-.uncle/workflow}/state}" raw
    [[ -s "$file" ]] || return 0
    raw="$(head -n 1 "$file")"
    printf '%s' "${raw#*:}"
}

# supervision_stage_end <stage> <status> [log] -- closes the stage's active
# interval and names the log the supervisor may quote from.
supervision_stage_end() {
    supervision_event stage_end "stage=$1" "status=$2" "log=${3:-}"
}

# supervision_gate_open / supervision_gate_close -- a human prompt is waiting
# for an answer; that time is excluded from every supervision timer (D-15).
# Every gate prompt in both drivers goes through gate_prompt, which opens;
# the read sites of the approval gates close. Any later stage activity also
# closes it on the controller side, so a missed close never counts as human time
# forever.
# The gate's identity (run UUID + monotonic prompt id, kind, class, choices,
# file) is emitted whether or not supervision is enabled: the TUI may answer
# a prompt at a human's request only when this metadata names it, and the
# read wrapper below attributes the line it reads from the matching receipt
# alone (D-5, D-6). Nothing here changes what the driver does with the line.
# Sets and exports UNCLE_GATE_RUN once per driver process. Not a command
# substitution: the assignment has to land in the calling shell.
supervision_gate_run() {
    if [[ -z "${UNCLE_GATE_RUN:-}" ]]; then
        UNCLE_GATE_RUN="$(python3 "$SUPERVISION_LIB_DIR/gate_answer.py" run-id 2>/dev/null || echo "run-$$")"
        export UNCLE_GATE_RUN
    fi
}

supervision_gate_open() {
    supervision_gate_run
    UNCLE_GATE_PROMPT="$(python3 "$SUPERVISION_LIB_DIR/gate_answer.py" open \
        --state-dir "${STATE_DIR:-.uncle/workflow}" --file "${UNCLE_STATUS_FILE:-}" --stage "${UNCLE_STATUS_STAGE:-}" \
        --run "$UNCLE_GATE_RUN" --text "${1:-}" --class "${UNCLE_GATE_CLASS:-}" --gate-file "${UNCLE_GATE_FILE:-}" 2>/dev/null || true)"
}

supervision_gate_close() {
    supervision_event gate_close "stage=${UNCLE_STATUS_STAGE:-}"
}

# supervision_gate_read VAR -- read one answer line into VAR (no command
# substitution: the caller's variable is assigned directly), then set
# UNCLE_GATE_ANSWERED_BY from the receipt for this exact run, prompt and
# answer, or to empty. The read's own status is returned unchanged.
supervision_gate_read() {
    local __var="$1" __line="" __rc=0
    IFS= read -r __line || __rc=$?
    printf -v "$__var" '%s' "$__line"
    UNCLE_GATE_ANSWERED_BY=""
    if [[ $__rc -eq 0 && -n "${UNCLE_GATE_PROMPT:-}" ]]; then
        UNCLE_GATE_ANSWERED_BY="$(python3 "$SUPERVISION_LIB_DIR/gate_answer.py" consume \
            --state-dir "${STATE_DIR:-.uncle/workflow}" --file "${UNCLE_STATUS_FILE:-}" --stage "${UNCLE_STATUS_STAGE:-}" \
            --run "${UNCLE_GATE_RUN:-}" --prompt-id "$UNCLE_GATE_PROMPT" --answer "$__line" 2>/dev/null || true)"
    else
        supervision_gate_close
    fi
    UNCLE_GATE_PROMPT=""
    return $__rc
}

# supervision_approved_by -- the `.approved-by` value for the answer just read:
# `unattended`, the supervisor receipt (`supervisor:<explicit|standing>:<name>`),
# or the human's configured name.
supervision_approved_by() {
    if [[ "${UNATTENDED:-0}" == 1 ]]; then
        printf unattended
    elif [[ -n "${UNCLE_GATE_ANSWERED_BY:-}" ]]; then
        printf '%s' "$UNCLE_GATE_ANSWERED_BY"
    else
        printf '%s' "${UNCLE_APPROVAL_NAME:-}"
    fi
}

# gate_read VAR -- the read every interactive prompt uses; libraries sourced
# without supervision.sh define the plain fallback themselves.
gate_read() {
    supervision_gate_read "$1"
}

# supervision_prompt <prompt_path> <stage> [log] -- set SUPERVISION_PROMPT to the
# prompt path the stage should read, and export UNCLE_SUPERVISION_NOTE as the
# consumed note's action id (empty when none) for the native stage's receipt
# event. Not a command substitution: the export has to reach the caller.
# Also names the task prompt and log so a diagnosis can quote bounded excerpts.
supervision_prompt() {
    local prompt="$1" stage="$2" out path note
    SUPERVISION_PROMPT="$prompt"
    UNCLE_SUPERVISION_NOTE=""
    export UNCLE_SUPERVISION_NOTE
    supervision_enabled || return 0
    supervision_event stage_prompt "stage=$stage" "prompt=$prompt" "log=${3:-}"
    out="${LOG_DIR:-${STATE_DIR:-.uncle/workflow}/logs}/${stage}.supervised-prompt.md"
    mkdir -p "$(dirname "$out")" 2>/dev/null || true
    { read -r path; read -r note; } < <(python3 "$SUPERVISION_LIB_DIR/supervisor.py" note-prompt \
            --state-dir "${STATE_DIR:-.uncle/workflow}" --stage "$stage" --prompt "$prompt" --out "$out" \
            --config "$(supervision_config_file)" 2>/dev/null) || return 0
    [[ -n "$path" && -s "$path" ]] || return 0
    SUPERVISION_PROMPT="$path"
    if [[ -n "$note" ]]; then
        UNCLE_SUPERVISION_NOTE="$note"
        export UNCLE_SUPERVISION_NOTE
        echo "Supervision: applying retained correction $note to $stage" >&2
    fi
}

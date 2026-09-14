#!/usr/bin/env bash
# Driver-side supervision hooks: status events for validators, and retained
# corrections appended to a stage prompt on a permitted retry.
#
# Everything here is inert unless `supervision.enabled true` is in the
# project's .uncle/config. Events are additive JSON lines on the status
# channel the TUI already reads; with no UNCLE_STATUS_FILE nothing is written.
# The prompt a stage reads is byte-identical to today's unless supervision is
# enabled and a note for this exact run and state exists.
#
# bash 3.2 compatible: no associative arrays, no ${var^^}.

SUPERVISION_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

supervision_config_file() {
    printf '%s' "${UNCLE_CONFIG:-${PROJECT_ROOT:-$PWD}/.uncle/config}"
}

# supervision_enabled -- exit 0 when the config says so, without any other lib.
supervision_enabled() {
    local file line
    file="$(supervision_config_file)"
    [[ -s "$file" ]] || return 1
    while IFS= read -r line; do
        line="${line%%#*}"
        line="$(printf '%s' "$line" | tr -s '[:space:]' ' ')"
        line="${line# }"
        line="${line% }"
        if [[ "$line" == "supervision.enabled true" ]]; then
            return 0
        fi
    done < "$file"
    return 1
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
supervision_gate_open() {
    supervision_event gate_open "stage=${UNCLE_STATUS_STAGE:-}" "prompt=${1:-}"
}

supervision_gate_close() {
    supervision_event gate_close "stage=${UNCLE_STATUS_STAGE:-}"
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

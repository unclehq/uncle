#!/usr/bin/env bash
# Prompt bytes and portable case conversion. Optional supervision is supplied
# by the caller; sourcing this module performs no initialization.

upper() {
    printf '%s' "$1" | tr '[:lower:]' '[:upper:]'
}

lower() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

gate_prompt() {
    if declare -f supervision_gate_open > /dev/null; then supervision_gate_open "$1"; fi
    if [[ -t 1 && "${TERM:-}" != "dumb" ]]; then
        printf '%s%s%s' $'\033[1m' "$1" $'\033[0m'
    else
        printf '%s' "$1"
    fi
}

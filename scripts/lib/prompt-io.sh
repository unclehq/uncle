#!/usr/bin/env bash
# Prompt bytes and portable case conversion. Optional supervision is supplied
# by the caller; sourcing this module performs no initialization.

. "$(cd "${BASH_SOURCE[0]%/*}" && pwd)/strings.sh"

upper() {
    local _r
    uncle_upper_to _r "$1"
    printf '%s' "$_r"
}

lower() {
    local _r
    uncle_lower_to _r "$1"
    printf '%s' "$_r"
}

gate_prompt() {
    if declare -f supervision_gate_open > /dev/null; then supervision_gate_open "$1"; fi
    if [[ -t 1 && "${TERM:-}" != "dumb" ]]; then
        printf '%s%s%s' $'\033[1m' "$1" $'\033[0m'
    else
        printf '%s' "$1"
    fi
}

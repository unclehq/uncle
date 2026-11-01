#!/usr/bin/env bash
# Case conversion and name sanitising with shell builtins only (bash 3.2: no ${v^^}, no ${v,,}).
#
# Environment-variable keys are built from stage names on nearly every state transition, and each `printf | tr` started a process (about
# 600 launches in twenty driver cases). The `_to` forms assign into the named variable, so even the subshell of a command substitution
# is avoided. Behaviour matches the `tr` calls they replace; strings.sh is sourced more than once safely.
if ! declare -f uncle_upper_to > /dev/null 2>&1; then
    # uncle_upper_to VAR STRING [CHARS]: upper-case STRING into VAR; each character listed in CHARS becomes `_`.
    uncle_upper_to() {
        local _chars="${3:-}" _out="" _c _i _code _oct
        for ((_i = 0; _i < ${#2}; _i++)); do
            _c="${2:_i:1}"
            case "$_c" in
                [a-z]) printf -v _code '%d' "'$_c"; printf -v _oct '%03o' $((_code - 32)); printf -v _c "\\$_oct" ;;
            esac
            if [[ -n "$_chars" && "$_chars" == *"${2:_i:1}"* ]]; then _c=_; fi
            _out="$_out$_c"
        done
        printf -v "$1" '%s' "$_out"
    }
    # uncle_lower_to VAR STRING: lower-case STRING into VAR.
    uncle_lower_to() {
        local _out="" _c _i _code _oct
        for ((_i = 0; _i < ${#2}; _i++)); do
            _c="${2:_i:1}"
            case "$_c" in
                [A-Z]) printf -v _code '%d' "'$_c"; printf -v _oct '%03o' $((_code + 32)); printf -v _c "\\$_oct" ;;
            esac
            _out="$_out$_c"
        done
        printf -v "$1" '%s' "$_out"
    }
    # uncle_sanitize_to VAR STRING ALLOWED: every character of STRING not in ALLOWED (a bracket-free list of literal characters plus the
    # classes a-z A-Z 0-9, given as the words `az`, `AZ`, `09`, then any extra characters, with no separators: "azAZ09._-") becomes `_`.
    uncle_sanitize_to() {
        local _out="" _c _i _keep
        for ((_i = 0; _i < ${#2}; _i++)); do
            _c="${2:_i:1}"; _keep=0
            case "$_c" in
                [a-z]) [[ "$3" == *az* ]] && _keep=1 ;;
                [A-Z]) [[ "$3" == *AZ* ]] && _keep=1 ;;
                [0-9]) [[ "$3" == *09* ]] && _keep=1 ;;
                *) [[ "$3" == *"$_c"* ]] && _keep=1 ;;
            esac
            [[ "$_keep" == 1 ]] || _c=_
            _out="$_out$_c"
        done
        printf -v "$1" '%s' "$_out"
    }
fi

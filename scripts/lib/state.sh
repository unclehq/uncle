#!/usr/bin/env bash
# Stage-token grammar for .uncle/workflow/state, shared by change-workflow.sh and
# from-issue.sh so the two cannot drift apart on it.
#
#   <STAGE>            the legacy form; still written when no issue is known
#   <issue>:<STAGE>    written when an issue number is resolvable
#
# The prefix is informational. .uncle/workflow/origin remains the sole authority for
# every origin-match decision (INV-1), so nothing reads the prefix as an
# identity. Reading is tolerant in both directions: a bare token written by an
# older driver, by hand, or by a test fixture stays valid indefinitely.
#
# bash 3.2 compatible: no associative arrays, no ${var^^}.

# state_read <file> [default] — the bare stage token, issue prefix stripped.
# Prints <default> (empty unless given) when the file is missing or empty.
state_read() {
    local file="$1" default="${2:-}" raw

    if [[ ! -s "$file" ]]; then
        printf '%s' "$default"
        return 0
    fi

    raw="$(head -n 1 "$file")"
    # Only an all-digit run followed by ':' is a prefix. Anything else (e.g.
    # "abc:IMPLEMENT") is returned intact so it still falls through to the
    # caller's unknown-state branch rather than being silently accepted.
    if [[ "$raw" =~ ^([0-9]+):(.*)$ ]]; then
        printf '%s' "${BASH_REMATCH[2]}"
    else
        printf '%s' "$raw"
    fi
}

# state_issue <file> — the issue number the state file is bound to, or empty.
state_issue() {
    local file="$1" raw

    if [[ ! -s "$file" ]]; then
        return 0
    fi

    raw="$(head -n 1 "$file")"
    if [[ "$raw" =~ ^([0-9]+): ]]; then
        printf '%s' "${BASH_REMATCH[1]}"
    fi
}

# state_write <file> <stage> [issue] — write the stage, prefixed with the issue
# number when one is known. A non-numeric or empty issue writes a bare token.
state_write() {
    local file="$1" stage="$2" issue="${3:-}"

    if [[ "$issue" =~ ^[0-9]+$ ]]; then
        printf '%s:%s\n' "$issue" "$stage" > "$file"
    else
        printf '%s\n' "$stage" > "$file"
    fi
}

# context_exhausted <file> — true when the file contains a token/context
# exhaustion message. That failure is recoverable: the user changes the model
# and resumes the stage, so the drivers call this out instead of a bare error.
context_exhausted() {
    grep -qiE 'context (length|window)|maximum context|out of (tokens|context)|token limit|too many tokens|context_length_exceeded' "$1"
}

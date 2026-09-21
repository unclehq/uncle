#!/usr/bin/env bash
# REQUIREMENTS.md and CHANGE_REQUEST.md are operator inputs: a human may drop
# either at the project root by hand, and that copy is authoritative. But
# uncle also generates them itself (the TUI's chat-derived brief, from-issue
# seeding), and a generated file is not the kind of thing a project's own
# repository should carry at its root -- it belongs beside the rest of
# uncle's own output, under .uncle/docs, exactly where a human-placed copy is
# not, so the two origins stay visually and physically distinct.
#
# The rule both reads and writes follow: a root copy always wins if present
# (someone put it there on purpose); otherwise the generated copy lives at
# .uncle/docs/<name>.
generated_input_path() {
    local name="$1"
    if [[ -e "$name" ]]; then
        printf '%s' "$name"
    else
        printf '.uncle/docs/%s' "$name"
    fi
}

# Where a freshly-generated copy should be written. Always .uncle/docs,
# regardless of whether a root copy exists -- a generator that finds a root
# copy already there should not be writing at all (see the caller-side
# "already exists" checks in from-issue.sh), and this function's job is only
# to name the destination and make sure it exists.
generated_input_write_path() {
    local name="$1"
    mkdir -p .uncle/docs
    printf '.uncle/docs/%s' "$name"
}

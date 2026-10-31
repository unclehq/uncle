#!/usr/bin/env bash
# Repair a rejected canonical delivery by editing it, not by writing it again.
#
# A parent planning stage that delivers a large JSON document and has it
# rejected for one defect used to be asked to write the whole document a second
# time: the delivery file was deleted and the retry prompt said "replace the same
# delivery file with a complete corrected JSON object". On a runner that pays per
# generated token that is the whole plan again for a one-line mistake.
#
# So the rejected file stays, and the retry is told to correct it in place with
# Edit and a unique text anchor. The same validators then run on the result; a
# repaired draft is never trusted. WORKFLOW_ANCHORED_REPAIR=0 restores the old
# delete-and-rewrite retry.
#
# Sourcing this file defines functions and nothing else.

# anchored_repair_keeps FILE: succeed when the rejected FILE should stay for an
# in-place correction. A missing or empty file has nothing to anchor to.
anchored_repair_keeps() {
    [[ "${WORKFLOW_ANCHORED_REPAIR:-1}" != 0 && -s "$1" ]]
}

# anchored_repair_tools TOOLS: TOOLS with Edit added when it is not already listed.
anchored_repair_tools() {
    case ",$1," in
        *,Edit,*) printf '%s' "$1" ;;
        *) printf '%s,Edit' "$1" ;;
    esac
}

# anchored_repair_note ERROR FILE: the retry paragraph appended to the prompt.
anchored_repair_note() {
    printf '\nThe previous canonical delivery was rejected: %s\n' "$1"
    printf 'The rejected file is still at `%s`. Do NOT write it again from scratch and do NOT rewrite it with Write.\n' "$2"
    printf 'Read it, then fix only the reported defect with Edit, using a unique text anchor from the file. Leave every other part unchanged.\n'
}

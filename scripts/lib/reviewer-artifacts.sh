#!/usr/bin/env bash
# Reviewer boundary filters. Definitions only; the caller supplies ROOT and
# STATE_DIR. Python validators retain their existing acceptance policies.

normalize_reviewer_packet() {
    local output_file="$1" runner="$2" normalized
    # Only specialist panel responses use the worker-packet envelope. Stage
    # artifacts are also JSON now, but have their own schemas (for example
    # `adversarial-review`) and must not be forced through that envelope.
    [[ "$output_file" == *-panel/*.json && -s "$output_file" ]] || return 0
    normalized="$(mktemp "$STATE_DIR/.reviewer-packet.XXXXXX")" || return 1
    if ! python3 "$ROOT/scripts/lib/reviewer_output.py" --packet "$runner" < "$output_file" > "$normalized"; then
        rm -f "$normalized"
        return 1
    fi
    mv "$normalized" "$output_file"
}

validate_reviewer_artifact() {
    local output_file="$1" runner="$2" normalized
    # MANUAL_CHECKLIST is JSON-authoritative. Validate its actual semantic
    # minimum at the runner boundary so a conversational "I wrote it" reply
    # never reaches the later execution gate as a successful artifact.
    [[ "${output_file##*/}" == MANUAL_CHECKLIST.md && -s "$output_file" ]] || return 0
    normalized="$(mktemp "$STATE_DIR/.reviewer-artifact.XXXXXX")" || return 1
    if ! python3 "$ROOT/scripts/lib/reviewer_output.py" --artifact "$output_file" "$runner" < "$output_file" > "$normalized"; then
        rm -f "$normalized"
        return 1
    fi
    mv "$normalized" "$output_file"
}

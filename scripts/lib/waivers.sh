#!/usr/bin/env bash
# Waivers, shared by both drivers.
#
# Extracted from stagegate.sh so the change workflow can offer the same
# decision. One definition, so a waiver recorded by either driver means the
# same thing and is written the same way.

# A required row that no environment can satisfy is a dead end unless someone
# can say so on the record. A waiver is that record: an operator's typed reason
# for one id, kept with the run. It never turns a row into a PASS -- the report
# still says the check was not performed -- it only stops the driver treating
# an impossible check as a reason to abandon the run.
waive_file() { printf '%s/waivers/%s' "$STATE_DIR" "$1"; }

waived_ids() {
    local id
    for id in "$@"; do
        [[ -s "$(waive_file "$id")" ]] || return 1
    done
    return 0
}

record_waiver() {
    local report="$1" reason
    shift
    local ids=("$@")

    # Unattended: there is nobody to type a reason, so the reason is the flag
    # itself. This is deliberately the least flattering wording available --
    # the waiver is what the audit reads, and it should not be mistakable for
    # someone having considered the check and decided it was fine.
    if [[ "${UNATTENDED:-0}" == 1 ]]; then
        reason="Waived by an unattended run; no person assessed this check."
        write_waivers "$report" "$reason" "${ids[@]}" || return 1
        record_unattended_gate "waiver" "$report: ${ids[*]}"
        return 0
    fi

    # A popup, when there is a terminal to draw one on. Waiving a required
    # check is the most consequential thing an operator does at this gate, and
    # it should look like a decision rather than another line of log output.
    #
    # Exit 2 means there was no terminal -- a piped or scripted run -- and the
    # text prompt below still has to work: a run that cannot draw a window
    # must still be able to decline.
    local popup="$ROOT/scripts/lib/waiver-popup.py" out status=2
    if [[ -f "$popup" ]] && python3 -c pass > /dev/null 2>&1; then
        out="$(mktemp)" || out=""
        if [[ -n "$out" ]]; then
            status=0
            python3 "$popup" --report "$report" --out "$out" "${ids[@]}" || status=$?
            if [[ "$status" == 0 ]]; then
                reason="$(cat "$out")"
                rm -f "$out"
                if [[ -n "$reason" ]]; then
                    write_waivers "$report" "$reason" "${ids[@]}" || return 1
                    return 0
                fi
                status=1
            fi
            rm -f "$out"
        fi
    fi
    if [[ "$status" == 1 ]]; then
        echo 'No waiver recorded; the run remains pending.'
        return 1
    fi

    echo
    echo "These required checks cannot be performed in this environment:"
    local id
    for id in "${ids[@]}"; do
        printf '  %s\n' "$id"
    done
    echo
    echo "Effort will not clear them -- amending $report's plan or the"
    echo "requirement behind it is the real fix, and is what should normally"
    echo "happen here. A waiver is the other option: it records why a required"
    echo "check cannot be performed and lets the run continue to its audit."
    echo "It does not make the check pass, and the report keeps saying so."
    gate_prompt "Type a reason to waive these checks for this run, or Enter to stop and amend the plan: "
    if ! IFS= read -r reason || [[ -z "$reason" ]]; then
        echo 'No waiver recorded; the run remains pending.'
        return 1
    fi
    write_waivers "$report" "$reason" "${ids[@]}"
}

# One writer for both the popup and the prompt: a waiver recorded one way must
# be indistinguishable from one recorded the other.
write_waivers() {
    local report="$1" reason="$2" id
    shift 2
    mkdir -p "$STATE_DIR/waivers" || return 1
    for id in "$@"; do
        {
            printf 'id: %s\n' "$id"
            printf 'report: %s\n' "$report"
            printf 'recorded: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
            printf 'reason: %s\n' "$reason"
        } > "$(waive_file "$id")" || return 1
    done
    echo "Waiver recorded for $# check(s); it is kept in $STATE_DIR/waivers."
    return 0
}

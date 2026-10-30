#!/usr/bin/env bash
# Implementation decisions. Definitions only; the driver owns state, paths,
# prompt/record/waiver helpers, review writers, and state/envelope hooks.

# The implementation stage can end with acceptance rows the agent could not
# deliver. Exiting there is right when someone is about to go fix it, and wrong
# when nobody is: the run stops, the issue stays open, and the operator is left
# to work out which files to edit and how to resume. Offer the decision instead.
#
# Retry and stop are the honest answers. Waive is the third, for a row no
# further attempt can deliver -- and it never becomes a pass: the rejected rows
# stay in implementation-completion.txt, the waiver records who accepted what,
# and the final audit reads both.
change_implementation_incomplete_choice() {
    local completion="$STATE_DIR/implementation-completion.txt" ids="" answer
    # A malformed acceptance contract is not an implementation failure.  There
    # are no rows a person can waive and another implementation attempt reads
    # exactly the same broken contract, so offering the normal choices creates
    # an infinite, misleading prompt loop.  Send it back through the existing
    # specification-and-plan approval path instead.
    #
    # [a-z]?: one optional trailing letter for a closely related sub-criterion
    # (AC-4b) -- implementation-completion.py accepts the same id shape (issue
    # 97: rejecting it here sent an otherwise-evaluable, ordinary rejected row
    # through this same "cannot be evaluated" branch, a full ANALYZE restart,
    # every time this one id recurred).
    if [[ -s "$completion" ]] && grep -qvE '^AC-[0-9]+[a-z]?: requires IMPLEMENTED,' "$completion"; then
        echo
        echo 'The approved acceptance contract cannot be evaluated; implementation cannot repair it.'
        echo 'Repair rebuilds .uncle/docs/CHANGE_SPEC.md and .uncle/docs/CHANGE_PLAN.md from the request and baseline, then asks for approval again.'
        if [[ "${UNATTENDED:-0}" == 1 ]]; then
            # Auto mode means human gates do not block progress. Repair is the
            # corrective action here, not a concession like a waiver -- it
            # rebuilds the contract and the rebuilt spec/plan still pass
            # through human_gate's own unattended path, so nothing here skips
            # review, it just avoids parking the run on a malformed contract
            # nobody is present to answer for.
            record_unattended_gate implementation-incomplete "repair the unevaluable acceptance contract without human review"
            echo "Unattended: repairing the acceptance contract; no person authorized this."
            rm -f "$APPROVAL_DIR/CHANGE_SPEC.sha256" "$APPROVAL_DIR/CHANGE_PLAN.sha256" \
                "$STATE_DIR/implementation-completion-repair"
            envelope_invalidate CHANGE_SPEC
            set_state ANALYZE
            return 3
        fi
        while true; do
            UNCLE_GATE_CLASS="sensitive:waiver"
            gate_prompt "Repair the acceptance contract or stop? [repair/stop]: "
            UNCLE_GATE_CLASS=""
            if ! { if declare -f gate_read > /dev/null; then gate_read answer; else IFS= read -r answer; fi; }; then
                echo
                echo "No answer; the run remains pending at IMPLEMENT."
                return 1
            fi
            case "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')" in
                repair|r|retry)
                    # `retry` remains an alias for people responding from an
                    # older dialog, but it deliberately repairs the contract
                    # instead of wasting another implementation attempt.
                    rm -f "$APPROVAL_DIR/CHANGE_SPEC.sha256" "$APPROVAL_DIR/CHANGE_PLAN.sha256" \
                        "$STATE_DIR/implementation-completion-repair"
                    envelope_invalidate CHANGE_SPEC
                    set_state ANALYZE
                    echo 'Repairing the acceptance contract before implementation can continue.'
                    return 3
                    ;;
                s|stop|'')
                    echo "Run remains pending at IMPLEMENT."
                    return 1
                    ;;
                *) echo "Answer repair or stop." ;;
            esac
        done
    fi
    echo
    echo "The implementation did not deliver every acceptance row."
    if [[ -s "$completion" ]]; then
        echo "Rejected rows:"
        sed 's/^/  /' "$completion"
        # Format errors cannot be waived as acceptance rows.
        if ! grep -qvE '^AC-[0-9]+[a-z]?: requires IMPLEMENTED,' "$completion"; then
            ids="$(awk -F: '{ printf "%s ", $1 }' "$completion")"
        fi
    fi
    echo
    if [[ "${UNATTENDED:-0}" == 1 && -z "${ids// /}" ]]; then
        # No rejected rows means nothing on the record to waive: the stage
        # delivered no change, or no acceptance report. Waiving an empty set
        # would be dishonest (and crashed record_waiver on bash 3.2).
        record_unattended_gate implementation-incomplete "stopped: no rejected acceptance rows to waive"
        echo "Unattended: no rejected acceptance rows to waive; the run remains pending at IMPLEMENT."
        return 1
    fi
    if [[ "${UNATTENDED:-0}" == 1 ]]; then
        # Auto mode means human gates do not block progress. `retry` reruns
        # the same plan unchanged and this same choice is reached again next
        # time it is still incomplete -- an unbounded loop with nobody there
        # to stop it -- so waive is the one terminating, honest option: the
        # rows stay rejected on the record and the final audit still reads
        # them, matching how a waiver behaves everywhere else in this driver.
        record_unattended_gate implementation-incomplete "waive rejected acceptance rows without human review: $ids"
        echo "Unattended: waiving rejected rows ($ids); no person authorized this. The audit still reads them."
        # shellcheck disable=SC2086
        if record_waiver "$completion" $ids; then
            return 2
        fi
        echo "Could not record the waiver; the run remains pending at IMPLEMENT."
        return 1
    fi
    while true; do
        UNCLE_GATE_CLASS="sensitive:waiver"
        gate_prompt "Retry the implementation, waive the rows above, or stop? [retry/waive/stop]: "
        UNCLE_GATE_CLASS=""
        if ! { if declare -f gate_read > /dev/null; then gate_read answer; else IFS= read -r answer; fi; }; then
            echo
            echo "No answer; the run remains pending at IMPLEMENT."
            return 1
        fi
        case "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')" in
            r|retry)
                # Clearing the digest is what lets the repair path run again for
                # this plan; without it the next pass repeats the same refusal.
                rm -f "$STATE_DIR/implementation-completion-repair"
                if plan_executability_enabled; then plan_tool retry; fi
                echo "Retrying implementation."
                return 0
                ;;
            w|waive)
                if [[ -z "${ids// /}" ]]; then
                    echo "No row ids to waive; edit the plan or retry instead."
                    continue
                fi
                # shellcheck disable=SC2086
                if record_waiver "$completion" $ids; then
                    echo "Waived. The rows stay rejected on the record; the audit still reads them."
                    return 2
                fi
                ;;
            s|stop|'')
                echo "Run remains pending at IMPLEMENT."
                return 1
                ;;
            *) echo "Answer retry, waive, or stop." ;;
        esac
    done
}

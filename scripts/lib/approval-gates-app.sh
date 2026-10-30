#!/usr/bin/env bash
# App approval policy, kept separate from the other driver family.
# Caller supplies path/prompt/record helpers, hash_file, state and optional
# supervision/performance hooks; cancel_speculation is app-owned.

review_and_approve() {
    local gate_start="$SECONDS"
    local view="$1" file
    local name="$2"
    local wording
    wording="$(lower "${3:-approve}")"

    case "$name" in
        UPDATED_PROJECT_PLAN) python3 "$ROOT/scripts/lib/plan_context.py" render-plan "$view" . || return 1 ;;
    esac
    file="$(approval_artifact_path "$view")"
    [[ -s "$file" ]] || { echo "Required approval artifact missing: $file"; exit 1; }

    local before
    local response

    # Unattended: record the approval against the bytes on disk, and record in
    # the run's own ledger that nobody read them. The digest still has to be
    # real -- later stages compare against it, and an approval attesting to
    # nothing would let a document change underneath them unnoticed.
    if [[ "${UNATTENDED:-0}" == 1 ]]; then
        before="$(hash_file "$file")"
        printf '%s\n' "$before" > "$APPROVAL_DIR/${name}.sha256"
        printf '%s\n' "$(if declare -f supervision_approved_by > /dev/null; then supervision_approved_by; elif [[ "${UNATTENDED:-0}" == 1 ]]; then printf unattended; else printf '%s' "${UNCLE_APPROVAL_NAME:-}"; fi)" > "$APPROVAL_DIR/${name}.approved-by"
        # The canonical packet was the item approved; never reverse-parse the
        # rendered view after recording that approval.
        record_unattended_gate "$name" "$wording $view without human review"
        echo "Unattended: recorded $wording of $view with no human review."
        if declare -f perf_record > /dev/null; then perf_record approval "$name" "$((SECONDS-gate_start))" 0; fi
        return 0
    fi

    while true; do
        before="$(hash_file "$file")"

        echo
        echo "=================================================="
        echo "HUMAN REVIEW REQUIRED: $view"
        echo "=================================================="
        echo
        echo "Review in another terminal with:"
        echo
        echo "  less $view"
        echo
        echo "or:"
        echo
        echo "  code $view"
        echo

        UNCLE_GATE_FILE="$view"
        gate_prompt "Ready to $wording $view? [Y/N] "
        UNCLE_GATE_FILE=""
        # IFS= keeps surrounding whitespace, so " y" is not an approval.
        # `|| true` keeps EOF from tripping `set -e` before the decline path
        # runs. The wrapper attributes the line (human, or a supervisor
        # receipt) and closes the gate; the answer is validated as before.
        response=""
        if declare -f gate_read > /dev/null; then gate_read response || true; else IFS= read -r response || true; fi

        case "$response" in
            y|Y) ;;
            *)
                if declare -f perf_record > /dev/null; then perf_record approval "$name" "$((SECONDS-gate_start))" 1; fi
                echo "Gate not accepted. Workflow paused."
                legacy_word_notice "$response"
                exit 0
                ;;
        esac

        # The approval must attest to the bytes that were actually read. If the
        # file moved during review — a human edit, or a speculative stage that
        # ignored its instructions and wrote here — re-open the gate instead of
        # recording an approval for content nobody reviewed.
        if [[ "$(hash_file "$file")" == "$before" ]]; then
            break
        fi

        echo
        echo "$view's canonical JSON changed while you were reviewing it."
        echo "Re-opening the gate so the approval covers what you read."
        cancel_speculation
    done

    # `before` is the digest that was just validated against the file, so it is
    # what gets recorded. Re-hashing here would attest to bytes that could have
    # landed after the check.
    printf '%s\n' "$before" > "$APPROVAL_DIR/${name}.sha256"
    printf '%s\n' "$(if declare -f supervision_approved_by > /dev/null; then supervision_approved_by; elif [[ "${UNATTENDED:-0}" == 1 ]]; then printf unattended; else printf '%s' "${UNCLE_APPROVAL_NAME:-}"; fi)" > "$APPROVAL_DIR/${name}.approved-by"
    # Markdown is a rendered view.  An edit to it cannot silently rewrite the
    # authoritative packet after the human has approved that packet.
    echo "Recorded approval for $file"
    if declare -f perf_record > /dev/null; then perf_record approval "$name" "$((SECONDS-gate_start))" 0; fi
}

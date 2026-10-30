#!/usr/bin/env bash
# Change approval policy, kept separate from the other driver family.
# Caller supplies path/prompt/record helpers, hash_file, state and optional
# supervision/performance hooks; show_spend is change-owned.

human_gate() {
    local gate_start="$SECONDS"
    local action="$1"
    shift

    local -a files=() views=()
    local -a names=()
    local gate_by

    while [[ "$#" -gt 0 ]]; do
        case "$2" in
            CHANGE_PLAN) python3 "$ROOT/scripts/lib/plan_context.py" render-change-plan-unreviewed "$1" . || return 1 ;;
        esac
        local view="$1" canonical
        canonical="$(approval_artifact_path "$view")"
        [[ -s "$canonical" ]] || { echo "Required approval artifact missing: $canonical"; exit 1; }
        views+=("$view")
        files+=("$canonical")
        names+=("$2")
        shift 2
    done

    # Unattended: record each approval against the bytes on disk and log that
    # nobody read them. The digests must still be real -- later stages compare
    # against them to catch a document changing underneath an approval.
    if [[ "${UNATTENDED:-0}" == 1 ]]; then
        local j act
        act="$(printf '%s' "$action" | tr '[:upper:]' '[:lower:]')"
        for j in "${!files[@]}"; do
            printf '%s\n' "$(hash_file "${files[$j]}")" > "$APPROVAL_DIR/${names[$j]}.sha256"
            gate_by="$(if declare -f supervision_approved_by > /dev/null; then supervision_approved_by; elif [[ "${UNATTENDED:-0}" == 1 ]]; then printf unattended; else printf '%s' "${UNCLE_APPROVAL_NAME:-}"; fi)"
            # A human name goes to `.approved-by`; `unattended` and supervisor
            # receipts go to `.delegated-by` with `.approved-by` left empty, so
            # nothing downstream reads a delegated answer as a keystroke.
            # `.gate-action` records what the gate asked for (Issue 59).
            case "$gate_by" in
                unattended|supervisor:*)
                    printf '%s\n' "$gate_by" > "$APPROVAL_DIR/${names[$j]}.delegated-by"
                    printf '\n' > "$APPROVAL_DIR/${names[$j]}.approved-by"
                    ;;
                *)
                    printf '%s\n' "$gate_by" > "$APPROVAL_DIR/${names[$j]}.approved-by"
                    printf '\n' > "$APPROVAL_DIR/${names[$j]}.delegated-by"
                    ;;
            esac
            printf '%s\n' "$action" > "$APPROVAL_DIR/${names[$j]}.gate-action"
            record_unattended_gate "${names[$j]}" "$act ${views[$j]} without human review"
        done
        echo "Unattended: recorded $act of ${files[*]} with no human review."
        if declare -f perf_record > /dev/null; then perf_record approval "${names[*]}" "$((SECONDS-gate_start))" 0; fi
        return 0
    fi

    echo
    echo "=================================================="
    echo "HUMAN REVIEW REQUIRED"
    local f
    for f in "${views[@]}"; do
        echo "  $f"
    done
    echo "=================================================="
    echo
    echo "Review with:"
    echo "  less ${views[*]}"
    echo
    echo "Edit with:"
    echo "  code ${views[*]}"
    echo
    echo "Edits you make now are picked up by the next stage."
    show_spend
    echo

    # Digests are captured before the prompt and recorded afterwards, so each
    # approval attests to the bytes the operator was shown.
    local -a digests=()
    local i
    for i in "${!files[@]}"; do
        digests+=("$(hash_file "${files[$i]}")")
    done

    local verb targets response=""
    verb="$(printf '%s' "$action" | tr '[:upper:]' '[:lower:]')"
    targets="$(printf '%s, ' "${views[@]}")"
    targets="${targets%, }"

    echo
    UNCLE_GATE_FILE="${views[0]}"
    gate_prompt "Ready to $verb $targets? [Y/N] "
    UNCLE_GATE_FILE=""
    # IFS= keeps surrounding whitespace, so " y" is not an approval. `|| true`
    # keeps EOF from tripping `set -e` before the decline path runs. The
    # wrapper attributes the line (human, or a supervisor receipt) and closes
    # the gate; the answer itself is validated exactly as before.
    if declare -f gate_read > /dev/null; then gate_read response || true; else IFS= read -r response || true; fi

    case "$response" in
        y|Y) ;;
        *)
            if declare -f perf_record > /dev/null; then perf_record approval "${names[*]}" "$((SECONDS-gate_start))" 1; fi
            echo "Gate not accepted. Workflow remains paused."
            legacy_word_notice "$response"
            exit 0
            ;;
    esac

    # Every file is re-checked before any approval is written, so a mutated
    # document cannot leave a half-approved gate behind.
    for i in "${!files[@]}"; do
        if [[ "$(hash_file "${files[$i]}")" != "${digests[$i]}" ]]; then
            if declare -f perf_record > /dev/null; then perf_record approval "${names[*]}" "$((SECONDS-gate_start))" 1; fi
            echo "${views[$i]}'s canonical JSON changed after it was shown for approval."
            echo "Gate not accepted. Workflow remains paused."
            exit 0
        fi
    done

    for i in "${!files[@]}"; do
        printf '%s\n' "${digests[$i]}" > "$APPROVAL_DIR/${names[$i]}.sha256"
        gate_by="$(if declare -f supervision_approved_by > /dev/null; then supervision_approved_by; elif [[ "${UNATTENDED:-0}" == 1 ]]; then printf unattended; else printf '%s' "${UNCLE_APPROVAL_NAME:-}"; fi)"
        # A human name goes to `.approved-by`; `unattended` and supervisor
        # receipts go to `.delegated-by` with `.approved-by` left empty, so
        # nothing downstream reads a delegated answer as a keystroke.
        # `.gate-action` records what the gate asked for (Issue 59).
        case "$gate_by" in
            unattended|supervisor:*)
                printf '%s\n' "$gate_by" > "$APPROVAL_DIR/${names[$i]}.delegated-by"
                printf '\n' > "$APPROVAL_DIR/${names[$i]}.approved-by"
                ;;
            *)
                printf '%s\n' "$gate_by" > "$APPROVAL_DIR/${names[$i]}.approved-by"
                printf '\n' > "$APPROVAL_DIR/${names[$i]}.delegated-by"
                ;;
        esac
        printf '%s\n' "$action" > "$APPROVAL_DIR/${names[$i]}.gate-action"
        echo "Recorded approval for ${views[$i]}"
    done
    if declare -f perf_record > /dev/null; then perf_record approval "${names[*]}" "$((SECONDS-gate_start))" 0; fi
}

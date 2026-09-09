#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
    cat <<'USAGE'
Usage:

  ./scripts/workflow.sh approve-plan
  ./scripts/workflow.sh approve-review
  ./scripts/workflow.sh approve-updated-plan
  ./scripts/workflow.sh status
USAGE
}

case "$#:${1:-}" in
    1:-h|1:--help) usage; exit 0 ;;
esac

mkdir -p .uncle/workflow/approvals

. "$ROOT/scripts/lib/sha256.sh"

# One bold prompt line. `read -p` suppresses its prompt when stdin is not a
# terminal, so the text is printed separately. Escapes are emitted only for a
# real terminal: piped captures and TERM=dumb stay free of control bytes.
gate_prompt() {
    if [[ -t 1 && "${TERM:-}" != "dumb" ]]; then
        printf '%s%s%s' $'\033[1m' "$1" $'\033[0m'
    else
        printf '%s' "$1"
    fi
}

# The gate used to require the words APPROVE/ACKNOWLEDGE. Automation that still
# pipes them now declines; say so, so the break is visible in the output rather
# than silent.
legacy_word_notice() {
    case "$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')" in
        APPROVE|ACKNOWLEDGE)
            echo "This gate now requires 'y' to approve."
            ;;
    esac
}

approve_file() {
    local file="$1"
    local approval_name="$2"

    if [[ ! -s "$file" ]]; then
        echo "Cannot approve missing or empty file: $file"
        exit 1
    fi

    # The digest is captured before the prompt and recorded afterwards, so the
    # approval attests to the bytes shown here rather than to whatever is on
    # disk once the operator has answered.
    local captured
    captured="$(hash_file "$file")"

    local confirmation=""

    echo
    echo "You are approving: $file"
    echo "SHA-256: $captured"
    echo
    gate_prompt "Ready to approve $file? [Y/N] "
    # IFS= keeps surrounding whitespace, so " y" is not an approval. `|| true`
    # keeps EOF from tripping `set -e` before the decline path runs.
    IFS= read -r confirmation || true

    case "$confirmation" in
        y|Y) ;;
        *)
            echo "Approval cancelled."
            legacy_word_notice "$confirmation"
            exit 1
            ;;
    esac

    if [[ "$(hash_file "$file")" != "$captured" ]]; then
        echo "$file changed after the digest above was shown."
        echo "Approval cancelled."
        exit 1
    fi

    printf '%s\n' "$captured" > ".uncle/workflow/approvals/${approval_name}.sha256"
    printf '%s\n' "$([[ "${UNATTENDED:-0}" == 1 ]] && printf unattended || printf '%s' "${UNCLE_APPROVAL_NAME:-}")" > ".uncle/workflow/approvals/${approval_name}.approved-by"
    echo "Approved $file"
}

case "$#:${1:-}" in
    1:approve-plan)
        approve_file PROJECT_PLAN.md PROJECT_PLAN
        echo "Next: ask the agent to run Stage 2."
        ;;

    1:approve-review)
        approve_file ADVERSARIAL_REVIEW.md ADVERSARIAL_REVIEW
        echo "Next: ask the agent to create UPDATED_PROJECT_PLAN.md."
        ;;

    1:approve-updated-plan)
        approve_file UPDATED_PROJECT_PLAN.md UPDATED_PROJECT_PLAN
        echo "Updated plan approved."
        echo "The agent may now build and continue through verification."
        ;;

    1:status)
        echo "Approval status:"
        for item in PROJECT_PLAN ADVERSARIAL_REVIEW UPDATED_PROJECT_PLAN; do
            approval=".uncle/workflow/approvals/${item}.sha256"
            file="${item}.md"

            if [[ -s "$approval" && -s "$file" ]]; then
                expected="$(cat "$approval")"
                actual="$(hash_file "$file")"

                if [[ "$expected" == "$actual" ]]; then
                    echo "  $file: APPROVED"
                else
                    echo "  $file: CHANGED AFTER APPROVAL"
                fi
            else
                echo "  $file: NOT APPROVED"
            fi
        done
        ;;

    *)
        usage
        exit 1
        ;;
esac

# Pure classifier for the FINAL_AUDIT.md verdict.
#
# Sourcing this file defines functions and nothing else, so both
# change-workflow.sh and scripts/tests/audit-verdict-test.sh can use it. Not
# executable on its own.
#
# classify_audit_verdict <file> prints exactly one of:
#   READY | READY_WITH_NON_BLOCKING_ISSUES | NOT_READY | UNKNOWN
#
# It fails closed. Only the last non-blank line of the file is considered, and
# that line must match one of the three verdict phrases from
# prompts/change/final-audit.md exactly, case-sensitively, once surrounding
# whitespace and markdown emphasis or heading markers are stripped. Trailing
# prose, a phrase embedded in a sentence, or two phrases on one line all
# classify as UNKNOWN.

classify_audit_verdict() {
    local file="${1:-}"

    if [[ -z "$file" || ! -s "$file" ]]; then
        printf '%s\n' UNKNOWN
        return 0
    fi

    local line
    line="$(tr -d '\r' < "$file" | awk 'NF { last = $0 } END { print last }')"
    line="$(printf '%s' "$line" \
        | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
              -e 's/^[#*_[:space:]]*//' -e 's/[*_[:space:]]*$//' \
              -e 's/^Conclusion:[[:space:]]*//' \
              -e 's/^[*_[:space:]]*//' -e 's/[*_[:space:]]*$//')"

    case "$line" in
        "READY")                          printf '%s\n' READY ;;
        "READY WITH NON-BLOCKING ISSUES") printf '%s\n' READY_WITH_NON_BLOCKING_ISSUES ;;
        "NOT READY")                      printf '%s\n' NOT_READY ;;
        *)                                printf '%s\n' UNKNOWN ;;
    esac
}

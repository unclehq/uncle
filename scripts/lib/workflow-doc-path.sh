#!/usr/bin/env bash
# Where a workflow-generated document actually lives: .uncle/docs/<name>.
#
# These 18 names are never operator input -- REQUIREMENTS.md and
# CHANGE_REQUEST.md are the two exceptions (generated-input.sh) that a human
# may place at the project root by hand, so they alone are resolved by
# checking root first. Everything below is pure workflow output with no such
# ambiguity, so it always lives under .uncle/docs, unconditionally.
#
# bash 3.2 compatible.

# workflow_doc_path <name> — the on-disk path for a workflow document,
# whether or not it exists yet. A path outside this list (a project's own
# file, an operator input) is returned unchanged.
workflow_doc_path() {
    case "${1##*/}" in
        REQUIREMENTS_INTERPRETATION.md|PROJECT_PLAN.md|UPDATED_PROJECT_PLAN.md|\
        BASELINE_REPORT.md|CHANGE_SPEC.md|CHANGE_PLAN.md|\
        UPDATED_CHANGE_PLAN.md|ADVERSARIAL_REVIEW.md|IMPLEMENTATION_NOTES.md|\
        CHANGE_TEST_REPORT.md|AUTOMATED_TEST_REPORT.md|MANUAL_CHECKLIST.md|\
        VERIFICATION_REPORT.md|DEFECTS.md|FINAL_AUDIT.md|PREFLIGHT_REPORT.md|TEST_REVIEW.md)
            printf '.uncle/docs/%s' "${1##*/}"
            return 0
            ;;
    esac
    printf '%s' "$1"
}

# ensure_workflow_docs_dir — created once, early, before any stage writes.
ensure_workflow_docs_dir() {
    mkdir -p .uncle/docs
}

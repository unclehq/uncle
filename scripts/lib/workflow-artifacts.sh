#!/usr/bin/env bash
# The one list of files the workflow itself writes.
#
# Two different checks need it and had drifted into two different lists: the
# frozen-scope check in plan-scope.sh, which must not call the workflow's own
# paper trail scope creep, and the review diff in implementation-review.sh,
# which must not bury the code change in that paper trail. When only tracked
# files were examined the divergence was invisible, because none of these
# artifacts is committed in a target repository.
#
# bash 3.2 compatible.

# workflow_artifact <path> — true for a file some stage of the workflow writes.
#
# Both pipelines' artifacts are listed together. A change repository never
# contains PROJECT_PLAN.md and a new application never contains
# BASELINE_REPORT.md, so there is nothing to gain from splitting the list and
# something to lose: whichever half is wrong fails closed on the other pipeline.
workflow_artifact() {
    case "$1" in
        .workflow/*|\
        REQUIREMENTS_INTERPRETATION.md|PROJECT_PLAN.md|UPDATED_PROJECT_PLAN.md|\
        BASELINE_REPORT.md|CHANGE_REQUEST.md|CHANGE_SPEC.md|CHANGE_PLAN.md|\
        UPDATED_CHANGE_PLAN.md|ADVERSARIAL_REVIEW.md|IMPLEMENTATION_NOTES.md|\
        CHANGE_TEST_REPORT.md|AUTOMATED_TEST_REPORT.md|MANUAL_CHECKLIST.md|\
        VERIFICATION_REPORT.md|DEFECTS.md|FINAL_AUDIT.md)
            return 0
            ;;
    esac
    return 1
}

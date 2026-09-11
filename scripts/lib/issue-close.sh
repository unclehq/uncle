#!/usr/bin/env bash
# Shared origin and audit checks for PR handoff. The historical filename and
# function names remain for compatibility; this library never closes issues.
# Origin grammar: owner/repo TAB issue [TAB gh|curl]. Fetch provenance is
# recorded for diagnostics; publication uses current gh authentication.
#
# bash 3.2 compatible.

# state_issue lives next door and is needed by state_origin_agree.
# hash_file, which this lib uses and its tests source it without.
. "$(dirname "${BASH_SOURCE[0]}")/sha256.sh"

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/state.sh"

# Legacy timeout setting retained for older callers.
ISSUE_CLOSE_TIMEOUT_SECS="${STAGEGATE_CLOSE_TIMEOUT:-30}"

# origin_field <file> <n> — field n of .uncle/workflow/origin, empty when absent.
origin_field() {
    local file="$1" n="$2"

    if [[ ! -s "$file" ]]; then
        return 0
    fi
    head -n 1 "$file" | awk -F'\t' -v n="$n" '{printf "%s", $n}'
}

# origin_fetch_method <file> — `gh` when the binding was recorded as fetched
# with an authenticated gh, `curl` for everything else including a legacy
# two-field file.
origin_fetch_method() {
    if [[ "$(origin_field "$1" 3)" == "gh" ]]; then
        printf 'gh'
    else
        printf 'curl'
    fi
}

# issue_close_timeout_cmd — `timeout`, `gtimeout`, or empty when neither exists.
issue_close_timeout_cmd() {
    if command -v timeout >/dev/null 2>&1; then
        printf 'timeout'
    elif command -v gtimeout >/dev/null 2>&1; then
        printf 'gtimeout'
    fi
}

# state_origin_agree <state_file> <origin_file>
#
# 0 when the state file's issue prefix and .uncle/workflow/origin's issue agree, when
# either is absent, or when the state names a *finished* run of another issue.
# Non-zero, with the reason printed, when an unfinished run disagrees: normal
# operation cannot produce that combination, so it is treated as corruption
# rather than silently resolved in either file's favour.
state_origin_agree() {
    local state_file="$1" origin_file="$2" prefix origin_issue stage

    prefix="$(state_issue "$state_file")"
    if [[ -z "$prefix" ]]; then
        return 0
    fi

    origin_issue="$(origin_field "$origin_file" 2)"
    if [[ -z "$origin_issue" || "$prefix" == "$origin_issue" ]]; then
        return 0
    fi

    # A COMPLETE state is the residue of a run that finished, not a hand edit.
    # Seeding the next issue writes .uncle/workflow/origin and leaves that residue
    # behind, so refusing here would make every checkout single-use: the second
    # issue could never start without deleting files by hand. The caller rebinds
    # the state to this issue instead.
    stage="$(state_read "$state_file")"
    if [[ "$stage" == "COMPLETE" ]]; then
        return 0
    fi

    echo "Refusing to act on corrupt workflow state: $state_file is bound to issue"
    echo "$prefix but $origin_file names issue $origin_issue."
    echo "One of the two was hand-edited. Reconcile them, or clear both with:"
    echo "  rm -f $state_file $origin_file"
    return 1
}

# issue_close_if_ready <run_id> <owner/repo> <issue> <verdict_file> <origin_file>
#                      <audit_file> <marker_file> <allow_close> <origin_bound>
#                      <run_owns_verdict> <fetch_method>
#
#   allow_close       1 unless the caller's kill switch is off
#   origin_bound      1 when the caller can prove it owns .uncle/workflow/origin for
#                     this invocation rather than having found it on disk
#   run_owns_verdict  1 when the caller can prove this run produced the verdict
#                     record (in-process, or a retry on the same concrete run id)
#   fetch_method      gh | curl, from the origin file's third field
#
# Eligibility returns 0 allowed, 1 skipped with a printed reason.
# Direct closing is disabled; eligibility is used only by PR handoff.
issue_close_eligible() {
    local run_id="$1" repo="$2" issue="$3"
    local verdict_file="$4" origin_file="$5" audit_file="$6" marker_file="$7"
    local allow_close="$8" origin_bound="$9" run_owns_verdict="${10}"
    local fetch_method="${11}"
    local record file_run_id verdict recorded_hash actual_hash comment
    local tmo rc

    if [[ "$allow_close" != "1" ]]; then
        echo "Issue closing is disabled (WORKFLOW_CLOSE_ISSUE=$allow_close);"
        echo "leaving $repo#$issue open."
        return 1
    fi

    if [[ ! -s "$verdict_file" ]]; then
        echo "No audit verdict was recorded ($verdict_file is absent);"
        echo "leaving $repo#$issue open."
        return 1
    fi

    record="$(head -n 1 "$verdict_file")"
    file_run_id="$(printf '%s' "$record" | awk -F'\t' '{print $1}')"
    verdict="$(printf '%s' "$record" | awk -F'\t' '{print $2}')"
    recorded_hash="$(printf '%s' "$record" | awk -F'\t' '{print $3}')"

    if [[ -z "$file_run_id" || -z "$verdict" || -z "$recorded_hash" ]]; then
        echo "Audit verdict record is malformed; leaving $repo#$issue open."
        return 1
    fi

    if [[ "$file_run_id" != "$run_id" ]]; then
        echo "Audit verdict belongs to run '$file_run_id', not this run ('$run_id');"
        echo "leaving $repo#$issue open."
        return 1
    fi

    if [[ "$(origin_field "$origin_file" 1)" != "$repo" \
        || "$(origin_field "$origin_file" 2)" != "$issue" ]]; then
        echo "Origin binding no longer names $repo#$issue;"
        echo "leaving the issue open."
        return 1
    fi

    if [[ ! -s "$audit_file" ]]; then
        echo "FINAL_AUDIT.md is missing; leaving $repo#$issue open."
        return 1
    fi

    actual_hash="$(hash_file "$audit_file")"
    if [[ "$actual_hash" != "$recorded_hash" ]]; then
        echo "FINAL_AUDIT.md changed after it was classified;"
        echo "leaving $repo#$issue open."
        return 1
    fi

    case "$verdict" in
        READY|READY_WITH_NON_BLOCKING_ISSUES) ;;
        *)
            echo "Final audit verdict: $verdict — leaving $repo#$issue open."
            return 1
            ;;
    esac

    # A recorded run id of '-' is the unset-STAGEGATE_RUN_ID sentinel and never
    # counts as proof; the caller resolves that before setting this flag.
    if [[ "$run_owns_verdict" != "1" ]]; then
        echo "This process did not produce the recorded audit verdict, so it cannot"
        echo "claim the completion. Leaving $repo#$issue open."
        return 1
    fi

    # A leftover .uncle/workflow/origin found on disk by an otherwise fresh run proves
    # nothing about what this invocation is working on.
    if [[ "$origin_bound" != "1" ]]; then
        echo "This run cannot prove it owns $origin_file: the state file carried no"
        echo "issue binding when the run started and STAGEGATE_ORIGIN_REPO/ISSUE were"
        echo "not set for this invocation. Leaving $repo#$issue open."
        return 1
    fi

    if ! command -v gh >/dev/null 2>&1; then
        echo "gh is no longer on PATH; PR handoff remains pending."
        echo "Authenticate gh and resume the PR handoff."
        return 1
    fi

    if ! gh auth status >/dev/null 2>&1; then
        echo "gh is not authenticated; PR handoff remains pending."
        echo "Authenticate gh and resume the PR handoff."
        return 1
    fi

    return 0
}

# Compatibility entry point for older callers. Direct issue closing was removed.
issue_close_if_ready() {
    echo "Direct issue closing is disabled; issues remain open until PR merge."
    return 0
}

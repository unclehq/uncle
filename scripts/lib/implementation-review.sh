#!/usr/bin/env bash
# Compose the document the human reads at the post-implementation gate.
#
# Every gate before this one is a gate on prose. The operator approves an
# interpretation, a plan, a review of the plan, and a revised plan — and then
# the pipeline writes the code, checks its own work, audits itself, and
# finishes, without the person who approved the plan ever seeing a line of
# what was built. This document is what makes that reviewable.
#
# It is generated, never agent-written: the diff is materialized from the
# working tree, the green-check table from the driver's own command runs, and
# the agent's account of its work is embedded rather than summarized. Because
# it is generated, it can be rebuilt byte-for-byte, which is what turns the
# approval digest into a tamper check on the tree rather than on a file.
#
# bash 3.2 compatible: no associative arrays, no ${var^^}.

# The list of files the workflow writes, shared with plan-scope.sh so the two
# checks cannot drift apart on it. They are gated on their own terms, and
# including them here would bury the code change in the paper trail describing
# it.
# hash_file, which this lib uses and its tests source it without.
. "$(dirname "${BASH_SOURCE[0]}")/sha256.sh"

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/workflow-artifacts.sh"

# A file listing the untracked paths that already existed when implementation
# started. Anything in it predates the change and is not part of it: a scratch
# file in the operator's checkout is not something the agent did.
#
# Set by the driver. Empty means every untracked file is new, which is the
# right reading for a new application built in an empty directory.
: "${WORKFLOW_UNTRACKED_BASELINE:=}"

# snapshot_untracked <out> — record the untracked paths present right now.
# Called once, before the implementation stage runs.
snapshot_untracked() {
    git ls-files --others --exclude-standard > "$1" 2>/dev/null || : > "$1"
}

# in_git_repo — whether git can answer questions about this directory at all.
#
# A new application is often built somewhere that was never `git init`ed. The
# gate must say that it cannot see the change, rather than showing an empty
# file list, which reads as "nothing was built".
in_git_repo() {
    git rev-parse --git-dir > /dev/null 2>&1
}

# change_diff_files — every path the working tree changed against HEAD,
# workflow artifacts removed.
#
# Untracked files are included. `git diff` alone would omit them, and a file
# the agent created is the one file in the change with no prior reviewer at
# all — precisely what this gate exists to show.
change_diff_files() {
    local f

    # Every git call is allowed to fail: a repository with no commits has no
    # HEAD, and a directory that was never initialised has no git at all.
    # Callers run under `set -o pipefail`, so the group must not carry a
    # non-zero status out of the pipeline.
    {
        git diff --name-only HEAD 2>/dev/null \
            || git diff --name-only 2>/dev/null \
            || true
        git ls-files --others --exclude-standard 2>/dev/null || true
    } | sort -u | while IFS= read -r f; do
        [[ -n "$f" ]] || continue
        if workflow_artifact "$f"; then
            continue
        fi
        if [[ -n "$WORKFLOW_UNTRACKED_BASELINE" \
            && -s "$WORKFLOW_UNTRACKED_BASELINE" ]] \
            && grep -qxF -- "$f" "$WORKFLOW_UNTRACKED_BASELINE"; then
            continue
        fi
        printf '%s\n' "$f"
    done
}

# write_change_diff <out> — the reviewable diff, tracked and untracked.
implementation_has_changes() {
    # No Git means there is no reliable diff to judge here.
    in_git_repo || return 0
    [[ -n "$(change_diff_files)" ]]
}

#
# An untracked file is rendered with `git diff --no-index`, which produces a
# real diff without `git add -N` writing to the index: the gate must not change
# the state it is reporting on.
write_change_diff() {
    local out="$1" f

    : > "$out"

    while IFS= read -r f; do
        [[ -n "$f" ]] || continue
        if git ls-files --error-unmatch -- "$f" > /dev/null 2>&1; then
            git diff HEAD -- "$f" >> "$out" 2>/dev/null || true
        else
            git diff --no-index -- /dev/null "$f" >> "$out" 2>/dev/null || true
        fi
    done < <(change_diff_files)
}

# embed_document <path> — one embedded section, or a line saying it is absent.
#
# A missing report is reported, not skipped. The gate's whole purpose is that
# the operator sees what is and is not there.
embed_document() {
    local path="$1"

    echo
    echo "---"
    echo
    if [[ ! -s "$path" ]]; then
        echo "## $path"
        echo
        echo "MISSING or empty. The implementation stage was expected to write it."
        return 0
    fi

    echo "## $path"
    echo
    echo "\`sha256:$(hash_file "$path")\`"
    echo
    cat "$path"
}

# write_implementation_review <out> <diff> <green_md> [document...]
#
# Section order is deliberate: what changed, whether it still passes, then what
# the agent says about both. The claims come last so they are read against the
# evidence rather than in place of it.
write_implementation_review() {
    local out="$1" diff="$2" green="$3"
    shift 3

    {
        echo "# Implementation review"
        echo
        echo "Generated by the driver from the working tree. Do not edit it:"
        echo "it is rebuilt every time this gate opens, and your approval"
        echo "records the digest of the tree, not of this file."
        echo
        echo "## Files changed"
        echo

        local files count
        files="$(change_diff_files)"
        count="$(printf '%s\n' "$files" | grep -c . || true)"

        if ! in_git_repo; then
            echo "UNKNOWN. This directory is not a git repository, so the"
            echo "driver cannot tell what the implementation stage changed."
            echo "Review the working tree directly before approving."
        elif [[ "${count:-0}" -eq 0 ]]; then
            echo "None. The implementation stage changed no source file."
            echo "That is either a no-op change or a stage that did not run."
        else
            printf '%s\n' "$files" | sed 's/^/- /'
            echo

            # --stat only knows about tracked paths, so an untracked file
            # appears in the list above and not in the summary. It is still in
            # the diff below, which is what the approval covers.
            local -a tracked=()
            local f
            while IFS= read -r f; do
                [[ -n "$f" ]] || continue
                if git ls-files --error-unmatch -- "$f" > /dev/null 2>&1; then
                    tracked+=("$f")
                fi
            done <<< "$files"

            if [[ "${#tracked[@]}" -gt 0 ]]; then
                git diff --stat HEAD -- "${tracked[@]}" 2>/dev/null \
                    | sed 's/^/    /' || true
            fi
        fi

        echo
        if [[ -s "$green" ]]; then
            cat "$green"
        else
            echo "## Green check"
            echo
            echo "NOT RUN."
        fi

        local doc
        for doc in "$@"; do
            embed_document "$doc"
        done

        echo
        echo "---"
        echo
        echo "## Diff"
        echo
        if [[ -s "$diff" ]]; then
            echo '```diff'
            cat "$diff"
            echo '```'
        else
            echo "Empty."
        fi
    } > "$out"
}

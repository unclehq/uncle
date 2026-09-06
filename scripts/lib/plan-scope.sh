#!/usr/bin/env bash
# Read the two machine-usable structures out of CHANGE_PLAN.md.
#
# The plan already states its own change surface twice: the change-impact table
# names every component it intends to touch, and the implementation sequence
# orders the work. Both were prose to the agent and invisible to the driver.
# These functions make them addressable, so the frozen scope can be handed to
# the implementation stage and checked against the diff afterwards.
#
# bash 3.2 compatible: no associative arrays, no ${var^^}.

# The list of files the workflow writes, shared with implementation-review.sh.
# Until untracked files were examined, this check and that one carried two
# different copies of it, and the difference could not show up: none of these
# artifacts is committed in a target repository, so `git diff` never named one.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/workflow-artifacts.sh"

# plan_scope_files <plan> — repo-relative paths from the change-impact table,
# one per line, unique, sorted.
#
# A first cell looks like one of:
#   | `app/records/api.py` | ...
#   | `app/records/service.py` — `enroll_voice` | ...
#   | `app/static/admin.js`, `admin.html` | ...
# Only backticked tokens that look like paths are taken, so a function name in
# the same cell is ignored rather than treated as a file.
plan_scope_files() {
    local plan="$1"

    [[ -s "$plan" ]] || return 0

    awk '
        /^## Change-impact table/ { intable = 1; next }
        intable && /^## / { intable = 0 }
        !intable { next }
        /^\|/ {
            # The whole row: the Component cell names what changes, and the
            # Test coverage cell names the tests that must change with it.
            # Both are the plan committing to a file.
            if ($0 ~ /^\|[- |]*\|$/) next
            line = $0
            # Emit each backticked token that contains a slash or a dot, which
            # is what separates a path from a symbol name.
            while (match(line, /`[^`]+`/)) {
                tok = substr(line, RSTART + 1, RLENGTH - 2)
                line = substr(line, RSTART + RLENGTH)
                # Repo-relative paths only. A leading slash is a route
                # ("/login", "/api/admin/users"), not a file.
                if (tok ~ /^\//) continue
                if (tok ~ /\//  || tok ~ /\.[A-Za-z0-9]+$/) print tok
            }
        }
    ' "$plan" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | grep -v '^$' | sort -u
}

# plan_steps <plan> — the implementation sequence, one step per line, in order,
# with its leading number removed.
plan_steps() {
    local plan="$1"

    [[ -s "$plan" ]] || return 0

    awk '
        /^## [0-9]+\. Implementation sequence/ { inseq = 1; next }
        inseq && /^## / { inseq = 0 }
        !inseq { next }
        /^[0-9]+\./ {
            sub(/^[0-9]+\.[[:space:]]*/, "")
            print
        }
    ' "$plan"
}

# plan_out_of_scope <plan> <file>... — the given files that the plan did not
# name. Artifacts the workflow itself writes are never out of scope.
plan_out_of_scope() {
    local plan="$1"
    shift

    local scope
    scope="$(plan_scope_files "$plan")"

    # No table means the scope is unknown, not empty. Treating every changed
    # file as a deviation would fail the stage on plan formatting rather than
    # on scope creep, so report nothing and let the caller warn.
    [[ -n "$scope" ]] || return 0

    local f
    for f in "$@"; do
        if workflow_artifact "$f"; then
            continue
        fi
        # A plan cell may name a sibling by basename alone
        # ("`app/static/admin.js`, `admin.html`"), so a scope entry with no
        # directory matches on basename. Tolerant in the safe direction: it
        # avoids calling an in-scope file a deviation.
        if printf '%s\n' "$scope" | grep -qxF "$f"; then
            continue
        fi
        if printf '%s\n' "$scope" | grep -v '/' | grep -qxF "${f##*/}"; then
            continue
        fi
        printf '%s\n' "$f"
    done
}

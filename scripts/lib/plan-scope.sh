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
    ' "$plan" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//; /^$/d' | sort -u
}

# The heading is numbered in a change plan ("## 20. Implementation sequence")
# and bare in a greenfield plan ("## Implementation order"): the prompts list
# sections by number, but the plan writes the heading it is given. Requiring the
# number meant this matched no greenfield plan at all, so stepwise implementation
# silently did nothing there.
#
# plan_steps <plan> — the implementation sequence, one step per line, in order,
# with its leading number removed.
plan_steps() {
    local plan="$1"

    [[ -s "$plan" ]] || return 0

    awk '
        # Greenfield plans head this "Implementation order"; change plans say
        # "Implementation sequence". Matching only the latter meant stepwise
        # implementation could never engage on a greenfield plan at all.
        /^## ([0-9]+\. )?Implementation (sequence|order)/ { inseq = 1; next }
        inseq && /^## / { inseq = 0 }
        !inseq { next }
        /^[0-9]+\./ {
            sub(/^[0-9]+\.[[:space:]]*/, "")
            print
        }
    ' "$plan"
}

# plan_step_owns <plan> — "<step number>TAB<path>" for every path a step claims.
#
# The plan declares which files each implementation step owns, in the same
# backticked form the change-impact table already uses:
#
#   1. Arithmetic core — Owns: `calc.js`, `tests/calc.test.js`
#   4. Reconcile — Owns: `*` — Depends on: 1, 2, 3
#
# Silence is not a partition: a step that declares nothing emits nothing, and
# every caller treats an undeclared step as owning the whole tree.
#
# The number emitted here is this step's *position* in the list (1, 2, 3, ...
# in the order the steps appear) -- never the literal digits the plan wrote
# before its period. Every caller (plan_steps for task text, step_groups.py
# for grouping) already identifies a step by that position; a plan is free to
# start at 0 for a prerequisite step ("0. Environment check"), and one did on
# a real run. Emitting the literal "0" there shifted every step's ownership
# and dependency lookups by one against the position every other caller uses,
# so a worker doing its actually-assigned, correctly-described task got
# checked against a different step's declared files and was rejected for
# writing exactly what it was told to.
plan_step_owns() {
    local plan="$1"

    [[ -s "$plan" ]] || return 0

    # A long `Owns:` list -- exactly what a step touching two dozen files
    # produces -- wraps onto its own following lines, one or more backticked
    # paths per line, until a blank line or prose ends it. The single-line
    # extraction below still runs first for whatever tokens share the
    # numbered heading's own line; `cur`/`owns` continue it across the lines
    # that follow, so a plan that correctly declared every file it touches
    # was not read as having declared none of them past the first line.
    awk '
        function extract(line,    tok) {
            while (match(line, /`[^`]+`/)) {
                tok = substr(line, RSTART + 1, RLENGTH - 2)
                line = substr(line, RSTART + RLENGTH)
                gsub(/^[ \t]+|[ \t]+$/, "", tok)
                if (tok == "") continue
                if (tok ~ /^\//) continue
                sub(/^\.\//, "", tok)
                print position[cur] "\t" tok
            }
        }
        /^## ([0-9]+\. )?Implementation (sequence|order)/ { inseq = 1; next }
        inseq && /^## / { inseq = 0 }
        !inseq { next }
        /^[0-9]+\./ {
            n = $0; sub(/\..*$/, "", n)
            position[n] = ++count
            cur = n
            owns = 0
            line = $0
            if (match(line, /[Oo]wns:/)) {
                line = substr(line, RSTART + RLENGTH)
                # Stop at a following field so "Depends on" paths are not owned.
                if (match(line, /[Dd]epends[ \t]+on:/)) line = substr(line, 1, RSTART - 1)
                owns = 1
                extract(line)
            }
            next
        }
        owns {
            line = $0
            trimmed = line
            gsub(/^[ \t]+|[ \t]+$/, "", trimmed)
            # A real continuation line is nothing but backticked tokens
            # joined by commas -- never prose that merely mentions a
            # backticked name, such as a bullet auditing call sites
            # ("- Audit every occurrence of ... `require_file`, ...", a real
            # plan). Stripping every backtick span and remaining comma/space
            # must leave nothing behind, or this is not one of them.
            check = trimmed
            gsub(/`[^`]+`/, "", check)
            gsub(/[ \t,]/, "", check)
            if (check != "") { owns = 0; next }
            if (match(line, /[Dd]epends[ \t]+on:/)) { line = substr(line, 1, RSTART - 1); owns = 0 }
            extract(line)
        }
    ' "$plan"
}

# plan_step_depends <plan> — "<step>TAB<step it waits for>" per declared edge.
#
# Both columns are positions, for the same reason plan_step_owns emits a
# position: "Depends on: 0" means the step written as "0." in the plan, which
# a dependency can only ever reference after it has already appeared, so its
# position is already known by the time a later step's "Depends on" is read.
plan_step_depends() {
    local plan="$1"

    [[ -s "$plan" ]] || return 0

    awk '
        /^## ([0-9]+\. )?Implementation (sequence|order)/ { inseq = 1; next }
        inseq && /^## / { inseq = 0 }
        !inseq { next }
        /^[0-9]+\./ {
            n = $0; sub(/\..*$/, "", n)
            position[n] = ++count
            line = $0
            if (match(line, /[Dd]epends[ \t]+on:/)) {
                line = substr(line, RSTART + RLENGTH)
                while (match(line, /[0-9]+/)) {
                    ref = substr(line, RSTART, RLENGTH)
                    print position[n] "\t" ((ref in position) ? position[ref] : ref)
                    line = substr(line, RSTART + RLENGTH)
                }
            }
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

# The plan sections that decide whether written code is still valid. A review
# that rewrites prose elsewhere -- risks, priorities, traceability, the
# disposition table it must add -- has not invalidated anything already built.
#
# Verification commands are deliberately absent: when only they move, the code
# is still right and the checks simply run differently, so that is a reason to
# re-run the green check, not to discard an implementation.
PLAN_MATERIAL_SECTIONS='Architecture|Components and responsibilities|Observable behaviors|Domain invariants|Domain model|Authoritative state|Data flow|Failure handling|Concurrency model|Implementation (order|sequence)'

# plan_material_sections <plan> — the text of those sections, normalised.
plan_material_sections() {
    local plan="$1"

    [[ -s "$plan" ]] || return 0

    awk -v want="$PLAN_MATERIAL_SECTIONS" '
        /^#{2,3} / {
            title = $0
            sub(/^#{2,3} +/, "", title)
            sub(/^[0-9]+\. +/, "", title)
            inwant = (title ~ "^(" want ")$")
            if (inwant) print "### " title
            next
        }
        inwant {
            line = $0
            gsub(/[ \t]+$/, "", line)
            if (line != "") print line
        }
    ' "$plan"
}

# plan_material_hash <plan> — one digest over those sections.
plan_material_hash() {
    plan_material_sections "$1" | python3 -c \
        'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
}

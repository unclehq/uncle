#!/usr/bin/env bash
# Read the two machine-usable structures out of .uncle/docs/CHANGE_PLAN.md.
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

# Plan packets retain their narrative for human rendering, but that narrative
# is carried by canonical JSON.  Scope/step extraction must consume that
# packet, never the rendered approval view.  Markdown remains only as a
# compatibility fallback for runs paused before canonical plan publication.
plan_text() {
    local plan="$1" records_status=0
    plan_record_lines text "$plan" || records_status=$?
    [[ "$records_status" == 3 ]] || return "$records_status"
    cat "$plan"
}

# Scope/text return 3 for legacy plans; step records include the shared Markdown fallback.
plan_record_lines() {
    local helper
    helper="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/plan_records.py"
    python3 -B "$helper" "$1" "$2" "${STATE_DIR:-}"
}

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
    local plan="$1" json

    local records_status=0
    plan_record_lines scope "$plan" || records_status=$?
    [[ "$records_status" == 3 ]] || return "$records_status"

    [[ -s "$plan" ]] || return 0

    # Observed repeatedly (canopy issue #4): an agent asked for a narrative
    # containing a "## Change-impact table" heading instead gives the table
    # its own top-level JSON field, change_impact_table -- a list of
    # objects, not markdown -- no matter how the heading instruction is
    # worded, the same way dispositions kept arriving as disposition_table.
    # Reading the table directly when it exists this way, instead of only
    # ever parsing it back out of rendered narrative prose, is not fooled
    # by which shape the model chose this run.
    case "$plan" in
        .uncle/docs/UPDATED_PROJECT_PLAN.md|.uncle/docs/PROJECT_PLAN.md|.uncle/docs/CHANGE_PLAN.md)
            local stem="${plan##*/}"; stem="${stem%.md}"
            json="${STATE_DIR:-.uncle/workflow}/documents/$stem.json"
            [[ -s "$json" ]] || json=""
            ;;
    esac
    if [[ -n "$json" ]]; then
        local structured
        structured="$(python3 - "$json" <<'PY'
import json, os, re, sys
try:
    payload = json.load(open(sys.argv[1], encoding='utf-8'))
except Exception:
    raise SystemExit(1)
table = payload.get('change_impact_table') if isinstance(payload, dict) else None
if not isinstance(table, list) or not table:
    raise SystemExit(1)
seen = []
for row in table:
    if not isinstance(row, dict):
        continue
    component = row.get('component')
    if not isinstance(component, str):
        continue
    for tok in re.split(r'[,\n]|`', component):
        tok = tok.strip().strip('`').strip()
        if not tok or tok.startswith('/'):
            continue
        # A path cell can carry a trailing annotation with no delimiter
        # ("server/app/records/api.py voice-login routes"); take only the
        # leading path-shaped run, same as the backticked-markdown path
        # already only takes the part inside the backticks.
        match = re.match(r'^\S+', tok)
        tok = match.group(0) if match else tok
        # A root file with no extension (`uncle`, `Makefile`, `Dockerfile`) has neither a
        # slash nor a dot; it is a file when it exists, a symbol name when it does not.
        if '/' in tok or re.search(r'\.[A-Za-z0-9]+$', tok) or (re.fullmatch(r'[A-Za-z0-9_-]+', tok) and os.path.isfile(tok)):
            seen.append(tok)
if not seen:
    raise SystemExit(1)
print('\n'.join(seen))
PY
)"
        if [[ -n "$structured" ]]; then
            printf '%s\n' "$structured" | sort -u
            return 0
        fi
    fi

    plan_text "$plan" | awk '
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
                else if (tok ~ /^[A-Za-z0-9_-]+$/) print "?" tok
            }
        }
    ' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//; /^$/d' | while IFS= read -r tok; do
        # "?name" is a bare token: an extensionless root file only when it exists.
        case "$tok" in
            '?'*) [[ -f "${tok#?}" ]] && printf '%s\n' "${tok#?}" ;;
            *) printf '%s\n' "$tok" ;;
        esac
    done | sort -u
}

# All step readers share the Python extractor, including legacy Markdown plans.
plan_steps() {
    plan_record_lines steps "$1"
}

plan_step_owns() {
    plan_record_lines owns "$1"
}

plan_step_depends() {
    plan_record_lines depends "$1"
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
        if grep -qxF "$f" <<<"$scope"; then
            continue
        fi
        if grep -v '/' <<<"$scope" | grep -qxF "${f##*/}"; then
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

    plan_text "$plan" | awk -v want="$PLAN_MATERIAL_SECTIONS" '
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
    '
}

# plan_material_hash <plan> — one digest over those sections.
plan_material_hash() {
    plan_material_sections "$1" | python3 -c \
        'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
}

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
    local plan="$1" stem candidate
    case "$plan" in
        .uncle/docs/PROJECT_PLAN.md|.uncle/docs/UPDATED_PROJECT_PLAN.md|.uncle/docs/CHANGE_PLAN.md)
            stem="${plan##*/}"; stem="${stem%.md}"
            candidate="${STATE_DIR:-.uncle/workflow}/documents/$stem.json"
            [[ -s "$candidate" ]] && plan="$candidate"
            ;;
    esac
    if [[ "$plan" == *.json ]]; then
        python3 - "$plan" <<'PY'
import json, sys
try:
    value = json.load(open(sys.argv[1], encoding='utf-8')).get('narrative', '')
    if not isinstance(value, str): raise ValueError()
    print(value)
except Exception:
    raise SystemExit(1)
PY
    else
        cat "$plan"
    fi
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

# A plan may head its steps "Implementation steps with Owns/Depends" (a model that wrote
# an unowned "Implementation order" and then added the owned list as its own section
# did exactly that), so `steps` is a recognised heading too: ownership was otherwise
# read from nothing and a correct plan stopped at the approval gate.
#
# The heading is numbered in a change plan ("## 20. Implementation sequence")
# and bare in a greenfield plan ("## Implementation order"): the prompts list
# sections by number, but the plan writes the heading it is given. Requiring the
# number meant this matched no greenfield plan at all, so stepwise implementation
# silently did nothing there.
#
# plan_table_steps_as_list — stdin to stdout, with an implementation-order TABLE
# rewritten as the numbered list every reader here understands.
#
# A planner is free to lay the steps out as
#
#   | Step | Description | Owns | Depends on |
#   | 1 | Add failing tests | `tests/calc.test.js` | — |
#
# and one did: the readers below only knew `1. ... Owns: ...` lines, saw no step
# at all, and the plan stopped at the approval gate for "a protected verification
# path with no owning implementation step" while its first step visibly owned it.
# Each data row becomes `N. <description> Owns: <cell> Depends on: <cell>`.  The step id
# may be `3`, `S-3`, `Step 3`; Owns may be a column or written inline in the Description
# cell (a plan did exactly that: `Owns: ...` at the end of each description, no Owns
# column, ids S-0..S-9).  Text elsewhere passes through unchanged.
# plan_step_blocks_as_list — stdin to stdout, with steps written as headings
# rewritten as the numbered list every reader here understands.
#
#   **Step 1: Project scaffolding**        (or `### Step 1: ...`, `**1. ...**`, `#### S-1: ...`)
#   - Create `playwright.config.js` ...
#   - Owns: `playwright.config.js`, `tests/calculator.spec.js`
#   - Depends on: Step 1
#
# becomes `1. Project scaffolding Owns: ... Depends on: 1`: the Owns:/Depends on: bullets
# are folded onto the step's own line, wherever they sit in its block.  The block's other
# lines follow it unchanged.  A numbered list or a table passes through untouched.
plan_step_blocks_as_list() {
    awk '
        function flush(    i) {
            if (!have) return
            printf "%s%s%s\n", head, (owns != "" ? " " owns : ""), (dep != "" ? " " dep : "")
            for (i = 1; i <= nbody; i++) print body[i]
            have = 0; nbody = 0; owns = ""; dep = ""
        }
        /^## ([0-9]+\. )?Implementation (sequence|order|steps)/ { flush(); insec = 1; print; next }
        insec && /^## / { flush(); insec = 0 }
        !insec { print; next }
        {
            line = $0
            t = line; sub(/^[ \t]+/, "", t)
            marked = (t ~ /^(\*\*|__|#+[ \t]+)/)
            stripped = t; sub(/^(\*\*|__|#+[ \t]+)/, "", stripped)
            if (marked && stripped ~ /^([Ss]tep[ \t]*|[Ss][ -]?)?[0-9]+[ \t]*[:.)-]/) {
                flush()
                n = stripped; sub(/^([Ss]tep[ \t]*|[Ss][ -]?)?/, "", n); sub(/[^0-9].*$/, "", n)
                title = stripped; sub(/^([Ss]tep[ \t]*|[Ss][ -]?)?[0-9]+[ \t]*[:.)-][ \t]*/, "", title)
                gsub(/(\*\*|__)[ \t]*$/, "", title)
                head = n ". " title; have = 1
                next
            }
            if (have && t ~ /^[-*+][ \t]+(\*\*)?[Oo]wns(\*\*)?[ \t]*:/) {
                v = t; sub(/^[-*+][ \t]+/, "", v); gsub(/\*\*/, "", v); owns = (owns != "" ? owns ", " : "") v; next
            }
            if (have && t ~ /^[-*+][ \t]+(\*\*)?[Dd]epends[ \t]+on(\*\*)?[ \t]*:/) {
                v = t; sub(/^[-*+][ \t]+/, "", v); gsub(/\*\*/, "", v)
                gsub(/\(none\)/, "none", v); dep = v; next
            }
            if (have) { body[++nbody] = line; next }
            print line
        }
        END { flush() }
    '
}

plan_table_steps_as_list() {
    plan_step_blocks_as_list | awk '
        function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
        # A step id: "3", "S-3", "S3", "Step 3", "#3".  Returns the number, or "" if the cell is not one.
        function stepnum(cell,    t) {
            t = tolower(trim(cell))
            if (t ~ /^(s|step|#)?[ ._-]*[0-9]+$/) { gsub(/[^0-9]/, "", t); return t }
            return ""
        }
        # A sentence ends a field: "S0. Dependencies pinned to exact versions" depends on S0 only.
        function firstsentence(text) { sub(/\.([ \t].*)?$/, "", text); return text }
        function flush(    i, line, num, pre, rest, k, nums, n, owns, dep, emitted) {
            # 1. Steps described by prose lines under the table: "S1 Owns: `a`, `b`. Depends on: S0."
            for (i = 1; i <= nbuf; i++) {
                line = buf[i]
                if (line ~ /^[ \t]*([Ss]tep[ \t]*|[Ss][ -]?)?[0-9]+[ \t]*[Oo]wns:/) {
                    pre = line; sub(/[Oo]wns:.*$/, "", pre); num = stepnum(pre)
                    if (num == "") continue
                    rest = line; sub(/^.*[Oo]wns:/, "", rest)
                    dep = ""
                    if (match(rest, /[Dd]epends[ \t]+on:/)) { dep = firstsentence(substr(rest, RSTART + RLENGTH)); rest = substr(rest, 1, RSTART - 1) }
                    proseOwns[num] = (num in proseOwns ? proseOwns[num] ", " : "") trim(rest)
                    if (dep != "") proseDep[num] = dep
                    prose[i] = num
                }
            }
            # 2. Rewrite the table rows (and drop the prose lines they absorbed).
            for (i = 1; i <= nbuf; i++) {
                if (i in prose) continue
                if (i in row) {
                    num = row[i]
                    owns = rowOwns[i]
                    if (num in proseOwns) owns = (owns != "" ? owns ", " : "") proseOwns[num]
                    dep = rowDep[i]; if (dep == "" && (num in proseDep)) dep = proseDep[num]
                    printf "%s. %s", num, rowTitle[i]
                    if (owns != "") printf " Owns: %s", owns
                    if (dep != "") printf " Depends on: %s", dep
                    printf "\n"
                    rowSeen[num] = 1
                } else print buf[i]
            }
            # 3. Prose steps with no table row become list steps of their own.
            n = 0
            for (k in proseOwns) if (!(k in rowSeen)) nums[++n] = k + 0
            for (i = 1; i <= n; i++) for (k = i + 1; k <= n; k++) if (nums[k] < nums[i]) { t = nums[i]; nums[i] = nums[k]; nums[k] = t }
            for (i = 1; i <= n; i++) {
                printf "%s. Owns: %s", nums[i], proseOwns[nums[i]]
                if (nums[i] in proseDep) printf " Depends on: %s", proseDep[nums[i]]
                printf "\n"
            }
            nbuf = 0; split("", buf); split("", prose); split("", row); split("", rowOwns); split("", rowDep)
            split("", rowTitle); split("", proseOwns); split("", proseDep); split("", rowSeen)
        }
        /^## ([0-9]+\. )?Implementation (sequence|order|steps)/ { if (insec) flush(); insec = 1; header = 0; print; next }
        insec && /^## / { flush(); insec = 0 }
        !insec { print; next }
        {
            # A bulleted step ("- S-2: Arithmetic core. Owns: `a`. Depends on: S-1.") is a
            # numbered step by another marker; a plan written this way stopped at the
            # approval gate with every protected path "unowned".
            if (match($0, /^[ \t]*[-*+][ \t]+([Ss]tep[ \t]*|[Ss])?[ ._-]*[0-9]+[ \t]*[:.)-]/)) {
                bl = $0; sub(/^[ \t]*[-*+][ \t]+/, "", bl)
                bn = bl; sub(/^([Ss]tep[ \t]*|[Ss])?[ ._-]*/, "", bn); sub(/[^0-9].*$/, "", bn)
                sub(/^([Ss]tep[ \t]*|[Ss])?[ ._-]*[0-9]+[ \t]*[:.)-][ \t]*/, "", bl)
                $0 = bn ". " bl
            }
            buf[++nbuf] = $0
            if ($0 !~ /^[ \t]*\|/) next
            n = split($0, f, "|")
            h1 = tolower(trim(f[2]))
            # The header row: its first cell names the step column, or a cell names Owns/Paths.
            if (!header && (h1 ~ /^(step|steps|#|id|no\.?|number)$/ || tolower($0) ~ /\|[ \t]*(owns|paths?|files?)[ \t]*\|/)) {
                ownsCol = 0; depCol = 0; descCol = 0
                for (i = 2; i < n; i++) {
                    h = tolower(trim(f[i]))
                    if (h ~ /^(owns|paths?|files?)/) ownsCol = i
                    else if (h ~ /^depend/) depCol = i
                    else if (h ~ /^(desc|title|task|work|what|summary|name)/) descCol = i
                }
                header = 1
                delete buf[nbuf]; nbuf--
                next
            }
            num = stepnum(f[2])
            if (header && num != "") {
                row[nbuf] = num
                rowTitle[nbuf] = descCol ? trim(f[descCol]) : trim(f[3])
                rowOwns[nbuf] = ownsCol ? trim(f[ownsCol]) : ""
                rowDep[nbuf] = depCol ? trim(f[depCol]) : ""
                next
            }
            if (trim(f[2]) ~ /^:?-+:?$/) { delete buf[nbuf]; nbuf-- }
        }
        END { if (insec) flush() }
    '

}

# plan_steps <plan> — the implementation sequence, one step per line, in order,
# with its leading number removed.
plan_steps() {
    local plan="$1"

    [[ -s "$plan" ]] || return 0

    plan_text "$plan" | plan_table_steps_as_list | awk '
        # Greenfield plans head this "Implementation order"; change plans say
        # "Implementation sequence". Matching only the latter meant stepwise
        # implementation could never engage on a greenfield plan at all.
        /^## ([0-9]+\. )?Implementation (sequence|order|steps)/ { inseq = 1; next }
        inseq && /^## / { inseq = 0 }
        !inseq { next }
        /^[0-9]+\./ {
            sub(/^[0-9]+\.[[:space:]]*/, "")
            print
        }
    '
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
    plan_text "$plan" | plan_table_steps_as_list | awk '
        function emit(tok) {
            gsub(/^[ \t]+|[ \t]+$/, "", tok)
            if (tok == "") return 0
            if (tok ~ /^\//) return 0
            sub(/^\.\//, "", tok)
            print position[cur] "\t" tok
            return 1
        }
        function extract(line,    tok, found) {
            found = 0
            while (match(line, /`[^`]+`/)) {
                tok = substr(line, RSTART + 1, RLENGTH - 2)
                line = substr(line, RSTART + RLENGTH)
                found += emit(tok)
            }
            return found
        }
        # Paths written without backticks ("Owns: a.js, tests/b.js."), as a planner did
        # and the plan then stopped at the approval gate: nothing was seen to own its
        # protected tests.  Only comma-separated tokens that look like a path (a
        # slash or a dot in them, or `*`) count, so prose such as "Owns: none
        # (read-only)" owns nothing.
        function extract_bare(line,    n, parts, i, tok) {
            n = split(line, parts, /,/)
            for (i = 1; i <= n; i++) {
                tok = parts[i]
                gsub(/^[ \t]+|[ \t]+$/, "", tok)
                sub(/[.;:]+$/, "", tok)
                sub(/[ \t].*$/, "", tok)
                if (tok ~ /^[A-Za-z0-9_.\/*@-]+$/ && (tok ~ /[\/.]/ || tok == "*") && tok !~ /^[.]+$/) emit(tok)
            }
        }
        /^## ([0-9]+\. )?Implementation (sequence|order|steps)/ { inseq = 1; next }
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
                if (!extract(line)) extract_bare(line)
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
    ' | awk '!seen[$0]++'
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

    plan_text "$plan" | plan_table_steps_as_list | awk '
        # Rendered plans normally put this field on the following bullet
        # (`- Depends on: 2`), rather than on the numbered heading.  Retain
        # the current step until the next heading so either layout has the
        # same scheduling semantics.
        function emit_dependencies(line,    ref) {
            if (!match(line, /[Dd]epends[ \t]+on:/)) return
            line = substr(line, RSTART + RLENGTH)
            while (match(line, /[0-9]+/)) {
                ref = substr(line, RSTART, RLENGTH)
                print current "\t" ((ref in position) ? position[ref] : ref)
                line = substr(line, RSTART + RLENGTH)
            }
        }
        /^## ([0-9]+\. )?Implementation (sequence|order|steps)/ { inseq = 1; next }
        inseq && /^## / { inseq = 0 }
        !inseq { next }
        /^[0-9]+\./ {
            n = $0; sub(/\..*$/, "", n)
            position[n] = ++count
            current = position[n]
            emit_dependencies($0)
            next
        }
        current { emit_dependencies($0) }
    '
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

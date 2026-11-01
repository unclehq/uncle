#!/usr/bin/env bash
# Files changed outside the plan's change-impact table must be on the record. An attended run that did not record them stops; an
# unattended run, which has no one to hand-edit JSON, has the driver record them (visibly, as driver-recorded) and carries on.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
unset UNATTENDED

awk '/^check_scope_deviations\(\) \{/ {p=1} p {print} p && /^}/ {exit}' "$ROOT/scripts/change-workflow.sh" > "$TMP/fn.sh"
check "function extracted" test -s "$TMP/fn.sh"

new_project() {   # <name> <recorded: files already recorded as deviations, space separated>
    local d="$TMP/$1"; rm -rf "$d"; mkdir -p "$d/.uncle/docs" "$d/.uncle/workflow/documents"
    printf '# Change plan\n\n## Change-impact table\n\n| Component |\n|---|\n| `app/main.sh` |\n' > "$d/.uncle/docs/CHANGE_PLAN.md"
    python3 - "$d" "${2:-}" <<'PY'
import json, sys
d, recorded = sys.argv[1], sys.argv[2].split()
plan = open(d + '/.uncle/docs/CHANGE_PLAN.md').read()
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': plan}, open(d + '/.uncle/workflow/documents/CHANGE_PLAN.json', 'w'))
fragment = {'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes', 'changed_files': [{'path': 'app/main.sh', 'purpose': 'x'}],
            'deviations': [{'file': f, 'reason': 'because'} for f in recorded], 'unresolved_concerns': [], 'deliveries': []}
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes', 'fragments': [fragment]},
          open(d + '/.uncle/workflow/documents/IMPLEMENTATION_NOTES.json', 'w'))
PY
    echo "$d"
}
# scope <dir> <changed files, newline separated> [env...] -> prints output, then rc=N
scope() {
    local d="$1" files="$2"; shift 2
    (
        cd "$d" || exit 1
        for a in "$@"; do export "$a"; done
        ROOT="$ROOT"; STATE_DIR=.uncle/workflow; export ROOT STATE_DIR
        change_diff_files() { printf '%s\n' "$files"; }
        . "$ROOT/scripts/lib/plan-scope.sh"
        . "$TMP/fn.sh"
        ( check_scope_deviations ); echo "rc=$?"
    ) 2>&1
}
recorded() { python3 "$ROOT/scripts/lib/implementation_notes.py" deviation-paths "$1" | sort | tr '\n' ' '; }

FILES=$'app/main.sh\nscripts/tests/a-test.sh\nscripts/tests/b-test.py'

d="$(new_project attended)"; out="$(scope "$d" "$FILES")"
check "attended: unrecorded out-of-scope files stop the run" grep -q 'rc=1' <<< "$out"
check "attended: the files and the rule are named" bash -c 'grep -q "scripts/tests/a-test.sh" <<< "$1" && grep -q "Every file outside the frozen scope" <<< "$1"' _ "$out"
check "attended: nothing was recorded for the implementer" test -z "$(recorded "$d")"

d="$(new_project unattended)"; out="$(scope "$d" "$FILES" UNATTENDED=1)"
check "unattended: the run is not stopped" grep -q 'rc=0' <<< "$out"
check "unattended: the driver says it recorded them" grep -q 'Unattended run: recorded the files above as deviations (driver-recorded)' <<< "$out"
check "unattended: both files are now in the canonical deviations" test "$(recorded "$d")" == 'scripts/tests/a-test.sh scripts/tests/b-test.py '
check "unattended: the in-scope file is not recorded" bash -c '! grep -q "app/main.sh" <<< "$1"' _ "$(recorded "$d")"
check "unattended: the rendered notes show them as driver-recorded" bash -c 'grep -q "scripts/tests/a-test.sh" "$1" && grep -q "Recorded by the driver" "$1"' _ "$d/.uncle/docs/IMPLEMENTATION_NOTES.md"
out2="$(scope "$d" "$FILES" UNATTENDED=1)"
check "unattended: a second pass finds them recorded and says so" grep -q '(all recorded in canonical IMPLEMENTATION_NOTES.json)' <<< "$out2"
check "unattended: ...without recording them again" test "$(grep -c 'Recorded by the driver' "$d/.uncle/docs/IMPLEMENTATION_NOTES.md")" == 2

d="$(new_project partial 'scripts/tests/a-test.sh')"; out="$(scope "$d" "$FILES" UNATTENDED=1)"
check "unattended: only the files not already recorded are added" test "$(recorded "$d")" == 'scripts/tests/a-test.sh scripts/tests/b-test.py '
check "unattended: ...and the implementer's own reason for the recorded one is kept" bash -c 'grep -q "because" "$1"' _ "$d/.uncle/docs/IMPLEMENTATION_NOTES.md"

d="$(new_project clean)"; out="$(scope "$d" 'app/main.sh' UNATTENDED=1)"
check "nothing outside the plan: passes and records nothing" bash -c 'grep -q "rc=0" <<< "$1" && [ -z "$2" ]' _ "$out" "$(recorded "$d")"

d="$(new_project allrecorded 'scripts/tests/a-test.sh scripts/tests/b-test.py')"; out="$(scope "$d" "$FILES")"
check "attended with everything recorded passes (the existing behavior)" grep -q 'rc=0' <<< "$out"

[[ "$fails" == 0 ]] && echo "unattended-scope-deviations-test.sh: all checks passed" || { echo "unattended-scope-deviations-test.sh: $fails failure(s)"; exit 1; }

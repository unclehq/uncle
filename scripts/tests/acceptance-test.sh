#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/acceptance.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
COUNT=0

check() {
    local expected="$1" actual
    actual="$(acceptance_result "$TMP/report.md" "${2:-}")"
    COUNT=$((COUNT + 1))
    if [[ "$actual" != "$expected" ]]; then
        echo "FAIL: expected $expected, got $actual"
        cat "$TMP/report.md"
        exit 1
    fi
}
report() {
    printf '## Findings\n\nNarrative says PASS.\n\n## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n%s\n' "$1" > "$TMP/report.md"
}

check UNKNOWN
report '| C1 | YES | PASS | command exited 0 |'
check PASS
check UNKNOWN 'C1 C2'
check PASS C1
for status in FAIL BLOCKED 'NOT RUN' N/A; do
    report "| C1 | YES | $status | observed result |"
    if [[ "$status" == FAIL ]]; then check REPAIR; else check BLOCKED-SETUP; fi
done
report $'| C1 | YES | FAIL | assertion failed |\n| C2 | YES | BLOCKED | browser unavailable |'
check REPAIR
report $'| C1 | YES | PASS | observed result |\n| C2 | NO | N/A | requirement excludes it |'
check PASS
check UNKNOWN 'C1 C2'
report '| C1 | NO | PASS | observed result |'
check UNKNOWN
report '| C1 | YES | PASS | |'
check UNKNOWN
report '| C1 | YES | SKIP | observed result |'
check UNKNOWN
report '| C1 | MAYBE | PASS | observed result |'
check UNKNOWN
report $'| C1 | YES | PASS | observed result |\n| C1 | YES | FAIL | duplicate |'
check UNKNOWN
report '| C1 | YES | PASS | unescaped | pipe |'
check UNKNOWN
report $'| C1 | YES | PASS | observed result |\n\nTrailing prose hiding a failure.'
check UNKNOWN
report '| C1 | YES | PASS | observed result |'
printf '\n## Hidden results\n\n| C2 | YES | FAIL | must not be ignored |\n' >> "$TMP/report.md"
check UNKNOWN
report '| C1 | YES | PASS | observed result |'
printf '\n## Acceptance gate\n\n| C2 | YES | PASS | duplicate section |\n' >> "$TMP/report.md"
check UNKNOWN
printf '## Acceptance gate\n\n| C1 | YES | PASS | missing header |\n' > "$TMP/report.md"
check UNKNOWN
report '| C1 | YES | PASS | observed result |'
sed 's/$/\r/' "$TMP/report.md" > "$TMP/crlf.md"
mv "$TMP/crlf.md" "$TMP/report.md"
check PASS
report $'| ASSERTIONS | YES | FAIL | missing list assertion |\n| AT-01/AC-02 | YES | NOT RUN | final human comparison pending |'
check REPAIR ASSERTIONS
report '| AT-01/AC-02 | YES | NOT RUN | final human comparison pending |'
check BLOCKED-SETUP
report $'| ASSERTIONS | YES | FAIL | missing assertion |\n| BAD | YES | INVALID | malformed report must not authorize repair |'
check UNKNOWN

# --- the three blocked classes are told apart -------------------------------
# One word for three situations made them one dead stop. Setup is doable now,
# a signature is what the workflow is for, and impossible means the plan is
# wrong -- so the verdict has to distinguish them.
for status in BLOCKED-SETUP BLOCKED-HUMAN BLOCKED-IMPOSSIBLE; do
    report "| C1 | YES | $status | observed result |"
    check "$status"
done

# Precedence, worst first: a defect outranks everything, then a check no
# environment can perform, then one waiting on an action, then one waiting on
# a person. Anything less and the report of the worse problem is lost.
report $'| C1 | YES | FAIL | assertion failed |\n| C2 | YES | BLOCKED-IMPOSSIBLE | no window under 500px |'
check REPAIR
report $'| C1 | YES | BLOCKED-IMPOSSIBLE | no window under 500px |\n| C2 | YES | BLOCKED-SETUP | safaridriver not enabled |'
check BLOCKED-IMPOSSIBLE
report $'| C1 | YES | BLOCKED-SETUP | tree not committed |\n| C2 | YES | BLOCKED-HUMAN | awaiting sign-off |'
check BLOCKED-SETUP
report $'| C1 | YES | PASS | observed result |\n| C2 | YES | BLOCKED-HUMAN | awaiting sign-off |'
check BLOCKED-HUMAN

# A non-required row of any class never blocks the run.
report $'| C1 | YES | PASS | observed result |\n| C2 | NO | BLOCKED-IMPOSSIBLE | optional and unreachable |'
check PASS

# The blocking rows can be named, so the driver can batch them or check them
# against waivers rather than printing a verdict and stopping.
report $'| C1 | YES | BLOCKED-IMPOSSIBLE | no window under 500px |\n| C2 | YES | BLOCKED-HUMAN | awaiting sign-off |\n| C3 | YES | BLOCKED | unclassified |\n| C4 | NO | BLOCKED-IMPOSSIBLE | optional |\n| C5 | YES | PASS | observed |'
ids() { acceptance_blocked_ids "$TMP/report.md" "$1" | tr '\n' ' ' | sed 's/ $//'; }
COUNT=$((COUNT + 1))
[ "$(ids BLOCKED-IMPOSSIBLE)" = "C1" ] || { echo "FAIL: impossible ids: $(ids BLOCKED-IMPOSSIBLE)"; exit 1; }
COUNT=$((COUNT + 1))
[ "$(ids BLOCKED-HUMAN)" = "C2" ] || { echo "FAIL: human ids: $(ids BLOCKED-HUMAN)"; exit 1; }
COUNT=$((COUNT + 1))
[ "$(ids BLOCKED-SETUP)" = "C3" ] || { echo "FAIL: setup ids (a bare BLOCKED counts): $(ids BLOCKED-SETUP)"; exit 1; }

COUNT=$((COUNT + 1))
acceptance_is_blocked BLOCKED-HUMAN || { echo "FAIL: BLOCKED-HUMAN is a blocked class"; exit 1; }
COUNT=$((COUNT + 1))
acceptance_is_blocked BLOCKED || { echo "FAIL: a bare BLOCKED is a blocked class"; exit 1; }
COUNT=$((COUNT + 1))
if acceptance_is_blocked PASS; then echo "FAIL: PASS is not blocked"; exit 1; fi
COUNT=$((COUNT + 1))
if acceptance_is_blocked REPAIR; then echo "FAIL: REPAIR is not blocked"; exit 1; fi
echo "acceptance-test.sh: $COUNT checks passed"

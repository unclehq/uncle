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
    if [[ "$status" == FAIL ]]; then check REPAIR; else check BLOCKED; fi
done
report $'| C1 | YES | FAIL | assertion failed |\n| C2 | YES | BLOCKED | browser unavailable |'
check BLOCKED
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
echo "acceptance-test.sh: $COUNT checks passed"

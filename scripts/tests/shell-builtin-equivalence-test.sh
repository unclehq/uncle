#!/usr/bin/env bash
# state_read, state_issue and green_regressions read their files with shell builtins (they used head and awk, a process each, on every
# state transition and gate). The oracles below are the originals, kept verbatim; every case must give the same answer.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }
. "$ROOT/scripts/lib/state.sh"; . "$ROOT/scripts/lib/green-check.sh"

old_state_read() {
    local file="$1" default="${2:-}" raw
    if [[ ! -s "$file" ]]; then printf '%s' "$default"; return 0; fi
    raw="$(head -n 1 "$file")"
    if [[ "$raw" =~ ^([0-9]+):(.*)$ ]]; then printf '%s' "${BASH_REMATCH[2]}"; else printf '%s' "$raw"; fi
}
old_green_regressions() {
    if [[ ! -s "$1" ]]; then printf '0'; return 0; fi
    awk '
        { t = index($0, "\t") }
        t > 0 && substr($0, 1, t - 1) == "REGRESSION" { n++ }
        END { printf "%d", n + 0 }
    ' "$1"
}

i=0
while IFS= read -r -d '' content; do
    i=$((i + 1)); printf '%s' "$content" > "$TMP/state.$i"
    [[ "$(state_read "$TMP/state.$i" dflt)" == "$(old_state_read "$TMP/state.$i" dflt)" ]] && ok || bad "state_read-$i" "differs for $(printf '%q' "$content")"
done < <(printf '%s\0' $'IMPLEMENT\n' 'IMPLEMENT' $'12:IMPLEMENT\n' '7:WAIT_PLAN_APPROVAL' 'abc:IMPLEMENT' $'FINAL_AUDIT\nsecond line\n' \
    $'  padded  \n' $'CRLF_STATE\r\n' 'back\slash' $'tab\there\n' '0:' ':X' $'\n' $'\nlate\n' '12:' '99999999999999999999:ZZ')
[[ "$(state_read "$TMP/does-not-exist" dflt)" == "dflt" ]] && ok || bad state_read-missing "default not returned"
: > "$TMP/empty"; [[ "$(state_read "$TMP/empty" dflt)" == "dflt" ]] && ok || bad state_read-empty "default not returned"

j=0
while IFS= read -r -d '' table; do
    j=$((j + 1)); printf '%s' "$table" > "$TMP/table.$j"
    [[ "$(green_regressions "$TMP/table.$j")" == "$(old_green_regressions "$TMP/table.$j")" ]] && ok || bad "green_regressions-$j" "differs for $(printf '%q' "$table")"
done < <(printf '%s\0' $'PASS\ta\nREGRESSION\tb\n' $'REGRESSION\tb' $'REGRESSIONX\tb\nREGRESSION\n' $'PREEXISTING\tx\nREGRESSION\ty\nREGRESSION\tz\n' \
    $'REGRESSION\r\tx\n' $'\tREGRESSION\n' $'notREGRESSION\tx\n' $'REGRESSION\t\nREGRESSION\t\n' $'FAIL\tREGRESSION\n' '' $'\n\n' $'REGRESSION\tcmd with spaces\n  REGRESSION\tindented\n')
: > "$TMP/emptytable"; [[ "$(green_regressions "$TMP/emptytable")" == "0" && "$(green_regressions "$TMP/none")" == "0" ]] && ok || bad green_regressions-empty "not 0"

if [[ "$FAIL" -ne 0 ]]; then echo "shell-builtin-equivalence-test.sh: $FAIL failed"; exit 1; fi
echo "shell-builtin-equivalence-test.sh: $PASS cases match the originals"

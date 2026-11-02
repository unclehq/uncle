#!/usr/bin/env bash
# hash_stdin replaced `python3 -c 'print(hashlib.sha256(sys.stdin.read().encode()).hexdigest())'` for the checklist-draft fingerprints.
# The Python is the oracle: every input must give the same digest line.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2"; }
. "$ROOT/scripts/lib/sha256.sh"
old() { python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest())'; }
i=0
while IFS= read -r -d '' text; do
    i=$((i + 1))
    want="$(printf '%s' "$text" | old)"; got="$(printf '%s' "$text" | hash_stdin)"
    [[ "$want" == "$got" ]] && ok || bad "case-$i" "want [$want] got [$got] for $(printf '%q' "$text")"
done < <(printf '%s\0' '' 'a' $'one\n' $'REQUIREMENTS_INTERPRETATION 5891b5b5\nPROJECT_PLAN deadbeef\n' 'no newline' $'caf\xc3\xa9 \xe2\x9c\x93\n' $'tab\there\r\n' "$(head -c 200000 /dev/zero | tr '\0' 'x')")
[[ "$(printf 'x' | hash_stdin | wc -l | tr -d ' ')" == 1 ]] && ok || bad one-line "output is not exactly one line"
if [[ "$FAIL" -ne 0 ]]; then echo "hash-stdin-test.sh: $FAIL failed"; exit 1; fi
echo "hash-stdin-test.sh: $PASS cases match the Python"

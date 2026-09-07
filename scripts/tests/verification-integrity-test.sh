#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/verification-integrity.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
mkdir tests
printf 'assert actual == expected\n' > tests/test.txt
printf 'source result\n' > tests/expected.txt
mkdir 'tests/with space'
printf '\000\001binary\377\n' > 'tests/with space/résumé.dat'
printf 'tests\n' > paths
baseline="$(verification_manifest paths)"
COUNT=0
if command -v python3 > /dev/null; then
    COUNT=$((COUNT+1))
    [[ "$(WORKFLOW_HASH_BACKEND=python verification_manifest paths)" == "$(WORKFLOW_HASH_BACKEND=shell verification_manifest paths)" ]] \
        || { echo 'FAIL: manifest backends disagree'; exit 1; }
fi
changed() {
    COUNT=$((COUNT + 1))
    if [[ "$(verification_manifest paths)" == "$baseline" ]]; then
        echo 'FAIL: protected change was not detected'; exit 1
    fi
}
rejected() {
    COUNT=$((COUNT + 1))
    if verification_manifest paths > /dev/null 2>&1; then
        echo 'FAIL: invalid or missing scope was accepted'; exit 1
    fi
}
printf 'assert True\n' > tests/test.txt
changed
printf 'assert actual == expected\n' > tests/test.txt
printf 'fabricated expectation\n' > tests/expected.txt
changed
printf 'source result\n' > tests/expected.txt
printf 'new test\n' > tests/added.txt
changed
rm tests/added.txt tests/test.txt
changed
printf 'assert actual == expected\n' > tests/test.txt
mkdir tests/__pycache__
printf 'bytecode\n' > tests/__pycache__/test.pyc
COUNT=$((COUNT + 1))
[[ "$(verification_manifest paths)" == "$baseline" ]] || { echo 'FAIL: bytecode changed manifest'; exit 1; }
for path in missing ../outside /etc/passwd ./tests .git .uncle/workspace tests/../tests; do
    printf '%s\n' "$path" > paths
    rejected
done
ln -s tests alias
printf 'alias/test.txt\n' > paths
rejected
printf 'tests\n' > paths
ln -s expected.txt tests/link
rejected
rm tests/link
# A traversal error must not be hidden by a later, readable scope.
printf 'control\n' > control.txt
printf 'tests\ncontrol.txt\n' > paths
find() { command find "$@"; return 1; }
WORKFLOW_HASH_BACKEND=shell rejected
unset -f find
printf '## Protected verification paths\n\n```text\ntests\n```\n' > plan.md
COUNT=$((COUNT + 1))
[[ "$(verification_paths plan.md)" == tests ]]
printf '## Protected verification paths\n\n```\ntests\n' > plan.md
COUNT=$((COUNT + 1))
if verification_paths plan.md > /dev/null; then echo 'FAIL: unclosed scope fence'; exit 1; fi
echo "verification-integrity-test.sh: $COUNT checks passed"

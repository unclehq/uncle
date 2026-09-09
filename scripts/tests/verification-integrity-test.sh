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
if python3 -c pass > /dev/null; then
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
        printf 'FAIL: invalid or missing scope was accepted (backend=%s, scope=%s)\n' \
            "${WORKFLOW_HASH_BACKEND:-auto}" "$(cat paths)"
        exit 1
    fi
}
make_symlink() {
    # Git Bash's default ln -s can silently copy the target. Request native
    # links, then check the fixture rather than treating a copy as a symlink.
    if MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict" ln -s "$1" "$2" 2>/dev/null \
        && [[ -L "$2" ]]; then
        return 0
    fi
    # Destinations are fresh fixtures under this test's temporary directory.
    rm -rf -- "$2"
    printf 'SKIP: real symlinks unavailable for fixture %s\n' "$2"
    return 1
}
# Directory suffixes canonicalize identically in both backends, while malformed
# paths and file/symlink scopes with a directory suffix remain rejected.
for backend in python shell; do
    for scope in tests/ 'tests/with space/'; do
        printf '%s\n' "${scope%/}" > paths
        canonical="$(WORKFLOW_HASH_BACKEND="$backend" verification_manifest paths)"
        printf '%s\n' "$scope" > paths
        COUNT=$((COUNT+1))
        [[ "$(WORKFLOW_HASH_BACKEND="$backend" verification_manifest paths)" == "$canonical" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
    done
    printf 'tests\ntests/\n' > paths
    COUNT=$((COUNT+1))
    [[ "$(WORKFLOW_HASH_BACKEND="$backend" verification_manifest paths)" == "$baseline" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
    for scope in tests// tests/./ tests/../ / ./ ../ tests/test.txt/ .git/ .uncle/; do
        printf '%s\n' "$scope" > paths
        WORKFLOW_HASH_BACKEND="$backend" rejected
    done
    if make_symlink tests alias-dir; then
        printf 'alias-dir/\n' > paths
        WORKFLOW_HASH_BACKEND="$backend" rejected
        rm alias-dir
    fi
    printf 'tests/\n' > paths
    printf 'new test\n' > tests/new.txt
    COUNT=$((COUNT+1))
    [[ "$(WORKFLOW_HASH_BACKEND="$backend" verification_manifest paths)" != "$baseline" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
    rm tests/new.txt
 done
printf 'tests\n' > paths
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
for path in missing ../outside /etc/passwd ./tests .git .uncle/workflow tests/../tests; do
    printf '%s\n' "$path" > paths
    rejected
done
if make_symlink tests alias; then
    printf 'alias/test.txt\n' > paths
    rejected
    rm alias
fi
printf 'tests\n' > paths
if make_symlink expected.txt tests/link; then
    rejected
    rm tests/link
fi
# A traversal error must not be hidden by a later, readable scope.
printf 'control\n' > control.txt
printf 'tests\ncontrol.txt\n' > paths
find() { command find "$@"; return 1; }
WORKFLOW_HASH_BACKEND=shell rejected
unset -f find
printf '## Protected verification paths\n\n```text\ntests\n```\n' > plan.md
COUNT=$((COUNT + 1))
[[ "$(verification_paths plan.md)" == tests ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
printf '## Protected verification paths\n\n```\ntests\n' > plan.md
COUNT=$((COUNT + 1))
if verification_paths plan.md > /dev/null; then echo 'FAIL: unclosed scope fence'; exit 1; fi
echo "verification-integrity-test.sh: $COUNT checks passed"

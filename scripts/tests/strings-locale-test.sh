#!/usr/bin/env bash
set -uo pipefail
# scripts/lib/strings.sh must convert case the same under every locale. On bash 3.2 with a UTF-8
# collation, the ranges [a-z] and [A-Z] match both cases, which turned "true" into garbage bytes.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fails=0
for loc in C en_US.UTF-8; do
    out="$(LC_ALL="$loc" bash -c '. "$1"; uncle_lower_to a "True-ABC xyz"; uncle_upper_to b "true-abc" "-"; uncle_sanitize_to c "Ab-1.x" "azAZ09"; printf "%s|%s|%s" "$a" "$b" "$c"' _ "$ROOT/scripts/lib/strings.sh")"
    if [[ "$out" != "true-abc xyz|TRUE_ABC|Ab_1_x" ]]; then
        echo "FAIL [$loc]: got '$out'"; fails=$((fails + 1))
    fi
done
[[ "$fails" == 0 ]] || exit 1
echo "strings-locale-test.sh: all checks passed"

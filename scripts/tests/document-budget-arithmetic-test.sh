#!/usr/bin/env bash
# document_budget and document_budget_prompt do their arithmetic in shell. The oracle here is the awk they used before, kept verbatim:
# for every source size on a grid around the floor, the multiplier steps and the ceiling, both must agree to the byte.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }
. "$ROOT/scripts/lib/gates.sh"
read -r FLOOR CEILING MULT LFLOOR LCEIL <<< "$DOCUMENT_BUDGET_RULE"
export STATE_DIR="$TMP/state"; mkdir -p "$STATE_DIR"
cd "$TMP"

reference_budget() {      # source_bytes -> "bytes lines", the original awk
    awk -v n="$1" -v m="$MULT" -v lo="$FLOOR" -v hi="$CEILING" -v ll="$LFLOOR" -v lh="$LCEIL" '
        BEGIN { b=n*m; if(b<lo)b=lo; if(b>hi)b=hi; l=int((b*ll+lo-1)/lo); if(l>lh)l=lh; printf "%.0f %.0f\n", b, l }'
}
reference_target() {      # bytes lines -> "target target_lines", the original awk
    awk -v b="$1" -v l="$2" 'BEGIN {b=int(b*.75); l=int(l*.75); printf "%.0f %.0f", (b<1?1:b), (l<1?1:l)}'
}

for size in 0 1 2 999 1000 1332 1333 1334 1335 5000 13333 13334 13335 20000 40000 99999 1000000; do
    if [[ "$size" == 0 ]]; then : > "$TMP/source.md"; else head -c "$size" /dev/zero | tr '\0' 'a' > "$TMP/source.md"; fi
    export DOCUMENT_BUDGET_SOURCE="$TMP/source.md"
    want="$(reference_budget "$size")"
    got="$(document_budget IMPLEMENTATION_NOTES.md)"
    [[ "$got" == "$want" ]] && ok || bad "budget-$size" "want [$want] got [$got]"
    read -r b l <<< "$want"
    wt="$(reference_target "$b" "$l")"
    gt="$(document_budget_prompt baseline | grep -F -- '- IMPLEMENTATION_NOTES.md:' | sed -E 's/.*Draft toward ([0-9]+) bytes and ([0-9]+) lines.*/\1 \2/')"
    if [[ -n "$gt" ]]; then
        [[ "$gt" == "$wt" ]] && ok || bad "target-$size" "want [$wt] got [$gt]"
    fi
done

# a saved increase wins when larger, and is normalised like %.0f (no leading zeros)
export DOCUMENT_BUDGET_SOURCE="$TMP/source.md"; printf 'a' > "$TMP/source.md"
mkdir -p "$STATE_DIR/document-budgets"
path="$(document_budget_override_path CHANGE_PLAN.md)"
printf '9000 300\n' > "$path"; [[ "$(document_budget CHANGE_PLAN.md)" == "9000 300" ]] && ok || bad saved-larger "$(document_budget CHANGE_PLAN.md)"
printf '10 10\n' > "$path";    [[ "$(document_budget CHANGE_PLAN.md)" == "4000 120" ]] && ok || bad saved-smaller "$(document_budget CHANGE_PLAN.md)"
WORKFLOW_DOC_MAX_BYTES=00012 bash -c '. "$0/scripts/lib/gates.sh"; export STATE_DIR="$1" DOCUMENT_BUDGET_SOURCE="$2"; document_budget CHANGE_PLAN.md' "$ROOT" "$STATE_DIR" "$TMP/source.md" | grep -qx '12 120' && ok || bad leading-zeros 'a saved override must normalise 00012 to 12'
WORKFLOW_DOC_MAX_BYTES=abc document_budget CHANGE_PLAN.md > /dev/null 2>&1 && bad non-numeric 'accepted' || ok

if [[ "$FAIL" -ne 0 ]]; then echo "document-budget-arithmetic-test.sh: $FAIL failed"; exit 1; fi
echo "document-budget-arithmetic-test.sh: $PASS checks passed"

#!/usr/bin/env bash
# A run bound to issue N whose origin file was overwritten by something else recovers, loudly; every other disagreement still refuses.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
. "$ROOT/scripts/lib/issue-close.sh"

# case <name> <state> <origin> <bound-or-empty> [env...] -> prints output; leaves $TMP/<name>/ for inspection
run_case() {
    local d="$TMP/$1"; mkdir -p "$d"; local state="$2" origin="$3" bound="$4"; shift 4
    printf '%s\n' "$state" > "$d/state"; printf "$origin" > "$d/origin"; [[ -z "$bound" ]] || printf "$bound" > "$d/origin.bound"
    ( for a in "$@"; do export "$a"; done; state_origin_agree "$d/state" "$d/origin"; echo "rc=$?" ) 2>&1
}

out="$(run_case heal 116:IMPLEMENT 'owner/repo\t42\tgh\n' 'unclehq/uncle\t116\tgh\n' STAGEGATE_ORIGIN_REPO=unclehq/uncle STAGEGATE_ORIGIN_ISSUE=116)"
check "a clobbered origin is restored when the launch binding matches the state" grep -q 'rc=0' <<< "$out"
check "...from the copy the writer kept (provenance field included)" test "$(cat "$TMP/heal/origin")" == $'unclehq/uncle\t116\tgh'
check "...with a loud warning" grep -q 'WARNING: .*named issue 42, but this run is bound to issue 116' <<< "$out"
check "...and the tamper is logged with what was found" grep -q 'found:       owner/repo 42 gh' "$TMP/heal/origin-tamper.log"

out="$(run_case nobound 116:IMPLEMENT 'owner/repo\t42\tgh\n' '' STAGEGATE_ORIGIN_REPO=unclehq/uncle STAGEGATE_ORIGIN_ISSUE=116)"
check "without a kept copy the binding alone restores it" grep -q 'rc=0' <<< "$out"
check "...as an unverified origin (no provenance field, so it fails closed at the close gate)" test "$(cat "$TMP/nobound/origin")" == $'unclehq/uncle\t116'

out="$(run_case wrongbound 116:IMPLEMENT 'owner/repo\t42\tgh\n' 'other/repo\t116\tgh\n' STAGEGATE_ORIGIN_REPO=unclehq/uncle STAGEGATE_ORIGIN_ISSUE=116)"
check "a kept copy for a different repository is not trusted" test "$(cat "$TMP/wrongbound/origin")" == $'unclehq/uncle\t116'

out="$(run_case other 116:IMPLEMENT 'owner/repo\t42\tgh\n' 'unclehq/uncle\t116\tgh\n' STAGEGATE_ORIGIN_REPO=unclehq/uncle STAGEGATE_ORIGIN_ISSUE=7)"
check "a launch binding for a different issue than the state is still refused" grep -q 'rc=1' <<< "$out"
check "...with the corruption message" grep -q 'Refusing to act on corrupt workflow state' <<< "$out"
check "...and the origin file is left alone" test "$(cat "$TMP/other/origin")" == $'owner/repo\t42\tgh'

out="$(run_case nobinding 116:IMPLEMENT 'owner/repo\t42\tgh\n' 'unclehq/uncle\t116\tgh\n')"
check "no launch binding at all: still refused (a hand edit, not this process's business)" grep -q 'rc=1' <<< "$out"

out="$(run_case agree 116:IMPLEMENT 'unclehq/uncle\t116\tgh\n' '' STAGEGATE_ORIGIN_REPO=unclehq/uncle STAGEGATE_ORIGIN_ISSUE=116)"
check "agreeing state and origin are untouched" grep -q 'rc=0' <<< "$out"
check "...with no warning and no tamper log" bash -c '[ ! -e "$1/origin-tamper.log" ] && ! grep -q WARNING <<< "$2"' _ "$TMP/agree" "$out"

out="$(run_case complete COMPLETE 'owner/repo\t42\tgh\n' '' )"
check "a finished run of another issue is still not corruption" grep -q 'rc=0' <<< "$out"

[[ "$fails" == 0 ]] && echo "origin-self-heal-test.sh: all checks passed" || { echo "origin-self-heal-test.sh: $fails failure(s)"; exit 1; }

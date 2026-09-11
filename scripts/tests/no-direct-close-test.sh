#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/issue-close.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
gh() {
    [[ "$*" == 'auth status' ]] || { echo "Unexpected gh mutation: $*" >&2; return 99; }
}
printf 'READY\n' > "$tmp/audit"
printf 'owner/repo\t13\tcurl\n' > "$tmp/origin"
printf 'run-1\tREADY\t%s\n' "$(hash_file "$tmp/audit")" > "$tmp/verdict"
# Fetch provenance must not block a currently authenticated, bound PR handoff.
issue_close_eligible run-1 owner/repo 13 "$tmp/verdict" "$tmp/origin" "$tmp/audit" "$tmp/marker" 1 1 1 curl
issue_close_if_ready run-1 owner/repo 13 "$tmp/verdict" "$tmp/origin" "$tmp/audit" "$tmp/marker" 1 1 1 curl
[[ ! -e "$tmp/marker" ]]
printf 'NOT READY\n' > "$tmp/audit"
if issue_close_eligible run-1 owner/repo 13 "$tmp/verdict" "$tmp/origin" "$tmp/audit" "$tmp/marker" 1 1 1 curl; then
    echo 'FAIL: changed audit authorized PR publication' >&2
    exit 1
fi
echo 'no-direct-close-test: passed'

#!/usr/bin/env bash
# finished_extras helper: duration format, start stamp, PR line, Total time parenthetical.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }
check() { if [[ "$2" == "$3" ]]; then ok; else bad "$1" "expected '$2', got '$3'"; fi; }
has()  { if [[ "$3" == *"$2"* ]]; then ok; else bad "$1" "expected to contain '$2', got '$3'"; fi; }

H="$ROOT/scripts/lib/finished_extras.py"
S="$WORK/state"
mkdir -p "$S/pr"
run() { python3 -B "$H" --state "$S" "$@"; }
stamp_ago() { python3 -c "import datetime,sys;print((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=int(sys.argv[1]))).strftime('%Y-%m-%dT%H:%M:%SZ'))" "$1" > "$S/run-started-at"; }
journal() { printf '%s' "$1" > "$S/pr/journal.json"; }

# formatter
fmt() { python3 -B -c "import sys;sys.path.insert(0,'$ROOT/scripts/lib');import finished_extras as f;print(f.format_duration($1))"; }
check fmt-0 "0s" "$(fmt 0)"
check fmt-59 "59s" "$(fmt 59)"
check fmt-60 "1m 0s" "$(fmt 60)"
check fmt-3723 "1h 2m 3s" "$(fmt 3723)"
check fmt-2832 "47m 12s" "$(fmt 2832)"
check fmt-neg "0s" "$(fmt -5)"

# start: write-once, reset, fresh stamp
run start; first="$(cat "$S/run-started-at")"
sleep 1; run start
check start-once "$first" "$(cat "$S/run-started-at")"
run reset
[[ ! -e "$S/run-started-at" ]] && ok || bad reset "stamp still present"
run start; [[ -e "$S/run-started-at" ]] && ok || bad restart "no stamp after reset"

# invalid / missing start
echo garbage > "$S/run-started-at"
has bad-start "Total time: unknown" "$(run print --unattended)"
rm -f "$S/run-started-at"
has no-start "Total time: unknown" "$(run print --unattended)"

# total time and parenthetical
stamp_ago 100
out="$(run print --unattended --reason not-published)"
has unatt-total "Total time: 1m " "$out"
[[ "$out" != *"stages"* ]] && ok || bad unatt-paren "parenthetical shown unattended"
printf '{"records":[{"elapsed_seconds":40},{"elapsed_seconds":20}]}' > "$S/session-totals.json"
has att-paren "(stages 1m 0s, approx. waiting at gates" "$(run print)"
printf '{"records":[{"elapsed_seconds":9999}]}' > "$S/session-totals.json"
has clamp "approx. waiting at gates 0s)" "$(run print)"
printf 'not json' > "$S/session-totals.json"
out="$(run print)"; [[ "$out" != *"stages"* ]] && ok || bad corrupt-totals "paren shown"
rm -f "$S/session-totals.json"
out="$(run print)"; [[ "$out" != *"stages"* ]] && ok || bad missing-totals "paren shown"

# PR line
journal '{"phase":"created","url":"https://x/pr/7","number":7,"draft":false}'
has pr-created "PR: https://x/pr/7 (#7)" "$(run print)"
[[ "$(run print)" != *draft* ]] && ok || bad pr-nodraft "draft marker on non-draft"
journal '{"phase":"created","url":"https://x/pr/8","number":8,"draft":true}'
has pr-draft "PR: https://x/pr/8 (#8) [draft]" "$(run print)"
journal '{"phase":"created","url":"https://x/pr/9","number":9}'
check pr-absent-draft "PR: https://x/pr/9 (#9)" "$(run print | tail -1)"
journal '{"phase":"created","url":"https://x/p\u001b[31m\nFAKE","number":1}'
out="$(run print)"
check inject-lines 2 "$(printf '%s\n' "$out" | wc -l | tr -d ' ')"
[[ "$out" != *$'\x1b'* ]] && ok || bad inject-esc "escape char survived"
journal '{phase'
check corrupt "PR: none (journal unreadable)" "$(run print | tail -1)"
rm -f "$S/pr/journal.json"
for r in handoff-disabled:"none (handoff disabled)" no-base-commit:"none (no base commit)" \
         publication-pending:"not created (publication pending)" not-published:"none (not published)" \
         not-applicable:"none (not applicable to new-application builds)" bogus:"none (not published)"; do
    check "reason-${r%%:*}" "PR: ${r#*:}" "$(run print --reason "${r%%:*}" | tail -1)"
done
check new-app "PR: none (not applicable to new-application builds)" "$(run print --kind new | tail -1)"

# stopped: no PR line unless a PR exists
check stopped-none 1 "$(run print --stopped | wc -l | tr -d ' ')"
check stopped-new 1 "$(run print --stopped --kind new | wc -l | tr -d ' ')"
journal '{"phase":"created","url":"https://x/pr/3","number":3}'
check stopped-pr 2 "$(run print --stopped | wc -l | tr -d ' ')"

# wrapper never fails
source "$ROOT/scripts/lib/finished-extras.sh"
ROOT="$ROOT" STATE_DIR="$S" finished_extras print >/dev/null && ok || bad wrapper "nonzero"

echo "finished-extras-test: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]

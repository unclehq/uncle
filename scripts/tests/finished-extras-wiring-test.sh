#!/usr/bin/env bash
# Static wiring/order check for finished_extras call sites in both drivers.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FAIL=0
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }
need() { grep -q -- "$3" "$2" && return 0; bad "$1" "$2 missing: $3"; }
line_of() { grep -n -- "$2" "$1" | head -1 | cut -d: -f1; }
before() { # id file first second
    local a b; a="$(line_of "$2" "$3")"; b="$(line_of "$2" "$4")"
    if [[ -n "$a" && -n "$b" && "$a" -lt "$b" ]]; then return 0; fi
    bad "$1" "$2: '$3' ($a) must precede '$4' ($b)"
}

CW="$ROOT/scripts/change-workflow.sh"
SG="$ROOT/scripts/stagegate.sh"
CP="$ROOT/scripts/lib/change-pr.sh"

for d in "$CW" "$SG"; do
    need source "$d" 'finished-extras.sh'
    need start "$d" 'finished_extras start'
    need reset "$d" 'finished_extras reset'
    need noop-fallback "$d" 'declare -f finished_extras'
done
before reset-start "$CW" 'finished_extras reset' 'finished_extras start'
before reset-start-sg "$SG" 'finished_extras reset' 'finished_extras start'

# change driver: block follows change_pr_complete; stop path uses --stopped
need cw-wrapper "$CW" 'change_pr_extras_print()'
before pr-then-extras "$CW" 'change_pr_complete </dev/null || pr_rc=' 'change_pr_extras_print "$pr_rc"'
need cw-stopped "$CW" 'finished_extras print --kind change --reason "$reason" --stopped'
need cw-used "$CW" 'declare -f change_pr_extras_print >/dev/null || change_pr_extras_print "\$pr_rc"'
if grep -n 'change_pr_complete' "$CW" | grep -v 'with_extras\|change_pr_complete ||\|^[0-9]*:#' | grep -q 'change_pr_complete$'; then
    bad cw-bare "bare change_pr_complete call bypasses extras"
fi

need cw-onexit-stopped "$CW" 'run-started-at" ]]; then'
need cw-onexit-print "$CW" 'finished_extras print --kind change --reason "$(change_pr_extras_reason'

# new-app driver: Finished build line unchanged, extras after it, stop path
need sg-build "$ROOT/scripts/lib/workflow-records.sh" "Finished build: verdict=%s skipped=%s path=%s"
need sg-stop "$SG" 'finished_extras print --kind new --reason not-applicable --stopped'
before build-then-extras "$SG" 'finished_build_line "$(completed_verdict)"' 'finished_extras print --kind new --reason not-applicable \${UNATTENDED'

# reason precedence helper exists in change-pr.sh
need reason-fn "$CP" 'change_pr_extras_reason()'

[[ "$FAIL" == 0 ]] && echo "finished-extras-wiring-test: PASS" || { echo "finished-extras-wiring-test: $FAIL failure(s)" >&2; exit 1; }

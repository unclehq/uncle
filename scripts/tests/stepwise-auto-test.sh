#!/usr/bin/env bash
# stepwise_implementation_enabled (auto): a short plan is single-shot unless its ownership lets two or more steps run
# at once -- the parallel fan-out lives in the stepwise path, so a short parallel plan has to take it.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
awk '/^stepwise_implementation_enabled\(\) \{/,/^}/' "$ROOT/scripts/change-workflow.sh" > "$TMP/fn.sh"
check "function extracted" test -s "$TMP/fn.sh"
. "$ROOT/scripts/lib/plan-scope.sh"; . "$ROOT/scripts/lib/parallel-implement.sh"

enabled() {   # plan-body [env...]
    local dir; dir="$(mktemp -d -p "$TMP")"; mkdir -p "$dir/.uncle/docs" "$dir/.uncle/workflow"
    printf '# Change plan\n\n## 20. Implementation sequence\n\n%s\n' "$1" > "$dir/.uncle/docs/CHANGE_PLAN.md"; shift
    ( cd "$dir"; ROOT="$ROOT"; STATE_DIR="$PWD/.uncle/workflow"; STEPWISE_IMPLEMENT=auto
      for a in "$@"; do eval "$a"; done
      . "$TMP/fn.sh"; stepwise_implementation_enabled )
}
TWO_INDEPENDENT=$'1. First — Owns: `a.js`\n2. Second — Owns: `b.js`'
TWO_CHAIN=$'1. First — Owns: `a.js`\n2. Second — Owns: `a.js`'
UNDECLARED=$'1. First\n2. Second'
ONE=$'1. Only — Owns: `a.js`'
enabled "$TWO_INDEPENDENT";                 check "two independent steps take the stepwise path"        test "$?" == 0
enabled "$TWO_CHAIN";                       check "two steps sharing a file stay single-shot"           test "$?" == 1
enabled "$UNDECLARED";                      check "steps declaring no ownership stay single-shot"       test "$?" == 1
enabled "$ONE";                             check "a one-step plan stays single-shot"                   test "$?" == 1
enabled "$TWO_INDEPENDENT" 'touch "$STATE_DIR/parallel-implementation-serial-fallback"'
                                            check "a rejected fan-out is not retried"                   test "$?" == 1
enabled "$TWO_INDEPENDENT" 'WORKFLOW_PARALLEL_IMPLEMENT=0'
                                            check "opting out of parallel implementation stays single-shot" test "$?" == 1
enabled "$TWO_INDEPENDENT" 'STEPWISE_IMPLEMENT=0'
                                            check "an explicit 0 still wins"                            test "$?" == 1
EIGHT=""; for i in 1 2 3 4 5 6 7 8; do EIGHT+="$i. Step — Owns: \`f.js\`"$'\n'; done
enabled "$EIGHT";                           check "eight steps stay stepwise as before"                 test "$?" == 0

[[ "$fails" == 0 ]] && echo "stepwise-auto-test.sh: all checks passed" || exit 1

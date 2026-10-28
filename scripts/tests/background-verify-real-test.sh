#!/usr/bin/env bash
# The real run_green_check, run by the background wrapper in a private copy, with real commands.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
P="$TMP/project"; mkdir -p "$P/.uncle/docs" "$P/.uncle/workflow/logs" "$P/src" "$P/tests"
cd "$P"
git init -q . 2>/dev/null
printf 'ok\n' > src/a.txt
printf "// vite preview --port 4173\n" > tests/config.js
cat > .uncle/docs/UPDATED_PROJECT_PLAN.md <<'PLAN'
# Plan

## Verification commands

```sh
cat tests/config.js
mkdir -p .test-out && echo written > .test-out/proof.txt
false
```
PLAN
printf 'tests/config.js\n' > .uncle/workflow/verification.paths
python3 -B "$ROOT/scripts/lib/verification_manifest.py" .uncle/workflow/verification.paths > .uncle/workflow/verification.manifest 2>/dev/null || true
export ROOT STATE_DIR="$P/.uncle/workflow" LOG_DIR="$P/.uncle/workflow/logs" UNATTENDED=1 GREEN_CHECK=1 PROJECT_ROOT="$P"
GREEN_CMDS="$STATE_DIR/green-check.commands"; GREEN_CUR="$STATE_DIR/green-check.current.tsv"; GREEN_CLASS="$STATE_DIR/green-check.tsv"
GREEN_MD="$STATE_DIR/green-check.md"; GREEN_OVERRIDE_FILE="$STATE_DIR/green-check-override"; GREEN_LIB_DIR="$ROOT/scripts/lib"
WORKFLOW_GREEN_CHECK_REUSE=1
. "$ROOT/scripts/lib/green-check.sh"
. "$ROOT/scripts/lib/background-verify.sh"
awk '/^run_green_check\(\) \{/,/^}/' "$ROOT/scripts/stagegate.sh" > "$TMP/fn.sh"; . "$TMP/fn.sh"
check_verification_inputs() { [[ "$(python3 -B "$ROOT/scripts/lib/verification_manifest.py" "$STATE_DIR/verification.paths" 2>/dev/null)" == "$(cat "$STATE_DIR/verification.manifest")" ]]; }
parallel_groups_format_hint() { :; }
early_checklist_start() { echo started >> "$STATE_DIR/early-started"; }
record_nonblocking_failure() { printf '%s\t%s\n' "$1" "$2" >> "$STATE_DIR/nonblocking.tsv"; }
record_test_failure_disposition() { :; }
green_failed_ids() { :; }
# Scheduling metadata is optional.  A malformed declaration must not make the
# background child exit before it replaces PENDING with actual command rows.
verify_parallel_groups() { return 1; }

green_check_background_start > /dev/null
check "pending at once" green_pending
check "placeholder rows" grep -q '^PENDING' "$GREEN_CLASS"
wait "$GREEN_BG_PID" 2>/dev/null
check "published rows: the false command is the one regression" bash -c '[ "$(grep -c "^REGRESSION" "$1")" == 1 ] && grep -q "^PASS	cat tests/config.js" "$1"' _ "$GREEN_CLASS"
check "the report is the real one" grep -q 'Green check' "$GREEN_MD"
check "bad optional scheduling falls back to sequential" grep -q 'Invalid Parallel verification groups; running the verification commands in order.' "$LOG_DIR/green-background.log"
check "the log shows the moved port" grep -q -- '--port 5673' "$LOG_DIR/green-check.log"
check "the project file keeps its port" grep -q -- "--port 4173" tests/config.js
check "the protected file still matches the approved manifest" check_verification_inputs
check "output written by the commands came back" test -s .test-out/proof.txt
check "the failure is on record" grep -q '^green-check' "$STATE_DIR/nonblocking.tsv"
check "no longer pending" bash -c '! test -e "$1/green-background.pending"' _ "$STATE_DIR"
[[ "$fails" == 0 ]] && echo OK
exit "$fails"

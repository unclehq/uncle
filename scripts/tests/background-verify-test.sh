#!/usr/bin/env bash
# The verification commands run wholly in the background: the call returns at once, the result files say PENDING until the commands
# finish in a private copy, then real results replace them; a change of code cancels a run; an attended run keeps the old behaviour.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
not() { ! "$@"; }

P="$TMP/project"; mkdir -p "$P/.uncle/docs" "$P/.uncle/workflow/logs" "$P/src" "$P/node_modules/x"
cd "$P"
printf 'export const a = 1;\n' > src/a.js
printf "export default { webServer: { command: 'vite preview --port 4173' } };\n" > playwright.config.js
cat > .uncle/docs/UPDATED_PROJECT_PLAN.md <<'PLAN'
# Plan

## Verification commands

```sh
npm test
npx playwright test
```
PLAN
export ROOT STATE_DIR="$P/.uncle/workflow" LOG_DIR="$P/.uncle/workflow/logs" UNATTENDED=1 GREEN_CHECK=1
GREEN_CMDS="$STATE_DIR/green-check.commands"; GREEN_CUR="$STATE_DIR/green-check.current.tsv"; GREEN_CLASS="$STATE_DIR/green-check.tsv"
GREEN_MD="$STATE_DIR/green-check.md"; GREEN_OVERRIDE_FILE="$STATE_DIR/green-check-override"
. "$ROOT/scripts/lib/green-check.sh"
. "$ROOT/scripts/lib/background-verify.sh"
early_checklist_start() { echo started >> "$STATE_DIR/early-started"; }
record_nonblocking_failure() { printf '%s\t%s\n' "$1" "$2" >> "$STATE_DIR/nonblocking.tsv"; }
record_test_failure_disposition() { : > "$STATE_DIR/disposition"; }
run_green_check() {   # the real one, reduced: runs in whatever directory it is called from, and writes the GREEN_* files it was given
    echo "cwd=$PWD port=$(grep -o 'port [0-9]*' playwright.config.js)" > "$STATE_DIR/ran-in"
    verify_commands .uncle/docs/UPDATED_PROJECT_PLAN.md > "$GREEN_CMDS"
    sleep "${FAKE_SECONDS:-1}"
    while IFS= read -r c; do printf '%s\t%s\n' "${FAKE_CODE:-0}" "$c"; done < "$GREEN_CMDS" > "$GREEN_CUR"
    awk -F'\t' -v mode="${FAKE_CODE:-0}" '{ printf "%s\t%s\n", (mode == 0 ? "PASS" : "REGRESSION"), $2 }' "$GREEN_CUR" > "$GREEN_CLASS"
    printf '## Green check\n\nran\n' > "$GREEN_MD"
}

# attended: not in the background
UNATTENDED=0; check "attended: off" not green_background_enabled
UNATTENDED=1; check "unattended: on" green_background_enabled
WORKFLOW_BACKGROUND_VERIFY=0 check "switch off wins" not green_background_enabled
WORKFLOW_BACKGROUND_VERIFY=1; UNATTENDED=0; check "switch on wins" green_background_enabled; unset WORKFLOW_BACKGROUND_VERIFY; UNATTENDED=1

# start returns at once and leaves a placeholder no stage reads as a failure
FAKE_SECONDS=2 FAKE_CODE=1
start=$SECONDS
green_check_background_start > /dev/null
check "returns without waiting" test $((SECONDS - start)) -lt 2
check "pending" green_pending
check "placeholder rows are PENDING" grep -q '^PENDING	npm test' "$GREEN_CLASS"
check "no failures while pending" test "$(green_regressions "$GREEN_CLASS")" == 0
check "the report says so" grep -q 'running in the background' "$GREEN_MD"

# Evidence consumers may wait once for the published result.  A failed command
# is still final evidence; only PENDING is prohibited.
green_wait_final > /dev/null
check "wait helper publishes final evidence" not grep -q '^PENDING' "$GREEN_CLASS"
check "wait helper accepts final regression evidence" grep -q '^REGRESSION' "$GREEN_CLASS"

# finish: real results replace the placeholder, in a copy with the port moved, and failures are recorded
check "not pending any more" not green_pending
check "real rows replace the placeholder" grep -q '^REGRESSION	npm test' "$GREEN_CLASS"
check "the failures are counted" test "$(green_regressions "$GREEN_CLASS")" == 2
check "it ran in the private copy" grep -q "cwd=.*green-background/project" "$STATE_DIR/ran-in"
check "with the port moved" grep -q "port 5673" "$STATE_DIR/ran-in"
check "the project's own config is untouched" grep -q "port 4173" playwright.config.js
check "failures recorded for the audit" grep -q '^green-check' "$STATE_DIR/nonblocking.tsv"
check "and the override file written" test -s "$GREEN_OVERRIDE_FILE"
check "the real commands file was published" grep -q 'npx playwright test' "$GREEN_CMDS"

check "the early checklist is started from the foreground" test -s "$STATE_DIR/early-started"

# a clean run records nothing and remembers the tree
rm -f "$STATE_DIR/nonblocking.tsv" "$GREEN_OVERRIDE_FILE"; FAKE_CODE=0 FAKE_SECONDS=1
green_check_background_start > /dev/null; wait "$GREEN_BG_PID" 2>/dev/null
check "clean: all PASS" grep -q '^PASS	npm test' "$GREEN_CLASS"
check "clean: nothing recorded" not test -e "$STATE_DIR/nonblocking.tsv"
check "clean: fingerprint remembered" grep -q ' clean$' "$STATE_DIR/green-check.fingerprint"
out="$(run_green_check_auto)"; check "same tree: reused, not run again" bash -c 'grep -q "reusing" <<< "$1"' _ "$out"

# a second start while running cancels the first (the code changed)
FAKE_SECONDS=30 FAKE_CODE=0
green_check_background_start > /dev/null; first="$GREEN_BG_PID"; sleep 0.5
printf 'export const a = 2;\n' > src/a.js
FAKE_SECONDS=1; green_check_background_start > /dev/null
check "the first run is gone" not kill -0 "$first" 2>/dev/null
wait "$GREEN_BG_PID" 2>/dev/null
check "the second one published" grep -q '^PASS' "$GREEN_CLASS"

# the same tree while running is not started twice
FAKE_SECONDS=5; green_check_background_start > /dev/null; running="$GREEN_BG_PID"
out="$(run_green_check_auto)"
check "already running: not started again" bash -c 'grep -q "already running" <<< "$1"' _ "$out"
check "same process" test "$GREEN_BG_PID" == "$running"
green_background_cancel
check "cancel clears the mark" not test -e "$STATE_DIR/green-background.pending"

# a placeholder left by a driver that died is removed at the next start
GREEN_BG_PID=""; : > "$STATE_DIR/green-background.pending"; printf 'PENDING\tnpm test\n' > "$GREEN_CLASS"
green_background_recover > /dev/null
check "stale placeholder removed" not test -e "$GREEN_CLASS"

# gated by the same stage code: the call sites use the wrapper, and the review is not bounced while pending
check "no foreground call site left" bash -c '! grep -n "run_green_check || true" "$1"' _ "$ROOT/scripts/stagegate.sh"
check "the pending branch precedes the evidence routes" bash -c 'a=$(grep -n "if green_pending; then" "$1" | head -1 | cut -d: -f1); b=$(grep -n "test-evidence-handoff-attempted\" \]\] && \[\[" "$1" | head -1 | cut -d: -f1); [ -n "$a" ] && [ "$a" -lt "$b" ]' _ "$ROOT/scripts/stagegate.sh"

[[ "$fails" == 0 ]] && echo OK
exit "$fails"

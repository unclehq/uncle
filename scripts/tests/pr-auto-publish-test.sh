#!/usr/bin/env bash
# Unattended (auto) mode publishes without a dialog; attended routing is unchanged.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILED=0; COUNT=0
check() { COUNT=$((COUNT+1)); [[ "$2" == "$3" ]] || { FAILED=$((FAILED+1)); echo "FAIL: $1: expected [$2] got [$3]"; }; }

. "$HERE/../lib/change-pr.sh"
LOG="$TMP/calls"
change_pr_publish() { printf 'publish interactive=%s auto=%s\n' "$1" "${UNCLE_AUTO_PUBLISH:-0}" >> "$LOG"; }
change_pr_engine() { printf 'engine %s\n' "$1" >> "$LOG"; return 1; }
ORIGIN_FILE="$TMP/origin"; printf 'unclehq/uncle\t107\tgh\n' > "$ORIGIN_FILE"
UNATTENDED_FILE="$TMP/unattended"; : > "$UNATTENDED_FILE"
VERDICT_FILE="$TMP/verdict"

run() { : > "$LOG"; ( CLOSE_ISSUE="$1" UNATTENDED="$2"; export UNCLE_STATUS_FILE="${3:-}"; change_pr_complete </dev/null >/dev/null 2>&1 ); cat "$LOG"; }

check "unattended, with a person channel, publishes with no dialog" "publish interactive=0 auto=1" "$(run 1 1 "$TMP/status")"
check "unattended, headless, publishes with no dialog" "publish interactive=0 auto=1" "$(run 1 1)"
check "attended, interactive, is not auto" "publish interactive=1 auto=0" "$(run 1 0 "$TMP/status")"
check "PR handoff disabled does not publish unattended" "engine completed-signing-resume" "$(run 0 1)"

if [[ "$FAILED" -ne 0 ]]; then echo "pr-auto-publish-test.sh: $FAILED of $COUNT checks failed"; exit 1; fi
echo "pr-auto-publish-test.sh: $COUNT checks passed"

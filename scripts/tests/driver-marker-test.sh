#!/usr/bin/env bash
# I-2: the launcher refuses to start a build from the home agent's process tree
# unless the app-issued marker is present and valid. Refusals happen before any
# driver or agent starts; the accept case is shown by reaching a later refusal
# (--attended with --unattended) instead of the marker error.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fail=0
check() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1 (got '$2', want '$3')"; fail=1; fi; }
run() { (cd "$TMP" && env -u UNCLE_APP_MARKER -u UNCLE_APP_MARKER_FILE -u UNCLE_NOUI UNCLE_SKIP_UPGRADE=1 "$@" 2>&1 </dev/null); }
printf 'tok123' > "$TMP/marker"; chmod 600 "$TMP/marker"
printf 'other' > "$TMP/bad"
MSG='app-issued marker'

out="$(run env UNCLE_HOME_AGENT=1 "$ROOT/uncle" --application hi --attended --unattended)"
check "absent marker refused" "$(grep -c "$MSG" <<<"$out")" 1
out="$(run env UNCLE_HOME_AGENT=1 bash -c "\"$ROOT/uncle\" --application hi --attended --unattended")"
check "refused via bash -c" "$(grep -c "$MSG" <<<"$out")" 1
out="$(run env UNCLE_HOME_AGENT=1 bash "$ROOT/uncle" --issue 5 --attended --unattended)"
check "refused via wrapper/--issue" "$(grep -c "$MSG" <<<"$out")" 1
out="$(run env UNCLE_HOME_AGENT=1 UNCLE_APP_MARKER=tok123 UNCLE_APP_MARKER_FILE="$TMP/bad" "$ROOT/uncle" --application hi --attended --unattended)"
check "wrong token refused" "$(grep -c "$MSG" <<<"$out")" 1
out="$(run env UNCLE_HOME_AGENT=1 UNCLE_APP_MARKER=tok123 UNCLE_APP_MARKER_FILE="$TMP/marker" "$ROOT/uncle" --application hi --attended --unattended)"
check "valid marker passes the check" "$(grep -c "$MSG" <<<"$out")" 0
out="$(run "$ROOT/uncle" --application hi --attended --unattended)"
check "human CLI (no agent env) passes the check" "$(grep -c "$MSG" <<<"$out")" 0
exit "$fail"

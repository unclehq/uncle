#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/project/.uncle"
printf 'requirements.runner codex\n' > "$TMP/project/.uncle/config"
(cd "$TMP/project"; printf 'q\n' | UNCLE_CONFIG="$TMP/project/.uncle/config" bash "$ROOT/uncle") > "$TMP/output" 2>&1
grep -q 'New application' "$TMP/output"
grep -q 'Change request' "$TMP/output"
if grep -q 'command not found' "$TMP/output"; then
    cat "$TMP/output"
    exit 1
fi
[[ "$(cat "$TMP/project/.uncle/config")" == 'requirements.runner codex' ]]
echo 'shell-menu-startup-test: passed'

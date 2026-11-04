#!/usr/bin/env bash
# Regression: change-workflow.sh must keep the launcher's resolved unattended mode
# (UNCLE_UNATTENDED=1, UNCLE_MODE_RESOLVED=1) instead of resetting it to 0 and
# refusing without a TTY.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
cd "$T" && git init -q && git commit -q --allow-empty -m init
out="$(UNCLE_PROJECT_ROOT="$T" UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=1 timeout 30 bash "$ROOT/scripts/change-workflow.sh" </dev/null 2>&1)"
case "$out" in
  *"attended mode needs an interactive terminal"*) echo "FAIL inherited unattended mode was refused"; exit 1 ;;
  *"Mode: unattended"*) echo "ok inherited unattended mode kept" ;;
  *) echo "FAIL unexpected output: $out"; exit 1 ;;
esac

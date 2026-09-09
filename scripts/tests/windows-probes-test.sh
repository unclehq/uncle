#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin" "$work/project"
printf '#!/bin/sh\nexit 49\n' > "$work/bin/python3"
chmod +x "$work/bin/python3"
cd "$work/project"
printf 'x\n' > fixture
printf 'fixture\n' > scopes
# A Store-style executable alias must select the shell manifest fallback.
PATH="$work/bin:$PATH" bash -c '. "$1/scripts/lib/verification-integrity.sh"; verification_manifest scopes' _ "$ROOT" > actual
bash -c '. "$1/scripts/lib/verification-integrity.sh"; WORKFLOW_HASH_BACKEND=shell verification_manifest scopes' _ "$ROOT" > expected
cmp actual expected
# Unavailable process inspection must refuse installation, not report idle.
. "$ROOT/scripts/lib/running-workflow.sh"
ps() { return 2; }
running_workflow_report 2> error
grep -q 'Cannot determine' error
unset -f ps
# The Windows branch consumes native command lines and strips CRLF.
powershell.exe() { printf '123\r\n'; }
OSTYPE=msys running_workflow_pids > ids
[[ "$(tr -d '[:space:]' < ids)" == 123 ]]
powershell.exe() { return 2; }
if OSTYPE=msys running_workflow_pids > /dev/null; then exit 1; fi
OSTYPE=msys running_workflow_report 2> error
grep -q 'refusing' error
echo 'windows-probes-test: Store alias fallback and fail-closed process checks passed'

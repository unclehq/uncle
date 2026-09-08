#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/workflow-directory.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
workflow_directory_migrate "$tmp"
[[ ! -e "$tmp/.uncle" ]]
mkdir -p "$tmp/.uncle/workspace/approvals"
printf '42:IMPLEMENT\n' > "$tmp/.uncle/workspace/state"
printf 'approved\n' > "$tmp/.uncle/workspace/approvals/plan"
mkdir "$tmp/.uncle/workspace/lock"
printf '%s\n' "$$" > "$tmp/.uncle/workspace/lock/pid"
if workflow_directory_migrate "$tmp" 2>/dev/null; then exit 1; fi
[[ -f "$tmp/.uncle/workspace/state" ]]
rm -rf "$tmp/.uncle/workspace/lock"
workflow_directory_migrate "$tmp"
[[ ! -e "$tmp/.uncle/workspace" ]]
[[ "$(cat "$tmp/.uncle/workflow/state")" == '42:IMPLEMENT' ]]
[[ "$(cat "$tmp/.uncle/workflow/approvals/plan")" == approved ]]
workflow_directory_migrate "$tmp"
mkdir "$tmp/.uncle/workspace"
printf 'old\n' > "$tmp/.uncle/workspace/state"
if workflow_directory_migrate "$tmp" 2>/dev/null; then exit 1; fi
[[ "$(cat "$tmp/.uncle/workflow/state")" == '42:IMPLEMENT' ]]
[[ "$(cat "$tmp/.uncle/workspace/state")" == old ]]
echo 'workflow-directory-test: passed'

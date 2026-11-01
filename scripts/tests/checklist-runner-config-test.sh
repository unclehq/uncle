#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/stage-config.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export UNCLE_CONFIG="$TMP/config"
for runner in codex claude kimi self-hosted; do
    printf 'manual-checklist.runner %s\nmanual-checklist.model local/test\nmanual-checklist.effort high\nmanual-checklist.network true\n' "$runner" > "$UNCLE_CONFIG"
    for stage in manual-checklist-base manual-checklist-delta; do
        [[ "$(uncle_stage_side "$stage")" == reviewer ]]
        [[ "$(uncle_stage_cmd "$stage")" == "$(uncle_stage_cmd manual-checklist)" ]]
        [[ "$(uncle_stage_model "$stage")" == "$(uncle_stage_model manual-checklist)" ]]
        [[ "$(uncle_stage_effort "$stage")" == high ]]
        [[ "$(uncle_stage_network "$stage")" == true ]]
    done
done
for runner in codex claude kimi self-hosted; do
    printf 'execute-checklist.runner %s\nexecute-checklist.model local/test\nexecute-checklist.effort high\nexecute-checklist.network true\n' "$runner" > "$UNCLE_CONFIG"
    for stage in execute-checklist-worker-MC-001 implementation-worker-2; do
        parent="${stage%%-worker-*}"
        [[ "$(uncle_stage_side "$stage")" == "$(uncle_stage_side "$parent")" ]]
        [[ "$(uncle_stage_cmd "$stage")" == "$(uncle_stage_cmd "$parent")" ]]
        [[ "$(uncle_stage_model "$stage")" == "$(uncle_stage_model "$parent")" ]]
        [[ "$(uncle_stage_effort "$stage")" == "$(uncle_stage_effort "$parent")" ]]
        [[ "$(uncle_stage_network "$stage")" == "$(uncle_stage_network "$parent")" ]]
    done
done
# Removed runner: saved cline fails loudly, never falls back.
printf 'manual-checklist.runner cline\nmanual-checklist.billing clinepass\n' > "$UNCLE_CONFIG"
if out="$(uncle_runner_cmd cline agent 2>&1)"; then echo 'cline runner must fail' >&2; exit 1; fi
[[ "$out" == *"Cline support was removed"* && "$out" == *claude* ]]
if out="$(uncle_runner_cmd zzz agent 2>&1)"; then echo 'unknown runner must fail' >&2; exit 1; fi
[[ "$out" == "uncle: runner 'zzz' is not supported (Cline support was removed). Set it to claude, codex, kimi or self-hosted with 'uncle' -> Configure." ]]
# D7: control characters (ESC, newline) are stripped from the echoed value.
if out="$(uncle_runner_cmd $'ab\033[31m\ncd' agent 2>&1)"; then echo 'control-char runner must fail' >&2; exit 1; fi
[[ "$out" == "uncle: runner 'ab[31mcd' is not supported (Cline support was removed). Set it to claude, codex, kimi or self-hosted with 'uncle' -> Configure." ]]
# Stale billing line and removed env vars do not change resolution.
printf 'manual-checklist.runner claude\nmanual-checklist.billing clinepass\n' > "$UNCLE_CONFIG"
base="$(uncle_stage_cmd manual-checklist)"
ROOT="$ROOT" WORKFLOW_CLINE_CMD=/bin/false UNCLE_CLINE_MODEL=x UNCLE_CLINE_EFFORT=high CLINE_CONFIG=/nope \
    bash -c '. "$1/scripts/lib/stage-config.sh"; [[ "$(uncle_stage_cmd manual-checklist)" == "$2" ]]' _ "$ROOT" "$base"
echo 'checklist-runner-config-test: passed'

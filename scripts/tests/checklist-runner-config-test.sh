#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/stage-config.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export UNCLE_CONFIG="$TMP/config"
for runner in codex cline claude kimi self-hosted; do
    printf 'manual-checklist.runner %s\nmanual-checklist.model local/test\nmanual-checklist.effort high\nmanual-checklist.network true\n' "$runner" > "$UNCLE_CONFIG"
    for stage in manual-checklist-base manual-checklist-delta; do
        [[ "$(uncle_stage_side "$stage")" == reviewer ]]
        [[ "$(uncle_stage_cmd "$stage")" == "$(uncle_stage_cmd manual-checklist)" ]]
        [[ "$(uncle_stage_model "$stage")" == "$(uncle_stage_model manual-checklist)" ]]
        [[ "$(uncle_stage_effort "$stage")" == high ]]
        [[ "$(uncle_stage_network "$stage")" == true ]]
    done
done
for runner in codex cline claude kimi self-hosted; do
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
echo 'checklist-runner-config-test: passed'

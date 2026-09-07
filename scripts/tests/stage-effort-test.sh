#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/stage-config.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
UNCLE_CONFIG="$work/config"
for stage in requirements baseline change-spec project-plan change-plan adversarial-review updated-plan updated-change-plan preflight implementation test-review manual-checklist execute-checklist final-audit; do
    rm -f "$UNCLE_CONFIG"
    [[ "$(uncle_effective_stage_effort "$stage")" == medium ]]
    printf 'effort low\n' > "$UNCLE_CONFIG"
    [[ "$(uncle_effective_stage_effort "$stage")" == low ]]
    printf '%s.effort high\n' "$stage" >> "$UNCLE_CONFIG"
    [[ "$(uncle_effective_stage_effort "$stage")" == high ]]
    var="WORKFLOW_EFFORT_$(printf '%s' "$stage" | tr '[:lower:]-' '[:upper:]_')"
    export "$var=medium"
    [[ "$(uncle_effective_stage_effort "$stage")" == medium ]]
    unset "$var"
done
printf 'implementation.effort low\n' > "$UNCLE_CONFIG"
[[ "$(uncle_effective_stage_effort implementation-step-2)" == low ]]
echo 'stage-effort-test.sh: all stages resolve defaults, legacy config, stage config, and environment overrides correctly'

#!/usr/bin/env bash
# codex's workspace-write sandbox denies loopback binds, so a stage that has to
# serve the product it verifies needs network access turned on deliberately.
# Default off: the boundary is the point.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/stage-config.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
UNCLE_CONFIG="$work/config"

# Absent config, absent key, and an explicit false all mean no network.
for stage in requirements preflight implementation execute-checklist final-audit; do
    rm -f "$UNCLE_CONFIG"
    [[ "$(uncle_stage_network "$stage")" == false ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
    printf 'other-stage.network true\n' > "$UNCLE_CONFIG"
    [[ "$(uncle_stage_network "$stage")" == false ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
    printf '%s.network false\n' "$stage" > "$UNCLE_CONFIG"
    [[ "$(uncle_stage_network "$stage")" == false ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
done

# Every spelling an operator is likely to write.
for value in true TRUE yes on 1; do
    printf 'execute-checklist.network %s\n' "$value" > "$UNCLE_CONFIG"
    [[ "$(uncle_stage_network execute-checklist)" == true ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
done

# Anything unrecognized stays off rather than guessing in the risky direction.
for value in maybe '' 0 no off; do
    printf 'execute-checklist.network %s\n' "$value" > "$UNCLE_CONFIG"
    [[ "$(uncle_stage_network execute-checklist)" == false ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
done

# A global key is the fallback, a stage key wins over it.
printf 'network true\n' > "$UNCLE_CONFIG"
[[ "$(uncle_stage_network implementation)" == true ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
printf 'implementation.network false\nnetwork true\n' > "$UNCLE_CONFIG"
[[ "$(uncle_stage_network implementation)" == false ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }

# Step variants inherit the parent stage's setting.
printf 'implementation.network true\n' > "$UNCLE_CONFIG"
[[ "$(uncle_stage_network implementation-step-3)" == true ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }

echo 'stage-network-test.sh: network defaults off, honors stage and global keys, and inherits to step variants'

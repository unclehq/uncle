#!/usr/bin/env bash
set -euo pipefail

# parallel_implement_enabled — the standing off switch for whole-project
# parallel implementation, requested after a plan's ownership declarations
# kept costing more (a stopped run, a manual plan edit) than the parallelism
# ever saved. WORKFLOW_PARALLEL_IMPLEMENT always wins when set; otherwise
# .uncle/config's `misc.parallel_implement` is a durable per-project choice.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/parallel-implement.sh"

FAILED=0
COUNT=0
check() {
    local name="$1" expect="$2"
    COUNT=$((COUNT + 1))
    local got=0
    parallel_implement_enabled || got=1
    if [[ "$got" != "$expect" ]]; then
        echo "FAIL: $name — expected enabled=$([[ $expect == 0 ]] && echo yes || echo no), got $([[ $got == 0 ]] && echo yes || echo no)" >&2
        FAILED=1
    fi
}

unset WORKFLOW_PARALLEL_IMPLEMENT 2>/dev/null || true
check "default (no env, no config function): enabled" 0

# stage-config.sh not sourced yet: uncle_config_get must not be assumed to
# exist. This mirrors stagegate.sh's real sourcing order, where
# parallel-implement.sh loads before stage-config.sh.
if declare -f uncle_config_get > /dev/null; then
    echo "FAIL: test setup — uncle_config_get should not be defined yet" >&2
    exit 1
fi

WORKFLOW_PARALLEL_IMPLEMENT=0 bash -c '. "'"$ROOT"'/scripts/lib/parallel-implement.sh"; parallel_implement_enabled' \
    && { echo "FAIL: WORKFLOW_PARALLEL_IMPLEMENT=0 must disable it" >&2; FAILED=1; }
COUNT=$((COUNT + 1))

WORKFLOW_PARALLEL_IMPLEMENT=1 bash -c '. "'"$ROOT"'/scripts/lib/parallel-implement.sh"; parallel_implement_enabled' \
    || { echo "FAIL: WORKFLOW_PARALLEL_IMPLEMENT=1 must enable it" >&2; FAILED=1; }
COUNT=$((COUNT + 1))

# Now bring in the config-reading function, as stagegate.sh does later in
# its own sourcing order, and prove the saved-config path.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
UNCLE_CONFIG="$TMP/config"
export UNCLE_CONFIG
. "$ROOT/scripts/lib/stage-config.sh"

printf 'misc.parallel_implement false\n' > "$UNCLE_CONFIG"
check "misc.parallel_implement false: disabled" 1

printf 'misc.parallel_implement true\n' > "$UNCLE_CONFIG"
check "misc.parallel_implement true: enabled" 0

: > "$UNCLE_CONFIG"
check "no config key at all: enabled (the existing default)" 0

# The environment variable is the escape hatch for a single run and must
# still win even when the saved config disagrees.
printf 'misc.parallel_implement false\n' > "$UNCLE_CONFIG"
WORKFLOW_PARALLEL_IMPLEMENT=1 check "env overrides a disabling config" 0

if [[ "$FAILED" -ne 0 ]]; then
    echo "parallel-implement-test.sh: $COUNT checks, some failed"
    exit 1
fi
echo "parallel-implement-test.sh: $COUNT checks passed"

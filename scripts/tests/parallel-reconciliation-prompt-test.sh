#!/usr/bin/env bash
set -euo pipefail

# Reconciliation steps run in isolated worktrees. They must not repeat the
# driver-owned full suite or write reports that cannot be adopted by the real
# project tree. Both workflow drivers build these prompts independently.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

for driver in scripts/stagegate.sh scripts/change-workflow.sh; do
    text="$(<"$ROOT/$driver")"
    [[ "$text" == *'Reconciliation execution boundary (binding)'* ]] || {
        echo "missing reconciliation boundary in $driver" >&2; exit 1;
    }
    [[ "$text" == *'driver alone runs the approved `Verification commands` block'* || "$text" == *'driver runs that block once after merged implementation'* || "$text" == *'driver runs'$'\n''that block once after merged implementation'* ]] || {
        echo "missing driver-owned verification rule in $driver" >&2; exit 1;
    }
    [[ "$text" == *'isolated worktree: it is not the canonical project tree'* || "$text" == *'driver cannot adopt reports created in a worker worktree'* ]] || {
        echo "missing isolated-report rule in $driver" >&2; exit 1;
    }
done

echo 'parallel-reconciliation-prompt-test.sh: reconciliation steps avoid duplicate full verification'

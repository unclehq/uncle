#!/usr/bin/env bash
set -euo pipefail
if [[ -n "${UNCLE_RUNTIME_ROOT:-}" && -d "$UNCLE_RUNTIME_ROOT/scripts" ]]; then
    ROOT="$(cd -L "$UNCLE_RUNTIME_ROOT" && pwd -L)"
else
    ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
exec python3 "$ROOT/scripts/lib/self_hosted.py" agent "$@"

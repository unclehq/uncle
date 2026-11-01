#!/usr/bin/env bash
# Every Python and shell suite in one pool, longest first. See scripts/lib/all_suites.py.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec python3 -B "$ROOT/scripts/lib/all_suites.py" "$@"

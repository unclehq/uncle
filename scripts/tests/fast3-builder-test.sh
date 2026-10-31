#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
python3 -I "$ROOT/scripts/tests/fast3-builder-test.py"

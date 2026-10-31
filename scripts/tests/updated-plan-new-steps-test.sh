#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -I "$ROOT/scripts/tests/updated-plan-new-steps-test.py"
python3 -I "$ROOT/scripts/tests/updated-plan-schema-order-test.py"

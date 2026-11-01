#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -I scripts/tests/schema-scope-unit-test.py

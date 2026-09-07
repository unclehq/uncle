#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/repair-limit.sh"
STATE_DIR="$(mktemp -d)"
trap 'rm -rf "$STATE_DIR"' EXIT
printf 'TEST_REVIEW.md\n' > "$STATE_DIR/repair-source"
gate_prompt() { printf '%s' "$1"; }
MAX_REPAIRS=2
ensure_repair_capacity 1 </dev/null
if ensure_repair_capacity 2 </dev/null; then exit 1; fi
[[ ! -e "$STATE_DIR/repair-limit" ]]
if ensure_repair_capacity 2 <<<'stop'; then exit 1; fi
ensure_repair_capacity 2 <<<'invalid
2
101
003'
[[ "$MAX_REPAIRS" == 3 && "$(cat "$STATE_DIR/repair-limit")" == 3 ]]
MAX_REPAIRS=2
ensure_repair_capacity 2 </dev/null
[[ "$MAX_REPAIRS" == 3 ]]
if ensure_repair_capacity 3 <<<'stop'; then exit 1; fi
MAX_REPAIRS=100
if ensure_repair_capacity 100 <<<'101'; then exit 1; fi
printf 'corrupt\n' > "$STATE_DIR/repair-limit"
if ensure_repair_capacity 2 </dev/null; then exit 1; fi
echo 'repair-limit-test.sh: approval, decline, EOF, validation, resume, and ceiling passed'

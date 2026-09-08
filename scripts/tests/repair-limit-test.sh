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
[[ ! -e "$STATE_DIR/repair-limit" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
if ensure_repair_capacity 2 <<<'stop'; then exit 1; fi
ensure_repair_capacity 2 <<<'invalid
2
101
003'
[[ "$MAX_REPAIRS" == 3 && "$(cat "$STATE_DIR/repair-limit")" == 3 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
MAX_REPAIRS=2
ensure_repair_capacity 2 </dev/null
[[ "$MAX_REPAIRS" == 3 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
if ensure_repair_capacity 3 <<<'stop'; then exit 1; fi
MAX_REPAIRS=100
if ensure_repair_capacity 100 <<<'101'; then exit 1; fi

# "+N" is how an operator who has just been stopped counts: N more attempts
# from here, not a new total. Reading "+3" as the total 3 would reject the
# answer of someone who meant to continue.
rm -f "$STATE_DIR/repair-limit"
MAX_REPAIRS=2
ensure_repair_capacity 2 <<<'+3'
[[ "$MAX_REPAIRS" == 5 && "$(cat "$STATE_DIR/repair-limit")" == 5 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }

# The same answer as an absolute total is still read as a total.
rm -f "$STATE_DIR/repair-limit"
MAX_REPAIRS=2
ensure_repair_capacity 2 <<<'3'
[[ "$MAX_REPAIRS" == 3 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }

# A relative bump that would clear the ceiling is refused, not clamped: the
# operator asked for something the run cannot give.
rm -f "$STATE_DIR/repair-limit"
MAX_REPAIRS=2
if ensure_repair_capacity 99 <<<'+5'; then exit 1; fi
[[ ! -e "$STATE_DIR/repair-limit" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }

# "+0" grants nothing, so it is a decline rather than a silent no-op that
# leaves the driver thinking it may repair again.
rm -f "$STATE_DIR/repair-limit"
MAX_REPAIRS=2
if ensure_repair_capacity 2 <<<'+0'; then exit 1; fi

# Junk after the plus is junk.
rm -f "$STATE_DIR/repair-limit"
MAX_REPAIRS=2
if ensure_repair_capacity 2 <<<'+abc'; then exit 1; fi

printf 'corrupt\n' > "$STATE_DIR/repair-limit"
if ensure_repair_capacity 2 </dev/null; then exit 1; fi
echo 'repair-limit-test.sh: approval, decline, EOF, validation, relative bumps, resume, and ceiling passed'

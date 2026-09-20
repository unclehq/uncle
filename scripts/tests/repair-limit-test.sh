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

# Unattended: extends to the standing ceiling and continues, without ever
# calling gate_read. A pipe stdin never closes under the TUI, so a check
# that only escaped on EOF would have hung here instead of failing over.
# Auto mode means a human gate does not block progress -- stopping a repair
# loop pending a human who is not coming was exactly that kind of block.
rm -f "$STATE_DIR/repair-limit"
MAX_REPAIRS=2
gate_read() { echo "FAIL: gate_read must not be called when unattended" >&2; exit 1; }
UNCLE_UNATTENDED=1
ensure_repair_capacity 2 </dev/null \
    || { echo "FAIL: unattended must extend and continue, not stop" >&2; exit 1; }
[[ "$MAX_REPAIRS" == 100 ]] || { echo "FAIL: unattended must extend to the standing ceiling of 100, got $MAX_REPAIRS" >&2; exit 1; }
[[ "$(cat "$STATE_DIR/repair-limit")" == 100 ]] || { echo "FAIL: extended limit must be persisted" >&2; exit 1; }
unset UNCLE_UNATTENDED

# The absolute ceiling still stops even unattended: a true runaway (already
# at 100) must not be extended further just because nobody is watching.
rm -f "$STATE_DIR/repair-limit"
MAX_REPAIRS=2
UNCLE_UNATTENDED=1
if ensure_repair_capacity 100 </dev/null; then
    echo "FAIL: the absolute ceiling must still stop the run, even unattended" >&2
    exit 1
fi
unset UNCLE_UNATTENDED

echo 'repair-limit-test.sh: approval, decline, EOF, validation, relative bumps, resume, ceiling, and unattended passed'

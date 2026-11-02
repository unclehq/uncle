#!/usr/bin/env bash
# The per-run Python host (scripts/lib/pyhost.py, pyhost.sh): a served call must be indistinguishable from a plain `python3` call, and a
# host that is missing, killed, refusing or slow must never change an answer. Helpers live in a throwaway install root so the host's
# rule "only a helper under ROOT/scripts/lib" is exercised for real.
set -uo pipefail
unset UNCLE_PY_HOST      # this suite tests the host itself; a run that switches it off for the others must not switch it off here
REAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'kill "${HOST_PID:-0}" 2>/dev/null; rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); }
FAILED_CHECKS=""
bad() { FAIL=$((FAIL + 1)); FAILED_CHECKS="$FAILED_CHECKS
FAIL [$1] $2"; }

ROOT="$TMP/install"; mkdir -p "$ROOT/scripts/lib" "$TMP/work"
cp "$REAL_ROOT/scripts/lib/pyhost.py" "$REAL_ROOT/scripts/lib/pyhost.sh" "$ROOT/scripts/lib/"
cat > "$ROOT/scripts/lib/echo_call.py" <<'PY'
import os, sys
print('argv', sys.argv[1:], 'cwd', os.getcwd(), 'foo', os.environ.get('FOO'), 'name', __name__, 'file', os.path.basename(__file__))
print('to stderr', file=sys.stderr)
sys.exit(int(os.environ.get('EXIT_CODE', '0')))
PY
cat > "$ROOT/scripts/lib/exit_true.py" <<'PY'
import sys
sys.exit(True)
PY
cat > "$ROOT/scripts/lib/exit_false.py" <<'PY'
import sys
sys.exit(False)
PY
cat > "$ROOT/scripts/lib/exit_text.py" <<'PY'
import sys
sys.exit('stopped because of a message')
PY
cat > "$ROOT/scripts/lib/boom.py" <<'PY'
raise ValueError('boom')
PY
cat > "$ROOT/scripts/lib/reads_input.py" <<'PY'
import sys
print('stdin said', sys.stdin.read().strip())
PY
cat > "$ROOT/scripts/lib/append_once.py" <<'PY'
import sys
with open(sys.argv[1], 'a') as out: out.write('x\n')
PY
cat > "$ROOT/scripts/lib/big.py" <<'PY'
import sys
sys.stdout.write('line of output\n' * 80000)
PY
cat > "$ROOT/scripts/lib/slow.py" <<'PY'
import time
time.sleep(1.5)
print('slow done')
PY
printf 'print("not a helper")\n' > "$TMP/work/elsewhere.py"
cat > "$ROOT/scripts/lib/whoami_parent.py" <<'PY'
import os
print(os.getppid())
PY
cat > "$ROOT/scripts/lib/reviewer_output.py" <<'PY'
import os, sys                                   # mentions stdin on purpose: the scan refuses it unless --from names the input
print('reviewer parent', os.getppid(), 'reads stdin' if '--from' not in sys.argv else 'reads a file')
PY
cat > "$ROOT/scripts/lib/writer_deadline.py" <<'PY'
import os, signal, sys                           # uses signal. on purpose, as the real helper does: only `stop` is served
def stop(pid): os.kill(pid, signal.SIGKILL)
print('deadline', sys.argv[1], 'parent', os.getppid())
PY
cat > "$ROOT/scripts/lib/build_timing.py" <<'PY'
import os, sys, threading
threading.Thread(target=lambda: None, daemon=True)     # the word the static scan refuses on
print('sub', sys.argv[1], 'parent', os.getppid())
PY

export ROOT
. "$ROOT/scripts/lib/pyhost.sh"
cd "$TMP/work"

# Reference answers come from the real interpreter, through the same function with the host not started.
want() { ( unset UNCLE_PY_HOST_DIR; command python3 "$@" ) ; }
same() {  # name args...: stdout, stderr and status must equal the real interpreter's
    local name="$1"; shift
    local wo we wr go ge gr
    wo="$(want "$@" 2>"$TMP/we")"; wr=$?; we="$(cat "$TMP/we")"
    go="$(python3 "$@" 2>"$TMP/ge")"; gr=$?; ge="$(cat "$TMP/ge")"
    if [[ "$wo" == "$go" && "$we" == "$ge" && "$wr" == "$gr" ]]; then ok; else
        bad "$name" "real=[$wo|$we|$wr] host=[$go|$ge|$gr]"; fi
}

# Before the host exists everything runs the real interpreter, correctly.
same no-host-yet "$ROOT/scripts/lib/echo_call.py" a b

uncle_py_host_start
for _ in $(seq 1 100); do [[ -e "$UNCLE_PY_HOST_DIR/ready" ]] && break; sleep 0.05; done
[[ -e "$UNCLE_PY_HOST_DIR/ready" ]] && ok || bad host-ready "the host did not come up"
HOST_PID="$(pgrep -f "pyhost.py serve $UNCLE_PY_HOST_DIR" | head -1)"

export FOO="from-the-driver"
# A served call really is served: its parent is the host, not this shell.
[[ "$(python3 "$ROOT/scripts/lib/whoami_parent.py")" == "$HOST_PID" ]] && ok || bad served-by-host "parent was $(python3 "$ROOT/scripts/lib/whoami_parent.py"), host is $HOST_PID"
# build_timing.py is refused by the scan (a daemon thread) but its one-shot subcommands are served; others are not.
[[ "$(python3 "$ROOT/scripts/lib/build_timing.py" stage X)" == "sub stage parent $HOST_PID" ]] && ok || bad subcommand-served "stage was not served by the host"
[[ "$(python3 "$ROOT/scripts/lib/build_timing.py" report .)" == "sub report parent $HOST_PID" ]] && ok || bad subcommand-report "report was not served by the host"
[[ "$(python3 "$ROOT/scripts/lib/build_timing.py" run)" != *"parent $HOST_PID" ]] && ok || bad subcommand-refused "run must not be served by the host"
# Conditional rules: reviewer_output.py only with --from; writer_deadline.py only for `stop`.
[[ "$(python3 "$ROOT/scripts/lib/reviewer_output.py" --from x.md claude)" == "reviewer parent $HOST_PID reads a file" ]] && ok || bad reviewer-from-served "--from was not served by the host"
[[ "$(python3 "$ROOT/scripts/lib/reviewer_output.py" claude < /dev/null)" == "reviewer parent $HOST_PID"* ]] && bad reviewer-stdin-refused "a stdin call was served by the host" || ok
[[ "$(python3 "$ROOT/scripts/lib/writer_deadline.py" stop 12345)" == "deadline stop parent $HOST_PID" ]] && ok || bad deadline-stop-served "stop was not served by the host"
[[ "$(python3 "$ROOT/scripts/lib/writer_deadline.py" watch 1 2 3)" == "deadline watch parent $HOST_PID" ]] && bad deadline-watch-refused "watch was served by the host" || ok
same parity "$ROOT/scripts/lib/echo_call.py" one "two words" 'three"quoted'
same parity-minus-B -B "$ROOT/scripts/lib/echo_call.py" one
EXIT_CODE=7 same exit-status "$ROOT/scripts/lib/echo_call.py"
same exit-true "$ROOT/scripts/lib/exit_true.py"
same exit-false "$ROOT/scripts/lib/exit_false.py"
same exit-message "$ROOT/scripts/lib/exit_text.py"
same uncaught-exception "$ROOT/scripts/lib/boom.py" 2>/dev/null
same non-helper-script "$TMP/work/elsewhere.py"
same inline-code -c 'print(1+1)'
same missing-script "$ROOT/scripts/lib/does_not_exist.py"
mkdir -p "$TMP/work/sub"; ( cd "$TMP/work/sub" && FOO='multi
line' same cwd-and-multiline-env "$ROOT/scripts/lib/echo_call.py" x )
same large-output "$ROOT/scripts/lib/big.py"

# A helper that reads stdin is REFUSEd and still answers correctly through the real interpreter.
[[ "$(echo piped | python3 "$ROOT/scripts/lib/reads_input.py")" == "stdin said piped" ]] && ok || bad reads-stdin "wrong answer"

# Never run twice: 25 served calls append exactly 25 lines.
: > "$TMP/work/count"
for _ in $(seq 1 25); do python3 "$ROOT/scripts/lib/append_once.py" "$TMP/work/count"; done
[[ "$(wc -l < "$TMP/work/count" | tr -d ' ')" == 25 ]] && ok || bad no-double-run "ran $(wc -l < "$TMP/work/count") times"

# 50 concurrent calls each get their own answer.
for i in $(seq 1 50); do ( python3 "$ROOT/scripts/lib/echo_call.py" "n$i" > "$TMP/c.$i" 2>/dev/null ) & done; wait
good=0; for i in $(seq 1 50); do grep -q "argv \['n$i'\]" "$TMP/c.$i" && good=$((good + 1)); done
[[ "$good" == 50 ]] && ok || bad concurrent "only $good of 50 calls got their own answer"

# A wrong token is refused by the host: it sends no ACK.
reply="$(exec 8<>"/dev/tcp/127.0.0.1/$UNCLE_PY_HOST_PORT"; printf '3\nbad1\n0\n0\n0' >&8; read -r -t 3 line <&8; echo "[$line]")"
[[ "$reply" == "[]" ]] && ok || bad wrong-token "host answered: $reply"

# A slow call completes.
same slow "$ROOT/scripts/lib/slow.py"

# Killing the host changes nothing: calls fall back to the real interpreter.
kill -9 "$HOST_PID" 2>/dev/null; sleep 0.3
same after-host-killed "$ROOT/scripts/lib/echo_call.py" still works
[[ "$(python3 "$ROOT/scripts/lib/exit_true.py"; echo $?)" == 1 ]] && ok || bad after-host-killed-status "wrong status"

# The host exits, and removes its directory, when its owner exits.
owner_dir="$(mktemp -d "$TMP/owner.XXXXXX")"
bash -c 'ROOT="$1"; . "$ROOT/scripts/lib/pyhost.sh"; UNCLE_PY_HOST_DIR="$2"; command python3 "$ROOT/scripts/lib/pyhost.py" serve "$2" "$$" "$ROOT" & sleep 1; exit 0' _ "$ROOT" "$owner_dir"
for _ in $(seq 1 60); do [[ ! -d "$owner_dir" ]] && break; sleep 0.1; done
[[ ! -d "$owner_dir" ]] && ok || bad owner-exit "the host's directory is still there after its owner exited"

# The host also removes its directory when it is signalled (a driver stops its background jobs on exit), and a signalled call does not.
sig_dir="$(mktemp -d "$TMP/sig.XXXXXX")"
command python3 "$ROOT/scripts/lib/pyhost.py" serve "$sig_dir" "$$" "$ROOT" > /dev/null 2>&1 &
sig_pid=$!
for _ in $(seq 1 100); do [[ -e "$sig_dir/ready" ]] && break; sleep 0.05; done
kill -TERM "$sig_pid" 2>/dev/null
for _ in $(seq 1 60); do [[ ! -d "$sig_dir" ]] && break; sleep 0.1; done
[[ ! -d "$sig_dir" ]] && ok || bad sigterm-cleanup "the host's directory survived SIGTERM"

if [[ "$FAIL" -ne 0 ]]; then printf '%s\n' "$FAILED_CHECKS"; echo "pyhost-test.sh: $FAIL failed"; exit 1; fi
echo "pyhost-test.sh: $PASS checks passed"

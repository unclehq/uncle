#!/usr/bin/env bash
# Launcher tests for --housekeeping: exclusivity, usage, did-you-mean,
# bare-TTY-free empty input refusal, and the line-menu entry numbering.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UNCLE="$ROOT/uncle"
fail=0
check() { # name, condition-exit
    if [[ "$2" == 0 ]]; then echo "PASS $1"; else echo "FAIL $1"; fail=1; fi
}
run() { UNCLE_SKIP_UPGRADE=1 bash "$UNCLE" "$@" 2>&1; }

out="$(run --help)"; rc=$?
check "help exits 0" "$rc"
grep -q -- '--housekeeping' <<<"$out"; check "usage lists --housekeeping" $?

out="$(run --housekeeping x --application y </dev/null)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'mutually exclusive' <<<"$out"; check "housekeeping then application refused" $?
out="$(run --application y --housekeeping x </dev/null)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'mutually exclusive' <<<"$out"; check "application then housekeeping refused" $?
out="$(run --issue 5 --housekeeping x </dev/null)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'mutually exclusive' <<<"$out"; check "issue then housekeeping refused" $?

out="$(run --housekeeping "" </dev/null)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'empty' <<<"$out"; check "empty text refused" $?
out="$(printf '   \n' | run --housekeeping)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'empty' <<<"$out"; check "blank piped stdin refused" $?

# Bare --housekeeping with a terminal on stdin is refused as empty input (AC-1/2).
out="$(python3 -I -c 'import os,pty,sys,subprocess
m,sl=pty.openpty()
env=dict(os.environ, UNCLE_SKIP_UPGRADE="1")
p=subprocess.Popen(["bash",sys.argv[1],"--housekeeping"],stdin=sl,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env)
out=p.communicate(timeout=30)[0].decode()
sys.stdout.write(out); sys.exit(p.returncode)' "$UNCLE")"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'empty input' <<<"$out"; check "bare --housekeeping on a TTY refused" $?

out="$(run --housekeepin x </dev/null)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'Did you mean --housekeeping' <<<"$out"; check "did-you-mean suggests --housekeeping" $?

# Prior behavior preserved: unknown flag still exits 1; existing exclusivity text kept.
out="$(run --bogus-flag </dev/null)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'Unknown argument' <<<"$out"; check "unknown flag unchanged" $?

# Configure menu: new entry is 4, existing 1-3 unchanged.
grep -q '1) Configure stages\\n  2) Configure self hosting\\n  3) Miscellaneous\\n  4) Housekeeping disallow list\\n  q) Back' "$UNCLE"
check "configure menu: housekeeping entry is last number" $?

exit "$fail"

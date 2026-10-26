#!/usr/bin/env bash
# `uncle` argument parsing: a near-miss flag gets the flag it was reaching for,
# an unrelated one gets the usage text, and both exit 1 before doing anything.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

run_uncle() { (cd "$TMP" && NO_COLOR=1 bash "$ROOT/uncle" "$@" > "$TMP/out" 2> "$TMP/err"); RC=$?; }

run_uncle --applcation 'build a calculator' --unattended
check "typo exits 1"                        test "$RC" -eq 1
check "typo is named"                       grep -qF "Unknown argument: --applcation" "$TMP/err"
check "typo gets the intended flag"         grep -qF "Did you mean --application?" "$TMP/err"
check "typo does not dump the usage text"   test "$(grep -c "Usage: uncle" "$TMP/err")" -eq 0
leftovers="$(find "$TMP" -mindepth 1 ! -name out ! -name err)"
check "nothing written to the project dir ($leftovers)" test -z "$leftovers"

run_uncle --isue 42
check "second flag also hinted"             grep -qF "Did you mean --issue?" "$TMP/err"

run_uncle --frobnicate
check "unrelated flag exits 1"              test "$RC" -eq 1
check "unrelated flag gets usage"           grep -qF "Usage: uncle" "$TMP/err"
check "unrelated flag gets no hint"         test "$(grep -c "Did you mean" "$TMP/err")" -eq 0

# The launch flags must reach the TUI process, not just the parser: a fake
# python3 stands in for the TUI and records what it was handed.
REAL_PYTHON3="$(command -v python3)"
mkdir -p "$TMP/bin"
cat > "$TMP/bin/python3" <<FAKE
#!/usr/bin/env bash
for a in "\$@"; do
    case "\$a" in
        *uncle_tui.py)
            printf 'action=%s\ntext=%s\nunattended=%s\n' "\${UNCLE_STARTUP_ACTION:-}" "\${UNCLE_STARTUP_TEXT:-}" "\${UNCLE_STARTUP_UNATTENDED:-}" > "$TMP/tui-env"
            exit 0 ;;
    esac
done
exec "$REAL_PYTHON3" "\$@"
FAKE
chmod +x "$TMP/bin/python3"
(cd "$TMP" && PATH="$TMP/bin:$PATH" NO_COLOR=1 bash "$ROOT/uncle" --application 'build a groovy calculator' --unattended > "$TMP/out" 2> "$TMP/err"); RC=$?
check "--application launches the TUI"            test "$RC" -eq 0
check "TUI receives the startup action"           grep -qxF "action=create_app" "$TMP/tui-env"
check "TUI receives the description"              grep -qxF "text=build a groovy calculator" "$TMP/tui-env"
check "TUI receives unattended mode"              grep -qxF "unattended=1" "$TMP/tui-env"

# --change-request: stdin is validated by the helper and handed to the TUI as a
# private file; every rejection exits 1 with nothing written or left behind.
CR="$TMP/cr"; mkdir -p "$CR/tmp" "$CR/proj"
cat > "$CR/bin-python3" <<FAKE
#!/usr/bin/env bash
for a in "\$@"; do
    case "\$a" in
        *uncle_tui.py)
            f="\${UNCLE_STARTUP_TEXT_FILE:-}"
            { printf 'action=%s\nunattended=%s\nargs=%s\n' "\${UNCLE_STARTUP_ACTION:-}" "\${UNCLE_STARTUP_UNATTENDED:-}" "\${UNCLE_STARTUP_TEXT:-}"
              printf 'file=%s\nmode=%s\n' "\$f" "\$(stat -f %Lp "\$f" 2>/dev/null || stat -c %a "\$f")"; } > "$CR/tui-env"
            cp "\$f" "$CR/tui-text"
            exit 0 ;;
    esac
done
exec "$REAL_PYTHON3" "\$@"
FAKE
mkdir -p "$CR/bin"; cp "$CR/bin-python3" "$CR/bin/python3"; chmod +x "$CR/bin/python3"
cr_run() { # input-command args...
    local feed="$1"; shift
    rm -f "$CR/tui-env" "$CR/tui-text"; rm -rf "$CR/proj"; mkdir -p "$CR/proj"
    (cd "$CR/proj" && eval "${CR_PRE:-:}" && eval "$feed" | TMPDIR="$CR/tmp" PATH="$CR/bin:$PATH" NO_COLOR=1 UNCLE_STARTUP_TEXT_FILE=/etc/hostname bash "$ROOT/uncle" "$@" > "$CR/out" 2> "$CR/err"); RC=$?
}
cr_clean() { check "$1: nothing left in TMPDIR" test -z "$(ls -A "$CR/tmp")"
             check "$1: nothing written to project" test -z "$(ls -A "$CR/proj")"; }

cr_run "printf 'fix it\r\nplain\rtext\n  '" --change-request
check "cr: launches"                      test "$RC" -eq 0
check "cr: action"                        grep -qxF "action=change_request" "$CR/tui-env"
check "cr: mode 0600"                     grep -qxF "mode=600" "$CR/tui-env"
check "cr: env path overridden"           bash -c "! grep -qF /etc/hostname '$CR/tui-env'"
check "cr: bytes normalized exactly"      cmp -s "$CR/tui-text" <(printf 'fix it\nplain\ntext\n  ')
check "cr happy: nothing left in TMPDIR after exit" test -z "$(ls -A "$CR/tmp")"

cr_run "printf x" --change-request --unattended
check "cr: unattended reaches TUI"        grep -qxF "unattended=1" "$CR/tui-env"
cr_run "printf x" --unattended --change-request
check "cr: unattended either order"       grep -qxF "unattended=1" "$CR/tui-env"

cr_fail() { # label input msg args...
    local label="$1" feed="$2" msg="$3"; shift 3
    cr_run "$feed" "$@"
    check "$label: exit 1"                test "$RC" -eq 1
    check "$label: message"               grep -qF -- "$msg" "$CR/err"
    check "$label: TUI not started"       test ! -e "$CR/tui-env"
    cr_clean "$label"
}
cr_fail "cr empty"   "printf ''"            "--change-request text cannot be empty" --change-request
cr_fail "cr blank"   "printf ' \n\t\n'"     "--change-request text cannot be empty" --change-request
cr_fail "cr nul"     "printf 'a\\000b'"     "contains NUL or control characters" --change-request
cr_fail "cr bell"    "printf 'a\\007b'"     "contains NUL or control characters" --change-request
cr_fail "cr del"     "printf 'a\\177b'"     "contains NUL or control characters" --change-request
cr_fail "cr c1"      "printf 'a\\302\\205b'" "contains NUL or control characters" --change-request
cr_fail "cr utf8"    "printf 'a\\377b'"     "not valid UTF-8" --change-request
cr_fail "cr cap+1"   "head -c 1048577 /dev/zero | tr '\\0' a" "exceeds 1048576 bytes" --change-request
cr_fail "cr excl app"   "printf x" "mutually exclusive" --change-request --application foo
cr_fail "cr excl app2"  "printf x" "mutually exclusive" --application foo --change-request
cr_fail "cr excl issue" "printf x" "mutually exclusive" --change-request --issue 5
cr_fail "cr excl issue2" "printf x" "mutually exclusive" --issue 5 --change-request

cr_run "head -c 1048576 /dev/zero | tr '\\0' a" --change-request
check "cr cap exactly accepted"           test "$RC" -eq 0
cr_run "printf 'caf\\303\\251 \\t ok'" --change-request
check "cr utf8 tab accepted"              cmp -s "$CR/tui-text" <(printf 'caf\303\251 \t ok')

for existing in file link; do
    if [[ "$existing" == file ]]; then pre='echo old > CHANGE_REQUEST.md'; else pre='ln -s nowhere CHANGE_REQUEST.md'; fi
    CR_PRE="$pre" cr_run "printf x" --change-request
    check "cr existing $existing: exit 1"  test "$RC" -eq 1
    check "cr existing $existing: message" grep -qF "CHANGE_REQUEST.md already exists. Run it or choose a new project; it was not overwritten." "$CR/err"
    check "cr existing $existing: untouched" test "$(ls -A "$CR/proj")" = "CHANGE_REQUEST.md"
    check "cr existing $existing: tmp clean" test -z "$(ls -A "$CR/tmp")"
done
rm -rf "$CR/proj"; mkdir -p "$CR/proj"

# python3 failing: fail closed, nothing left over.
mkdir -p "$CR/nopy"; printf '#!/bin/sh\nexit 3\n' > "$CR/nopy/python3"; chmod +x "$CR/nopy/python3"
(cd "$CR/proj" && printf x | TMPDIR="$CR/tmp" PATH="$CR/nopy:$PATH" NO_COLOR=1 bash "$ROOT/uncle" --change-request > "$CR/out" 2> "$CR/err"); RC=$?
check "cr failing python: exit nonzero"   test "$RC" -ne 0
check "cr failing python: tmp clean"      test -z "$(ls -A "$CR/tmp")"

# TTY stdin is refused before anything is read.
rc_tty="$(cd "$CR/proj" && TMPDIR="$CR/tmp" NO_COLOR=1 "$REAL_PYTHON3" -c '
import os, pty, sys
pid, fd = pty.fork()
if pid == 0:
    os.execvp("bash", ["bash", sys.argv[1], "--change-request"])
out = b""
while True:
    try:
        chunk = os.read(fd, 4096)
    except OSError:
        break
    if not chunk: break
    out += chunk
_, status = os.waitpid(pid, 0)
sys.stderr.write(out.decode())
print(os.waitstatus_to_exitcode(status))' "$ROOT/uncle" 2> "$CR/err")"
check "cr tty: exit 1"                    test "$rc_tty" = 1
check "cr tty: message"                   grep -qF "reads the change request from stdin; pipe or redirect it in" "$CR/err"
cr_clean "cr tty"

# Documentation.
check "usage mentions flag"               bash -c "NO_COLOR=1 bash '$ROOT/uncle' --help | grep -qF -- '--change-request'"
check "usage has trust warning"           bash -c "NO_COLOR=1 bash '$ROOT/uncle' --help | grep -qF 'untrusted input to'"
check "README mentions flag"              grep -qF -- "--change-request" "$ROOT/README.md"
check "README has trust warning"          grep -qF "untrusted input" "$ROOT/README.md"
run_uncle --change-reqest
check "typo hints --change-request"       grep -qF "Did you mean --change-request?" "$TMP/err"

if [[ "$fails" -gt 0 ]]; then echo "launcher-args-test.sh: $fails failure(s)"; exit 1; fi
echo "launcher-args-test.sh: all checks passed"

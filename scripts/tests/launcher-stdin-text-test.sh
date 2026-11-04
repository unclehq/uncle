#!/usr/bin/env bash
# `uncle --application` / `--housekeeping` take their text from piped stdin when
# no value is given, or from `--OPT=VALUE`.  A fake python3 stands in for the TUI
# and records the env contract (UNCLE_STARTUP_TEXT vs UNCLE_STARTUP_TEXT_FILE),
# then deletes the file and its private dir the way the real TUI does.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
REAL_PYTHON3="$(command -v python3)"
HELPER="$ROOT/scripts/lib/housekeeping_input.py"

mkdir -p "$TMP/bin" "$TMP/work"
cat > "$TMP/bin/python3" <<FAKE
#!/usr/bin/env bash
for a in "\$@"; do
    case "\$a" in
        *uncle_tui.py)
            f="\${UNCLE_STARTUP_TEXT_FILE:-}"
            {
                printf 'action=%s\n' "\${UNCLE_STARTUP_ACTION:-}"
                printf 'text=%s\n' "\${UNCLE_STARTUP_TEXT:-}"
                printf 'file=%s\n' "\$f"
                if [[ -n "\$f" && -f "\$f" ]]; then
                    printf 'file_exists=1\n'
                    cp "\$f" "$TMP/tui-file-content"
                    rm -f "\$f"; rmdir "\$(dirname "\$f")" 2>/dev/null
                else
                    printf 'file_exists=0\n'
                fi
            } > "$TMP/tui-env"
            exit 0 ;;
    esac
done
exec "$REAL_PYTHON3" "\$@"
FAKE
chmod +x "$TMP/bin/python3"

# run_uncle STDIN_FILE args... -> RC; fresh TMPDIR each time in $TMP/tmpdir
run_uncle() {
    local in="$1"; shift
    rm -rf "$TMP/tmpdir" "$TMP/tui-env" "$TMP/tui-file-content"; mkdir -p "$TMP/tmpdir"
    (cd "$TMP/work" && TMPDIR="$TMP/tmpdir" UNCLE_SKIP_UPGRADE=1 PATH="$TMP/bin:$PATH" NO_COLOR=1 \
        bash "$ROOT/uncle" "$@" < "$in" > "$TMP/out" 2> "$TMP/err"); RC=$?
}
residue() { test -z "$(find "$TMP/tmpdir" -mindepth 1 2>/dev/null)"; }
envval() { grep "^$1=" "$TMP/tui-env" | head -1 | cut -d= -f2-; }
content_is() { test "$(cat "$TMP/tui-file-content"; printf x)" = "$1x"; }

# unread_case OPTARGS... : run with a pipe holding bytes; report exit and unread count.
cat > "$TMP/unread.py" <<'PY'
import os, subprocess, sys
r, w = os.pipe()
os.write(w, b'piped text\n')
tmpdir = sys.argv[1]
env = dict(os.environ, TMPDIR=tmpdir, UNCLE_SKIP_UPGRADE='1', NO_COLOR='1')
p = subprocess.run(['bash', sys.argv[2]] + sys.argv[3:], stdin=r, env=env,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=os.environ['WORKDIR'], timeout=60)
os.set_blocking(r, False)
try:
    left = len(os.read(r, 100))
except BlockingIOError:
    left = 0
sys.stdout.write('rc=%d unread=%d residue=%d\n' % (p.returncode, left, len(os.listdir(tmpdir))))
sys.stderr.write(p.stderr.decode())
PY
unread_case() {
    rm -rf "$TMP/tmpdir" "$TMP/tui-env"; mkdir -p "$TMP/tmpdir"
    UNREAD="$(WORKDIR="$TMP/work" PATH="$TMP/bin:$PATH" "$REAL_PYTHON3" -I "$TMP/unread.py" "$TMP/tmpdir" "$ROOT/uncle" "$@" 2> "$TMP/err")"
}

printf 'build a calculator\n' > "$TMP/in-line"
printf 'x\r\n' > "$TMP/in-crlf"
printf 'x\n\n' > "$TMP/in-two-nl"
printf '\n' > "$TMP/in-nl"
: > "$TMP/in-empty"

for pair in application:create_app housekeeping:housekeeping; do
    OPT="${pair%%:*}"; ACTION="${pair##*:}"

    # stdin case: file set, text empty
    run_uncle "$TMP/in-line" "--$OPT"
    check "$OPT stdin exits 0" test "$RC" -eq 0
    check "$OPT stdin action" test "$(envval action)" = "$ACTION"
    check "$OPT stdin leaves UNCLE_STARTUP_TEXT empty" test -z "$(envval text)"
    check "$OPT stdin sets UNCLE_STARTUP_TEXT_FILE" test -n "$(envval file)"
    check "$OPT stdin file existed at TUI start" test "$(envval file_exists)" = 1
    check "$OPT stdin trailing newline stripped" content_is 'build a calculator'
    check "$OPT stdin no TMPDIR residue after exec" residue

    # value case: text set, file empty
    run_uncle "$TMP/in-empty" "--$OPT" 'some value'
    check "$OPT value exits 0" test "$RC" -eq 0
    check "$OPT value sets text" test "$(envval text)" = "some value"
    check "$OPT value leaves file empty" test -z "$(envval file)"
    run_uncle "$TMP/in-empty" "--$OPT=eq value"
    check "$OPT = form sets text" test "$(envval text)" = "eq value"
    check "$OPT = form leaves file empty" test -z "$(envval file)"
    run_uncle "$TMP/in-empty" "--$OPT=--text"
    check "$OPT =--text delivers --text" test "$(envval text)" = "--text"

    # value-form text is unvalidated (control chars, whitespace-only pass through)
    run_uncle "$TMP/in-empty" "--$OPT" $'a\tb\001c'
    check "$OPT value-form text unvalidated" test "$(envval text)" = $'a\tb\001c'

    # both set (caller-exported env, stdin case): the file wins, text stays as exported
    rm -rf "$TMP/tmpdir" "$TMP/tui-env"; mkdir -p "$TMP/tmpdir"
    (cd "$TMP/work" && UNCLE_STARTUP_TEXT=ignored TMPDIR="$TMP/tmpdir" UNCLE_SKIP_UPGRADE=1 PATH="$TMP/bin:$PATH" \
        bash "$ROOT/uncle" "--$OPT" < "$TMP/in-line" > "$TMP/out" 2> "$TMP/err"); RC=$?
    check "$OPT both set: file present for TUI to prefer" test "$(envval file_exists)" = 1
    check "$OPT both set: launcher still hands over the file" content_is 'build a calculator'

    # stdin newline handling
    run_uncle "$TMP/in-crlf" "--$OPT"
    check "$OPT stdin 'x\\r\\n' -> 'x'" content_is 'x'
    run_uncle "$TMP/in-two-nl" "--$OPT"
    check "$OPT stdin 'x\\n\\n' -> 'x\\n'" content_is $'x\n'
    run_uncle "$TMP/in-nl" "--$OPT"
    check "$OPT stdin newline alone refused" test "$RC" -eq 1
    check "$OPT stdin newline alone says empty" grep -q 'cannot be empty' "$TMP/err"
    check "$OPT stdin newline alone: no residue" residue

    # empty non-TTY stdin and --OPT --other
    run_uncle "$TMP/in-empty" "--$OPT"
    check "$OPT empty stdin exits 1" test "$RC" -eq 1
    check "$OPT empty stdin message" grep -qF "Error: --$OPT text cannot be empty" "$TMP/err"
    check "$OPT empty stdin: no residue" residue
    run_uncle /dev/null "--$OPT" --unattended
    check "$OPT --unattended is never text: exit 1" test "$RC" -eq 1
    check "$OPT --unattended is never text: message" grep -qF "Error: --$OPT text cannot be empty" "$TMP/err"
    run_uncle "$TMP/in-line" "--$OPT" --unattended
    check "$OPT stdin + --unattended exits 0" test "$RC" -eq 0
    check "$OPT stdin + --unattended reads stdin" test "$(envval file_exists)" = 1
    run_uncle "$TMP/in-line" --unattended "--$OPT"
    check "$OPT --unattended before option reads stdin" test "$(envval file_exists)" = 1

    # a value beginning with -- needs the = form (hint names it)
    run_uncle /dev/null "--$OPT" --foo
    check "$OPT --foo not text: exit 1" test "$RC" -eq 1
    run_uncle /dev/null "--$OPT=--foo"
    check "$OPT =--foo works" test "$(envval text)" = "--foo"

    # -h, verify, "" handling: -h/verify are values; "" refused without reading stdin
    run_uncle "$TMP/in-empty" "--$OPT" -h
    check "$OPT -h is a value" test "$(envval text)" = "-h"
    run_uncle "$TMP/in-empty" "--$OPT" verify
    check "$OPT verify is a value" test "$(envval text)" = "verify"

    # empty value forms with non-empty piped stdin: refused, pipe unread, no residue
    for form in '' '='; do
        if [[ -z "$form" ]]; then unread_case "--$OPT" ""; else unread_case "--$OPT="; fi
        check "$OPT empty value form '$form': exit 1, stdin unread, no residue" test "$UNREAD" = "rc=1 unread=11 residue=0"
        check "$OPT empty value form '$form': message" grep -qF "Error: --$OPT text cannot be empty" "$TMP/err"
    done

    # unknown argument after the option: exit 1, stdin unread, no temp file
    unread_case "--$OPT" --bogus
    check "$OPT --bogus: exit 1, stdin unread, no residue" test "$UNREAD" = "rc=1 unread=11 residue=0"
    unread_case "--$OPT" bogus-positional
    check "$OPT unknown after value: nothing read" test "$(cut -d' ' -f3 <<<"$UNREAD")" = "residue=0"

    # second mode option: mutually exclusive, before any stdin read
    for other in application housekeeping; do
        unread_case "--$OPT" "--$other"
        check "$OPT then --$other: exit 1, stdin unread, no residue" test "$UNREAD" = "rc=1 unread=11 residue=0"
        check "$OPT then --$other: mutually exclusive" grep -q 'mutually exclusive' "$TMP/err"
    done
done

# cross-option: --application --bogus (task case spelled out)
unread_case --application --bogus
check "--application --bogus: exit 1, unread, no residue" test "$UNREAD" = "rc=1 unread=11 residue=0"

# ---- helper: housekeeping_input.py --label, newline handling, cap ----
helper() { # stdin from file $1, extra args after; sets HOUT HRC
    local in="$1"; shift
    rm -rf "$TMP/priv"; mkdir -p "$TMP/priv"; chmod 700 "$TMP/priv"
    HOUT="$("$REAL_PYTHON3" -I "$HELPER" "$@" < "$in" 2> "$TMP/herr")"; HRC=$?
}
helper_content() { "$REAL_PYTHON3" -I -c 'import sys; sys.stdout.write(repr(open(sys.argv[1],"rb").read()))' "$HOUT"; }

helper "$TMP/in-line" "$TMP/priv"
check "helper old invocation valid" test "$HRC" -eq 0
check "helper stdin strips one newline" test "$(helper_content)" = "b'build a calculator'"
helper "$TMP/in-crlf" "$TMP/priv"
check "helper CRLF then strip -> x" test "$(helper_content)" = "b'x'"
printf 'x\n\r\n' > "$TMP/in-mixed"
helper "$TMP/in-mixed" "$TMP/priv"
check "helper x LF CRLF -> 'x\\n'" test "$(helper_content)" = "b'x\\n'"
printf 'x\r' > "$TMP/in-cr"
helper "$TMP/in-cr" "$TMP/priv"
check "helper lone CR normalised then stripped" test "$(helper_content)" = "b'x'"
helper "$TMP/in-nl" "$TMP/priv"
check "helper newline alone refused" test "$HRC" -eq 1
helper /dev/null --label --application "$TMP/priv"
check "helper label in message" grep -qF -- "--application text cannot be empty" "$TMP/herr"
helper /dev/null "$TMP/priv"
check "helper default label is --housekeeping" grep -qF -- "--housekeeping text cannot be empty" "$TMP/herr"
helper /dev/null --label --application "$TMP/priv" --text $'x\n'
check "helper --text not stripped" test "$(helper_content)" = "b'x\\n'"
check "helper --text success with label" test "$HRC" -eq 0

CAP=1048576
"$REAL_PYTHON3" -I -c 'import sys; sys.stdout.buffer.write(b"a" * 1048576)' > "$TMP/cap-exact"
"$REAL_PYTHON3" -I -c 'import sys; sys.stdout.buffer.write(b"a" * 1048577)' > "$TMP/cap-over"
"$REAL_PYTHON3" -I -c 'import sys; sys.stdout.buffer.write(b"a" * 1048575 + b"\n")' > "$TMP/cap-nl-exact"
"$REAL_PYTHON3" -I -c 'import sys; sys.stdout.buffer.write(b"a" * 1048576 + b"\n")' > "$TMP/cap-nl-over"
"$REAL_PYTHON3" -I -c 'import sys; sys.stdout.buffer.write(b"a" * 1048574 + b"\r\n")' > "$TMP/cap-crlf-exact"
"$REAL_PYTHON3" -I -c 'import sys; sys.stdout.buffer.write(b"a" * 1048575 + b"\r\n")' > "$TMP/cap-crlf-over"
helper "$TMP/cap-exact" --label --application "$TMP/priv"
check "helper 1048576 raw bytes pass" test "$HRC" -eq 0
helper "$TMP/cap-over" --label --application "$TMP/priv"
check "helper 1048577 raw bytes fail" test "$HRC" -eq 1
check "helper over-cap message names option" grep -qF -- "--application" "$TMP/herr"
helper "$TMP/cap-nl-exact" "$TMP/priv"
check "helper 1048576 raw bytes ending in newline pass" test "$HRC" -eq 0
helper "$TMP/cap-nl-over" "$TMP/priv"
check "helper 1048576 body + trailing newline fails (cap is on raw bytes)" test "$HRC" -eq 1
helper "$TMP/cap-crlf-exact" "$TMP/priv"
check "helper CRLF input at exactly cap passes" test "$HRC" -eq 0
helper "$TMP/cap-crlf-over" "$TMP/priv"
check "helper CRLF input one over cap fails" test "$HRC" -eq 1

printf 'a\000b' > "$TMP/in-nul"
printf 'a\001b' > "$TMP/in-ctl"
printf 'a\tb\nc\rd' > "$TMP/in-ok"
printf '\377\376' > "$TMP/in-bad"
helper "$TMP/in-nul" "$TMP/priv";  check "helper NUL refused" test "$HRC" -eq 1
helper "$TMP/in-ctl" "$TMP/priv";  check "helper control refused" test "$HRC" -eq 1
helper "$TMP/in-bad" "$TMP/priv";  check "helper invalid UTF-8 refused" test "$HRC" -eq 1
helper "$TMP/in-ok" "$TMP/priv";   check "helper tab/LF/CR accepted" test "$HRC" -eq 0
check "helper tab/LF/CR normalised" test "$(helper_content)" = "b'a\\tb\\nc\\nd'"
check "helper refusal leaves no file" test -z "$(find "$TMP/priv" -mindepth 1 -type f | grep -v . ; true)" || true
helper "$TMP/in-nul" "$TMP/priv"
check "helper rejection writes nothing" test -z "$(find "$TMP/priv" -mindepth 1)"

# launcher: over-cap and invalid input via stdin refused for both options
for OPT in application housekeeping; do
    run_uncle "$TMP/cap-over" "--$OPT"
    check "$OPT over-cap stdin exits 1" test "$RC" -eq 1
    check "$OPT over-cap stdin: no residue" residue
    run_uncle "$TMP/cap-exact" "--$OPT"
    check "$OPT exact-cap stdin exits 0" test "$RC" -eq 0
    run_uncle "$TMP/in-nul" "--$OPT"
    check "$OPT NUL stdin exits 1" test "$RC" -eq 1
    run_uncle "$TMP/in-bad" "--$OPT"
    check "$OPT invalid UTF-8 stdin exits 1" test "$RC" -eq 1
done

# ---- TTY: bare option on a terminal is refused with the D-1 message ----
for OPT in application housekeeping; do
    out="$("$REAL_PYTHON3" -I -c 'import os,pty,sys,subprocess
m,sl=pty.openpty()
env=dict(os.environ, UNCLE_SKIP_UPGRADE="1", NO_COLOR="1")
p=subprocess.Popen(["bash",sys.argv[1],"--"+sys.argv[2]],stdin=sl,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env)
out=p.communicate(timeout=30)[0].decode()
sys.stdout.write(out); sys.exit(p.returncode)' "$ROOT/uncle" "$OPT")"; rc=$?
    check "$OPT bare on a TTY exits 1" test "$rc" -eq 1
    check "$OPT bare on a TTY: empty input message" grep -q 'empty input' <<<"$out"
    check "$OPT bare on a TTY: no 'requires an argument'" test -z "$(grep 'requires an argument' <<<"$out")"
done

# ---- --issue: stdin only when no issue reference is given ----
printf '#42\n' > "$TMP/in-issue"
run_uncle "$TMP/in-issue" --issue
check "--issue bare reads piped ref: exit 0" test "$RC" -eq 0
check "--issue bare: action" test "$(envval action)" = github_issue
check "--issue bare: ref normalised" test "$(envval text)" = 42
run_uncle "$TMP/in-line" --issue 7
check "--issue 7 ignores stdin: exit 0" test "$RC" -eq 0
check "--issue 7 ref" test "$(envval text)" = 7
run_uncle "$TMP/in-issue" --issue --unattended
check "--issue then option reads stdin" test "$(envval text)" = 42
run_uncle "$TMP/in-empty" --issue
check "--issue empty stdin refused" test "$RC" -eq 1
run_uncle "$TMP/in-line" --issue
check "--issue invalid piped ref refused" test "$RC" -eq 1

if [[ "$fails" -eq 0 ]]; then echo "all launcher stdin text checks passed"; exit 0; fi
echo "$fails check(s) failed"; exit 1

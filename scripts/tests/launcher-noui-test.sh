#!/usr/bin/env bash
# Launcher --noui dispatch: refusals exit 2, help unchanged, attended needs a tty.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
UNCLE="$HERE/../../uncle"
fail=0
check() { # name expected actual
    if [[ "$2" == "$3" ]]; then echo "ok - $1"; else echo "FAIL - $1: expected $2 got $3"; fail=1; fi
}
export UNCLE_SKIP_UPGRADE=1
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
cd "$tmp" || exit 1

# Bare --noui / UNCLE_NOUI=1 now start the REPL (formerly refused with exit 2); see the
# stub-python3 rows below. Rows proving unrecognized arguments keep the old error follow them.
"$UNCLE" --noui --noinput --application x </dev/null >/dev/null 2>&1; check "noui with noinput exits 2" 2 $?
"$UNCLE" --noui --help </dev/null >"$tmp/h" 2>&1; check "help with noui exits 0" 0 $?
grep -q -- '--noui' "$tmp/h"; check "usage documents --noui" 0 $?
"$UNCLE" --noui --application a --issue 1 </dev/null >/dev/null 2>&1; check "multiple startup actions refused" 1 $?

"$UNCLE" --noui --application '' </dev/null >/dev/null 2>&1; check "noui empty application text exits 2" 2 $?
echo t | "$UNCLE" --noui --attended --change-request >/dev/null 2>&1; check "noui attended without tty exits 2" 2 $?
"$UNCLE" --noui --attended --application x </dev/null >/dev/null 2>&1; check "noui attended no tty (application) exits 2" 2 $?
"$UNCLE" --attended --application x </dev/null >/dev/null 2>&1; check "attended without noui keeps exit 1" 1 $?
grep -q -- 'never starts the UI' "$tmp/h"; check "usage contrasts --noui with --noinput" 0 $?

# Identity with committed HEAD when --noui is absent and UNCLE_NOUI is unset, 0 or empty:
# a stub python3 records argv + environment of every call; the working-tree launcher
# and the committed-HEAD launcher must produce identical records.
ROOT_DIR="$(cd "$HERE/../.." && pwd)"
bin="$tmp/bin"; mkdir -p "$bin"
cat >"$bin/python3" <<'STUB'
#!/usr/bin/env bash
{ printf 'ARGV:'; printf ' [%s]' "$@"; printf '\n'; env | grep -v -E '^(_|SHLVL|PWD|OLDPWD|UNCLE_CAPTURE)=' | sort; } >>"$UNCLE_CAPTURE"
exit 0
STUB
chmod +x "$bin/python3"
head_launcher="$ROOT_DIR/.uncle-head-launcher-$$"
if git -C "$ROOT_DIR" show HEAD:uncle >"$head_launcher" 2>/dev/null; then
    chmod +x "$head_launcher"
    trap 'rm -rf "$tmp" "$head_launcher"' EXIT
    capture() { # launcher envspec...
        local l="$1"; shift
        : >"$tmp/cap"
        ( cd "$tmp" && env -u UNCLE_NOUI "$@" PATH="$bin:$PATH" UNCLE_CAPTURE="$tmp/cap" "$l" --application x </dev/null >/dev/null 2>&1 )
        sed -e "s#$head_launcher#LAUNCHER#g" "$tmp/cap"
    }
    for spec in "UNSET=1" "UNCLE_NOUI=0" "UNCLE_NOUI="; do
        a="$(capture "$UNCLE" "$spec")"; b="$(capture "$head_launcher" "$spec")"
        [[ -n "$a" ]]; check "capture non-empty ($spec)" 0 $?
        [[ "$a" == "$b" ]]; check "argv/env identical to HEAD launcher ($spec)" 0 $?
        grep -q 'uncle_headless' <<<"$a"; check "no headless exec ($spec)" 1 $?
    done
    # Bare --noui plus an unrecognized argument: same stderr and exit code as the HEAD launcher.
    for args in "--noui --bogus" "--noui --bogus --application x" "--noui extra"; do
        # shellcheck disable=SC2086
        "$UNCLE" $args </dev/null >/dev/null 2>"$tmp/ea"; ra=$?
        # shellcheck disable=SC2086
        "$head_launcher" $args </dev/null >/dev/null 2>"$tmp/eb"; rb=$?
        sed -i.bak -e "s#$head_launcher#LAUNCHER#g" "$tmp/eb"
        check "unrecognized arg keeps exit code ($args)" "$rb" "$ra"
        [[ "$ra" != 0 ]]; check "unrecognized arg is an error ($args)" 0 $?
        # usage text documents the REPL now, so only the error line is compared
        [[ "$(head -n1 "$tmp/ea")" == "$(head -n1 "$tmp/eb")" ]]; check "unrecognized arg keeps error line ($args)" 0 $?
    done
else
    echo "SKIP - HEAD launcher unavailable (not a git checkout)"
fi

# Bare forms exec the REPL (stub python3 records argv; nothing real runs).
for form in "--noui" "UNCLE_NOUI=1"; do
    : >"$tmp/cap"
    if [[ "$form" == UNCLE_NOUI=1 ]]; then
        ( cd "$tmp" && env UNCLE_NOUI=1 PATH="$bin:$PATH" UNCLE_CAPTURE="$tmp/cap" "$UNCLE" </dev/null >/dev/null 2>&1 ); rc=$?
    else
        ( cd "$tmp" && env -u UNCLE_NOUI PATH="$bin:$PATH" UNCLE_CAPTURE="$tmp/cap" "$UNCLE" $form </dev/null >/dev/null 2>&1 ); rc=$?
    fi
    check "bare $form exits via REPL stub" 0 $rc
    grep -q 'uncle_repl' "$tmp/cap"; check "bare $form execs uncle_repl" 0 $?
done
REPO="$(cd "$HERE/../.." && pwd)"
# Real REPL through the launcher: EOF exits 0 with the banner; --noinput still refused (AC-1).
out="$(env UNCLE_RUNTIME_ROOT="$REPO" "$UNCLE" --noui </dev/null 2>&1)"; check "real bare --noui exits 0 on EOF" 0 $?
grep -q 'interactive session' <<<"$out"; check "real bare --noui prints the banner" 0 $?
out="$(UNCLE_NOUI=1 UNCLE_RUNTIME_ROOT="$REPO" "$UNCLE" </dev/null 2>&1)"; check "real UNCLE_NOUI=1 exits 0 on EOF" 0 $?
grep -q 'interactive session' <<<"$out"; check "real UNCLE_NOUI=1 prints the banner" 0 $?
"$UNCLE" --noui --noinput </dev/null >/dev/null 2>&1; check "bare --noui --noinput still exits 2" 2 $?
exit $fail

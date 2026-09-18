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
            printf 'action=%s\ntext=%s\n' "\${UNCLE_STARTUP_ACTION:-}" "\${UNCLE_STARTUP_TEXT:-}" > "$TMP/tui-env"
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

if [[ "$fails" -gt 0 ]]; then echo "launcher-args-test.sh: $fails failure(s)"; exit 1; fi
echo "launcher-args-test.sh: all checks passed"

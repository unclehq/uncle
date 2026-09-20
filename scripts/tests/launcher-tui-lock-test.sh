#!/usr/bin/env bash
# Two uncle invocations in the same project directory is how concurrent
# builds (several GitHub-workflow runs at once) are supposed to work, and it
# used to. A stale-TUI-replacement feature made this unconditional and broke
# it: starting a second `uncle` killed the first one outright. It must stay
# opt-in (UNCLE_TUI_REPLACE_STALE=1), never the default.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

REAL_PYTHON3="$(command -v python3)"
mkdir -p "$TMP/bin" "$TMP/project/.uncle"
cat > "$TMP/bin/python3" <<FAKE
#!/usr/bin/env bash
for a in "\$@"; do
    case "\$a" in
        *uncle_tui.py)
            if [[ -n "\${FAKE_TUI_SURVIVE:-}" ]]; then
                trap '' TERM
                while :; do sleep 0.1; done
            fi
            exit 0 ;;
    esac
done
exec "$REAL_PYTHON3" "\$@"
FAKE
chmod +x "$TMP/bin/python3"

start_stale_tui() {
    (cd "$TMP/project" && PATH="$TMP/bin:$PATH" FAKE_TUI_SURVIVE=1 \
        "$TMP/bin/python3" "$ROOT/uncle_tui.py" --noinput &)
    local waited
    for waited in 1 2 3 4 5 6 7 8 9 10; do
        old_pid="$(pgrep -f "$TMP/bin/python3 $ROOT/uncle_tui.py" | head -1)"
        [[ -n "$old_pid" ]] && break
        sleep 0.2
    done
    [[ -n "$old_pid" ]] || return 1
    # Only the real uncle_tui.py self-registers its PID (_record_tui_pid);
    # the fake stands in for the long-running process, not that write.
    printf '%s' "$old_pid" > "$TMP/project/.uncle/tui.lock"
}

run_second_uncle() {
    (cd "$TMP/project" && PATH="$TMP/bin:$PATH" "$@" \
        NO_COLOR=1 bash "$ROOT/uncle" --application 'build a groovy calculator' --unattended \
        > "$TMP/out" 2> "$TMP/err")
}

check "stale TUI started" start_stale_tui
run_second_uncle
check "default: starting a second uncle leaves the first alive" kill -0 "$old_pid"
kill -9 "$old_pid" 2>/dev/null || true
wait 2>/dev/null

check "stale TUI started (opt-in case)" start_stale_tui
run_second_uncle env UNCLE_TUI_REPLACE_STALE=1
check "opt-in: starting a second uncle replaces the first" bash -c '! kill -0 '"$old_pid"' 2>/dev/null'
kill -9 "$old_pid" 2>/dev/null || true
wait 2>/dev/null

if [[ "$fails" -gt 0 ]]; then echo "launcher-tui-lock-test.sh: $fails failure(s)"; exit 1; fi
echo "launcher-tui-lock-test.sh: all checks passed"

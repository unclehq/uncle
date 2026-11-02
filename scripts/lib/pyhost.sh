# Client half of the per-run Python host (scripts/lib/pyhost.py). Sourced by a driver, which calls uncle_py_host_start once.
#
# Defines `python3` as a function in the driver's own shell (never exported, so nothing else is affected). A call of the form
# `python3 [-B] helper.py args...` is handed to the host over a loopback socket when the host is up; the host answers REFUSE for
# anything it does not serve, and every other form (-c, -m, `-`, a script that is not a helper) runs the real interpreter.
# Rules the client keeps:
#   * no wait: uncle_py_host_start returns at once, and calls made before the host is ready run the real interpreter;
#   * a failure before the host acknowledges the call (no connection, REFUSE, no ACK within 5 s) falls back to the real interpreter;
#     once acknowledged a call is never re-run, so a helper with side effects cannot run twice;
#   * UNCLE_PY_HOST=0 turns it off.
# bash 3.2 compatible: fixed file descriptor 9, no BASHPID, no read -N.

uncle_py_host_start() {
    [[ "${UNCLE_PY_HOST:-1}" != 0 && -z "${UNCLE_PY_HOST_DIR:-}" && -n "${ROOT:-}" && -f "$ROOT/scripts/lib/pyhost.py" ]] || return 0
    local dir
    dir="$(mktemp -d "${TMPDIR:-/tmp}/uncle-pyhost.XXXXXX" 2>/dev/null)" || return 0
    command python3 "$ROOT/scripts/lib/pyhost.py" serve "$dir" "$$" "$ROOT" > /dev/null 2>&1 &
    disown 2>/dev/null || true
    UNCLE_PY_HOST_DIR="$dir"          # not exported: only this shell and its subshells use it
    UNCLE_PY_HOST_PORT=""
}

python3() {
    local dir="${UNCLE_PY_HOST_DIR:-}"
    if [[ -z "$dir" ]]; then command python3 "$@"; return; fi
    local first="${1:-}"
    if [[ "$first" == -B ]]; then first="${2:-}"; fi
    # Stdin needs no test here: the host runs a call with /dev/null and REFUSEs any helper whose source mentions stdin.
    if [[ "$first" != *.py || ! -f "$first" ]]; then command python3 "$@"; return; fi
    if [[ -z "${UNCLE_PY_HOST_PORT:-}" ]]; then
        [[ -e "$dir/ready" ]] || { command python3 "$@"; return; }
        IFS= read -r UNCLE_PY_HOST_PORT < "$dir/port" || { UNCLE_PY_HOST_PORT=""; command python3 "$@"; return; }
        IFS= read -r UNCLE_PY_HOST_TOKEN < "$dir/token" || { UNCLE_PY_HOST_PORT=""; command python3 "$@"; return; }
    fi
    local LC_ALL=C _arg _env _argc="$#" _ack="" _rc="" _pid="" _out="" _err=""
    # The 2>/dev/null belongs to the group: `exec ... 2>/dev/null` would redirect this shell's own stderr for good.
    if ! { exec 9<>"/dev/tcp/127.0.0.1/$UNCLE_PY_HOST_PORT"; } 2>/dev/null; then command python3 "$@"; return; fi
    _env="$(export -p)"
    {
        printf '%d\n%s' "${#UNCLE_PY_HOST_TOKEN}" "$UNCLE_PY_HOST_TOKEN"
        printf '%d\n%s' "${#PWD}" "$PWD"
        printf '%d\n%s' "${#_argc}" "$_argc"
        for _arg in "$@"; do printf '%d\n%s' "${#_arg}" "$_arg"; done
        printf '%d\n%s' "${#_env}" "$_env"
    } >&9 2>/dev/null || { exec 9>&- 9<&-; command python3 "$@"; return; }
    if ! read -r -t 5 _ack <&9 || [[ "$_ack" != ACK ]]; then exec 9>&- 9<&-; command python3 "$@"; return; fi
    if ! read -r -t 900 _rc _pid <&9 || [[ -z "$_pid" ]]; then
        exec 9>&- 9<&-
        echo "python host: the call did not complete: python3 $*" >&2
        return 1
    fi
    exec 9>&- 9<&-
    IFS= read -r -d '' _out < "$dir/o.$_pid" || true
    IFS= read -r -d '' _err < "$dir/e.$_pid" || true
    if [[ -n "$_out" ]]; then printf '%s' "$_out"; fi
    if [[ -n "$_err" ]]; then printf '%s' "$_err" >&2; fi
    return "$_rc"
}

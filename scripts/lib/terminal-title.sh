#!/usr/bin/env bash
# Shared title ownership and interruptible workflow waits (Bash 3.2).
# The cleanup entry point is also used by the curses owner.
if [[ "${BASH_SOURCE[0]}" == "$0" && "${1:-}" == "--stop-tree" ]]; then
    python3 - "$2" "${3:-}" <<'PY'
import os
import signal
import subprocess
import sys
import time

root = int(sys.argv[1])
include_root = sys.argv[2] == 'include-root'
known = {root}
if sys.platform == 'darwin':
    # libproc can enumerate our children even when a sandbox denies ps's
    # system-wide sysctl. PROC_PIDTBSDINFO starts with flags/status/xstatus/pid/ppid.
    import ctypes
    libproc = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    def info(pid):
        buf = ctypes.create_string_buffer(512)
        if libproc.proc_pidinfo(pid, 3, 0, buf, len(buf)) <= 0:
            return None
        fields = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint))
        return fields[4], 'Z' if fields[1] == 5 else 'R'
    def processes():
        rows = {}
        pending = list(known | {os.getpid()})
        while pending:
            p = pending.pop()
            if p in rows:
                continue
            row = info(p)
            if row is None:
                continue
            rows[p] = row
            size = 64
            while True:
                children = (ctypes.c_int * size)()
                count = libproc.proc_listchildpids(p, children, ctypes.sizeof(children))
                if count < 0:
                    raise OSError(ctypes.get_errno(), 'proc_listchildpids')
                if count < size:
                    break
                size *= 2
            pending.extend(children[:count])
        # Only ancestors of this helper are needed to exclude its shell.
        p = os.getpid()
        while p != root:
            row = info(p)
            if row is None or row[0] in (0, p):
                break
            rows[p] = row
            p = row[0]
        return rows
else:
    def processes():
        rows = subprocess.check_output(['ps', '-axo', 'pid=,ppid=,stat='], text=True)
        return {int(p): (int(parent), state) for p, parent, state in
                (line.split(None, 2) for line in rows.splitlines())}

rows = processes()
# Exclude this helper and its ancestors when cleaning the calling shell.
excluded = set()
pid = os.getpid()
while pid != root and pid in rows:
    excluded.add(pid)
    pid = rows[pid][0]
sent = {}
while True:
    rows = processes()
    changed = True
    while changed:
        children = {p for p, (parent, _) in rows.items()
                    if parent in known and p not in excluded}
        changed = not children <= known
        known |= children
    known = {p for p in known if p == root or p in rows}
    live = {p for p in known if p in rows and not rows[p][1].startswith('Z')
            and (p != root or include_root)}
    if not live:
        break
    parents = {rows[p][0] for p in live}
    leaves = live - parents
    now = time.monotonic()
    for p in leaves:
        sig = signal.SIGTERM if p not in sent else signal.SIGKILL
        if p in sent and now - sent[p] < 2:
            continue
        try:
            os.kill(p, sig)
        except ProcessLookupError:
            pass
        sent.setdefault(p, now)
    time.sleep(.05)
PY
    exit $?
fi

UNCLE_TITLE_ACTIVE=0
uncle_title_begin() {
    local issue="${1:-}"
    [[ -z "${UNCLE_TITLE_OWNER:-}" && -n "$issue" && "$issue" != *[!0-9]* \
        && -t 1 && -t 2 && -n "${TERM:-}" && "$TERM" != dumb ]] || return 0
    UNCLE_TITLE_ACTIVE=1
    export UNCLE_TITLE_OWNER="$$"
    printf '\033]2;uncle issue #%s\007' "$issue" 2>/dev/null || true
}
uncle_title_end() {
    [[ "$UNCLE_TITLE_ACTIVE" == 1 ]] || return 0
    UNCLE_TITLE_ACTIVE=0
    unset UNCLE_TITLE_OWNER
    [[ -t 1 && -t 2 && -n "${TERM:-}" && "$TERM" != dumb ]] || return 0
    printf '\033]2;uncle\007' 2>/dev/null || true
}
uncle_cancel() {
    trap '' INT TERM
    bash "$ROOT/scripts/lib/terminal-title.sh" --stop-tree "$$"
    wait 2>/dev/null || true
    exit "$1"
}
uncle_run() {
    # Explicit stdin preserves gate answers: asynchronous commands otherwise
    # inherit /dev/null when job control is disabled.
    "$@" <&0 &
    local child=$! status=0
    wait "$child" || status=$?
    return "$status"
}

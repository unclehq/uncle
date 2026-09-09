#!/usr/bin/env bash
# The waiver popup, driven through a pseudo-terminal.
#
# The rest of the waiver tests run headless and therefore exercise the text
# fallback. That leaves the window itself unverified -- and an operator who
# cannot see or dismiss it is an operator who cannot decline, which is the one
# answer this gate must always accept.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export UNCLE_POPUP="$ROOT/scripts/lib/waiver-popup.py"

if ! python3 -c pass > /dev/null 2>&1; then
    echo "waiver-popup-test.sh: skipped, python3 is not available"
    exit 0
fi
python3 -c "import curses, pty" 2>/dev/null || {
    echo "waiver-popup-test.sh: skipped, this python has no curses or POSIX pseudo-terminal support"
    exit 0
}

python3 -B - <<'PY'
import os, pty, select, sys, tempfile, time

POPUP = os.environ["UNCLE_POPUP"]
failures = []


def drive(keys, ids=("MC-14", "MC-17"), settle=1.5):
    """Run the popup on a pty, send keys, return (exit status, screen, reason)."""
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    out.close()
    os.unlink(out.name)
    argv = [sys.executable, "-B", POPUP, "--report", "VERIFICATION_REPORT.md",
            "--out", out.name] + list(ids)
    pid, fd = pty.fork()
    if pid == 0:                                   # child: the popup
        os.environ["TERM"] = "xterm"
        os.environ["LINES"], os.environ["COLUMNS"] = "40", "100"
        try:
            os.execv(sys.executable, argv)
        finally:
            os._exit(127)

    screen, deadline = "", time.time() + settle
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            screen += chunk.decode("utf-8", "replace")
    for k in keys:
        os.write(fd, k.encode())
        time.sleep(0.25)
    # Drain whatever it painted after the keys, then reap.
    end = time.time() + 3
    status = None
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                pass
            else:
                screen += chunk.decode("utf-8", "replace")
        done, st = os.waitpid(pid, os.WNOHANG)
        if done:
            status = os.WEXITSTATUS(st)
            break
    if status is None:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        failures.append("the popup never exited")
        status = -1
    os.close(fd)
    reason = None
    if os.path.exists(out.name):
        with open(out.name) as fh:
            reason = fh.read().strip()
        os.unlink(out.name)
    return status, screen, reason


# --- it draws, and says what it is about ------------------------------------
status, screen, reason = drive(["a reason typed into the window", "\r"])
for needle in ("Waive a required check", "MC-14", "MC-17",
               "cannot be performed", "does not make the check pass"):
    if needle not in screen:
        failures.append("the window never showed %r" % needle)
if status != 0:
    failures.append("typing a reason and pressing Enter should record it, exit was %s" % status)
if reason != "a reason typed into the window":
    failures.append("the reason should be recorded verbatim, got %r" % reason)

# --- Esc declines, and records nothing --------------------------------------
status, screen, reason = drive(["half a reason", "\x1b"])
if status != 1:
    failures.append("Esc should decline with exit 1, got %s" % status)
if reason is not None:
    failures.append("Esc must not record a waiver, got %r" % reason)

# --- Enter on an empty box is a decline, not a blank waiver -----------------
status, screen, reason = drive(["\r"])
if status != 1:
    failures.append("an empty reason should decline with exit 1, got %s" % status)
if reason is not None:
    failures.append("an empty reason must not record a waiver, got %r" % reason)

# --- backspace edits rather than submitting ---------------------------------
status, screen, reason = drive(["abcXY", "\x7f", "\x7f", "Z", "\r"])
if reason != "abcZ":
    failures.append("backspace should edit the reason, got %r" % reason)

if failures:
    for f in failures:
        print("FAIL: " + f)
    raise SystemExit(1)
print("waiver-popup-test.sh: the popup draws, records a typed reason, and declines on Esc or empty")
PY

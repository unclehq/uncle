#!/usr/bin/env python3
"""REPL on a real pty (AC-5, AC-6, I-1 byte scan, I-5): Ctrl-C at idle and during a
build, and an attended gate answered from the same terminal. Fake drivers only."""
import os
import pty
import select
import shutil
import signal
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts" / "lib"
FAILS = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


TMP = Path(tempfile.mkdtemp(prefix="uncle-repl-pty-"))
RT, PROJ = TMP / "rt", TMP / "proj"
(RT / "scripts").mkdir(parents=True)
PROJ.mkdir()
PIDS, ANSWER = TMP / "pids", TMP / "answer"
DRIVER = RT / "scripts" / "from-issue.sh"


def set_driver(body):
    DRIVER.write_text("#!/usr/bin/env bash\n" + body)
    DRIVER.chmod(0o755)


class Pty:
    def __init__(self, args):
        env = dict(os.environ, UNCLE_PROJECT_ROOT=str(PROJ), UNCLE_RUNTIME_ROOT=str(RT), TERM="xterm",
                   UNCLE_PIDFILE=str(PIDS), UNCLE_ANSWER=str(ANSWER))
        env.pop("UNCLE_STARTUP_ATTENDED", None)
        env.pop("UNCLE_STARTUP_UNATTENDED", None)
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execvpe(sys.executable, [sys.executable, "-B", str(LIB / "uncle_repl.py")] + args, env)
        self.buf = b""

    def read_until(self, needle, timeout=20):
        end = time.time() + timeout
        while needle.encode() not in self.buf and time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.2)
            if r:
                try:
                    chunk = os.read(self.fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                self.buf += chunk
        return needle.encode() in self.buf

    def mark(self):
        self.buf = b""

    def send(self, data):
        os.write(self.fd, data)

    def wait(self, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            self.read_until("\0", 0.2)
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                return os.waitstatus_to_exitcode(status)
        os.kill(self.pid, signal.SIGKILL)
        os.waitpid(self.pid, 0)
        return None


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# Idle Ctrl-C: first cancels the line, second consecutive quits (SB-8)
set_driver('echo "Workflow complete."\n')
s = Pty(["--attended"])
check("prompt shown on a tty", s.read_until("uncle> "))
s.mark()
s.send(b"\x03")
check("first idle Ctrl-C cancels line and re-prompts", s.read_until("uncle> "))
s.send(b"\x03")
code = s.wait()
check("second consecutive Ctrl-C quits with 0", code == 0, str(code))
scan = s.buf
check("no alt-screen / cursor-addressing escapes (I-1)",
      not any(x in scan for x in (b"\x1b[?1049", b"\x1b[H", b"\x1b[2J", b"\x1b[?25")), repr(scan[:200]))

# Ctrl-C during a build: build stopped, prompt returns, nothing left running (SB-9)
set_driver('echo $$ > "$UNCLE_PIDFILE"\nsleep 300 &\necho $! >> "$UNCLE_PIDFILE"\necho building\nwait\n')
s = Pty(["--attended"])
s.read_until("uncle> ")
s.send(b"/mode unattended\r")
s.read_until("mode: unattended")
s.mark()
s.send(b"build issue 5\r")
s.read_until("building")
s.send(b"\x03")
check("prompt returns after Ctrl-C during build", s.read_until("uncle> "), repr(s.buf[-300:]))
check("interrupted build is not reported complete", b"Workflow complete" not in s.buf)
pids = [int(x) for x in PIDS.read_text().split()]
time.sleep(0.5)
check("no build process left after Ctrl-C", len(pids) == 2 and not any(alive(x) for x in pids), str(pids))
s.send(b"/quit\r")
code = s.wait()
check("session exits after /quit with the interrupted build code", code == 130, str(code))

# Attended gate answered from the same terminal; marked attended for the driver (AC-6, I-5)
set_driver('echo "attended=${UNCLE_ATTENDED_STDIN:-unset}" > "$UNCLE_ANSWER.env"\n'
           'echo "Human gate: approve the plan? [y/N]"\nread -r a\necho "$a" > "$UNCLE_ANSWER"\necho "Workflow complete."\n')
s = Pty(["--attended"])
s.read_until("uncle> ")
s.send(b"build issue 6\r")
check("gate prompt reaches the terminal", s.read_until("Human gate:"))
s.send(b"yes\r")
s.read_until("Workflow complete.")
s.read_until("uncle> ")
check("gate answer typed in the session reaches the driver", ANSWER.exists() and ANSWER.read_text().strip() == "yes")
check("driver ran in attended mode", (TMP / "answer.env").read_text().strip() == "attended=1")
s.send(b"/quit\r")
code = s.wait()
check("completed attended build exits 0", code == 0, str(code))

shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAILS else 0)

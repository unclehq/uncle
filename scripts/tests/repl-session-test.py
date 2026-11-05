#!/usr/bin/env python3
"""Bare `uncle --noui` REPL session (AC-1..4, 7, 9, I-1, I-2, I-4, I-6) with a fake
chat runner and fake drivers. No live agent, no network."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))
FAILS = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


TMP = Path(tempfile.mkdtemp(prefix="uncle-repl-test-"))
RT, PROJ = TMP / "rt", TMP / "proj"
(RT / "scripts").mkdir(parents=True)
PROJ.mkdir()
for name, body in {
    "from-issue.sh": 'echo "fake-issue-driver $*"\necho "Workflow complete."\n',
    "stagegate.sh": 'echo "fake-stagegate-driver"\necho "Workflow complete."\n',
    "slow.sh": 'echo $$ > "$UNCLE_PIDFILE"\nsleep 300 &\necho $! >> "$UNCLE_PIDFILE"\nwait\n',
}.items():
    p = RT / "scripts" / name
    p.write_text("#!/usr/bin/env bash\n" + body)
    p.chmod(0o755)
(RT / "scripts" / "from-issue-slow.sh").write_text("")


def runner(kind, payload=""):
    """A fake chat runner: stream-json assistant event on stdout."""
    p = TMP / f"chat-{kind}.py"
    if kind == "fail":
        p.write_text("import sys\nsys.stdin.read()\nsys.exit(1)\n")
    else:
        p.write_text("import sys, json\nsys.stdin.read()\n"
                     "print(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':%r}]}}))\n" % payload)
    return f"{sys.executable} {p}"


def session(lines, runner_cmd=None, extra=None, raw=None):
    env = dict(os.environ, UNCLE_PROJECT_ROOT=str(PROJ), UNCLE_RUNTIME_ROOT=str(RT),
               UNCLE_STARTUP_UNATTENDED="1", UNCLE_SKIP_UPGRADE="1")
    env.pop("UNCLE_STARTUP_ATTENDED", None)
    if runner_cmd:
        env["UNCLE_REPL_RUNNER"] = runner_cmd
    env.update(extra or {})
    data = raw if raw is not None else ("\n".join(lines) + "\n" if lines else "").encode()
    r = subprocess.run([sys.executable, "-B", str(LIB / "uncle_repl.py")], input=data, env=env,
                       capture_output=True, timeout=60)
    return r.returncode, r.stdout.decode(), r.stderr.decode()


# AC-1 / SB-1 / SB-13: banner, EOF exits 0, no prompt decoration, no escapes
rc, out, err = session([])
check("EOF with no input exits 0", rc == 0, str(rc))
check("banner printed", "interactive session" in out and "/quit" in out, out)
check("piped run has no prompt decoration or escapes", "uncle> " not in out and "\x1b" not in out + err)

# AC-2 / SB-2: free-form reply, prompt-less, session continues
rc, out, err = session(["hello there", "/mode"], runner("ok", "Hi, I am Uncle."))
check("free-form line prints plain reply", "Hi, I am Uncle." in out and "mode: unattended" in out, out)
check("reply session exits 0", rc == 0, str(rc))

# SB-3: runner failure -> one-line error, session survives
rc, out, err = session(["hello", "/mode"], runner("fail"))
check("runner failure prints one error line", err.count("chat failed") == 1, err)
check("session survives runner failure", "mode: unattended" in out and rc == 0, f"{rc} {out}")

# AC-3 / SB-4: issue build goes through the executor and the fake driver
rc, out, err = session(["build issue 7", "/mode"])
check("build issue 7 runs the issue driver with the number", "fake-issue-driver 7" in out, out)
check("build exit 0 and prompt returns", rc == 0 and "mode: unattended" in out, f"{rc}")

# SB-5: NL create-app request validated and run (stagegate driver)
action = {"uncle_action": "create_app", "message": "Building.", "document": "A tiny app", "start": True}
rc, out, err = session(["make me a tiny app"], runner("create", json.dumps(action)))
check("create_app request starts the stagegate driver", "fake-stagegate-driver" in out and "Building." in out, out + err)
check("brief written under project", any(PROJ.rglob("REQUIREMENTS.md")) or any(PROJ.rglob("REQUIREMENTS.md.previous")))

# AC-3 / I-2 refusals: a smuggled field and an unsupported action never reach a driver
bad = {"uncle_action": "run_app", "message": "x", "shell": "touch /tmp/pwned"}
rc, out, err = session(["do it"], runner("bad", json.dumps(bad)))
check("action with unexpected field is refused, no driver", "fake-" not in out and "unexpected fields" in err, out + err)
rc, out, err = session(["do it"], runner("bad2", json.dumps({"uncle_action": "rm_rf", "message": "x"})))
check("unsupported action is refused, no driver", "fake-" not in out and "unsupported" in err, out + err)

# SB-10: attended build with piped stdin refuses, session continues, exit 2
rc, out, err = session(["build issue 3", "/mode"], extra={"UNCLE_STARTUP_ATTENDED": "1", "UNCLE_STARTUP_UNATTENDED": "0"})
check("attended piped build refused with exit 2", rc == 2 and "needs an interactive terminal" in err, f"{rc} {err}")
check("session continues after refusal", "mode: attended" in out, out)

# AC-4: blank lines ignored, order kept, over-long line bounded, last build result wins
long = b"x" * (1048576 + 10) + b"\n"
rc, out, err = session(None, raw=b"\n\n/mode\n" + long + b"build issue 4\n/mode unattended\n")
check("blank ignored; long line rejected with message", "line too long" in err, err)
check("later lines still run in order after long line", "fake-issue-driver 4" in out and out.index("mode: unattended") < out.index("fake-issue-driver 4"))
check("exit code is last build result after refusal", rc == 0, str(rc))

# AC-9 / SB-14: slash commands, usage, settings
rc, out, err = session(["/help", "/mode bogus", "/issue x", "/settings", "/stop", "/frob", "/quit", "/mode"])
check("/help lists commands", "/quit" in out)
check("/mode with bad arg prints usage", "usage: /mode" in err)
check("/issue with bad arg prints usage", "usage: /issue N" in err)
check("/settings prints mode and root", "mode: unattended" in out and str(PROJ) in out)
check("/quit stops reading further lines", out.count("mode: ") == 1, out)
check("unknown command refused", "unknown command: /frob" in err and rc == 2, f"{rc}")
rc, out, err = session(["/mode attended", "/mode"])
check("/mode attended changes mode", "mode: attended" in out and out.count("mode: attended") == 2, out)

# I-6: conversation text never reaches the driver argv
rc, out, err = session(["secret-history-token", "build issue 8"], runner("ok", "noted"))
check("history is not replayed into driver", "fake-issue-driver 8" in out and "secret-history-token" not in out.split("noted", 1)[1])

# I-1: importing the session pulls in no curses
r = subprocess.run([sys.executable, "-B", "-c",
                    "import sys; sys.path.insert(0, %r); import uncle_repl; sys.exit(int('curses' in sys.modules or 'uncle_tui' in sys.modules))" % str(LIB)])
check("uncle_repl imports no curses/TUI", r.returncode == 0)

# I-4 / AC-7: SIGTERM mid-build leaves no child
(RT / "scripts" / "from-issue.sh").write_text("#!/usr/bin/env bash\n" + (RT / "scripts" / "slow.sh").read_text().split("\n", 1)[1] if False else
                                                 "#!/usr/bin/env bash\necho $$ > \"$UNCLE_PIDFILE\"\nsleep 300 &\necho $! >> \"$UNCLE_PIDFILE\"\nwait\n")
pidfile = TMP / "pids"
env = dict(os.environ, UNCLE_PROJECT_ROOT=str(PROJ), UNCLE_RUNTIME_ROOT=str(RT), UNCLE_STARTUP_UNATTENDED="1",
           UNCLE_PIDFILE=str(pidfile))
p = subprocess.Popen([sys.executable, "-B", str(LIB / "uncle_repl.py")], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
p.stdin.write(b"build issue 9\n")
p.stdin.flush()
for _ in range(100):
    if pidfile.exists() and len(pidfile.read_text().split()) >= 2:
        break
    time.sleep(0.1)
pids = [int(x) for x in pidfile.read_text().split()] if pidfile.exists() else []
check("build child started", len(pids) == 2, str(pids))
p.send_signal(signal.SIGTERM)
try:
    code = p.wait(timeout=30)
except subprocess.TimeoutExpired:
    p.kill()
    code = None
time.sleep(0.5)


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


check("SIGTERM exits 143", code == 143, str(code))
check("no build child survives SIGTERM", pids and not any(alive(x) for x in pids), str(pids))
for x in pids:
    try:
        os.kill(x, signal.SIGKILL)
    except OSError:
        pass

# I-2 defect injection: with validation neutralised the refusal test must detect it
import repl_actions  # noqa: E402
import uncle_headless  # noqa: E402


def smuggle_reaches_driver():
    calls = []
    orig_run, orig_prep = uncle_headless.run, uncle_headless.prepare_driver
    uncle_headless.run = lambda *a, **k: calls.append(a) or 0
    uncle_headless.prepare_driver = lambda *a, **k: ["x"]
    ctx = SimpleNamespace(root=str(PROJ), err=sys.stderr, out=sys.stdout, env={}, attended=False,
                          stdin_fd=0, confirm=lambda q: True, runtime=str(RT))
    try:
        code = repl_actions.execute({"uncle_action": "github_issue", "issue": "1", "start": True,
                                     "message": "", "shell": "x"}, ctx)
    finally:
        uncle_headless.run, uncle_headless.prepare_driver = orig_run, orig_prep
    return code, calls


import io  # noqa: E402
sys.stderr, saved = io.StringIO(), sys.stderr
code, calls = smuggle_reaches_driver()
check("executor refuses smuggled field (exit 2, no run)", code == 2 and not calls, f"{code} {calls}")
orig_validate = repl_actions.validate
repl_actions.validate = lambda a: dict(a)  # injected defect: no validation
code, calls = smuggle_reaches_driver()
repl_actions.validate = orig_validate
sys.stderr = saved
check("defect injection (validation removed) is detected by the same probe", code != 2 and bool(calls), f"{code} {calls}")


# ---- Added regression coverage (repair): helpers -------------------------------------------------
import io  # noqa: E402,F811
import threading  # noqa: E402
import uncle_repl  # noqa: E402
import home_actions  # noqa: E402,F811

(RT / "scripts" / "from-issue.sh").write_text(
    "#!/usr/bin/env bash\n" + 'echo "fake-issue-driver $*"\n[ -n "${FAKE_ESC:-}" ] && printf \'title\\033]0;pwn\\007\\033[31mred\\n\'\n'
    'echo "Workflow complete."\nexit ${FAKE_RC:-0}\n')


def inproc(data, env_extra=None, argv=(), root=None):
    """Drive a real Session in this process on a pipe; returns (code, stdout, stderr)."""
    r, w = os.pipe()
    os.write(w, data)
    os.close(w)
    env = dict(os.environ, UNCLE_PROJECT_ROOT=str(root or PROJ), UNCLE_RUNTIME_ROOT=str(RT), UNCLE_SKIP_UPGRADE="1")
    for k in ("UNCLE_STARTUP_ATTENDED", "UNCLE_STARTUP_UNATTENDED", "UNCLE_REPL_RUNNER", "FAKE_RC", "FAKE_ESC"):
        env.pop(k, None)
    env.update(env_extra or {"UNCLE_STARTUP_UNATTENDED": "1"})
    o, e = io.StringIO(), io.StringIO()
    sess = uncle_repl.Session(list(argv), env, SimpleNamespace(stdin_fd=r, stdout=o, stderr=e))
    try:
        code = sess.loop()
    finally:
        os.close(r)
    return code, o.getvalue(), e.getvalue()


# AC-4 / D-8: exit-code matrix -- code comes only from the last build-or-refusal event
rc, out, err = session(["build issue 4", "hello", "/mode", "/help"], runner("ok", "hi"), extra={"FAKE_RC": "1"})
check("matrix: failed build then chat/slash lines -> 1", rc == 1, str(rc))
rc, out, err = session(["/frob", "build issue 4"])
check("matrix: refusal then successful build -> 0", rc == 0, str(rc))
rc, out, err = session(["build issue 4", "/frob"])
check("matrix: successful build then refusal -> 2", rc == 2, str(rc))
rc, out, err = session(["build issue 4", "/frob", "hello", "/mode"], runner("ok", "hi"), extra={"FAKE_RC": "1"})
check("matrix: failed build then refusal then chat -> 2", rc == 2, str(rc))
rc, out, err = session(["/frob", "build issue 4"], extra={"FAKE_RC": "1"})
check("matrix: refusal then failed build -> 1", rc == 1, str(rc))
rc, out, err = session(["/mode", "/help", "hello"], runner("ok", "hi"))
check("matrix: no build/refusal event -> 0", rc == 0, str(rc))
orig_run = uncle_headless.run
uncle_headless.run = lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt())
code, out, err = inproc(b"build issue 4\n")
uncle_headless.run = orig_run
check("matrix: Ctrl-C-stopped build then EOF -> 130", code == 130, str(code))


def last_refusal_code():
    return inproc(b"build issue 4\n/frob\n")[0]


check("exit-code probe: refusal last -> 2", last_refusal_code() == 2)
orig_refuse = uncle_repl.Session.refuse
uncle_repl.Session.refuse = lambda self, t: self.complain(t)  # injected defect: refusals leave the code alone
injected = last_refusal_code()
uncle_repl.Session.refuse = orig_refuse
check("defect injection (refusal ignored) detected by exit-code probe", injected != 2, str(injected))

# AC-4: over-long line boundaries
rc, out, err = session(None, raw=b"x" * 1048576 + b"\n/mode\n", runner_cmd=runner("ok", "boundary-ok"))
check("exactly 1048576 bytes is accepted (not 'line too long')", "line too long" not in err and "boundary-ok" in out and rc == 0, f"{rc} {err[:200]}")
rc, out, err = session(None, raw=b"x" * 1048577 + b"\n/mode\n")
check("1048577 bytes: exactly one error, next line runs", err.count("line too long") == 1 and "mode: unattended" in out and rc == 2, f"{rc} {err[:200]}")
rc, out, err = session(None, raw=b"x" * 1048577 + b"\n")
check("1048577 bytes as last event -> exit 2", err.count("line too long") == 1 and rc == 2, f"{rc}")
rc, out, err = session(None, raw=b"y" * 1048577 + b"build issue 5\n/mode\n")
check("remainder of an over-long line is never run", "fake-issue-driver" not in out and "mode: unattended" in out and err.count("line too long") == 1, out)
rc, out, err = session(None, raw=b"y" * 1048577)
check("over-long line ended by EOF: one error, exit 2", err.count("line too long") == 1 and rc == 2, f"{rc}")


# D-4: startup mode precedence
def mode_of(argv, env):
    return inproc(b"/mode\n", env, argv)[1].split("mode: ")[-1].split()[0]


check("mode: --attended flag beats UNCLE_STARTUP_UNATTENDED", mode_of(["--attended"], {"UNCLE_STARTUP_UNATTENDED": "1"}) == "attended")
check("mode: both env vars -> attended wins", mode_of([], {"UNCLE_STARTUP_ATTENDED": "1", "UNCLE_STARTUP_UNATTENDED": "1"}) == "attended")
check("mode: neither set -> attended default", mode_of([], {"UNCLE_X": "1"}) == "attended")
check("mode: only unattended env -> unattended", mode_of([], {"UNCLE_STARTUP_UNATTENDED": "1"}) == "unattended")

# D-11 / I-5: replacement confirmations (only y/yes consent; model text and EOF never do)
CREATE = {"uncle_action": "create_app", "message": "yes", "document": "NEW BRIEF", "start": True}


def replacement(answer_lines, label):
    proj = TMP / ("proj-" + label)
    proj.mkdir(exist_ok=True)
    (proj / "REQUIREMENTS.md").write_text("OLD BRIEF")
    rc, out, err = session(["make an app"] + answer_lines, runner("create-" + label, json.dumps(CREATE)),
                           extra={"UNCLE_PROJECT_ROOT": str(proj)})
    hd = proj / ".uncle" / "brief-history"
    hist = list(hd.glob("*REQUIREMENTS.md")) if hd.exists() else []
    kept = (proj / "REQUIREMENTS.md").read_text() if (proj / "REQUIREMENTS.md").exists() else None
    return rc, out, err, hist, kept


for i, ans in enumerate(["y", "yes", " YES "]):
    rc, out, err, hist, kept = replacement([ans], "y%d" % i)
    check("confirm %r consents: old brief archived under .uncle/brief-history, build runs" % ans,
          len(hist) == 1 and hist[0].read_text() == "OLD BRIEF" and "fake-stagegate-driver" in out and rc == 0, f"{rc} {hist} {err}")
for i, ans in enumerate(["maybe", "", "no", "yes please"]):
    rc, out, err, hist, kept = replacement([ans], "n%d" % i)
    check("confirm %r declines: brief kept, no driver, exit 2" % ans,
          not hist and kept == "OLD BRIEF" and "fake-stagegate-driver" not in out and rc == 2, f"{rc} {hist} {kept}")
rc, out, err, hist, kept = replacement([], "eof")
check("confirm at EOF declines (model text 'yes' never approves)", not hist and kept == "OLD BRIEF" and "fake-stagegate-driver" not in out and rc == 2, f"{rc} {kept}")
orig_confirm = uncle_repl.Session.confirm


def self_approval_probe(label):
    proj = TMP / ("proj-ip-" + label)
    proj.mkdir(exist_ok=True)
    (proj / "REQUIREMENTS.md").write_text("OLD BRIEF")
    orig_ask = uncle_repl.Session._ask
    uncle_repl.Session._ask = lambda self, line: ("yes", home_actions.parse_reply(json.dumps(CREATE)))
    try:
        inproc(b"make an app\n", root=proj)
    finally:
        uncle_repl.Session._ask = orig_ask
    f = proj / "REQUIREMENTS.md"
    return f.exists() and f.read_text() == "OLD BRIEF"


check("gate self-approval probe: model reply cannot confirm replacement", self_approval_probe("a"))
uncle_repl.Session.confirm = lambda self, q: True  # injected defect: self-approval
injected_ok = self_approval_probe("b")
uncle_repl.Session.confirm = orig_confirm
check("defect injection (self-approving confirm) detected by gate probe", not injected_ok)

# I-1: escape bytes from model replies, driver output and exception text never reach the terminal
esc_reply = "hi\x1b]0;pwn\x07\x1b[31m red\x9b"
rc, out, err = session(["hello"], runner("esc", esc_reply))
check("escape bytes in a model reply are stripped", "\x1b" not in out + err and "\x07" not in out and "hi" in out and "red" in out, repr(out))
rc, out, err = session(["build issue 6"], extra={"FAKE_ESC": "1"})
check("escape bytes in driver/issue-title output are stripped", "\x1b" not in out + err and "\x07" not in out and "title" in out, repr(out))
orig_ask = uncle_repl.Session._ask
uncle_repl.Session._ask = lambda self, line: (_ for _ in ()).throw(RuntimeError("bad\x1b[31m\x1b]0;x\x07boom"))
code, out, err = inproc(b"hello\n")
uncle_repl.Session._ask = orig_ask
check("escape bytes in exception text are stripped", "\x1b" not in err and "\x07" not in err and "boom" in err, repr(err))


def esc_probe():
    return "\x1b" in "".join(inproc(b"/frob\x1b[31m\n")[1:])


check("escape probe: ESC filtered from echoed output", not esc_probe())


class _Passthrough:
    def feed(self, data, final=False):
        return data.decode("utf-8", "replace")


orig_flt = uncle_repl.EscapeFilter
uncle_repl.EscapeFilter = _Passthrough  # injected defect: no filtering
injected = esc_probe()
uncle_repl.EscapeFilter = orig_flt
check("defect injection (EscapeFilter removed) detected by escape probe", injected)


# Handler discipline: signal handlers identical before/after a build
def handlers():
    return signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)


def clobbering_run(rc=0, exc=None):
    def fake(*a, **k):
        signal.signal(signal.SIGTERM, lambda *x: None)
        signal.signal(signal.SIGINT, lambda *x: None)
        if exc:
            raise exc
        return rc
    return fake


before = handlers()
inproc(b"build issue 1\n")
check("getsignal identical around a real normal build", handlers() == before)
inproc(b"build issue 1\n", {"UNCLE_STARTUP_UNATTENDED": "1", "FAKE_RC": "1"})
check("getsignal identical around a real failed build", handlers() == before)
for label, stub in (("normal", clobbering_run(0)), ("failed", clobbering_run(1)),
                    ("Ctrl-C-stopped", clobbering_run(exc=KeyboardInterrupt())), ("raising", clobbering_run(exc=RuntimeError("x")))):
    uncle_headless.run = stub
    inproc(b"build issue 1\n")
    uncle_headless.run = orig_run
    check("getsignal restored after a run() that replaced handlers (%s)" % label, handlers() == before, str(handlers()))
r_, w_ = os.pipe()
os.close(w_)
uncle_repl.main([], dict(os.environ, UNCLE_PROJECT_ROOT=str(PROJ), UNCLE_RUNTIME_ROOT=str(RT)),
                SimpleNamespace(stdin_fd=r_, stdout=io.StringIO(), stderr=io.StringIO()))
os.close(r_)
check("getsignal identical before and after main()", handlers() == before)

# I-4: SIGTERM during an in-flight chat request leaves no runner process
chat_pid = TMP / "chat-pid"
(TMP / "chat-slow.py").write_text("import os, sys, time\nsys.stdin.read()\nopen(%r, 'w').write(str(os.getpid()))\ntime.sleep(300)\n" % str(chat_pid))
env = dict(os.environ, UNCLE_PROJECT_ROOT=str(PROJ), UNCLE_RUNTIME_ROOT=str(RT), UNCLE_STARTUP_UNATTENDED="1",
           UNCLE_REPL_RUNNER=f"{sys.executable} {TMP / 'chat-slow.py'}")
p = subprocess.Popen([sys.executable, "-B", str(LIB / "uncle_repl.py")], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
p.stdin.write(b"hello\n")
p.stdin.flush()
for _ in range(100):
    if chat_pid.exists() and chat_pid.read_text():
        break
    time.sleep(0.1)
cpid = int(chat_pid.read_text()) if chat_pid.exists() and chat_pid.read_text() else 0
check("chat runner started", cpid > 0)
p.send_signal(signal.SIGTERM)
try:
    code = p.wait(timeout=30)
except subprocess.TimeoutExpired:
    p.kill()
    code = None
time.sleep(0.5)
check("SIGTERM during chat exits 143", code == 143, str(code))
check("no chat runner survives SIGTERM", cpid > 0 and not alive(cpid), str(cpid))
if cpid:
    try:
        os.kill(cpid, signal.SIGKILL)
    except OSError:
        pass


def _swallow(fn):
    try:
        fn()
    except Exception:
        pass


def sigterm_leaves_chat_runner():
    """In-process: start a real chat turn, deliver the session's SIGTERM handler, report whether the runner lives."""
    import repl_chat
    pidf = TMP / "chat-pid2"
    pidf.unlink(missing_ok=True)
    (TMP / "chat-slow2.py").write_text("import os, sys, time\nsys.stdin.read()\nopen(%r, 'w').write(str(os.getpid()))\ntime.sleep(300)\n" % str(pidf))
    sess = uncle_repl.Session([], dict(os.environ, UNCLE_PROJECT_ROOT=str(PROJ)),
                              SimpleNamespace(stdin_fd=0, stdout=io.StringIO(), stderr=io.StringIO()))
    t = threading.Thread(target=lambda: _swallow(lambda: repl_chat.ask(
        [sys.executable, str(TMP / "chat-slow2.py")], "p", str(PROJ), dict(os.environ), TMP / "c2.log")), daemon=True)
    t.start()
    for _ in range(100):
        if pidf.exists() and pidf.read_text():
            break
        time.sleep(0.1)
    pid = int(pidf.read_text())
    try:
        sess.on_sigterm(signal.SIGTERM, None)
    except SystemExit:
        pass
    time.sleep(0.5)
    live = alive(pid)
    repl_chat._cancelled.set()
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    t.join(10)
    return live


check("orphan probe: session SIGTERM handler kills the chat runner", not sigterm_leaves_chat_runner())
import repl_chat as _rc  # noqa: E402
orig_term = _rc.terminate
_rc.terminate = lambda: None  # injected defect: handler no longer kills the chat runner
leaked = sigterm_leaves_chat_runner()
_rc.terminate = orig_term
check("defect injection (terminate removed) detected by orphan probe", leaked)

# I-2 parse_reply bypass defect injection: the executor must refuse a smuggled field only because parse_reply validates
sys.stderr = io.StringIO()
orig_parse = home_actions.parse_reply
home_actions.parse_reply = lambda text: json.loads(text)  # injected defect: no parse_reply validation
code, calls = smuggle_reaches_driver()
home_actions.parse_reply = orig_parse
sys.stderr = saved
check("defect injection (parse_reply bypassed) is detected by the smuggled-field probe", code != 2 and bool(calls), f"{code} {calls}")

# TUI and REPL share one issue-request matcher
sys.path.insert(0, str(ROOT))
try:
    import uncle_tui  # noqa: E402
    check("ISSUE_REQUEST_RE is one shared object (uncle_tui is home_actions)", uncle_tui.ISSUE_REQUEST_RE is home_actions.ISSUE_REQUEST_RE)
    # MC-404 automated part: the TUI home still routes "build issue N" as an issue request and
    # leaves slash commands and free text to the chat path, using the shared matcher.
    rx = uncle_tui.ISSUE_REQUEST_RE
    check("TUI matcher accepts 'build issue 1' and '#12' forms", bool(rx.fullmatch("build issue 1")) and bool(rx.fullmatch("build issue #12")))
    check("TUI matcher rejects /help and free text", not rx.fullmatch("/help") and not rx.fullmatch("hello there") and not rx.fullmatch("build issue"))
except Exception as exc:  # pragma: no cover
    check("uncle_tui importable for identity check", False, str(exc))

# Home-agent parity: without a runner override the REPL runs the tool-enabled agent and
# grants a denied Bash call (auto in unattended mode, after y in attended mode), then retries.
fakebin = TMP / "fakebin"
fakebin.mkdir()
(fakebin / "claude").write_text("""#!/usr/bin/env python3
import sys, json
a = sys.argv; sys.stdin.read()
ok = 'Bash(echo hi)' in a[a.index('--allowedTools')+1]
print(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':'ran it: hi' if ok else 'denied'}]}}))
print(json.dumps({'type':'result','permission_denials':[] if ok else [{'tool_name':'Bash','tool_input':{'command':'echo hi'}}]}))
""")
(fakebin / "claude").chmod(0o755)
agent_env = {"PATH": f"{fakebin}:{os.environ['PATH']}"}
rc, out, err = session(["run echo hi"], extra=agent_env)
check("unattended: denied Bash is auto-granted and retried", "ran it: hi" in out and "Auto mode" in out, out + err)
rc, out, err = session(["run echo hi", "y"], extra=dict(agent_env, UNCLE_STARTUP_ATTENDED="1", UNCLE_STARTUP_UNATTENDED="0"))
check("attended: denied Bash asks, y grants and retries", "Allow exactly this" in out and "ran it: hi" in out, out + err)
rc, out, err = session(["run echo hi", "n"], extra=dict(agent_env, UNCLE_STARTUP_ATTENDED="1", UNCLE_STARTUP_UNATTENDED="0"))
check("attended: n declines the grant", "ran it: hi" not in out, out + err)

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAILS else 0)

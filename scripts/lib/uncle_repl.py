"""Line-based interactive session for bare `uncle --noui` (no curses)."""
import os
import time
import re
import signal
import sys
from types import SimpleNamespace

import home_actions
import repl_actions
import repl_chat
import uncle_headless
from uncle_headless import EscapeFilter

MAX_LINE = 1048576
STAGES = ("triage", "plan", "review", "implement", "verify", "do")
USAGE = {
    "help": "usage: /help",
    "quit": "usage: /quit",
    "exit": "usage: /exit",
    "mode": "usage: /mode [attended|unattended]",
    "issue": "usage: /issue N",
    "stop": "usage: /stop",
    "resume": "usage: /resume [N]",
    "clear": "usage: /clear",
    "triage": "usage: /triage",
    "do": "usage: /do",
    "settings": "usage: /settings",
}
HELP = ("Type a message to chat, or a request such as 'build issue 12'.\n"
        "Commands: /help /mode [attended|unattended] /issue N /stop /resume [N] /clear "
        "/triage /do /settings /quit\n")


class Out:
    """The single escape-filtered writer for every REPL stdout/stderr byte."""

    def __init__(self, stream):
        self.stream, self.flt = stream, EscapeFilter()

    def write(self, text):
        if isinstance(text, bytes):
            data = text
        else:
            data = str(text).encode("utf-8", "replace")
        clean = self.flt.feed(data)
        if clean:
            self.stream.write(clean)
        return len(text)

    def flush(self):
        try:
            self.stream.flush()
        except (OSError, ValueError):
            pass


class LineReader:
    """Unbuffered fd line reader with a byte bound; never reads past the newline."""

    def __init__(self, fd, tty=False):
        self.fd, self.tty = fd, tty

    def read(self, prompt=""):
        """Return (status, line): ok | long | eof. Raises KeyboardInterrupt."""
        if self.tty and self.fd == 0:
            if prompt:
                sys.stdout.write(prompt)
                sys.stdout.flush()
            try:
                import readline  # noqa: F401  (line editing when available)
            except ImportError:
                pass
        buf, over = bytearray(), False
        while True:
            try:
                ch = os.read(self.fd, 1)
            except InterruptedError:
                continue
            if not ch:
                if over:
                    return "long", ""
                if buf:
                    return "ok", buf.decode("utf-8", "replace")
                return "eof", ""
            if ch == b"\n":
                if over:
                    return "long", ""
                return "ok", buf.decode("utf-8", "replace").rstrip("\r")
            if not over:
                if len(buf) >= MAX_LINE:
                    over = True
                    buf = bytearray()
                else:
                    buf += ch


class Session:
    def __init__(self, argv, env, io):
        self.env = dict(os.environ if env is None else env)
        io = io or SimpleNamespace()
        self.in_fd = getattr(io, "stdin_fd", 0)
        raw_out = getattr(io, "stdout", None) or sys.stdout
        raw_err = getattr(io, "stderr", None) or sys.stderr
        self.out, self.err = Out(raw_out), Out(raw_err)
        try:
            self.tty = os.isatty(self.in_fd)
        except OSError:
            self.tty = False
        self.reader = LineReader(self.in_fd, self.tty)
        self.root = self.env.get("UNCLE_PROJECT_ROOT") or os.getcwd()
        self.runtime = self.env.get("UNCLE_RUNTIME_ROOT") or self.env.get("UNCLE_RUNTIME") or self.root
        if "--attended" in argv or self.env.get("UNCLE_STARTUP_ATTENDED") == "1":
            attended = True
        elif self.env.get("UNCLE_STARTUP_UNATTENDED") == "1":
            attended = False
        else:
            # Plain `uncle --noui`: like the TUI, auto mode is the default and
            # only an explicit `misc.auto_mode false` runs attended.
            attended = self._config_auto_mode() is False
        self.attended = attended
        self.prompt_on = self.tty or self.env.get("UNCLE_REPL_PROMPT") == "1"
        self.code = 0
        self.history = []
        self.idle_ctrlc = 0
        self.chat = None
        self.running = False
        self.last_action = None
        self.started = time.time()

    # -- output helpers
    def say(self, text):
        self.out.write(text if text.endswith("\n") else text + "\n")
        self.out.flush()

    def complain(self, text):
        self.err.write(text if text.endswith("\n") else text + "\n")
        self.err.flush()

    def refuse(self, text):
        self.complain(text)
        self.code = 2

    def _config_auto_mode(self):
        path = self.env.get("UNCLE_CONFIG") or os.path.join(self.root, ".uncle", "config")
        value = ""
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == "misc.auto_mode":
                        value = parts[1].lower()
        except OSError:
            pass
        return value != "false"

    # -- confirmations: only user input on the REPL reader, y/yes consents.
    # An unattended session has no one to ask: every question is answered yes.
    def confirm(self, question):
        if not self.attended:
            self.say("Auto mode: " + question + " yes")
            return True
        self.say(question + " [y/N]")
        try:
            status, line = self.reader.read("")
        except KeyboardInterrupt:
            return False
        return status == "ok" and line.strip().lower() in ("y", "yes")

    # -- chat
    def _terminate_chat(self):
        for target in (self.chat, repl_chat):
            fn = getattr(target, "terminate", None) if target is not None else None
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass

    def _cancel_chat(self):
        fn = getattr(self.chat, "cancel", None)
        if callable(fn):
            try:
                fn()
                return
            except Exception:
                pass
        self._terminate_chat()

    def _ask(self, line):
        if self.chat is None:
            self.chat = repl_chat.ChatSession(self.root, self.env, self.attended, self.confirm, self.say)
        self.chat.attended = self.attended
        return self.chat.ask(line, self.history)

    # -- actions
    def ctx(self, text, change=False):
        return SimpleNamespace(root=self.root, runtime=self.runtime, attended=self.attended,
                               env=self.env, out=self.out, err=self.err, stdin_fd=self.in_fd,
                               confirm=self.confirm, text=text, history=self.history,
                               issue_change=change, session=self)

    def execute(self, action, text, change=False):
        """Run a validated action; the result of a build or refusal sets the exit code."""
        saved = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
        self.running = True
        try:
            code = repl_actions.execute(action, self.ctx(text, change))
        except KeyboardInterrupt:
            code = 130
        except Exception as exc:
            self.complain("uncle --noui: action failed: %s" % exc)
            code = 1
        finally:
            self.running = False
            for s, h in saved.items():
                if signal.getsignal(s) is not h:
                    signal.signal(s, h)
        if isinstance(code, int):
            self.code = code
        if self.code == 143:
            raise SystemExit(143)

    def issue_action(self, m):
        ref = m.group("issue")
        return {"uncle_action": "github_issue", "issue": ref.lstrip("#"), "start": True,
                "message": ""}

    # -- lines
    def slash(self, line):
        parts = line.split()
        name = parts[0][1:].lower()
        args = parts[1:]
        if len(name) == 1 and "a" <= name <= "z":
            cands = list(USAGE)
            for extra in ("quit", "exit"):
                if extra not in cands:
                    cands.append(extra)
            hits = [c for c in cands if c.startswith(name)]
            if len(hits) == 1:
                name = hits[0]
            elif len(hits) > 1:
                self.refuse("ambiguous command: /%s (matches: %s)" % (name, ", ".join("/" + h for h in sorted(hits))))
                return None
        if name in ("quit", "exit"):
            if args:
                self.complain(USAGE[name])
                return None
            return "quit"
        if name not in USAGE:
            self.refuse("unknown command: /%s\n%s" % (name, HELP.strip().splitlines()[-1]))
            return None
        if name == "help":
            self.say(HELP.rstrip("\n")) if not args else self.complain(USAGE[name])
        elif name == "mode":
            if not args:
                self.say("mode: %s" % ("attended" if self.attended else "unattended"))
            elif len(args) == 1 and args[0] in ("attended", "unattended"):
                self.attended = args[0] == "attended"
                self.say("mode: %s" % args[0])
            else:
                self.complain(USAGE[name])
        elif name == "issue":
            if len(args) == 1 and re.fullmatch(r"#?[1-9][0-9]*", args[0]):
                self.execute({"uncle_action": "github_issue", "issue": args[0].lstrip("#"),
                              "start": True, "message": ""}, line)
            else:
                self.complain(USAGE[name])
        elif name == "stop":
            if args:
                self.complain(USAGE[name])
            else:
                self.say("no build running")
        elif name == "resume":
            if len(args) == 1 and re.fullmatch(r"#?[1-9][0-9]*", args[0]):
                self.execute({"uncle_action": "github_issue", "issue": args[0].lstrip("#"),
                              "start": True, "message": ""}, line)
            elif args:
                self.complain(USAGE[name])
            else:
                self.execute({"uncle_action": "resume_build"}, line)
        elif name == "clear":
            if args:
                self.complain(USAGE[name])
            else:
                self.execute({"uncle_action": "clear_build"}, line)
        elif name in ("triage", "do"):
            if args:
                self.complain(USAGE[name])
            else:
                self.say("/%s needs the TUI; run `uncle` without --noui." % name)
        elif name == "settings":
            self.say("mode: %s\nroot: %s" % ("attended" if self.attended else "unattended", self.root))
        return None

    def handle(self, line):
        text = line.strip()
        if not text:
            return None
        if text.startswith("/"):
            return self.slash(text)
        m = home_actions.ISSUE_REQUEST_RE.fullmatch(text)
        if m:
            self.history.append(("user", text))
            self.execute(self.issue_action(m), text, bool(m.group("change")))
            return None
        self.history.append(("user", text))
        try:
            reply, action = self._ask(text)
        except KeyboardInterrupt:
            self._cancel_chat()
            self.say("(cancelled)")
            self.idle_ctrlc = 1
            return "interrupted"
        except Exception as exc:
            self.complain("uncle --noui: chat failed: %s" % exc)
            return None
        if reply:
            self.history.append(("assistant", reply))
            self.say(reply)
        for note in getattr(self.chat, "notes", []) or []:
            self.say(note)
        cwd = getattr(self.chat, "last_cwd", None)
        if cwd is not None:
            if not self.apply_cwd(cwd, action):
                return None
        elif action:
            self.execute(action, text)
        return None

    # -- uncle_cwd: the TUI's _validate_agent_cwd / _agent_cwd, for the REPL
    def validate_cwd(self, path):
        if not (isinstance(path, str) and os.path.isabs(path)):
            raise ValueError("path is not absolute")
        resolved = os.path.realpath(path)
        if not os.path.isdir(resolved):
            raise ValueError("not a directory")
        if resolved in (os.path.realpath(os.sep), os.path.realpath(os.path.expanduser("~"))):
            raise ValueError("/ and the home directory are not allowed")
        return resolved

    def created_here(self, resolved):
        try:
            info = os.stat(resolved)
        except OSError:
            return False
        return getattr(info, "st_birthtime", info.st_ctime) >= self.started - 1

    def apply_cwd(self, path, action):
        """Switch the session root; True when the same reply's action may still run."""
        try:
            resolved = self.validate_cwd(path)
        except ValueError as exc:
            self.say("Ignored uncle_cwd (%s).%s" % (exc, " The action in the same reply was cancelled." if action else ""))
            return False
        if resolved != os.path.realpath(self.root):
            if not (self.created_here(resolved) or not self.attended):
                if not self.confirm("The agent wants to work in %s, which it did not create this session. Switch?" % resolved):
                    if action:
                        self.say("The action in the same reply is cancelled.")
                    return False
            self.switch_root(resolved)
        if action:
            self.execute(action, "")
        return True

    def switch_root(self, path):
        self._terminate_chat()
        self.root = path
        self.env["UNCLE_PROJECT_ROOT"] = path
        self.env["UNCLE_CONFIG"] = os.path.join(path, ".uncle", "config")
        os.environ["UNCLE_PROJECT_ROOT"] = path
        os.environ["UNCLE_CONFIG"] = self.env["UNCLE_CONFIG"]
        if not (self.env.get("UNCLE_RUNTIME_ROOT") or self.env.get("UNCLE_RUNTIME")):
            self.runtime = path
        self.chat = None
        self.say("Working in " + path)

    def on_sigterm(self, signum, frame):
        self._terminate_chat()
        raise SystemExit(143)

    def loop(self):
        self.say("uncle --noui interactive session. Type /help for commands, /quit to exit.")
        prompt = "uncle> " if self.prompt_on else ""
        while True:
            try:
                status, line = self.reader.read(prompt)
            except KeyboardInterrupt:
                self.idle_ctrlc += 1
                if self.idle_ctrlc >= 2:
                    return self.code
                self.say("")
                continue
            if status == "eof":
                return self.code
            if status == "long":
                self.refuse("uncle --noui: line too long (limit %d bytes); discarded" % MAX_LINE)
                self.idle_ctrlc = 0
                continue
            self.idle_ctrlc = 0
            try:
                outcome = self.handle(line)
            except KeyboardInterrupt:
                self.idle_ctrlc = 1
                continue
            if outcome == "quit":
                return self.code
            if outcome == "interrupted":
                self.idle_ctrlc = 1


def main(argv=None, env=None, io=None):
    session = Session(list(argv or []), env, io)
    old_term = signal.signal(signal.SIGTERM, session.on_sigterm)
    try:
        return session.loop()
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 143
    finally:
        signal.signal(signal.SIGTERM, old_term)
        session._terminate_chat()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

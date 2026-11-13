#!/usr/bin/env python3
"""Headless (--noui) runner: runs a driver with no curses and no terminal control.

Usage: uncle_headless.py [--attended] [--root DIR] -- DRIVER_ARGV...

Exit codes: 0 completed, 1 driver failure, 2 refusal before spawn, 3 stopped
at a gate (driver exit 0 without a completion banner), 128+n on a forwarded
signal n.
"""
import codecs
import collections
import json
import os
import re
import select
import signal
import stat
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import headless_preview  # noqa: E402

try:
    import run_duties as _duties
except Exception:  # pragma: no cover - the shared module is written by step 1
    _duties = None

_DEFAULT_BANNERS = ("Workflow complete.", "Change workflow complete.",
                    "Workflow complete with waived acceptance.",
                    "Change workflow complete with waived acceptance.")
COMPLETION_BANNERS = tuple(getattr(_duties, "COMPLETION_BANNERS", _DEFAULT_BANNERS))
_FINISHED_START = ("Finished build:", "READY - ", "NOT READY - ")
_FINISHED_TAIL = ("Total time:", "PR:")

LINE_CAP = 8192
KILL_GRACE_SECONDS = 10.0
IDLE_FLUSH_SECONDS = 0.2


class EscapeFilter:
    """Stateful allowlist filter: output has only printable text, TAB and LF."""

    def __init__(self):
        self.dec = codecs.getincrementaldecoder("utf-8")("replace")
        self.state = "text"
        self.last_cr = False

    def feed(self, data, final=False):
        out = []
        for ch in self.dec.decode(data, final):
            o = ord(ch)
            st = self.state
            if st == "text":
                if o == 0x1B:
                    self.state = "esc"
                elif ch == "\n":
                    if not self.last_cr:
                        out.append("\n")
                elif ch == "\r":
                    out.append("\n")
                elif ch == "\t":
                    out.append(ch)
                elif o < 0x20 or 0x7F <= o <= 0x9F:
                    pass
                else:
                    out.append(ch)
                self.last_cr = ch == "\r"
                continue
            self.last_cr = False
            if st == "esc":
                if ch == "[":
                    self.state = "csi"
                elif ch == "]":
                    self.state = "osc"
                elif ch in "P_^X":
                    self.state = "str"
                elif 0x20 <= o <= 0x2F:
                    pass  # intermediate bytes: stay in esc
                elif o == 0x1B:
                    pass
                else:
                    self.state = "text"
            elif st == "csi":
                if 0x40 <= o <= 0x7E:
                    self.state = "text"
                elif o == 0x1B:
                    self.state = "esc"
            elif st == "esc_st":  # ESC seen inside osc/str: "\\" ends it
                self.state = "text" if ch == "\\" else "esc"
            else:  # osc / str: end at BEL (osc) or ST (ESC \)
                if o == 0x07 and st == "osc":
                    self.state = "text"
                elif o == 0x1B:
                    self.state = "esc_st"
        return "".join(out)


_SECRET_NAMES = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def redact(text, env):
    for name, value in env.items():
        up = name.upper()
        if len(value) >= 8 and (any(s in up for s in _SECRET_NAMES) or "SIGNING" in up):
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"-----BEGIN [A-Z ]*(PRIVATE KEY|KEY BLOCK)[A-Z ]*-----.*", "[REDACTED]", text)
    return text


def classify_exit(returncode, signaled, completed):
    """Precedence: forwarded signal > nonzero driver exit > no banner > ok."""
    if signaled:
        return 128 + signaled
    if returncode is not None and returncode < 0:
        return 128 - returncode
    if returncode != 0:
        return 1
    return 0 if completed else 3


def _elapsed(start):
    s = int(time.monotonic() - start)
    return "[+%02d:%02d:%02d] " % (s // 3600, s % 3600 // 60, s % 60)


class _Writer:
    def __init__(self, out, start):
        self.out, self.start, self.at_start = out, start, True

    def emit(self, text):
        if not text:
            return
        if self.at_start:
            self.out.write(_elapsed(self.start))
        self.out.write(text)
        self.out.flush()
        self.at_start = text.endswith("\n")


POLL_SECONDS = 0.5
STATE_READ_CAP = 2048
_URL_RE = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/\S*)?$")


def _read_state(path):
    """Bounded, nonblocking read of a regular file; None on any failure or oversize."""
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        data = os.read(fd, STATE_READ_CAP + 1)
        if len(data) > STATE_READ_CAP:
            return None
        return data.decode("utf-8")
    except (OSError, ValueError, UnicodeError):
        return None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _one_line(text):
    """Strip escape sequences and every control/separator character; single line."""
    text = EscapeFilter().feed(text.encode("utf-8", "replace"), True)
    text = "".join(" " if ch in "\n\t" else ch for ch in text)
    return "".join(ch for ch in text if ch.isprintable()).strip()


def _valid_url(raw):
    if raw is None:
        return None
    url = raw.strip()
    if not url or any((not ch.isprintable()) or ch.isspace() for ch in url):
        return None
    if len(url.encode("utf-8")) > STATE_READ_CAP or not _URL_RE.match(url):
        return None
    return url


def _alive(path):
    raw = _read_state(path)
    try:
        pid = int((raw or "").strip())
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (ValueError, OSError, OverflowError):
        return False


def new_watch_state():
    return {"seen_preview": None, "emitted_app_urls": set(), "launch_printed": False}


def _scan_announcements(root, state, env=None):
    """Return new 'App:' lines from the driver's state files (read-only).

    The preview's own address (Local preview: / Preview (not local):) is said by the driver itself
    (preview_announce.py), so every way of running uncle shows it once."""
    lines = []
    try:
        base = os.path.join(root, ".uncle", "workflow")
        if _alive(os.path.join(base, "app-server.pid")):
            url = _valid_url(_read_state(os.path.join(base, "app-server.url")))
            if url and url not in state["emitted_app_urls"]:
                state["emitted_app_urls"].add(url)
                lines.append("App: %s\n" % _one_line(url))
    except Exception:
        pass
    return lines


def _launch_line(root, state):
    """One 'App: launch ...' line from .uncle/launch.json, once; None when absent/malformed."""
    if state["launch_printed"]:
        return None
    try:
        if not os.path.isfile(os.path.join(root, ".uncle", "launch.json")):
            return None
        import completion_preview
        spec = completion_preview.launch_spec(root)
        kind = spec.get("kind")
        if kind == "none":
            text = "none"
        elif kind == "command":
            text = "command " + json.dumps(spec.get("command"))
        elif kind == "webpage" and spec.get("command"):
            text = "page %s %s" % (json.dumps(spec["command"]), spec.get("url", ""))
        elif kind == "webpage":
            text = "page %s" % (spec.get("path") or spec.get("url") or "")
        else:
            return None
        state["launch_printed"] = True
        return "App: launch %s\n" % _one_line(text)
    except Exception:
        return None


def run(cmd, root, attended=False, env=None, out=None, err=None, stdin_fd=0,
        grace=KILL_GRACE_SECONDS, idle=IDLE_FLUSH_SECONDS, install_signals=True,
        desktop_decision=True):
    out = out or sys.stdout
    err = err or sys.stderr
    base = dict(os.environ if env is None else env)
    if attended and not os.isatty(stdin_fd):
        err.write("uncle --noui: attended mode needs an interactive terminal on stdin; "
                  "piped, file or closed stdin cannot approve a gate.\n")
        return 2
    received = []
    old = {}
    if install_signals:
        def handler(signum, frame):
            received.append(signum)
        for s in (signal.SIGINT, signal.SIGTERM):
            old[s] = signal.signal(s, handler)
    try:
        if received:
            return 128 + received[0]
        base["UNCLE_STATUS_FILE"] = base.get("UNCLE_STATUS_FILE") or ""
        base["UNCLE_STEERING"] = "1"
        base["UNCLE_SIGNING_JSON"] = "1"
        base["NO_COLOR"] = "1"
        base.pop("UNCLE_ATTENDED_STDIN", None)
        if attended:
            base["UNCLE_ATTENDED_STDIN"] = "1"
        start = time.monotonic()
        proc = subprocess.Popen(cmd, cwd=root, env=base,
                                stdin=subprocess.PIPE if attended else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True, bufsize=0)
        return _stream(proc, base, root, attended, out, err, stdin_fd, start,
                       received, grace, idle, desktop_decision)
    finally:
        for s, h in old.items():
            signal.signal(s, h)


def _killpg(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _stream(proc, env, root, attended, out, err, stdin_fd, start, received,
            grace, idle, desktop_decision):
    flt, writer = EscapeFilter(), _Writer(out, start)
    acc, finished, completed, in_block = "", [], False, False
    gates = []
    fd = proc.stdout.fileno()
    stdin_open = attended
    sent_term = killed = False
    term_at = 0.0
    last_data = time.monotonic()
    eof = False
    efd = proc.stderr.fileno()
    eflt = EscapeFilter()  # stderr's own filter and line buffer: no state shared with stdout
    eacc, eof_err, discard = "", False, False
    elast = time.monotonic()
    tail = collections.deque(maxlen=20)  # redacted diagnostic lines; never replayed
    watch = new_watch_state()
    next_scan = 0.0
    preview = headless_preview.HeadlessPreview(root, env)   # the screen's early page and finished-app tab, without the screen

    def announce(lines):
        for text in lines:
            writer.emit(redact(text, env))

    def handle_line(line, banner_only=False):
        nonlocal completed, in_block
        text = line.strip()
        if banner_only:
            if text in COMPLETION_BANNERS:
                completed = True
            return
        if text.startswith(_FINISHED_START):
            finished.append(text)
            in_block = True
        elif in_block and text.startswith(_FINISHED_TAIL):
            finished.append(text)
        if text in COMPLETION_BANNERS:
            completed = True
        if text.startswith("Human gate:") or "REVIEW REQUIRED" in text:
            gates.append(text)

    def emit_err(line):
        if len(line) > LINE_CAP:
            line = line[:LINE_CAP] + "…[truncated]"
        shown = redact(line, env)
        tail.append(shown)
        err.write(shown + "\n")
        err.flush()
        handle_line(line, banner_only=True)

    def feed_err(data, final=False):
        nonlocal eacc, discard
        eacc += eflt.feed(data, final)
        while "\n" in eacc:
            line, eacc = eacc.split("\n", 1)
            if discard:
                discard = False
            else:
                emit_err(line)
        if len(eacc) > LINE_CAP and not discard:
            emit_err(eacc)  # bounded buffer: emit the capped head, drop the rest of this line
            eacc, discard = "", True
        elif discard:
            eacc = ""
        if final and eacc:
            emit_err(eacc)
            eacc = ""

    def flush_out_partial():
        nonlocal acc
        if acc:
            writer.emit(redact(acc, env))
            handle_line(acc)
            acc = ""

    def drain_err(cap=2.0):
        # Read what is left on stderr (bounded) and flush the partial line.
        nonlocal eof_err
        deadline = time.monotonic() + cap
        while not eof_err and time.monotonic() < deadline:
            r, _, _ = select.select([efd], [], [], 0.05)
            if not r:
                if proc.poll() is not None:
                    break
                continue
            data = os.read(efd, 65536)
            if not data:
                break
            feed_err(data)
        eof_err = True
        flush_out_partial()
        feed_err(b"", True)

    while True:
        if received and not sent_term:
            _killpg(proc, signal.SIGTERM)
            sent_term, term_at = True, time.monotonic()
        if sent_term and not killed and (len(received) > 1 or time.monotonic() - term_at >= grace):
            _killpg(proc, signal.SIGKILL)
            killed = True
        rl = [] if eof else [fd]
        if not eof_err:
            rl.append(efd)
        if stdin_open:
            rl.append(stdin_fd)
        if not rl:
            break
        ready, _, _ = select.select(rl, [], [], 0.05)
        if fd in ready:
            data = os.read(fd, 65536)
            if not data:
                eof = True
                acc += flt.feed(b"", True)
            else:
                acc += flt.feed(data)
                last_data = time.monotonic()
            while "\n" in acc:
                line, acc = acc.split("\n", 1)
                handle_line(line)
                writer.emit(redact(line, env) + "\n")
            if eof and acc:
                writer.emit(redact(acc, env))
                handle_line(acc)
                acc = ""
        elif not eof and proc.poll() is not None:
            # The driver is gone and nothing is left to read. A descendant that kept the pipe open must not hold us here
            # until it exits on its own: treat this as EOF so the group kill below can reap it.
            eof = True
            acc += flt.feed(b"", True)
            while "\n" in acc:
                line, acc = acc.split("\n", 1)
                handle_line(line)
                writer.emit(redact(line, env) + "\n")
            if acc:
                writer.emit(redact(acc, env))
                handle_line(acc)
                acc = ""
            if not eof_err:
                drain_err()
        elif acc and (time.monotonic() - last_data >= idle):
            # prompt without newline (or idle pipe): never withhold it
            writer.emit(redact(acc, env))
            handle_line(acc)
            acc = ""
        if not eof_err and efd in ready:
            edata = os.read(efd, 65536)
            if not edata:
                eof_err = True
                flush_out_partial()
                feed_err(b"", True)
            else:
                flush_out_partial()  # never split a pending stdout partial
                feed_err(edata)
                elast = time.monotonic()
        elif eacc and (time.monotonic() - elast >= idle):
            flush_out_partial()
            emit_err(eacc)
            eacc = ""
            eflt.state = "text"
        if stdin_open and stdin_fd in ready:
            try:
                chunk = os.read(stdin_fd, 65536)
            except OSError:
                chunk = b""
            try:
                if chunk:
                    proc.stdin.write(chunk)
                    proc.stdin.flush()
                else:
                    proc.stdin.close()
                    stdin_open = False
            except (BrokenPipeError, OSError):
                stdin_open = False
        now = time.monotonic()
        preview.poll()
        if now >= next_scan and writer.at_start and not acc:
            next_scan = now + POLL_SECONDS
            announce(_scan_announcements(root, watch, env))
        if eof and eof_err and (not stdin_open or proc.poll() is not None):
            break
    # reap, still honoring a late signal; ignore repeats
    while proc.poll() is None:
        if received and not sent_term:
            _killpg(proc, signal.SIGTERM)
            sent_term, term_at = True, time.monotonic()
        if sent_term and not killed and (len(received) > 1 or time.monotonic() - term_at >= grace):
            _killpg(proc, signal.SIGKILL)
            killed = True
        time.sleep(0.02)
    _killpg(proc, signal.SIGKILL)  # no surviving descendants
    rc = proc.returncode
    # The driver stops its own preview server when it exits, so a completed build is left with nothing showing the result.
    after = []
    if classify_exit(rc, received[0] if received else 0, completed) == 0:
        after = preview.finish()
    final = _scan_announcements(root, watch, env) + after
    launch = _launch_line(root, watch)
    if launch:
        final.append(launch)
    if final:
        if not writer.at_start:
            writer.emit("\n")
        announce(final)
    if finished:
        out.write("\n".join(finished) + "\n")
        out.flush()
    if desktop_decision and attended:
        _record_skipped(root, err)
    code = classify_exit(rc, received[0] if received else 0, completed)
    if rc not in (0, None) and not received:
        err.write("uncle --noui: driver exited with status %d\n" % (rc if rc > 0 else 128 - rc))
    elif code == 3:
        err.write("uncle --noui: driver stopped without completing (gate or blocked); exit 3\n")
        if gates:
            err.write("uncle --noui: stopped at: %s\n" % gates[-1])
    err.flush()
    return code


def _record_skipped(root, err):
    try:
        import desktop_launch
        desktop_launch.record(root, "skipped", reason="noui", decision="skipped")
    except Exception as exc:  # the record is best effort; never mask the run
        err.write("uncle --noui: could not record desktop decision: %s\n" % exc)


def main(argv):
    # The launcher execs with no arguments and states the mode in its environment.
    attended = os.environ.get("UNCLE_STARTUP_ATTENDED") == "1"
    # The launcher cd's into the runtime root, so the project is named by env.
    root, args = os.environ.get("UNCLE_PROJECT_ROOT") or os.getcwd(), list(argv)
    while args and args[0] != "--":
        a = args.pop(0)
        if a == "--attended":
            attended = True
        elif a == "--root" and args:
            root = args.pop(0)
        else:
            sys.stderr.write("usage: uncle_headless.py [--attended] [--root DIR] -- DRIVER...\n")
            return 2
    if args:
        args.pop(0)
    if not args:
        args = _driver_from_env(root, sys.stderr)
        if args is None:
            return 2
        # Like the TUI: a run gets its own worktree. Issue runs make theirs in
        # from-issue.sh once the title names the branch, so they are skipped.
        if _duties is not None and os.environ.get("UNCLE_STARTUP_ACTION") != "github_issue":
            runtime = os.environ.get("UNCLE_RUNTIME_ROOT") or os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            kind = os.environ.get("UNCLE_STARTUP_ACTION") or os.path.basename(args[0])
            directory = _duties.prepare_worktree(runtime, root, kind=kind)
            if directory:
                root = directory
                os.environ["UNCLE_PROJECT_ROOT"] = directory
                os.environ["UNCLE_PROJECT_ROOT_LOCKED"] = "1"
                sys.stdout.write("Working in %s\n" % directory)
    if attended and "--attended" not in args:
        args.append("--attended")
    _set_title(args)
    return run(args, root, attended=attended)


def _driver_from_env(root, err):
    """Wrapper kept for its signature; see prepare_driver."""
    return prepare_driver(root, err)


def prepare_driver(root, err, env=None):
    """Build driver argv from UNCLE_STARTUP_*; only allowlisted actions and fixed names.

    Mirrors the TUI: --application seeds REQUIREMENTS.md, --change-request seeds
    CHANGE_REQUEST.md and --issue passes the reference to from-issue.sh.
    """
    e = os.environ if env is None else env
    action = e.get("UNCLE_STARTUP_ACTION", "")
    if _duties is None or action not in _duties.STARTUP_ACTIONS:
        err.write("uncle --noui: UNCLE_STARTUP_ACTION must be one of %s\n"
                  % ", ".join(sorted(getattr(_duties, "STARTUP_ACTIONS", ()))))
        return None
    path = e.get("UNCLE_STARTUP_TEXT_FILE", "")
    text = e.get("UNCLE_STARTUP_TEXT", "")
    if path:
        try:
            st = os.lstat(path)
            if not os.path.isfile(path) or os.path.islink(path) or st.st_uid != os.getuid():
                raise OSError("untrusted text file")
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            err.write("uncle --noui: cannot read startup text file: %s\n" % exc)
            return None
    if not text.strip():
        err.write("uncle --noui: startup text is empty\n")
        return None
    try:
        if action == "create_app":
            from chat import Conversation
            from generated_input import generated_input_write_path
            document = _duties.startup_brief_document(text, "app", Conversation.fields["app"])
            target = generated_input_write_path("REQUIREMENTS.md", root)
            if os.path.lexists(target):
                os.replace(target, str(target) + ".previous")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(document)
        elif action == "change_request":
            for archived in _duties.archive_change_request(root, e):
                err.write("uncle --noui: archived the previous change request to %s\n" % archived)
            _duties.write_change_request(root, text)
        issue_mode = ""
        if action == "github_issue":
            issue_mode = e.get("UNCLE_STARTUP_ISSUE_MODE", "")
        # Driver scripts live in the install/runtime root, never the project.
        runtime = e.get("UNCLE_RUNTIME_ROOT") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        argv = _duties.build_driver_command(action, text, False, runtime, issue_mode)
    except (OSError, ValueError, ImportError, KeyError) as exc:
        err.write("uncle --noui: cannot prepare %s: %s\n" % (action, exc))
        return None
    return argv


def _set_title(args):
    if os.environ.get("UNCLE_TITLE_OWNER") or not sys.stderr.isatty():
        return
    sys.stderr.write("\033]0;uncle %s\007" % os.path.basename(args[0]))
    sys.stderr.flush()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

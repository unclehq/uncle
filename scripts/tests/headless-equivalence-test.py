#!/usr/bin/env python3
"""AC-8: a --noui run and a TUI run of the same fake driver leave the same
artifacts and attestation fields (timestamps and desktop-launch.json excluded;
the latter differs by design, D-9). The TUI side runs under a pty."""
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import run_duties  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def first_literal(*names):
    for n in names:
        v = getattr(run_duties, n, None)
        if isinstance(v, str):
            return v
        if isinstance(v, (list, tuple)) and v:
            return v[0]
    return None


BANNER = first_literal("COMPLETION_BANNERS", "COMPLETION_BANNER")
check("run_duties exports a completion banner literal", BANNER is not None)

FAKE_DRIVER = """#!/usr/bin/env bash
mkdir -p .uncle/docs .uncle/workflow
echo "working" > .uncle/docs/RESULT.md
echo '{"stage":"done"}' > .uncle/workflow/status.json
echo "step one"
echo "%s"
exit 0
""" % (BANNER or "COMPLETE")


def make_runtime():
    """A runtime root whose scripts/stagegate.sh is the fake driver; every other
    entry is linked to the real tree. uncle_tui.py is copied (it realpath()s itself)."""
    r = Path(tempfile.mkdtemp(prefix="uncle-equiv-rt-"))
    for e in ROOT.iterdir():
        if e.name in ("scripts", "uncle", "uncle_tui.py", ".git", ".uncle", "__pycache__"):
            continue
        (r / e.name).symlink_to(e)
    shutil.copy2(ROOT / "uncle", r / "uncle")
    shutil.copy2(ROOT / "uncle_tui.py", r / "uncle_tui.py")
    (r / "scripts").mkdir()
    for e in (ROOT / "scripts").iterdir():
        if e.name not in ("stagegate.sh", "__pycache__"):
            (r / "scripts" / e.name).symlink_to(e)
    drv = r / "scripts" / "stagegate.sh"
    drv.write_text(FAKE_DRIVER)
    drv.chmod(0o755)
    return r


def make_project():
    d = Path(tempfile.mkdtemp(prefix="uncle-equiv-"))
    subprocess.run(["git", "-c", "commit.gpgsign=false", "init", "-q"], cwd=d, check=True)
    return d


def snapshot(d):
    """Artifact list plus attestation fields, minus timestamps/desktop-launch."""
    out = {}
    for p in sorted(d.rglob("*")):
        rel = p.relative_to(d)
        if ".git" in rel.parts or p.is_dir() or p.name == "desktop-launch.json":
            continue
        text = p.read_text(errors="replace")
        if p.suffix == ".json":
            try:
                obj = json.loads(text)
                obj = {k: v for k, v in obj.items() if "time" not in k.lower() and not k.endswith("_at")}
                text = json.dumps(obj, sort_keys=True)
            except ValueError:
                pass
        out[str(rel)] = text
    # UI-only bookkeeping that only the curses front end writes (D-9 scope): not a
    # property of the run itself, so it is not compared.
    ui_only = (".gitignore", ".uncle/model-catalog.json", ".uncle/model-catalog.json.lock",
               ".uncle/tui.lock", ".uncle/workflow/supervision/", ".uncle/workflow/supervisor/")
    return {k: v for k, v in out.items() if not k.startswith(ui_only)}


def run_headless(d):
    env = dict(os.environ, UNCLE_RUNTIME_ROOT=str(RT), UNCLE_SKIP_UPGRADE="1")
    r = subprocess.run([str(RT / "uncle"), "--noui", "--unattended", "--application", "fixture"],
                       cwd=d, env=env, capture_output=True, text=True, timeout=120)
    return r.returncode


def run_tui(d):
    env = dict(os.environ, UNCLE_RUNTIME_ROOT=str(RT), UNCLE_SKIP_UPGRADE="1", TERM="xterm")
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(d)
        os.execvpe(str(RT / "uncle"), [str(RT / "uncle"), "--unattended", "--application", "fixture"], env)
    deadline = time.time() + 60
    buf = b""
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            return os.waitstatus_to_exitcode(status)
        if (d / ".uncle" / "workflow" / "status.json").exists():
            time.sleep(1)  # the fake driver has finished; the UI itself is not under test
            os.write(fd, b"q")
            break
    for sig in (15, 9):
        try:
            os.kill(pid, sig)
        except OSError:
            break
        end = time.time() + 5
        while time.time() < end:
            try:
                done, _ = os.waitpid(pid, os.WNOHANG)
            except OSError:
                done = pid
            if done:
                break
            time.sleep(0.1)
        else:
            continue
        break
    return None if not (d / ".uncle" / "workflow" / "status.json").exists() else 0


RT = make_runtime()
h, t = make_project(), make_project()
try:
    hc = run_headless(h)
    tc = run_tui(t)
    check("headless run exits 0", hc == 0, str(hc))
    check("tui run finished under the pty", tc is not None)
    hs, ts = snapshot(h), snapshot(t)
    check("artifact lists match", sorted(hs) == sorted(ts), f"{sorted(hs)} vs {sorted(ts)}")
    for k in sorted(set(hs) & set(ts)):
        check(f"content matches: {k}", hs[k] == ts[k])
finally:
    shutil.rmtree(h, ignore_errors=True)
    shutil.rmtree(t, ignore_errors=True)
    shutil.rmtree(RT, ignore_errors=True)

sys.exit(1 if FAILS else 0)

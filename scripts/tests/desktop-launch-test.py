#!/usr/bin/env python3
"""Module tests for scripts/lib/desktop_launch.py (cases a-f of the plan).

Written against the contract: detect(root), launch_decision(attended,
unattended, headless, opted_out), DesktopLaunch(...).start()/close().
Expectations come from the approved plan, not the implementation.
"""
import itertools
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import desktop_launch as dl  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f" {detail}"))
    if not cond:
        FAILS.append(name)


def get(obj, key):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def project(files):
    d = tempfile.mkdtemp(prefix="desktop-launch-")
    for rel, content in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content if isinstance(content, str) else json.dumps(content))
    return d


def pkg(scripts=None, deps=None, main=None):
    p = {"name": "x", "devDependencies": deps or {}}
    if scripts is not None:
        p["scripts"] = scripts
    if main:
        p["main"] = main
    return {"package.json": p}


# ---- detection -------------------------------------------------------------
d = project(pkg({"start": "electron ."}, {"electron": "^30"}))
r = dl.detect(d)
check("electron start detected", get(r, "framework") == "electron", r)
check("electron start command", list(get(r, "command") or []) == ["npm", "start"], r)

d = project(pkg({"dev": "x"}, {"electron": "^30"}))
check("electron dev command", list(get(dl.detect(d), "command") or []) == ["npm", "run", "dev"])

d = project(pkg({"start": "a", "dev": "b"}, {"electron": "^30"}))
r = dl.detect(d)
check("both start+dev ambiguous", get(r, "command") is None and len(get(r, "candidates") or []) >= 2, r)

d = project(pkg({"tauri": "tauri"}, {"@tauri-apps/cli": "^1"}))
r = dl.detect(d)
check("tauri detected", get(r, "framework") == "tauri", r)
check("tauri npm run tauri dev", list(get(r, "command") or []) == ["npm", "run", "tauri", "dev"], r)

d = project({"package.json": "{not json"})
r = dl.detect(d)
check("(f) malformed package.json -> none", get(r, "framework") in (None, "none") and get(r, "command") is None, r)

d = project({"README": "x"})
check("no package.json -> none", get(dl.detect(d), "command") is None)

# ---- (a) launch_decision 16-combination matrix ----------------------------
def outcome(res):
    # Normalise: return (action, reason) as lowercase strings
    if isinstance(res, tuple):
        return tuple(str(x).lower() if x is not None else None for x in res[:2])
    a = get(res, "action") or get(res, "outcome") or get(res, "status")
    return (str(a).lower() if a else None, str(get(res, "reason")).lower() if get(res, "reason") else None)


for attended, unattended, headless, opted_out in itertools.product([False, True], repeat=4):
    res = dl.launch_decision(attended=attended, unattended=unattended, headless=headless, opted_out=opted_out)
    text = " ".join(str(x) for x in outcome(res))
    if opted_out:
        exp = "opted-out"
    elif unattended:
        exp = "unattended"
    elif headless:
        exp = "headless"
    else:
        exp = None
    label = f"(a) matrix att={attended} un={unattended} hl={headless} oo={opted_out}"
    if exp:
        check(label, exp in text, text)
        others = {"opted-out", "unattended", "headless"} - {exp}
        check(label + " only own reason", not any(o in text for o in others), text)
    else:
        check(label + " -> confirm", not any(o in text for o in ("opted-out", "unattended", "headless")), text)

# ---- launch helpers --------------------------------------------------------
def make_launch(root, argv, grace=None):
    env = dict(os.environ)
    if grace is not None:
        env["WORKFLOW_PREVIEW_DESKTOP_GRACE"] = str(grace)
    old = os.environ.copy()
    os.environ.update(env)
    try:
        return dl.DesktopLaunch(root, argv)
    finally:
        os.environ.clear()
        os.environ.update(old)


def start_and_wait(root, argv, grace):
    old = os.environ.get("WORKFLOW_PREVIEW_DESKTOP_GRACE")
    os.environ["WORKFLOW_PREVIEW_DESKTOP_GRACE"] = str(grace)
    try:
        l = dl.DesktopLaunch(root, argv)
        res = l.start()
        return l, res
    finally:
        if old is None:
            os.environ.pop("WORKFLOW_PREVIEW_DESKTOP_GRACE", None)
        else:
            os.environ["WORKFLOW_PREVIEW_DESKTOP_GRACE"] = old


def status_of(res, root):
    s = get(res, "status")
    if s:
        return str(s).lower()
    p = os.path.join(root, ".uncle/workflow/desktop-launch.json")
    if os.path.exists(p):
        return json.load(open(p)).get("status")
    return None


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


W = ".uncle/workflow"
PY = sys.executable

# ---- (b) grace outcomes ----------------------------------------------------
root = tempfile.mkdtemp()
l, res = start_and_wait(root, [PY, "-c", "import sys;print('boom');sys.exit(3)"], 2)
check("(b) nonzero exit within grace -> failed", status_of(res, root) == "failed", res)
check("(b) failed removes pid file", not os.path.exists(os.path.join(root, W, "desktop-app.pid")))

root = tempfile.mkdtemp()
l, res = start_and_wait(root, [PY, "-c", "print('bye')"], 2)
check("(b) exit 0 within grace -> failed", status_of(res, root) == "failed", res)
check("(b) failed result carries log tail", "bye" in json.dumps(res, default=str) or "bye" in open(os.path.join(root, W, "desktop-app.log")).read())

root = tempfile.mkdtemp()
l, res = start_and_wait(root, [PY, "-c", "import time;time.sleep(60)"], 1)
check("(b) alive past grace -> launched", status_of(res, root) == "launched", res)
pid = json.load(open(os.path.join(root, W, "desktop-app.pid")))["pid"]

# ---- (e) modes 0600 --------------------------------------------------------
for name in ("desktop-app.pid", "desktop-app.log", "desktop-launch.json"):
    p = os.path.join(root, W, name)
    ok = os.path.exists(p) and stat.S_IMODE(os.stat(p).st_mode) == 0o600
    check(f"(e) {name} mode 0600", ok)

# ---- (d) close terminates own child ---------------------------------------
l.close()
time.sleep(0.5)
check("(d) close() terminates started child", not alive(pid))

# ---- (c) pid-file liveness -------------------------------------------------
def write_pid(root, pid, command):
    os.makedirs(os.path.join(root, W), exist_ok=True)
    with open(os.path.join(root, W, "desktop-app.pid"), "w") as f:
        json.dump({"pid": pid, "command": command, "log": "x", "started": time.time()}, f)


sleeper = subprocess.Popen([PY, "-c", "import time;time.sleep(60)"])
try:
    root = tempfile.mkdtemp()
    write_pid(root, 99999999, [PY, "-c", "x"])
    l, res = start_and_wait(root, [PY, "-c", "import time;time.sleep(30)"], 1)
    check("(c) dead pid overwritten -> launched", status_of(res, root) == "launched", res)
    l.close()

    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, W))
    open(os.path.join(root, W, "desktop-app.pid"), "w").write("{garbage")
    l, res = start_and_wait(root, [PY, "-c", "import time;time.sleep(30)"], 1)
    check("(c) corrupt pid file is stale -> launched", status_of(res, root) == "launched", res)
    l.close()

    root = tempfile.mkdtemp()
    write_pid(root, sleeper.pid, ["definitely", "not", "the", "command"])
    l, res = start_and_wait(root, [PY, "-c", "import time;time.sleep(30)"], 1)
    check("(c) live pid, mismatched command -> stale", status_of(res, root) == "launched", res)
    l.close()
    check("(c/d) mismatched pid never signalled", sleeper.poll() is None)

    # (d) never-started instance with a foreign live pid file sends no signal
    root = tempfile.mkdtemp()
    write_pid(root, sleeper.pid, [PY, "-c", "import time;time.sleep(60)"])
    never = dl.DesktopLaunch(root, [PY, "-c", "pass"])
    never.close()
    time.sleep(0.3)
    check("(d) close() on unstarted instance leaves foreign pid alive", sleeper.poll() is None)
finally:
    sleeper.kill()
    sleeper.wait()

# ---- (e) control bytes stripped from displayed tail ------------------------
root = tempfile.mkdtemp()
code = "import sys;sys.stdout.write('\\x1b[31mred\\x1b[0m\\x07\\x00end\\n');sys.exit(1)"
l, res = start_and_wait(root, [PY, "-c", code], 2)
shown = json.dumps(res, default=str)
check("(e) displayed tail free of ESC/BEL/NUL", "\\u001b" not in shown and "\\u0007" not in shown and "\\u0000" not in shown and "\x1b" not in shown, shown)

# ---- (f) grace parsing -----------------------------------------------------
for bad in ("abc", "-5", ""):
    root = tempfile.mkdtemp()
    t0 = time.time()
    l, res = start_and_wait(root, [PY, "-c", "import time;time.sleep(30)"], bad)
    el = time.time() - t0
    check(f"(f) grace {bad!r} -> default 3s", status_of(res, root) == "launched" and 2.5 <= el < 8, el)
    l.close()

root = tempfile.mkdtemp()
t0 = time.time()
l, res = start_and_wait(root, [PY, "-c", "import time;time.sleep(30)"], 0)
check("(f) grace 0 -> immediate check, alive = launched", status_of(res, root) == "launched" and time.time() - t0 < 2.5)
l.close()
root = tempfile.mkdtemp()
l, res = start_and_wait(root, [PY, "-c", "import sys;sys.exit(1)"], 0)
check("(f) grace 0 immediate exit observed as failed or launched-then-gone", status_of(res, root) in ("failed", "launched"))

shutil.rmtree(d, ignore_errors=True)
if FAILS:
    print(f"{len(FAILS)} failure(s)")
    sys.exit(1)
print("all desktop-launch module tests passed")

#!/usr/bin/env python3
"""`uncle --noui` honours the agent's uncle_cwd block like the TUI does."""
import io, json, os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))
import repl_chat, uncle_repl

FAILS = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: FAILS.append(name)

TMP = Path(tempfile.mkdtemp(prefix="uncle-cwd-test-")).resolve()
old = TMP / "old"; old.mkdir()
new = TMP / "new"; new.mkdir()

def mk(attended, answer="y"):
    out = io.StringIO()
    s = uncle_repl.Session([], {"UNCLE_PROJECT_ROOT": str(old), "UNCLE_STARTUP_" + ("ATTENDED" if attended else "UNATTENDED"): "1"},
                           SimpleNamespace(stdout=out, stderr=out))
    s.started = 4e9  # nothing counts as created this session
    s.confirm = lambda q: answer == "y"
    s.say = lambda t: out.write(t + "\n")
    return s, out

chat = repl_chat.ChatSession(str(old), {})
text, action = chat._split_agent_reply('Going.\n```uncle_cwd\n{"path": "%s"}\n```' % new)
check("cwd block split from prose", text == "Going." and chat.last_cwd == str(new) and action is None)
chat._split_agent_reply('x\n```uncle_cwd\nnope\n```')
check("malformed cwd noted", chat.last_cwd is None and chat.notes)

s, out = mk(False)
check("unattended switch", s.apply_cwd(str(new), None) and s.root == str(new) and os.environ["UNCLE_PROJECT_ROOT"] == str(new) and s.chat is None)
s, out = mk(True, "n")
check("attended decline keeps root", not s.apply_cwd(str(new), None) and s.root == str(old))
s, out = mk(True, "y")
check("attended accept switches", s.apply_cwd(str(new), None) and s.root == str(new))
s, out = mk(True)
check("relative path refused", not s.apply_cwd("new", {"x": 1}) and s.root == str(old) and "cancelled" in out.getvalue())
check("home refused", not s.apply_cwd(os.path.expanduser("~"), None) and s.root == str(old))
s, out = mk(True, "n"); s.started = 0
check("created-here switches without asking", s.apply_cwd(str(new), None) and s.root == str(new))
sys.exit(1 if FAILS else 0)

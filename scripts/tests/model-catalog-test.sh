#!/usr/bin/env bash
# Model-catalog refresh: fetchers, filters, cache, concurrency, TUI apply path.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1
[ -f scripts/lib/model_catalog.py ] || { echo "FAIL - scripts/lib/model_catalog.py missing"; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export TMP ROOT
python3 -I - <<'PY'
import os, sys, json, time, threading, subprocess
sys.path.insert(0, os.path.join(os.environ["ROOT"], "scripts", "lib"))
sys.path.insert(0, os.environ["ROOT"])
import model_catalog as mc
import uncle_tui as m
tmp = os.environ["TMP"]
fails = 0
def check(desc, cond):
    global fails
    print(("ok   - " if cond else "FAIL - ") + desc)
    fails += 0 if cond else 1

def tui(root, fetchers):
    t = m.UncleTUI.__new__(m.UncleTUI)
    t.model_cache_path = os.path.join(root, '.uncle', 'model-catalog.json'); t.home_history = []; t.model_fetchers = fetchers
    t.picker_kind = "model"; t.picker_target = "s"; t.supervision = {}
    t.stage_runner = lambda s: RUNNER[0]
    return t
RUNNER = ["codex"]
def ids(t):
    return [i for k, i in t._picker_rows() if k == "model"]
def drain(t):
    for _ in range(100):
        time.sleep(0.05)
        if t.model_catalog_queue.qsize() >= len(t.model_fetchers) or not t.model_fetchers: break
    return t.poll_model_catalog()

ok_fetch = lambda mid: (lambda: ("ok", [{"id": mid, "label": mid.upper()}], ""))
fetchers = {"claude": ok_fetch("claude-new-1"), "codex": ok_fetch("gpt-new"),
            "kimi": ok_fetch("moonshot-ai/new")}

# AC-1 refresh replaces picker rows
os.environ.pop("UNCLE_MODEL_REFRESH", None)
root = os.path.join(tmp, "p1"); os.makedirs(root)
t = tui(root, fetchers); t._start_model_refresh(); drain(t)
for r, want in (("codex", "gpt-new"), ("claude", "claude-new-1"), ("kimi", "moonshot-ai/new")):
    RUNNER[0] = r
    check("AC-1 %s picker rows equal refreshed ids" % r, ids(t) == [want])

# AC-5 cache persisted and applied before refresh completes
cache = os.path.join(root, ".uncle", "model-catalog.json")
check("AC-5 cache file written", os.path.isfile(cache))
slow = threading.Event()
t2 = tui(root, {"codex": lambda: (slow.wait(5), ("failed", [], "x"))[1]})
t2._start_model_refresh(); RUNNER[0] = "codex"
check("AC-5 cache applied before fetch completes", ids(t2) == ["gpt-new"])
slow.set(); drain(t2)
check("AC-2 failure keeps cached catalog + one diagnostic",
      ids(t2) == ["gpt-new"] and sum(1 for k, s in t2.home_history if "refresh failed" in s) == 1)
open(cache, "w").write("{not json")
t3 = tui(root, {}); t3._start_model_refresh()
check("AC-5 corrupt cache ignored (static catalog)", ids(t3) == [i for _, es in m.MODEL_CATALOG_CODEX for _, i in es])

# AC-2 failed/empty with no cache -> static; one diagnostic listing failures
root2 = os.path.join(tmp, "p2"); os.makedirs(root2)
bad = {"claude": lambda: ("failed", [], "boom"), "codex": lambda: (_ for _ in ()).throw(RuntimeError("x")),
       "kimi": lambda: ("ok", [], "")}
t4 = tui(root2, bad); t4._start_model_refresh(); drain(t4)
RUNNER[0] = "claude"
check("AC-2 static retained on failure", ids(t4) == [i for _, es in m.MODEL_CATALOG_CLAUDE for _, i in es])
diag = [s for k, s in t4.home_history]
check("AC-2 one concise diagnostic line", len(diag) == 1 and "claude" in diag[0] and "codex" in diag[0])

# AC-3 skipped -> no diagnostic; module skip cases; daemon threads
t5 = tui(root2, {"claude": lambda: ("skipped", [], "no"), "codex": lambda: ("skipped", [], "no"),
                 "kimi": lambda: ("skipped", [], "no")})
t5._start_model_refresh(); drain(t5)
check("AC-3 skipped providers emit no diagnostic", t5.home_history == [])
check("AC-3 codex skipped without binary", mc.fetch_codex(which=lambda n: None)[0] == "skipped")
check("AC-3 claude skipped without key", mc.fetch_claude(env={}, which=lambda n: "/x")[0] == "skipped")
check("AC-3 kimi skipped without config", mc.fetch_kimi(env={"UNCLE_KIMI_CONFIG": tmp + "/nope"})[0] == "skipped")
def to(argv, timeout): raise subprocess.TimeoutExpired(argv, timeout)
check("AC-3 codex timeout -> failed", mc.fetch_codex(runner=to, which=lambda n: "/x")[0] == "failed")
seen = []
mc.fetch_codex(runner=lambda a, tmo: (seen.append(tmo), (0, "{}"))[1], which=lambda n: "/x")
check("AC-3 codex fetch is time-bounded", seen == [mc.CODEX_TIMEOUT])
before = set(threading.enumerate()); ev = threading.Event()
t6 = tui(root2, {"codex": lambda: (ev.wait(5), ("failed", [], ""))[1]})
t6._start_model_refresh()
new = [x for x in threading.enumerate() if x not in before]
check("AC-3 fetch runs on a daemon thread, UI not blocked", new and all(x.daemon for x in new))
ev.set()

# AC-4 stored selections untouched
cfg = os.path.join(tmp, "cfg"); open(cfg, "w").write("model_x=old-model-id\n"); b = open(cfg, "rb").read()
RUNNER[0] = "codex"
t7 = tui(os.path.join(tmp, "p7"), fetchers); t7._start_model_refresh(); drain(t7)
check("AC-4 config bytes unchanged", open(cfg, "rb").read() == b)
check("AC-4 absent stored id not in rows but label lookup unaffected", "old-model-id" not in ids(t7))

# AC-6 filters
c = mc.filter_catalog("claude", [{"id": x} for x in ("claude-a", "gpt-4", "bad id", "claude-a", "opus-x", "taken")], taken={"taken"})
check("AC-6 claude allowlist + dedupe", [e["id"] for e in c] == ["claude-a", "opus-x"])
c = mc.filter_catalog("codex", [{"id": x} for x in ("gpt-5", "o3-mini", "kimi-k", "claude-opus")])
check("AC-6 codex excludes other vendors", [e["id"] for e in c] == ["gpt-5"])
check("AC-6 cap 50", len(mc.filter_catalog("kimi", [{"id": "m%d" % i} for i in range(80)])) == 50)
check("AC-6 kimi toml parse", [e["id"] for e in mc.parse_kimi_toml('[models."a/b"]\nx=1\n[models."c"]\n')] == ["a/b", "c"])
cx = json.dumps({"models": [{"slug": "g1", "display_name": "G One", "visibility": "list"}, {"slug": "g2", "visibility": "hide"}]})
check("AC-6 codex parse keeps visibility list", mc.parse_codex(cx) == [{"id": "g1", "label": "G One"}])

# AC-7 disabled
os.environ["UNCLE_MODEL_REFRESH"] = "0"
t8 = tui(root, fetchers); t8._start_model_refresh(); time.sleep(0.2)
check("AC-7 refresh and cache disabled", t8.model_catalogs == {} and t8.model_catalog_queue.empty()
      and ids(t8) == [i for _, es in m.MODEL_CATALOG_CODEX for _, i in es])
del os.environ["UNCLE_MODEL_REFRESH"]

# concurrent cache writers
cp = os.path.join(tmp, "cc", "c.json")
ts = [threading.Thread(target=mc.save_provider, args=(cp, "p%d" % i, [["g", [["l", "m"] * 50]]])) for i in range(16)]
[x.start() for x in ts]; [x.join() for x in ts]
check("concurrent writers keep a parseable cache with every provider", len(mc.load_cache(cp)) == 16)

# AC-9 redirect refusal, key never surfaced, atomic cache replace
import io, urllib.request, urllib.error
class FakeResp:
    status = 200
    def __init__(self, b): self.b = b
    def read(self, n=-1): return self.b
    def __enter__(self): return self
    def __exit__(self, *a): return False
class Op:
    def __init__(self, fn): self.fn = fn
    def open(self, req, timeout=None): return self.fn(req, timeout)
KEY = "sk-secret-123"
which_ok = lambda n: "/bin/" + n
def redirecting(req, timeout):
    raise urllib.error.HTTPError(req.full_url, 302, "Found", {"Location": "https://evil.example/"}, io.BytesIO(b""))
r = mc.fetch_claude(env={"ANTHROPIC_API_KEY": KEY}, opener=Op(redirecting), which=which_ok)
check("AC-9 redirect is a failure with no catalog", r[0] == "failed" and r[1] == [])
check("AC-9 failure reason never contains the key", KEY not in repr(r))
h = mc._NoRedirect()
check("AC-9 opener refuses to follow redirects",
      h.redirect_request(urllib.request.Request("https://api.anthropic.com/"), None, 302, "F", {}, "https://evil.example/") is None)
def boom(req, timeout): raise RuntimeError("leak " + KEY)
check("AC-9 exception text not surfaced", KEY not in repr(mc.fetch_claude(env={"ANTHROPIC_API_KEY": KEY}, opener=Op(boom), which=which_ok)))
seen_to = []
mc.fetch_claude(env={"ANTHROPIC_API_KEY": KEY}, opener=Op(lambda r, t: (seen_to.append(t), FakeResp(b'{"data":[]}'))[1]), which=which_ok)
check("AC-9 claude fetch is time-bounded", seen_to == [mc.CLAUDE_TIMEOUT])
ap = os.path.join(tmp, "atomic", "c.json")
mc.save_provider(ap, "claude", [["g", [["l", "m"]]]])
good = open(ap).read()
try: mc.save_provider(ap, "codex", object())
except Exception: pass
check("AC-9 failed write leaves prior cache intact, no temp files",
      open(ap).read() == good and [f for f in os.listdir(os.path.dirname(ap)) if f.startswith(".model-catalog.")] == [])

# Defect injection: each broken variant must be caught by the same assertion
orig_merge = mc.merge
mc.merge = lambda prev, new: list(new)
check("DEFECT merge replacing with empty is detected", orig_merge([1], []) == [1] and mc.merge([1], []) != [1])
mc.merge = orig_merge
orig_f = mc._FILTERS["codex"]
mc._FILTERS["codex"] = lambda i: True
check("DEFECT disabled codex filter is detected", [e["id"] for e in mc.filter_catalog("codex", [{"id": "claude-opus"}])] != [])
mc._FILTERS["codex"] = orig_f
check("DEFECT restored filter rejects foreign ids", mc.filter_catalog("codex", [{"id": "claude-opus"}]) == [])
t9 = tui(os.path.join(tmp, "p9"), {"codex": lambda: ("ok", [], "")})
t9._start_model_refresh(); drain(t9)
check("DEFECT empty ok result does not replace static picker",
      ids(t9) == [i for _, es in m.MODEL_CATALOG_CODEX for _, i in es])

# Recorded-fixture parsers + format drift (fail closed)
FX = os.path.join(os.environ["ROOT"], "scripts", "tests", "fixtures", "model-catalog")
rd = lambda n: open(os.path.join(FX, n), encoding="utf-8").read()
w_ok = lambda n: "/x"
r = mc.fetch_codex(runner=lambda a, t: (0, rd("codex-models.json")), which=w_ok)
check("FIXTURE codex real output: listed gpt kept, hidden and o3 dropped",
      r[0] == "ok" and [e["id"] for e in r[1]] == ["gpt-5.1-codex", "gpt-5.1-codex-mini"]
      and r[1][0]["label"] == "GPT-5.1 Codex")
for fx in ("codex-drift-renamed.json", "codex-drift-text.txt"):
    r = mc.fetch_codex(runner=lambda a, t, fx=fx: (0, rd(fx)), which=w_ok)
    check("FIXTURE %s fails closed with no catalog" % fx, r[0] == "failed" and r[1] == [])
r = mc.fetch_codex(runner=lambda a, t: (1, rd("codex-models.json")), which=w_ok)
check("FIXTURE codex nonzero exit fails closed", r[0] == "failed" and r[1] == [])
kp = os.path.join(FX, "kimi-config.toml")
r = mc.fetch_kimi(env={"UNCLE_KIMI_CONFIG": kp})
check("FIXTURE kimi toml: valid ids kept, unsafe id dropped",
      r[0] == "ok" and [e["id"] for e in r[1]] == ["moonshot-ai/kimi-k2", "moonshot-ai/kimi-k2-thinking"])
r = mc.fetch_kimi(env={"UNCLE_KIMI_CONFIG": os.path.join(FX, "kimi-drift.toml")})
check("FIXTURE kimi renamed table fails closed", r[0] == "failed" and r[1] == [])
r = mc.fetch_kimi(env={}, reader=lambda p: "[models.\"a\"\nbroken ===")
check("FIXTURE kimi garbled toml fails closed", r[0] == "failed" and r[1] == [])

# Defect injection against fixtures: mutated parsers must be detected
orig_pc = mc.parse_codex
mc.parse_codex = lambda text: [{"id": m["slug"], "label": m["slug"]} for m in json.loads(text)["models"]]
r = mc.fetch_codex(runner=lambda a, t: (0, rd("codex-models.json")), which=w_ok)
check("DEFECT parser ignoring visibility is detected", "gpt-internal" in [e["id"] for e in r[1]])
mc.parse_codex = orig_pc
orig_pk = mc.parse_kimi_toml
mc.parse_kimi_toml = lambda text: [{"id": "x", "label": "x"}]
r = mc.fetch_kimi(env={"UNCLE_KIMI_CONFIG": os.path.join(FX, "kimi-drift.toml")})
check("DEFECT kimi parser that invents ids is detected", r[0] == "ok")
mc.parse_kimi_toml = orig_pk
r = mc.fetch_kimi(env={"UNCLE_KIMI_CONFIG": os.path.join(FX, "kimi-drift.toml")})
check("DEFECT restored kimi parser fails closed on drift", r[0] == "failed")
orig_fc = mc.filter_catalog
mc.filter_catalog = lambda p, c, taken=(), cap=50: list(c)
r = mc.fetch_codex(runner=lambda a, t: (0, rd("codex-models.json")), which=w_ok)
check("DEFECT disabled filter in fetcher is detected", "o3-mini" in [e["id"] for e in r[1]])
mc.filter_catalog = orig_fc

# Opt-out golden equality: refresh disabled, even with a populated cache
os.environ["UNCLE_MODEL_REFRESH"] = "0"
gr = os.path.join(tmp, "golden"); os.makedirs(gr)
mc.save_provider(os.path.join(gr, ".uncle", "model-catalog.json"), "codex", [["Codex (live)", [["N", "gpt-cached"]]]])
tg = tui(gr, fetchers); tg._start_model_refresh(); time.sleep(0.2)
for r_, cat in (("codex", m.MODEL_CATALOG_CODEX), ("claude", m.MODEL_CATALOG_CLAUDE)):
    RUNNER[0] = r_
    check("AC-7 golden %s picker rows equal static catalog under opt-out" % r_,
          ids(tg) == [i for _, es in cat for _, i in es])
check("AC-7 golden no diagnostics and cache untouched",
      tg.home_history == [] and "gpt-new" not in open(os.path.join(gr, ".uncle", "model-catalog.json")).read())
del os.environ["UNCLE_MODEL_REFRESH"]

# T-AC1-nonblocking / T-AC5-optout-values / T-AC2-timeout / T-SI2 (step 4)
gate = threading.Event()
rp = os.path.join(tmp, "nb"); os.makedirs(rp)
tn = tui(rp, {})
t0 = time.time()
tn._start_model_refresh(fetchers={"codex": lambda: (gate.wait(5), ("ok", [{"id": "gpt-late", "label": "L"}], ""))[1]})
t_start = time.time() - t0
t1 = time.time(); tn.poll_model_catalog(); t_poll = time.time() - t1
check("T-AC1-nonblocking _start_model_refresh and poll return while fetch is blocked", t_start < 1.0 and t_poll < 0.5)
RUNNER[0] = "codex"
check("T-AC1-nonblocking picker still static while fetch pending", "gpt-late" not in ids(tn))
gate.set()
for _ in range(100):
    time.sleep(0.05)
    if tn.model_catalog_queue.qsize(): break
tn.poll_model_catalog()
check("T-AC1-nonblocking result applied after fetch completes", ids(tn) == ["gpt-late"])
for v in ("0", "off", "false", "no", "OFF", " No "):
    os.environ["UNCLE_MODEL_REFRESH"] = v
    called = []
    to = tui(os.path.join(tmp, "oo"), {})
    to._start_model_refresh(fetchers={"codex": lambda: called.append(1) or ("ok", [{"id": "x", "label": "x"}], "")})
    time.sleep(0.1)
    check("T-AC5-optout-values %r: no fetch, library agrees" % v, not called and not mc.refresh_enabled() and to.model_catalogs == {})
os.environ.pop("UNCLE_MODEL_REFRESH", None)
check("T-AC5-optout-values unset/1/yes keep refresh on", mc.refresh_enabled({}) and mc.refresh_enabled({"UNCLE_MODEL_REFRESH": "1"}) and mc.refresh_enabled({"UNCLE_MODEL_REFRESH": "yes"}))
tw = tui(os.path.join(tmp, "si2"), {})
tw.supervision = {"stage1": {"model": "stored-model-not-in-list"}}
before = repr(tw.supervision)
tw._start_model_refresh(fetchers={"codex": ok_fetch("gpt-new")}); drain(tw)
check("T-SI2-config-untouched stored stage selection unchanged by refresh", repr(tw.supervision) == before)
check("T-AC3-timeout-bounded library timeouts are finite", all(isinstance(x, (int, float)) and 0 < x <= 30 for x in (mc.CLAUDE_TIMEOUT, mc.CODEX_TIMEOUT, mc.KIMI_TIMEOUT)))
r = mc.fetch_codex(runner=lambda a, t: (_ for _ in ()).throw(subprocess.TimeoutExpired("codex", t)), which=w_ok)
check("T-AC2-timeout codex timeout -> failed, no catalog", r[0] == "failed" and r[1] == [])

sys.exit(1 if fails else 0)
PY
mainrc=$?

# ---- SI1-SI6 mutation matrix: patch a COPY of the module; the named probe must fail on the mutant.
MROOT="$TMP/mut" ROOT="$ROOT" python3 -I - <<'PY'
import os, re, sys, shutil, subprocess
root, mroot = os.environ["ROOT"], os.environ["MROOT"]
src = open(os.path.join(root, "scripts", "lib", "model_catalog.py")).read()
PRE = "import sys,os,io,json,threading,tempfile,urllib.error;sys.path.insert(0,%r);import model_catalog as mc\n"
P = {
 "merge-empty": "assert mc.merge([1],[])==[1]",
 "cache-concurrent": "d=tempfile.mkdtemp();cp=os.path.join(d,'c.json')\nts=[threading.Thread(target=mc.save_provider,args=(cp,'p%d'%i,[['g',[['l','m']]]])) for i in range(16)]\n[x.start() for x in ts];[x.join() for x in ts]\nassert len(mc.load_cache(cp))==16",
 "cache-atomic": "d=tempfile.mkdtemp();cp=os.path.join(d,'c.json')\nmc.save_provider(cp,'a',[['g',[['l','m']]]])\nassert 'a' in mc.load_cache(cp)",
 "secret": "K='sk-secret-123'\nclass O:\n  def open(s,r,timeout=None): raise RuntimeError('leak '+K)\nr=mc.fetch_claude(env={'ANTHROPIC_API_KEY':K},opener=O(),which=lambda n:'/b')\nassert K not in repr(r)",
 "filter": "assert mc.filter_catalog('codex',[{'id':'claude-opus'},{'id':'o3-mini'}])==[]",
 "timeout": "seen=[]\nclass R:\n  status=200\n  def read(s,n=-1): return b'{\"data\":[]}'\n  def __enter__(s): return s\n  def __exit__(s,*a): return False\nclass O:\n  def open(s,r,timeout=None): seen.append(timeout); return R()\nmc.fetch_claude(env={'ANTHROPIC_API_KEY':'k'},opener=O(),which=lambda n:'/b')\nassert seen==[mc.CLAUDE_TIMEOUT]",
 "optout": "assert not any(mc.refresh_enabled({'UNCLE_MODEL_REFRESH':v}) for v in ('0','off','false','no'))",
 "cache-corrupt": "d=tempfile.mkdtemp();cp=os.path.join(d,'c.json');open(cp,'w').write('{bad');assert mc.load_cache(cp)=={}",
}
M = [  # id, probe, old, new
 ("T-MUT-SI1", "merge-empty", "return list(refreshed) if refreshed else list(previous or [])", "return list(refreshed)"),
 ("T-MUT-SI4-lost-update", "cache-concurrent", "current = load_cache(path)", "current = {}"),
 ("T-MUT-SI4-no-replace", "cache-atomic", "os.replace(tmp, path)", "pass"),
 ("T-MUT-SI5", "secret", 'return ("failed", [], "claude: %s" % type(exc).__name__)', 'return ("failed", [], "claude: %s" % exc)'),
 ("T-MUT-SI6", "filter", '(opus|sonnet|o3|kimi)', '(zzzzqq)'),
 ("T-MUT-SI3-timeout", "timeout", "op.open(req, timeout=timeout)", "op.open(req)"),
 ("T-MUT-OPTOUT", "optout", '("0", "off", "false", "no")', '("0",)'),
 ("T-MUT-SI4-corrupt", "cache-corrupt", "    except Exception:\n        return {}\n\n\ndef load_cached", "    except OSError:\n        return {}\n\n\ndef load_cached"),
]
fails = 0
for i, (mid, pk, old, new) in enumerate(M):
    d = os.path.join(mroot, str(i)); os.makedirs(d)
    if old not in src:
        print("FAIL - %s mutation target not found in module" % mid); fails += 1; continue
    for tag, text in (("control", src), ("mutant", src.replace(old, new, 1))):
        open(os.path.join(d, "model_catalog.py"), "w").write(text)
        rc = subprocess.run([sys.executable, "-I", "-c", PRE % d + P[pk]], capture_output=True, timeout=60).returncode
        if tag == "control" and rc != 0:
            print("FAIL - %s probe %s fails on unmutated module" % (mid, pk)); fails += 1; break
        if tag == "mutant":
            ok = rc != 0
            print(("ok   - %s killed by probe '%s'" if ok else "FAIL - %s SURVIVED probe '%s'") % (mid, pk)); fails += 0 if ok else 1
sys.exit(1 if fails else 0)
PY
mutrc=$?
[ "$mainrc" -eq 0 ] && [ "$mutrc" -eq 0 ]

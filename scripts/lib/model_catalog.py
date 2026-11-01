"""Pure model-catalog helpers: parsers, filters, merge, cache, fetchers.

A catalog is a list of ``{"id": str, "label": str}`` dicts. Fetchers return
``(status, catalog, reason)`` with status ``ok|skipped|failed``.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request

try:  # pragma: no cover - platform dependent
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

PROVIDERS = ("claude", "codex", "kimi")
CAP = 50
CODEX_TIMEOUT = 8
CLAUDE_TIMEOUT = 5
KIMI_TIMEOUT = 2
ANTHROPIC_URL = "https://api.anthropic.com/v1/models?limit=100"
ANTHROPIC_HOST = "api.anthropic.com"
CACHE_VERSION = 1

_CLAUDE_RE = re.compile(r"^(claude|opus|sonnet|haiku)[A-Za-z0-9._:-]*$")
_CODEX_EXCLUDE_RE = re.compile(r"(opus|sonnet|o3|kimi)", re.I)
_KIMI_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

_cache_lock = threading.Lock()


def refresh_enabled(env=None):
    env = os.environ if env is None else env
    return str(env.get("UNCLE_MODEL_REFRESH", "1")).strip().lower() not in ("0", "off", "false", "no")


# ---------------------------------------------------------------- parsers
def _entry(mid, label=None):
    return {"id": mid, "label": label or mid}


def parse_codex(text):
    """Parse `codex debug models` JSON; keep visibility == list."""
    data = json.loads(text)
    items = data.get("models", []) if isinstance(data, dict) else data
    out = []
    for m in items or []:
        if not isinstance(m, dict) or m.get("visibility") != "list":
            continue
        slug = m.get("slug")
        if isinstance(slug, str) and slug:
            name = m.get("display_name")
            out.append(_entry(slug, name if isinstance(name, str) and name else slug))
    return out


def parse_kimi_toml(text):
    """Return model ids from [models."id"] tables."""
    ids = []
    if tomllib is not None:
        try:
            models = tomllib.loads(text).get("models", {})
            if isinstance(models, dict):
                ids = list(models.keys())
        except Exception:
            ids = []
    if not ids:
        ids = re.findall(r'^\s*\[models\.(?:"([^"]+)"|([A-Za-z0-9_-]+))\]', text, re.M)
        ids = [a or b for a, b in ids]
    return [_entry(i) for i in ids]


def parse_anthropic(text):
    data = json.loads(text)
    out = []
    for m in data.get("data", []) if isinstance(data, dict) else []:
        if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"]:
            name = m.get("display_name")
            out.append(_entry(m["id"], name if isinstance(name, str) and name else m["id"]))
    return out


# ---------------------------------------------------------------- filters
_FILTERS = {
    "claude": lambda i: bool(_CLAUDE_RE.match(i)),
    "codex": lambda i: not _CODEX_EXCLUDE_RE.search(i) and bool(_KIMI_RE.match(i)),
    "kimi": lambda i: bool(_KIMI_RE.match(i)),
}


def filter_catalog(provider, catalog, taken=(), cap=CAP):
    """Apply shim allowlist, uniqueness vs `taken` ids, and the cap."""
    check = _FILTERS[provider]
    seen = set(taken)
    out = []
    for m in catalog:
        mid = m.get("id") if isinstance(m, dict) else None
        if not isinstance(mid, str) or mid in seen or not check(mid):
            continue
        seen.add(mid)
        out.append({"id": mid, "label": m.get("label") or mid})
        if len(out) >= cap:
            break
    return out



def merge(previous, refreshed):
    """Refreshed replaces previous wholesale unless empty."""
    return list(refreshed) if refreshed else list(previous or [])


# ------------------------------------------------------------------ cache
def load_cache(path):
    """Return {provider: {fetched_at, groups}}; missing/corrupt -> {}."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        provs = data["providers"]
        if data.get("version") != CACHE_VERSION or not isinstance(provs, dict):
            return {}
        return {k: v for k, v in provs.items()
                if isinstance(v, dict) and isinstance(v.get("groups"), list)}
    except Exception:
        return {}


def load_cached_catalogs(path):
    return {k: v["groups"] for k, v in load_cache(path).items()}


def save_provider(path, name, groups, now=None, _between=None):
    """Read-modify-write one provider's entry under a lock; atomic rename."""
    import time
    with _cache_lock:
        lock_fh = None
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            if fcntl is not None:
                try:
                    lock_fh = open(path + ".lock", "a")
                    fcntl.flock(lock_fh, fcntl.LOCK_EX)
                except OSError:
                    lock_fh = None
            current = load_cache(path)
            if _between:
                _between()
            current[name] = {"fetched_at": now if now is not None else time.time(),
                             "groups": groups}
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)),
                                       prefix=".model-catalog.")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump({"version": CACHE_VERSION, "providers": current}, fh)
                os.replace(tmp, path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        finally:
            if lock_fh is not None:
                try:
                    fcntl.flock(lock_fh, fcntl.LOCK_UN)
                except OSError:
                    pass
                lock_fh.close()


# --------------------------------------------------------------- fetchers
def _default_runner(argv, timeout):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout


def fetch_codex(runner=None, which=shutil.which, timeout=CODEX_TIMEOUT, taken=()):
    if not which("codex"):
        return ("skipped", [], "codex not on PATH")
    try:
        rc, out = (runner or _default_runner)(["codex", "debug", "models"], timeout)
        if rc != 0:
            return ("failed", [], "codex exited %s" % rc)
        cat = filter_catalog("codex", parse_codex(out), taken)
        return ("ok", cat, "") if cat else ("failed", [], "no usable models")
    except subprocess.TimeoutExpired:
        return ("failed", [], "codex timed out")
    except Exception as exc:
        return ("failed", [], "codex: %s" % type(exc).__name__)


def _read_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read(1 << 20)


def fetch_kimi(env=None, reader=None, taken=(), timeout=KIMI_TIMEOUT):
    env = os.environ if env is None else env
    path = env.get("UNCLE_KIMI_CONFIG") or os.path.expanduser("~/.kimi-code/config.toml")
    if reader is None and not os.path.isfile(path):
        return ("skipped", [], "kimi config not found")
    try:
        box = {}

        def work():
            try:
                box["text"] = (reader or _read_file)(path)
            except BaseException as exc:  # noqa: BLE001
                box["exc"] = exc

        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            return ("failed", [], "kimi timed out")
        if "exc" in box:
            raise box["exc"]
        text = box["text"]
        cat = filter_catalog("kimi", parse_kimi_toml(text), taken)
        return ("ok", cat, "") if cat else ("failed", [], "no usable models")
    except Exception as exc:
        return ("failed", [], "kimi: %s" % type(exc).__name__)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_claude_opener():
    return urllib.request.build_opener(_NoRedirect)


def fetch_claude(env=None, opener=None, which=shutil.which, timeout=CLAUDE_TIMEOUT, taken=()):
    env = os.environ if env is None else env
    key = env.get("ANTHROPIC_API_KEY")
    if not which("claude"):
        return ("skipped", [], "claude not on PATH")
    if not key:
        return ("skipped", [], "ANTHROPIC_API_KEY not set")
    try:
        req = urllib.request.Request(ANTHROPIC_URL, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01"})
        op = opener or build_claude_opener()
        with op.open(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            if status != 200:
                return ("failed", [], "HTTP %s" % status)
            body = resp.read(1 << 20).decode("utf-8")
        cat = filter_catalog("claude", parse_anthropic(body), taken)
        return ("ok", cat, "") if cat else ("failed", [], "no usable models")
    except urllib.error.HTTPError as exc:
        return ("failed", [], "HTTP %s" % exc.code)
    except Exception as exc:
        return ("failed", [], "claude: %s" % type(exc).__name__)



GROUP_NAMES = {"claude": "Claude (live)", "codex": "Codex (live)", "kimi": "Kimi (live)"}


def to_groups(provider, catalog):
    """Picker shape: [(group, [(label, id), ...])]; empty catalog -> []."""
    if not catalog:
        return []
    return [(GROUP_NAMES[provider], [(m["label"], m["id"]) for m in catalog])]


def default_fetchers(taken=()):
    """name -> zero-arg callable returning (status, catalog, reason)."""
    return {
        "claude": lambda: fetch_claude(taken=taken),
        "codex": lambda: fetch_codex(taken=taken),
        "kimi": lambda: fetch_kimi(taken=taken),
    }

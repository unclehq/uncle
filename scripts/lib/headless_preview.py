#!/usr/bin/env python3
"""Preview for `uncle --noui`: the browser tab the interactive screen opens, without the screen.

The preview build is the driver's own stage and already runs headless: it serves a first look and opens a tab, and the driver
stops that server when it exits. Two things used to belong to the interactive screen alone, and are done here for --noui:

  * Early page. When a previewable page appears while an application is being built and the driver is not already serving one
    (the preview build was skipped, for example in a directory that already holds a project), open it, from the same stages
    the screen watches. A driver-owned server is never duplicated.
  * Finished app. When the build completes, the driver has stopped its server and nothing is left showing the result. Serve the
    finished project and open it.

Both start `preview_server.py` detached, the same code the driver uses, so a React or Svelte project is handed to its dev server
once dependencies exist and the page reloads itself. The server this starts at the end outlives the command, so it expires
(one hour) and says how to stop it. Nothing here runs for a change request, or for a desktop
application (those are launched, not browsed).

Turn it off with WORKFLOW_PREVIEW_OPEN_BROWSER=0 (the driver's own switch).
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The stages the screen opens a first page from (uncle_tui.py _PREVIEW_STAGES), as driver states. A gate (WAIT_*) is not a stage
# being run, and a first tab during test review or the audit would surprise someone reading those reports.
EARLY_STATES = ('REQUIREMENTS', 'PROJECT_PLAN', 'ADVERSARIAL_REVIEW', 'UPDATED_PLAN', 'PREFLIGHT', 'IMPLEMENT', 'REPAIR')
POLL_SECONDS = 0.5
URL_WAIT_SECONDS = 8.0
DEFAULT_TTL_SECONDS = 3600
# The early server is normally stopped by the driver's exit trap; this only bounds one left behind by a driver that died.
EARLY_TTL_SECONDS = 6 * 3600
OFF = ('0', 'false', 'no', 'off')


def hosted_run(env=None):
    """True in a hosted run, where the host publishes the one signed preview link and no loopback preview is started."""
    env = os.environ if env is None else env
    return env.get('UNCLE_HOSTED') == '1'


def enabled(env=None):
    env = os.environ if env is None else env
    if hosted_run(env):
        return False
    return str(env.get('WORKFLOW_PREVIEW_OPEN_BROWSER', '')).strip().lower() not in OFF


def workflow_dir(root):
    return Path(root) / '.uncle' / 'workflow'


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def family(root):
    """The driver's own record of which state machine ran: 'app' (a new application) or 'change'."""
    return _read(workflow_dir(root) / 'family')


def driver_state(root):
    raw = _read(workflow_dir(root) / 'state')
    return raw.split(':', 1)[1] if re.match(r'^[0-9]+:', raw) else raw


def server_alive(root):
    """True when a live preview server (the driver's, or one started here) is recorded and its process exists."""
    try:
        pid = int(_read(workflow_dir(root) / 'preview-server.pid'))
        os.kill(pid, 0)
    except (ValueError, OSError):
        return False
    return True


def page_available(root):
    """Something to show: a root index.html, or a React/Svelte project with the dev server installed."""
    try:
        if (Path(root) / 'index.html').stat().st_size > 0:
            return True
    except OSError:
        pass
    try:
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        from preview_server import development_preview
        return development_preview(root) is not None
    except Exception:       # noqa: BLE001 - a project we cannot inspect has nothing we can show
        return False


def desktop_app(root):
    """A desktop application (Electron, Tauri) is launched, not browsed; the screen does not open a tab for it either."""
    try:
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import desktop_launch
        return desktop_launch.detect(root).get('framework') != 'none'
    except Exception:       # noqa: BLE001
        return False


def start_live_preview(root, ttl=None, env=None):
    """Start the driver's own preview server detached, with a lifetime. Returns its pid, or None."""
    state = workflow_dir(root)
    try:
        (state / 'logs').mkdir(parents=True, exist_ok=True)
        log = open(state / 'logs' / 'preview-server.log', 'ab')
    except OSError:
        return None
    child_env = dict(os.environ if env is None else env)
    if ttl:
        child_env['UNCLE_PREVIEW_TTL_SECONDS'] = str(int(ttl))
    try:
        with log:
            process = subprocess.Popen([sys.executable, '-B', str(HERE / 'preview_server.py'), 'start', str(root), str(state)],
                                       cwd=str(root), env=child_env, stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
    except OSError:
        return None
    return process.pid


def wait_for_url(root, timeout=URL_WAIT_SECONDS, clock=time.monotonic, sleep=time.sleep):
    url_file = workflow_dir(root) / 'preview-server.url'
    deadline = clock() + timeout
    while clock() < deadline:
        if _read(url_file):
            return True
        sleep(0.1)
    return False


class HeadlessPreview:
    """Called by the headless runner: `poll()` while the driver runs, `finish()` once it has completed."""

    def __init__(self, root, env=None, start=None, clock=time.monotonic, wait=None):
        self.root = str(root)
        self.env = env
        self.start = start or (lambda ttl=None: start_live_preview(self.root, ttl=ttl, env=self.env))
        self.clock = clock
        self.wait = wait or (lambda: wait_for_url(self.root))
        self.early_started = False
        self._next = 0.0

    def poll(self):
        """The early page. True when it started one now."""
        if self.early_started or not enabled(self.env):
            return False
        now = self.clock()
        if now < self._next:
            return False
        self._next = now + POLL_SECONDS
        if family(self.root) != 'app' or driver_state(self.root) not in EARLY_STATES:
            return False
        if server_alive(self.root):
            self.early_started = True      # the driver owns it (it keeps its own tab, handoff and reload): never a second one
            return False
        if not page_available(self.root):
            return False
        if self.start(EARLY_TTL_SECONDS) is None:
            return False
        self.early_started = True
        return True

    def finish(self):
        """The finished app. Returns the lines to announce after the runner's own `Preview:` line (possibly none)."""
        if not enabled(self.env) or family(self.root) != 'app':
            return []
        if desktop_app(self.root) or not page_available(self.root):
            return []
        if server_alive(self.root):
            return []
        ttl = DEFAULT_TTL_SECONDS
        pid = self.start(ttl)
        if pid is None:
            return ['Local preview: could not start a preview server for the finished application\n']
        if not self.wait():
            return ['Local preview: the preview server did not report an address; see .uncle/workflow/logs/preview-server.log\n']
        minutes = max(1, int(ttl // 60))
        lines = []
        url = _read(workflow_dir(self.root) / 'preview-server.url')
        if url:
            if str(HERE) not in sys.path:
                sys.path.insert(0, str(HERE))
            import preview_announce
            lines.append(preview_announce.line(url, is_hosted=hosted_run(self.env)) + '\n')
        lines.append('Local preview: the server (pid %d) keeps running for %d minutes; stop it earlier with: kill %d\n' % (pid, minutes, pid))
        return lines

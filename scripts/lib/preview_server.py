"""Serve a project's web page and reload the browser whenever it changes.

Implementation keeps rewriting the page long after the first draft lands: on a
calculator build the preview became viewable at 01:49:15 and the stage ran until
01:54:25, rewriting index.html and style.css at 01:54:19 and 01:54:24. Opening
the file once showed the first draft -- in that run, a calculator whose
stylesheet did not exist yet -- and then left it stale for five minutes.

A file:// URL cannot reload itself and the page is the agent's artifact, so
injecting a reload script into it on disk is not an option. Serving the tree
instead lets the snippet be added to the bytes on the way out, leaving every
file untouched. One tab, opened at the earliest moment, correct from then on.

Bound to loopback on an ephemeral port: this serves a working tree, and nothing
outside the machine has any business reading it.
"""
import hashlib
import json
import os
import re
import socket
import subprocess
import signal
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
from urllib.request import urlopen
from urllib.parse import urljoin
import webbrowser
from process_tree import group_options, kill_tree, launch_command
from project_paths import project_files

VERSION_PATH = '/__uncle_preview_version'
HANDOFF_PATH = '/__uncle_preview_handoff'
POLL_MS = 700

_RELOAD = """
<script>
(function () {
  var current = null;
  function poll() {
    fetch(%r, {cache: 'no-store'})
      .then(function (r) { return r.text(); })
      .then(function (target) { if (target) { location.replace(target); } })
      .catch(function () {});
    fetch(%r, {cache: 'no-store'})
      .then(function (r) { return r.text(); })
      .then(function (v) {
        if (current === null) { current = v; }
        else if (v !== current) { location.reload(); }
      })
      .catch(function () {});
  }
  poll();
  setInterval(poll, %d);
})();
</script>
""" % (HANDOFF_PATH, VERSION_PATH, POLL_MS)


def tree_version(root):
    """A digest that changes whenever a served file does."""
    digest = hashlib.sha256()
    for rel in sorted(project_files(root)):
        try:
            info = (Path(root) / rel).stat()
        except OSError:
            continue
        digest.update(rel.encode('utf-8', 'replace'))
        digest.update(b'%d:%d' % (info.st_size, info.st_mtime_ns))
    return digest.hexdigest()


class _Handler(SimpleHTTPRequestHandler):
    # Set on the per-server subclass below.  It is the last known standalone
    # page from preview-build, retained while implementation temporarily
    # replaces index.html with a Vite source entrypoint.
    fallback_html = None
    handoff_url = ''

    def log_message(self, *args):
        pass                                    # curses owns the terminal

    def do_GET(self):
        if self.path.split('?')[0] == HANDOFF_PATH:
            body = self.handoff_url.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split('?')[0] == VERSION_PATH:
            body = tree_version(self.directory).encode('ascii')
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return
        SimpleHTTPRequestHandler.do_GET(self)

    def send_head(self):
        """Append the reload snippet to HTML, on the wire only."""
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            for index in ('index.html', 'index.htm'):
                if os.path.isfile(os.path.join(path, index)):
                    path = os.path.join(path, index)
                    break
        # A Vite entrypoint is not a static web page: it imports JSX/CSS from
        # /src and needs Vite's transform pipeline.  During `npm install`, it
        # can replace the styled standalone preview before Vite and the
        # framework runtime are usable. Keep the visible, styled preview in
        # place until serve_live_preview hands the tab to Vite.
        if (self.fallback_html and self.path.split('?', 1)[0] in ('/', '/index.html')
                and _needs_development_server(path)):
            path = self.fallback_html
        if not path.endswith(('.html', '.htm')) or not os.path.isfile(path):
            return SimpleHTTPRequestHandler.send_head(self)
        try:
            body = Path(path).read_bytes() + _RELOAD.encode('utf-8')
        except OSError:
            return SimpleHTTPRequestHandler.send_head(self)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        import io
        return io.BytesIO(body)


def _needs_development_server(path):
    """Whether an HTML page imports application source needing Vite/etc."""
    try:
        body = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False
    return bool(re.search(r'<script[^>]+type=["\']module["\'][^>]+src=["\']/?src/',
                          body, re.I))


class PreviewServer:
    """A live-reloading view of `root`, or nothing at all.

    Never raises on failure: a preview that cannot start must not disturb a
    running build. `url` is None when it did not come up.
    """

    def __init__(self, root, page='index.html', fallback_html=None):
        self.root = str(Path(root).resolve())
        self.url = None
        self.server = None
        fallback = Path(fallback_html).resolve() if fallback_html else None
        if fallback is not None and not fallback.is_file():
            fallback = None
        handler = type('PreviewHandler', (_Handler,), {
            'fallback_html': str(fallback) if fallback else None,
            'handoff_url': '',
        })
        self.handler = handler
        try:
            self.server = ThreadingHTTPServer(
                ('127.0.0.1', 0), partial(handler, directory=self.root))
        except OSError:
            return
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d/%s' % (self.server.server_address[1], page.lstrip('/'))

    def handoff(self, url):
        """Redirect the existing preview tab only after a usable replacement exists."""
        self.handler.handoff_url = url or ''

    def close(self):
        if self.server is not None:
            try:
                self.server.shutdown()
                self.server.server_close()
            except OSError:
                pass
            self.server = None


def _open_local_browser(url):
    """Open only the loopback preview URL, with an OS fallback."""
    if webbrowser.open(url):
        return True
    try:
        if sys.platform == 'darwin':
            subprocess.Popen(['open', url], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os.name == 'nt':
            os.startfile(url)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(['xdg-open', url], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def serve_live_preview(root, state):
    """Serve the standalone preview, then hand off to Vite when it exists."""
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    server = PreviewServer(root, fallback_html=state / 'preview/static-index.html')
    if server.url is None:
        return 1
    pid_path, url_path = state / 'preview-server.pid', state / 'preview-server.url'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    url_path.write_text(server.url, encoding='utf-8')
    _open_local_browser(server.url)
    stopped = threading.Event()
    previous = signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    development = None
    handed_off = False
    try:
        while not stopped.wait(.2):
            # preview-build deliberately creates standalone HTML before the
            # implementation has dependencies.  Once implementation installs
            # Vite, serving its module index through SimpleHTTPServer produces
            # a blank page.  The preview owner, not the TUI, owns this
            # transition so it also works unattended.
            if development is None:
                reused = existing_development_url(state)
                if reused:
                    server.handoff(reused)
                    url_path.write_text(reused, encoding='utf-8')
                    handed_off = True
                    continue
                spec = development_preview(root)
                if spec is None:
                    continue
                development = DevelopmentPreview(root, spec)
                continue
            if development.process is None or development.process.poll() is not None:
                development.close()
                development = None
                handed_off = False
                server.handoff('')
                for name in ('preview-vite.pid', 'preview-vite.url'):
                    (state / name).unlink(missing_ok=True)
                continue
            # HTTP alone is insufficient: Vite can return index.html while a
            # JSX import still fails. Require the entry module and, where the
            # project already has Playwright, an actual mounted browser DOM
            # before replacing the styled static preview.
            if not handed_off and development.ready() and development.rendered():
                (state / 'preview-vite.pid').write_text(str(development.process.pid), encoding='utf-8')
                (state / 'preview-vite.url').write_text(development.url, encoding='utf-8')
                server.handoff(development.url)
                url_path.write_text(development.url, encoding='utf-8')
                handed_off = True
    finally:
        signal.signal(signal.SIGTERM, previous)
        if server is not None:
            server.close()
        if development is not None:
            development.close()
        for name in ('preview-vite.pid', 'preview-vite.url'):
            (state / name).unlink(missing_ok=True)
        pid_path.unlink(missing_ok=True)
        url_path.unlink(missing_ok=True)
    return 0


def stop_live_preview(state):
    state = Path(state)
    try:
        pid = int((state / 'preview-server.pid').read_text(encoding='utf-8'))
        os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError):
        pass
    # A completed run must not leave the TUI or a later invocation pointing at
    # a terminated loopback server.  The owner normally removes these in its
    # finally block, but a forced process shutdown bypasses that cleanup.
    for name in ('preview-server.pid', 'preview-server.url',
                 'preview-vite.pid', 'preview-vite.url'):
        (state / name).unlink(missing_ok=True)


def development_preview(root):
    """A local Vite preview spec for a React/Svelte source project, or None.

    Source modules cannot be served by the static preview server. Require the
    project's installed Vite binary before starting anything, so polling during
    `npm install` is harmless and a failed early launch is not mistaken for a
    usable preview.
    """
    root = Path(root).resolve()
    try:
        package = json.loads((root / 'package.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    scripts = package.get('scripts') if isinstance(package, dict) else None
    deps = {}
    if isinstance(package, dict):
        for name in ('dependencies', 'devDependencies'):
            value = package.get(name)
            if isinstance(value, dict):
                deps.update(value)
    framework = 'react' in deps or 'react-dom' in deps or 'svelte' in deps
    if not framework or not isinstance(scripts, dict):
        return None
    vite = root / 'node_modules' / '.bin' / 'vite'
    # A Vite executable can appear before npm has finished installing the
    # application's framework packages. Starting it at that point returns
    # index.html successfully but fails module resolution in the browser,
    # leaving an empty #root. Do not hand off the visible preview until the
    # runtime named by package.json is actually present.
    required_runtime = ('svelte',) if 'svelte' in deps and 'react' not in deps else ('react', 'react-dom')
    if not vite.is_file() or any(not (root / 'node_modules' / name / 'package.json').is_file()
                                 for name in required_runtime):
        return None
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    if not isinstance(scripts.get('dev'), str):
        # A project that names its dev server something else (`start`, `serve`) still has a source index.html
        # that only a dev server can run -- served statically it is a blank page (noinit: `start` was Vite,
        # there was no `dev`).  The binary is already installed; run it directly with our own host and port.
        if 'vite' not in deps and 'vite' not in ' '.join(str(v) for v in scripts.values()):
            return None
        return {'command': [str(vite), '--host', '127.0.0.1', '--port', str(port), '--strictPort'],
                'url': 'http://127.0.0.1:%d' % port}
    manager = 'pnpm' if (root / 'pnpm-lock.yaml').is_file() else 'yarn' if (root / 'yarn.lock').is_file() else 'npm'
    command = ([manager, 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(port), '--strictPort'])
    return {'command': command, 'url': 'http://127.0.0.1:%d' % port}


class DevelopmentPreview:
    """A disposable loopback dev server for React/Svelte's early preview."""

    def __init__(self, root, spec):
        self.root, self.url, self.process = str(Path(root).resolve()), spec['url'], None
        self.cancelled = threading.Event()
        try:
            self.process = subprocess.Popen(launch_command(spec['command']), cwd=self.root,
                                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, **group_options())
        except OSError:
            self.url = None
            return

    def ready(self):
        """True only when Vite serves both its document and source entry module."""
        try:
            body = urlopen(self.url, timeout=1).read().decode('utf-8', 'replace')
            match = re.search(r'<script[^>]+type=["\']module["\'][^>]+src=["\']([^"\']+)', body, re.I)
            if not match:
                return True
            urlopen(urljoin(self.url, match.group(1)), timeout=1).read(1)
            return True
        except OSError:
            return False

    def rendered(self):
        """Require a mounted root and no browser/module error before handoff.

        This uses the project's existing Playwright dependency only.  A
        preview must never install a browser or dependency merely to check a
        throwaway page; without Playwright we retain the known-good standalone
        preview instead of gambling on an unverified Vite page.
        """
        root = Path(self.root)
        package = next((name for name in ('playwright', '@playwright/test')
                        if (root / 'node_modules' / name / 'package.json').is_file()), None)
        if package is None:
            return False
        program = r'''
import { chromium } from %r;
const browser = await chromium.launch({headless: true});
const page = await browser.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
page.on('console', item => { if (item.type() === 'error') errors.push(item.text()); });
try {
  await page.goto(%r, {waitUntil: 'networkidle', timeout: 8000});
  const mounted = await page.locator('#root').evaluate(node => node.childElementCount > 0 || node.textContent.trim().length > 0);
  await browser.close();
  process.exit(mounted && errors.length === 0 ? 0 : 1);
} catch (_) { await browser.close(); process.exit(1); }
''' % (package, self.url)
        try:
            result = subprocess.run(['node', '--input-type=module', '-e', program], cwd=self.root,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=12)
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def close(self):
        self.cancelled.set()
        if self.process and self.process.poll() is None:
            kill_tree(self.process)


def existing_development_url(state):
    """Reuse the driver-owned application server instead of spawning Vite twice."""
    state = Path(state)
    for prefix in ('app-server', 'preview-vite'):
        try:
            pid = int((state / (prefix + '.pid')).read_text(encoding='utf-8'))
            os.kill(pid, 0)
            url = (state / (prefix + '.url')).read_text(encoding='utf-8').strip()
            if url:
                urlopen(url, timeout=1).read(1)
                return url
        except (OSError, ValueError):
            continue
    return ''


def main(argv):
    if argv[:1] == ['start'] and len(argv) == 3:
        return serve_live_preview(argv[1], argv[2])
    if argv[:1] == ['stop'] and len(argv) == 2:
        stop_live_preview(argv[1])
        return 0
    raise SystemExit('usage: preview_server.py start PROJECT STATE_DIR | stop STATE_DIR')


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

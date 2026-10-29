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
import webbrowser
from process_tree import group_options, kill_tree, launch_command
from project_paths import project_files

VERSION_PATH = '/__uncle_preview_version'
POLL_MS = 700

_RELOAD = """
<script>
(function () {
  var current = null;
  function poll() {
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
""" % (VERSION_PATH, POLL_MS)


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
    def log_message(self, *args):
        pass                                    # curses owns the terminal

    def do_GET(self):
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


class PreviewServer:
    """A live-reloading view of `root`, or nothing at all.

    Never raises on failure: a preview that cannot start must not disturb a
    running build. `url` is None when it did not come up.
    """

    def __init__(self, root, page='index.html'):
        self.root = str(Path(root).resolve())
        self.url = None
        self.server = None
        try:
            self.server = ThreadingHTTPServer(
                ('127.0.0.1', 0), partial(_Handler, directory=self.root))
        except OSError:
            return
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d/%s' % (self.server.server_address[1], page.lstrip('/'))

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
    """Serve and open the preview until the workflow explicitly stops it."""
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    server = PreviewServer(root)
    if server.url is None:
        return 1
    pid_path, url_path = state / 'preview-server.pid', state / 'preview-server.url'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    url_path.write_text(server.url, encoding='utf-8')
    _open_local_browser(server.url)
    stopped = threading.Event()
    previous = signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    try:
        while not stopped.wait(.2):
            pass
    finally:
        signal.signal(signal.SIGTERM, previous)
        server.close()
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
    if not vite.is_file():
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
        threading.Thread(target=self._open_when_ready, daemon=True).start()

    def _open_when_ready(self):
        deadline = time.monotonic() + 30
        while not self.cancelled.wait(.2):
            if self.process.poll() is not None or time.monotonic() >= deadline:
                return
            try:
                with urlopen(self.url, timeout=1):
                    _open_local_browser(self.url)
                    return
            except OSError:
                pass

    def close(self):
        self.cancelled.set()
        if self.process and self.process.poll() is None:
            kill_tree(self.process)


def main(argv):
    if argv[:1] == ['start'] and len(argv) == 3:
        return serve_live_preview(argv[1], argv[2])
    if argv[:1] == ['stop'] and len(argv) == 2:
        stop_live_preview(argv[1])
        return 0
    raise SystemExit('usage: preview_server.py start PROJECT STATE_DIR | stop STATE_DIR')


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

"""Launch the built application and stream its output without blocking curses."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from urllib.parse import urlparse
from urllib.request import urlopen
import webbrowser
from process_tree import group_options, kill_tree, launch_command

STAR_URL = 'https://github.com/unclehq/uncle'


def has_starred():
    """Unknown authentication/network state is not evidence of a star."""
    try:
        result = subprocess.run(['gh', 'api', '--hostname', 'github.com', '--method', 'GET',
                                 'user/starred/unclehq/uncle'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, timeout=5)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def launch_spec(root):
    root = Path(root).resolve()
    manifest = root / '.uncle' / 'launch.json'
    if manifest.is_file():
        data = json.loads(manifest.read_text())
        if not isinstance(data, dict) or data.get('kind') not in ('command', 'webpage', 'none'):
            raise ValueError('Invalid .uncle/launch.json kind')
        command = data.get('command')
        if command is not None and (not isinstance(command, list) or not command or
                                    not all(isinstance(x, str) and x and '\0' not in x for x in command)):
            raise ValueError('Launch command must be a nonempty argument array')
        if data['kind'] == 'command' and command is None:
            raise ValueError('Command project requires a launch command')
        if 'terminal' in data and not isinstance(data['terminal'], bool):
            raise ValueError('Launch terminal flag must be boolean')
        if data['kind'] == 'command' and any(Path(arg).name in ('uncle', 'uncle_tui.py') for arg in command):
            data['terminal'] = True
        if data['kind'] == 'webpage':
            if data.get('path'):
                target = (root / data['path']).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    raise ValueError('Webpage path must be an existing project file')
                data['url'] = target.as_uri()
            else:
                url = urlparse(data.get('url', ''))
                if url.scheme not in ('http', 'https') or url.hostname not in ('localhost', '127.0.0.1', '::1'):
                    raise ValueError('Preview URL must be a local HTTP address')
        return data
    if (root / 'index.html').is_file():
        return {'kind': 'webpage', 'url': (root / 'index.html').as_uri()}
    return {'kind': 'none'}


class CompletionPreview:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.process = None
        self.reader_thread = None
        self.cancelled = threading.Event()
        self.terminal_done = threading.Event()
        self.lock = threading.Lock()
        self.kind = 'none'
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            spec = launch_spec(self.root)
            self.kind = spec['kind']
            if self.kind == 'command' and spec.get('terminal'):
                self.events.put(('terminal', spec['command']))
                while not self.cancelled.is_set() and not self.terminal_done.wait(.1):
                    pass
                return
            if spec.get('command'):
                with self.lock:
                    if self.cancelled.is_set():
                        return
                    self.process = subprocess.Popen(launch_command(spec['command']), cwd=self.root,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        env=dict(os.environ, PYTHONUNBUFFERED='1'), **group_options())
                self.reader_thread = threading.Thread(target=self.read, daemon=True)
                self.reader_thread.start()
            if self.kind == 'webpage':
                url = spec['url']
                if self.process:
                    # loopback_candidates: launch_spec already accepts
                    # localhost/127.0.0.1/::1 as interchangeable, but a real
                    # run showed why the readiness check must be too. `npm
                    # run preview`'s default host is `localhost`, which on a
                    # machine where that resolves to ::1 only leaves a
                    # literal `127.0.0.1` in launch.json refused forever --
                    # the server was ready the whole time, just reachable
                    # under a different one of the three equivalent names.
                    deadline = time.monotonic() + 30
                    parsed = urlparse(url)
                    port_suffix = ':%d' % parsed.port if parsed.port else ''
                    path_suffix = (parsed.path or '') + (('?' + parsed.query) if parsed.query else '')
                    candidates = [url] + [
                        '%s://%s%s%s' % (parsed.scheme, ('[%s]' % host if ':' in host else host),
                                         port_suffix, path_suffix)
                        for host in ('127.0.0.1', 'localhost', '::1') if host != parsed.hostname]
                    while not self.cancelled.is_set():
                        if self.process.poll() is not None:
                            raise ValueError('Preview server exited before it was ready')
                        ready = False
                        for candidate in candidates:
                            try:
                                with urlopen(candidate, timeout=1):
                                    url, ready = candidate, True
                                    break
                            except OSError:
                                continue
                        if ready:
                            break
                        if time.monotonic() > deadline:
                            raise ValueError('Preview server did not become ready within 30 seconds')
                        self.cancelled.wait(.1)
                if not self.cancelled.is_set() and not webbrowser.open(url):
                    raise ValueError('Could not open browser: ' + url)
            elif self.process:
                self.events.put(('output', 'Running application. Use chat to send input; Esc stops the application.\n'))
                while self.process.poll() is None and not self.cancelled.wait(.1):
                    pass
                if not self.cancelled.is_set():
                    self.reader_thread.join(timeout=1)
                    self.events.put(('output', 'Application exited with code %s.\n' % self.process.returncode))
        except (OSError, ValueError) as error:
            self.events.put(('output', 'Application preview: %s\n' % error))
            self.close()
        finally:
            if not self.cancelled.is_set():
                self.events.put(('done', has_starred()))
            else:
                self.events.put(('done', False))

    def read(self):
        try:
            while True:
                chunk = os.read(self.process.stdout.fileno(), 4096)
                if not chunk:
                    break
                self.events.put(('output', chunk.decode('utf-8', 'replace')))
        except (OSError, ValueError):
            pass

    def send(self, message):
        if not self.process or self.process.poll() is not None:
            raise ValueError('Application is no longer running')
        try:
            self.process.stdin.write((message + '\n').encode())
            self.process.stdin.flush()
        except (OSError, ValueError) as error:
            raise ValueError('Could not send application input') from error

    def close(self):
        self.cancelled.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                kill_tree(self.process)
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
            if self.process and self.process.stdin:
                self.process.stdin.close()
        if self.reader_thread and self.reader_thread is not threading.current_thread():
            self.reader_thread.join(timeout=1)
        if self.process and self.process.stdout and (not self.reader_thread or not self.reader_thread.is_alive()):
            self.process.stdout.close()

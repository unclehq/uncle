"""Desktop app (Electron/Tauri) detection, launch gating and process tracking.

Pure-ish helpers plus a DesktopLaunch class. Writes only these untracked files
under <root>/.uncle/workflow/: desktop-app.pid, desktop-app.log and
desktop-launch.json. It never writes test-report rows or tracked files and
never uses shell=True.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

DISABLED_VALUES = ('0', 'false', 'no', 'off')
DEFAULT_GRACE = 3.0
PID_FILE = 'desktop-app.pid'
LOG_FILE = 'desktop-app.log'
RECORD_FILE = 'desktop-launch.json'
ELECTRON_DEPS = ('electron', 'electron-builder', '@electron-forge/cli')

_ANSI = re.compile(
    r'\x1b\[[0-?]*[ -/]*[@-~]'          # CSI
    r'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'  # OSC
    r'|\x1b[@-Z\\-_]'                    # other 2-char escapes
)
_CONTROL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')


def workflow_dir(root):
    return Path(root) / '.uncle' / 'workflow'


def opted_out(env=None):
    env = os.environ if env is None else env
    return str(env.get('WORKFLOW_PREVIEW_DESKTOP', '')).strip().lower() in DISABLED_VALUES


def grace_seconds(env=None):
    env = os.environ if env is None else env
    raw = env.get('WORKFLOW_PREVIEW_DESKTOP_GRACE')
    if raw is None or str(raw).strip() == '':
        return DEFAULT_GRACE
    try:
        value = float(str(raw).strip())
    except ValueError:
        return DEFAULT_GRACE
    if value != value or value < 0 or value == float('inf'):
        return DEFAULT_GRACE
    return value


def sanitize(text):
    text = _ANSI.sub('', text or '')
    return _CONTROL.sub('', text.replace('\r', ''))


def read_config_command(root):
    """Return (argv|None, warning|None) for desktop.launch_command."""
    path = Path(root) / '.uncle' / 'config'
    try:
        lines = path.read_text(errors='replace').splitlines()
    except OSError:
        return None, None
    value = None
    for line in lines:
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        m = re.match(r'^desktop\.launch_command\s*[=:]?\s*(.*)$', s)
        if m:
            value = m.group(1)
    if value is None:
        return None, None
    try:
        argv = shlex.split(value)
    except ValueError:
        argv = []
    if not argv:
        return None, 'ignoring empty or invalid desktop.launch_command'
    return argv, None


def _load_package(root):
    try:
        data = json.loads((Path(root) / 'package.json').read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _is_electron(pkg):
    if not pkg:
        return False
    for key in ('dependencies', 'devDependencies'):
        deps = pkg.get(key)
        if isinstance(deps, dict) and any(d in deps for d in ELECTRON_DEPS):
            return True
    return False


def _is_tauri(root, pkg):
    if (Path(root) / 'src-tauri' / 'tauri.conf.json').is_file():
        return True
    if pkg:
        for key in ('dependencies', 'devDependencies'):
            deps = pkg.get(key)
            if isinstance(deps, dict) and '@tauri-apps/cli' in deps:
                return True
    return False


def _result(framework, command=None, candidates=None, reason=None, warning=None):
    return {'framework': framework, 'command': command,
            'candidates': candidates or [], 'reason': reason, 'warning': warning}


def detect(root):
    """Detect a desktop framework and its launch argv.

    Returns {framework, command, candidates, reason, warning}. framework is
    'electron', 'tauri', 'ambiguous' (both frameworks) or 'none'. command is
    None unless a single command was resolved.
    """
    pkg = _load_package(root)
    electron = _is_electron(pkg)
    tauri = _is_tauri(root, pkg)
    if not electron and not tauri:
        return _result('none')
    if electron and tauri:
        return _result('ambiguous', candidates=[['npm', 'start'], ['npm', 'run', 'tauri', 'dev']],
                       reason='both Electron and Tauri detected')
    framework = 'electron' if electron else 'tauri'
    override, warning = read_config_command(root)
    if override:
        return _result(framework, command=override, candidates=[override], warning=warning)
    scripts = pkg.get('scripts') if pkg else None
    scripts = scripts if isinstance(scripts, dict) else {}
    if framework == 'electron':
        has_start, has_dev = 'start' in scripts, 'dev' in scripts
        if has_start and has_dev:
            return _result(framework, candidates=[['npm', 'start'], ['npm', 'run', 'dev']],
                           reason='both start and dev scripts exist', warning=warning)
        if has_start:
            return _result(framework, command=['npm', 'start'], candidates=[['npm', 'start']], warning=warning)
        if has_dev:
            return _result(framework, command=['npm', 'run', 'dev'], candidates=[['npm', 'run', 'dev']],
                           warning=warning)
        binary = Path(root) / 'node_modules' / '.bin' / 'electron'
        if pkg and pkg.get('main') and binary.exists():
            cmd = [str(Path('node_modules') / '.bin' / 'electron'), '.']
            return _result(framework, command=cmd, candidates=[cmd], warning=warning)
        return _result(framework, candidates=[['npm', 'start']],
                       reason='no start or dev script', warning=warning)
    # tauri
    if 'tauri' in scripts:
        cmd = ['npm', 'run', 'tauri', 'dev']
        return _result(framework, command=cmd, candidates=[cmd], warning=warning)
    return _result(framework, candidates=[['cargo', 'tauri', 'dev']],
                   reason='no tauri script', warning=warning)


def headless_reason(env=None, platform=None):
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if str(env.get('CI', '')).strip():
        return 'CI environment'
    if env.get('SSH_CONNECTION') or env.get('SSH_TTY'):
        return 'SSH session'
    if platform.startswith('linux') and not (env.get('DISPLAY') or env.get('WAYLAND_DISPLAY')):
        return 'no display (DISPLAY/WAYLAND_DISPLAY unset)'
    return None


def launch_decision(attended, unattended, headless, opted_out=False):
    """Return (action, reason). action in 'noop', 'skip', 'prompt'.

    Precedence: opted_out > unattended > headless > attended-confirm.
    """
    if opted_out:
        return 'noop', 'opted-out'
    if unattended:
        return 'skip', 'unattended'
    if headless:
        return 'skip', 'headless'
    if attended:
        return 'prompt', 'attended'
    return 'skip', 'not-attended'


def _write_private(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, text.encode('utf-8', 'replace'))
    finally:
        os.close(fd)


def record(root, status, reason=None, **extra):
    data = {'status': status, 'reason': reason}
    data.update(extra)
    _write_private(workflow_dir(root) / RECORD_FILE, json.dumps(data, indent=2) + '\n')
    return data


def _pid_command(pid):
    try:
        out = subprocess.run(['ps', '-o', 'command=', '-p', str(int(pid))],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    text = out.stdout.strip()
    return text or None


def _command_matches(recorded, actual):
    if not recorded or not actual:
        return False
    rec = ' '.join(recorded) if isinstance(recorded, list) else str(recorded)
    first = rec.split()[0] if rec.split() else ''
    return rec in actual or (bool(first) and os.path.basename(first) in actual)


def live_pid_info(root):
    """Return the pid-file dict when it names a live, matching process, else None."""
    path = workflow_dir(root) / PID_FILE
    try:
        data = json.loads(path.read_text())
        pid = int(data['pid'])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(data, dict) or pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    except OSError:
        return None
    if not _command_matches(data.get('command'), _pid_command(pid)):
        return None
    return data


def _log_tail(path, lines=20):
    try:
        text = Path(path).read_text(errors='replace')
    except OSError:
        return ''
    return sanitize('\n'.join(text.splitlines()[-lines:]))


class DesktopLaunch:
    """Launch a desktop app, watch it through a grace period, and clean up."""

    def __init__(self, root, argv, framework=None, grace=None, on_event=None):
        self.root = Path(root)
        self.argv = list(argv)
        self.framework = framework
        self.grace = grace_seconds() if grace is None else grace
        self.on_event = on_event or (lambda message: None)
        self.process = None
        self.status = 'pending'
        self.message = ''
        self.exit_code = None
        self.log_tail = ''
        self._thread = None
        self._graced = threading.Event()
        self._lock = threading.Lock()

    @property
    def pid_path(self):
        return workflow_dir(self.root) / PID_FILE

    @property
    def log_path(self):
        return workflow_dir(self.root) / LOG_FILE

    def _emit(self, message):
        try:
            self.on_event(message)
        except Exception:
            pass

    def _remove_pid(self):
        try:
            self.pid_path.unlink()
        except OSError:
            pass

    def _fail(self, message):
        self.status = 'failed'
        self.message = message
        record(self.root, 'failed', message, command=self.argv, framework=self.framework,
               exit_code=self.exit_code, log_tail=self.log_tail)
        self._remove_pid()
        self._emit(message)

    def start(self, wait=True):
        """Spawn the process and run the grace check; returns self (see .status).

        wait=False returns right after spawn with the grace check in a thread.
        """
        if not self._spawn():
            return self
        if wait:
            self._graced.wait()
        return self

    def _spawn(self):
        wf = workflow_dir(self.root)
        wf.mkdir(parents=True, exist_ok=True)
        try:
            log_fd = os.open(str(self.log_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(log_fd, 0o600)
        except OSError as exc:
            self._fail('desktop launch failed: %s' % exc)
            return False
        try:
            from process_tree import group_options
            options = group_options()
        except Exception:
            options = {'start_new_session': True} if os.name != 'nt' else {}
        try:
            self.process = subprocess.Popen(
                self.argv, cwd=str(self.root), stdin=subprocess.DEVNULL,
                stdout=log_fd, stderr=subprocess.STDOUT, **options)
        except (OSError, ValueError) as exc:
            os.close(log_fd)
            self._fail('desktop launch failed: %s' % exc)
            return False
        os.close(log_fd)
        try:
            _write_private(self.pid_path, json.dumps({
                'pid': self.process.pid, 'command': ' '.join(self.argv),
                'log': str(self.log_path), 'started': time.time()}) + '\n')
        except OSError:
            pass
        self.status = 'starting'
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()
        return True

    def _watch(self):
        deadline = time.monotonic() + self.grace
        code = self.process.poll()
        while code is None and time.monotonic() < deadline:
            time.sleep(0.05)
            code = self.process.poll()
        with self._lock:
            if self.status == 'closed':
                self._graced.set()
                return
            if code is not None:
                self.exit_code = code
                self.log_tail = _log_tail(self.log_path)
                self._fail('desktop app exited with code %s within %.1fs; log tail:\n%s'
                           % (code, self.grace, self.log_tail))
                self._graced.set()
                return
            self.status = 'launched'
            self.message = 'desktop app running (pid %d), log %s' % (self.process.pid, self.log_path)
            record(self.root, 'launched', None, command=self.argv, framework=self.framework,
                   pid=self.process.pid, log=str(self.log_path))
        self._graced.set()
        self._emit(self.message)
        # Post-grace crash reporting (only meaningful while the TUI is open).
        while self.process.poll() is None:
            time.sleep(0.25)
            if self.status == 'closed':
                return
        with self._lock:
            if self.status != 'launched':
                return
            self.exit_code = self.process.returncode
            self.status = 'exited'
            self._remove_pid()
            self.log_tail = _log_tail(self.log_path)
        self._emit('desktop app exited with code %s' % self.exit_code)

    def wait(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)

    def close(self):
        """Kill this session's own process tree (never a pid read from a file)."""
        with self._lock:
            process = self.process
            if process is None:
                return
            self.status = 'closed'
        if process.poll() is None:
            try:
                from process_tree import kill_tree
                kill_tree(process)
            except Exception:
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.wait(timeout=5)
            except Exception:
                pass
        self._remove_pid()

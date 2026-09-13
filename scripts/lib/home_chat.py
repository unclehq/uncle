"""Background homepage requests using the existing reviewer CLI contract."""
import queue
import subprocess
import tempfile
import threading
from pathlib import Path
from process_tree import start_check, launch_command, kill_tree, finish_check

class HomeRequest:
    def __init__(self, command, prompt, env, issue_lookup=None, cwd=None):
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.issue_context = ''
        self.cwd = str(Path(cwd or Path.cwd()).resolve())
        self.thread = threading.Thread(target=self._run, args=(command, prompt, env, issue_lookup), daemon=True)
        self.thread.start()

    def cancel(self):
        self.cancelled.set()

    def _run(self, command, prompt, env, issue_lookup=None):
        process = None
        try:
            if issue_lookup is not None:
                self.issue_context = issue_lookup()
                prompt += self.issue_context
            if self.cancelled.is_set():
                raise ValueError('Chat request cancelled')
            if len(prompt.encode('utf-8')) > 180000:
                raise ValueError('Chat and issue context is too large. Use fewer references or /clear.')
            with tempfile.TemporaryDirectory(prefix='uncle-chat-') as directory:
                reply = Path(directory) / 'reply.txt'
                try:
                    process = start_check(launch_command(command + ['--output-last-message', str(reply), prompt]),
                                          cwd=self.cwd, env=env, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
                    for _ in range(1500):
                        if self.cancelled.is_set():
                            raise ValueError('Chat request cancelled')
                        try:
                            code = process.wait(timeout=0.2)
                            break
                        except subprocess.TimeoutExpired:
                            continue
                    else:
                        raise ValueError('Chat timed out after five minutes. Check Configure and retry.')
                    if code:
                        raise ValueError(f'Chat runner exited with status {code}. Check its login and Configure, then retry.')
                    if not reply.exists():
                        raise ValueError('Chat runner returned no reply. Check Configure and retry.')
                    with reply.open('rb') as source:
                        data = source.read(1024 * 1024 + 1)
                    if len(data) > 1024 * 1024:
                        raise ValueError('Chat reply exceeds 1 MiB')
                    answer = data.decode('utf-8', errors='replace').strip()
                    if not answer:
                        raise ValueError('Chat runner returned an empty reply. Please retry.')
                    self.events.put(('reply', answer))
                finally:
                    if process is not None:
                        kill_tree(process)
                        process.wait()
                        finish_check(process)
        except (OSError, ValueError) as exc:
            self.events.put(('error', str(exc)))


class IssueSeedRequest(HomeRequest):
    """Import an issue in the background without starting or approving a build."""
    def _run(self, command, root, env, issue_lookup=None):
        process = None
        try:
            with tempfile.TemporaryFile() as log:
                process = start_check(launch_command(command), cwd=root, env=env,
                                      stdout=log, stderr=log)
                try:
                    for _ in range(1500):
                        if self.cancelled.is_set():
                            raise ValueError('Issue import cancelled')
                        try:
                            code = process.wait(timeout=0.2)
                            break
                        except subprocess.TimeoutExpired:
                            continue
                    else:
                        raise ValueError('Issue import timed out. Check GitHub access and retry.')
                    if code:
                        log.seek(0, 2)
                        log.seek(max(0, log.tell() - 4000))
                        raise ValueError('Issue import failed: ' + log.read().decode('utf-8', errors='replace'))
                    self.events.put(('issue_seeded', 'Created CHANGE_REQUEST.md from the GitHub issue.'))
                finally:
                    kill_tree(process)
                    process.wait()
                    finish_check(process)
        except (OSError, ValueError) as exc:
            self.events.put(('error', str(exc)))

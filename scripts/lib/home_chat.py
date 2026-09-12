"""Background homepage requests using the existing reviewer CLI contract."""
import queue
import subprocess
import tempfile
import threading
from pathlib import Path
from process_tree import start_check, launch_command, kill_tree, finish_check

class HomeRequest:
    def __init__(self, command, prompt, env):
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.thread = threading.Thread(target=self._run, args=(command, prompt, env), daemon=True)
        self.thread.start()

    def cancel(self):
        self.cancelled.set()

    def _run(self, command, prompt, env):
        process = None
        try:
            with tempfile.TemporaryDirectory(prefix='uncle-chat-') as directory:
                reply = Path(directory) / 'reply.txt'
                try:
                    process = start_check(launch_command(command + ['--output-last-message', str(reply), prompt]),
                                          cwd=directory, env=env, stdout=subprocess.DEVNULL,
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

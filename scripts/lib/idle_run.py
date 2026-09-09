"""Stream a child's output and bound silence, including native Windows children."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from process_tree import start_check, finish_check, kill_tree, launch_command


def run(seconds, command, usage_before=None):
    if seconds <= 0:
        raise ValueError('Idle timeout must be positive')

    def interrupt(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, interrupt)
    child = None
    with tempfile.TemporaryDirectory(prefix='uncle-stream-') as directory:
        path = Path(directory) / 'output'
        try:
            with path.open('wb') as output, path.open('rb') as reader:
                child = start_check(launch_command(command), stdout=output, stderr=subprocess.STDOUT)
                heartbeat = last_usage = time.monotonic()
                while True:
                    data = reader.read(65536)
                    if data:
                        heartbeat = time.monotonic()
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
                        continue
                    status = child.poll()
                    if status is not None:
                        # Drain bytes written between the read and poll.
                        sys.stdout.buffer.write(reader.read())
                        sys.stdout.buffer.flush()
                        return status if status >= 0 else 128 - status
                    now = time.monotonic()
                    if now - heartbeat >= seconds:
                        print(f'agent-kimi.sh: no output for {seconds}s; stopping kimi.', file=sys.stderr)
                        return 143
                    if usage_before and os.environ.get('UNCLE_STATUS_FILE') and now - last_usage >= 10:
                        last_usage = now
                        try:
                            result = subprocess.run([sys.executable, str(Path(__file__).with_name('kimi-usage.py')),
                                                     'collect', usage_before], capture_output=True, timeout=5)
                            usage = json.loads(result.stdout)
                            if usage.get('usage'):
                                usage.update(event='usage', stage=os.environ.get('UNCLE_STATUS_STAGE', ''),
                                             total_tokens=sum(usage['usage'].values()))
                                with open(os.environ['UNCLE_STATUS_FILE'], 'a', encoding='utf-8', newline='\n') as stream:
                                    stream.write(json.dumps(usage) + '\n')
                        except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
                            pass
                    time.sleep(.05)
        finally:
            if child is not None:
                try:
                    kill_tree(child)
                    child.wait()
                finally:
                    finish_check(child)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, required=True)
    parser.add_argument('--usage-before')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('command is required')
    try:
        sys.exit(run(args.seconds, command, args.usage_before))
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + '\n')

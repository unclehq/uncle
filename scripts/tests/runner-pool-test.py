#!/usr/bin/env python3
"""A workflow reuses one live native runner and reaps it with the driver."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / 'scripts/lib/runner_pool.py'


PROVIDER = r'''#!/usr/bin/env python3
import json, os, sys
for line in sys.stdin:
    value=json.loads(line)
    if value.get('method') == 'initialize':
        print(json.dumps({'jsonrpc':'2.0','id':value['id'],'result':{'provider':os.getpid()}}),flush=True)
    elif value.get('method') == 'ping':
        print(json.dumps({'jsonrpc':'2.0','id':value['id'],'result':{'pid':os.getpid()}}),flush=True)
'''

CLAUDE_PROVIDER = r'''#!/usr/bin/env python3
import json, os, sys, time
for line in sys.stdin:
    value=json.loads(line)
    if value.get('type') == 'user':
        time.sleep(.35)
        print(json.dumps({'type':'result','result':json.dumps({'pid':os.getpid()})}),flush=True)
'''


class Pool(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='runner-pool-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.provider = self.root / 'provider.py'
        self.provider.write_text(PROVIDER)
        self.owner = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        self.addCleanup(lambda: self.owner.poll() is None and self.owner.kill())

    def client(self):
        return subprocess.Popen(
            [sys.executable, '-B', str(POOL), 'connect', '--root', str(self.root/'pool'),
             '--owner', str(self.owner.pid), '--runner', 'codex', '--side', 'agent',
             '--', sys.executable, '-B', str(self.provider)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=self.root)

    def claude_client(self):
        provider = self.root / 'claude-provider.py'
        provider.write_text(CLAUDE_PROVIDER)
        return subprocess.Popen(
            [sys.executable, '-B', str(POOL), 'connect', '--root', str(self.root/'claude-pool'),
             '--owner', str(self.owner.pid), '--runner', 'claude', '--side', 'reviewer',
             '--', sys.executable, '-B', str(provider)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=self.root)

    def request(self, client, ident, method):
        client.stdin.write(json.dumps({'jsonrpc':'2.0','id':ident,'method':method})+'\n')
        client.stdin.flush()
        ready, _, _ = select.select([client.stdout], [], [], 10)
        self.assertTrue(ready, client.stderr.read() if client.poll() is not None else 'runner response timed out')
        value = json.loads(client.stdout.readline())
        if value.get('type') == 'runner_pool':
            ready, _, _ = select.select([client.stdout], [], [], 10)
            self.assertTrue(ready, 'runner response timed out after pool event')
            value = json.loads(client.stdout.readline())
        return value

    def stop_client(self, client):
        client.terminate(); client.wait(timeout=5)
        for stream in (client.stdin, client.stdout, client.stderr):
            stream.close()

    def test_reuses_process_and_owner_exit_reaps_it(self):
        first = self.client()
        initialized = self.request(first, 'init-1', 'initialize')['result']
        pid = self.request(first, 'ping-1', 'ping')['result']['pid']
        self.assertEqual(initialized['provider'], pid)
        self.stop_client(first)

        second = self.client()
        # Repeated protocol initialization is answered by the pool, while the
        # following request proves the original provider is still alive.
        self.assertEqual(self.request(second, 'init-2', 'initialize')['result']['provider'], pid)
        self.assertEqual(self.request(second, 'ping-2', 'ping')['result']['pid'], pid)
        self.stop_client(second)

        self.owner.terminate(); self.owner.wait(timeout=5)
        deadline = time.monotonic()+8
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(.1)
        else:
            self.fail('pooled runner survived its workflow owner')

    def test_claude_input_eof_does_not_reuse_a_streaming_slot(self):
        first = self.claude_client()
        first.stdin.write(json.dumps({'type': 'user', 'prompt': 'first'}) + '\n')
        first.stdin.close()  # matches claude -p: prompt input ends before result
        first_pool = json.loads(first.stdout.readline())
        self.assertEqual(first_pool['type'], 'runner_pool')

        # Before the first result arrives, a second request must acquire a
        # different pool slot rather than splice into the first response.
        second = self.claude_client()
        second.stdin.write(json.dumps({'type': 'user', 'prompt': 'second'}) + '\n')
        second.stdin.close()
        second_pool = json.loads(second.stdout.readline())
        self.assertEqual(second_pool['type'], 'runner_pool')
        self.assertNotEqual(first_pool['pool_pid'], second_pool['pool_pid'])

        first_result = json.loads(first.stdout.readline())
        second_result = json.loads(second.stdout.readline())
        self.assertEqual(first_result['type'], 'result')
        self.assertEqual(second_result['type'], 'result')
        self.stop_client(first); self.stop_client(second)


if __name__ == '__main__':
    unittest.main()

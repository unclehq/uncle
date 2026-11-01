#!/usr/bin/env python3
"""Hermetic provider pools exercised through the production Bash entry gate."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import unit_scheduler as scheduler

STUB = r'''
import fcntl, json, os, pathlib, subprocess, sys, time
root, name, mode = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
def event(action):
    with (root / 'events').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps([name, action]) + '\n')
event('start')
if mode == 'slow' and name == '0':
    deadline = time.monotonic() + 15
    while not (root / 'refilled').exists() and time.monotonic() < deadline:
        time.sleep(.02)
    assert (root / 'refilled').exists(), 'batch barrier prevented refill'
elif mode == 'slow' and int(name) >= 2:
    (root / 'refilled').touch()
if mode == 'cancel':
    child = subprocess.Popen([sys.executable, '-c',
        'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])
    (root / ('child-' + name)).write_text(str(child.pid))
    time.sleep(60)
time.sleep(.08)
event('end')
if mode == 'retry' and name == '1' and not (root / 'retried').exists():
    (root / 'retried').touch()
    sys.exit(7)
(root / (name + '.result')).write_text(name)
'''


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        (self.path / 'stub.py').write_text(STUB)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_', 'UNCLE_'))}
        self.env.update(ROOT=str(ROOT), STATE_DIR=str(self.path), UNCLE_CONFIG=str(self.path / 'config'),
                        WORKFLOW_SELF_HOSTED_MAX_CONCURRENCY='2')

    def launch(self, mode='slow', count=6, provider='self-hosted'):
        script = r'''
set -eu
. "$ROOT/scripts/lib/model-jobs.sh"
stage_uses_self_hosted() { [[ "$provider" == self-hosted ]]; }
uncle_stage_runner() { printf '%s' "$provider"; }
trap 'workflow_model_cancel' EXIT
trap 'exit 143' TERM
pids=()
for ((n=0; n<count; n++)); do
    (
        workflow_model_enter updated-plan || exit 1
        if [[ "$mode" == retry ]]; then
            python3 "$STATE_DIR/stub.py" "$STATE_DIR" "$n" "$mode" ||
                python3 "$STATE_DIR/stub.py" "$STATE_DIR" "$n" "$mode"
        else
            python3 "$STATE_DIR/stub.py" "$STATE_DIR" "$n" "$mode"
        fi
    ) &
    pids+=("$!")
    # Force a known first pair; later admission order is deliberately free.
    if [[ "$n" -lt 2 ]]; then
        for ((tick=0; tick<300; tick++)); do
            [[ -f "$STATE_DIR/events" ]] && grep -q "\[\"$n\", \"start\"\]" "$STATE_DIR/events" && break
            sleep .02
        done
    fi
done
for ((n=0; n<count; n++)); do
    wait "${pids[$n]}"
    cat "$STATE_DIR/$n.result"
done
'''
        env = dict(self.env, mode=mode, count=str(count), provider=provider)
        child = subprocess.Popen(['bash', '-c', script], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: child.poll() is None and child.kill())
        return child

    def finish(self, child):
        out, err = child.communicate(timeout=30)
        self.assertEqual(child.returncode, 0, err)
        return out

    def events(self):
        return [json.loads(line) for line in (self.path / 'events').read_text().splitlines()]

    def peak(self, rows):
        active = set()
        peak = 0
        for name, action in rows:
            if action == 'start':
                self.assertNotIn(name, active)
                active.add(name)
                peak = max(peak, len(active))
            else:
                active.remove(name)
        self.assertFalse(active)
        return peak

    def test_continuous_refill_capacity_and_order(self):
        self.assertEqual(self.finish(self.launch()), '012345')
        rows = self.events()
        self.assertEqual(self.peak(rows), 2)
        self.assertLess(min(rows.index([str(n), 'start']) for n in range(2, 6)), rows.index(['0', 'end']))
        self.assertFalse(list(self.path.glob('model-units/*/*/*.json')))

    def test_retry_is_private(self):
        self.assertEqual(self.finish(self.launch('retry')), '012345')
        rows = self.events()
        for n in range(6):
            self.assertEqual(rows.count([str(n), 'start']), 2 if n == 1 else 1)
        self.assertLessEqual(self.peak(rows), 2)

    def test_hosted_opt_in_capacity(self):
        self.env['WORKFLOW_CODEX_MAX_CONCURRENCY'] = '2'
        self.assertEqual(self.finish(self.launch(provider='codex')), '012345')
        self.assertEqual(self.peak(self.events()), 2)

    def test_cancel_active_queued_and_descendants(self):
        child = self.launch('cancel', 5)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if len(list(self.path.glob('model-units/*/*/*.json'))) == 5:
                break
            time.sleep(.03)
        self.assertEqual(len(list(self.path.glob('model-units/*/*/*.json'))), 5)
        descendants = [int(path.read_text()) for path in self.path.glob('child-*')]
        self.assertEqual(len(descendants), 2)
        child.terminate()
        child.communicate(timeout=10)
        self.assertEqual(child.returncode, 143)
        self.assertEqual(len(self.events()), 2, 'queued work started during cancellation')
        table = scheduler.processes()
        self.assertFalse([pid for pid in descendants if pid in table and not table[pid][1].startswith('Z')])

    def test_config_and_env_precedence(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(scheduler.capacity('self-hosted', 'updated-plan', {}), 24)
            self.assertEqual(scheduler.capacity('claude', 'updated-plan', {}), 0)
            self.assertEqual(scheduler.capacity('codex', 'updated-plan', {}), 0)
            config = {'self-hosted.max-concurrency': '20', 'updated-plan.max-concurrency': '12'}
            self.assertEqual(scheduler.capacity('self-hosted', 'updated-plan-worker-edits-1', config), 12)
            os.environ['WORKFLOW_SELF_HOSTED_MAX_CONCURRENCY'] = '18'
            self.assertEqual(scheduler.capacity('self-hosted', 'updated-plan-worker-edits-1', config), 18)
            os.environ['WORKFLOW_SELF_HOSTED_MAX_CONCURRENCY_UPDATED_PLAN'] = '16'
            self.assertEqual(scheduler.capacity('self-hosted', 'updated-plan-worker-edits-1', config), 16)
            os.environ['WORKFLOW_SELF_HOSTED_MAX_CONCURRENCY_UPDATED_PLAN_WORKER_EDITS_1'] = '14'
            self.assertEqual(scheduler.capacity('self-hosted', 'updated-plan-worker-edits-1', config), 14)

    def test_legacy_and_invalid_settings(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(scheduler.capacity('self-hosted', 'updated-plan', {'self-hosted.stage-jobs': '3'}), 3)
            for invalid in ('0', '-1', 'bogus', '257'):
                with self.assertRaises(ValueError):
                    scheduler.capacity('self-hosted', 'updated-plan', {'self-hosted.max-concurrency': invalid})
            with self.assertRaises(ValueError):
                scheduler.granularity('codex', config={'codex.granularity': 'invalid'})

    def test_granularity_accessor_and_legacy_size(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(scheduler.granularity('self-hosted', config={}), 'small')
            self.assertEqual(scheduler.granularity('claude', config={}), 'large')
            self.assertEqual(scheduler.group_size('self-hosted', config={}), 1)
            self.assertEqual(scheduler.group_size('codex', config={}), 2)
            config = {'self-hosted.stage-jobs': '2'}
            self.assertEqual(scheduler.group_size('self-hosted', config=config), 2)
            config['self-hosted.granularity'] = 'small'
            self.assertEqual(scheduler.group_size('self-hosted', config=config), 1)

    def test_stale_lease_is_reclaimed(self):
        pool = self.path / 'leases'
        pool.mkdir()
        (pool / 'stale.json').write_text(json.dumps(dict(pid=os.getpid(), stamp='wrong birth', active=True)))
        scheduler.acquire(pool, 1, os.getpid(), os.getpid())
        self.assertFalse((pool / 'stale.json').exists())
        self.assertTrue(json.loads((pool / ('%d.json' % os.getpid())).read_text())['active'])


if __name__ == '__main__':
    unittest.main()

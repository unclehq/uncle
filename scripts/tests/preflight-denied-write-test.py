#!/usr/bin/env python3
"""A write the read-only preflight sandbox refuses is reported to the worker, not treated as a violation that ends the run.

The run that found this: a preflight probe started headless Chrome, whose crash reporter writes under ~/Library; the sandbox refused
the write ('Operation not permitted'), and the harness read that as the worker breaking the read-only rule and stopped the build."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import http_agent as agent  # noqa: E402

SANDBOX = (sys.platform == 'darwin' and shutil.which('sandbox-exec')) or (sys.platform.startswith('linux') and shutil.which('bwrap'))


class DeniedWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'project'
        self.root.mkdir()
        (self.root / 'keep.txt').write_text('original')
        self.outside = Path(self.tmp.name).resolve() / 'outside.txt'
        env = mock.patch.dict(os.environ, {'UNCLE_PROJECT_ROOT': str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.policy = agent.Policy(self.root, shell=True)
        self.policy.preflight_worker = 'preflight-worker-tooling'
        self.addCleanup(self.policy.cleanup if hasattr(self.policy, 'cleanup') else (lambda: None))
        self.addCleanup(self.finish)

    def finish(self):
        for method in ('stop_children', 'close', 'finish'):
            if hasattr(self.policy, method):
                getattr(self.policy, method)()
                return

    def bash(self, command):
        return agent.run_tool(self.policy, 'bash', {'command': command})

    @unittest.skipUnless(SANDBOX, 'needs sandbox-exec or bubblewrap')
    def test_a_refused_write_is_reported_and_the_run_carries_on(self):
        out = self.bash('echo x > "%s"; echo after' % self.outside)
        self.assertIsNone(self.policy.preflight_violation, out)
        self.assertNotIn('error:', out.splitlines()[0])
        self.assertIn('after', out)                                    # the worker's command went on
        self.assertIn('read-only outside this probe', out)             # and it was told what happened
        self.assertFalse(self.outside.exists())                        # the sandbox did refuse the write

    @unittest.skipUnless(SANDBOX, 'needs sandbox-exec or bubblewrap')
    def test_the_project_itself_is_never_touched_by_a_probe(self):
        self.bash('echo changed > keep.txt; echo new > added.txt')
        self.assertEqual((self.root / 'keep.txt').read_text(), 'original')
        self.assertFalse((self.root / 'added.txt').exists())

    def test_a_write_tool_outside_the_delivery_path_is_still_a_violation(self):
        out = agent.run_tool(self.policy, 'write_file', {'path': 'src/x.txt', 'content': 'x'})
        self.assertTrue(out.startswith('error: '))
        self.assertIn('read-only preflight refused write_file', self.policy.preflight_violation)
        self.assertFalse((self.root / 'src' / 'x.txt').exists())

    def test_the_driver_still_stops_on_the_violation_message_only(self):
        import inspect
        stage = (ROOT / 'scripts' / 'stagegate.sh').read_text()
        self.assertIn("grep -q 'read-only preflight refused'", stage)
        # The probe's own note must never contain the phrase the driver greps for, or every refused write would stop the run.
        self.assertNotIn('read-only preflight refused', inspect.getsource(agent._preflight_bash))


if __name__ == '__main__':
    unittest.main()

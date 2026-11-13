#!/usr/bin/env python3
"""A read-only preflight probe may call `mktemp` the usual way on macOS (it used to be refused as a write)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import preflight_readonly as pr  # noqa: E402

DARWIN = sys.platform == 'darwin' and shutil.which('sandbox-exec')


class Probe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scratch = Path(self.tmp.name).resolve() / 'scratch'
        (self.scratch / 'project').mkdir(parents=True)
        (self.scratch / 'tmp').mkdir()

    def run_probe(self, command):
        env = dict(os.environ, TMPDIR=str(self.scratch / 'tmp'))
        done = subprocess.run(pr.probe_command(command, self.scratch), cwd=self.scratch / 'project', env=env,
                              capture_output=True, text=True, timeout=60)
        return done.returncode, (done.stdout + done.stderr).strip()

    def test_the_prelude_only_redirects_template_less_calls(self):
        text = pr.MKTEMP_PRELUDE
        self.assertIn('*XXX*', text)
        self.assertIn('command mktemp -p "${TMPDIR:-/tmp}"', text)
        self.assertIn('export -f mktemp', text)

    @unittest.skipUnless(DARWIN, 'the quirk and the sandbox are macOS')
    def test_the_usual_mktemp_forms_land_in_the_scratch_not_var_folders(self):
        for form in ('mktemp -d', 'mktemp', 'mktemp -d -t probe', 'mktemp -d "$TMPDIR/x.XXXXXX"'):
            status, out = self.run_probe(form)
            self.assertEqual(status, 0, '%s: %s' % (form, out))
            self.assertTrue(out.startswith(str(self.scratch / 'tmp')), '%s -> %s' % (form, out))

    @unittest.skipUnless(DARWIN, 'the quirk and the sandbox are macOS')
    def test_the_worker_idiom_that_failed_the_run_now_works(self):
        status, out = self.run_probe('S=$(mktemp -d); cp -R . "$S/p" 2>/dev/null; cd "$S/p" && pwd')
        self.assertEqual(status, 0, out)
        self.assertTrue(out.startswith(str(self.scratch / 'tmp')), out)

    @unittest.skipUnless(DARWIN, 'the quirk and the sandbox are macOS')
    def test_a_child_script_inherits_it_and_real_writes_are_still_refused(self):
        status, out = self.run_probe("bash -c 'mktemp -d'")
        self.assertEqual(status, 0, out)
        self.assertTrue(out.startswith(str(self.scratch / 'tmp')), out)
        outside = Path(self.tmp.name).resolve() / 'outside.txt'
        status, out = self.run_probe('echo x > "%s"' % outside)
        self.assertNotEqual(status, 0)
        self.assertIn('Operation not permitted', out)
        self.assertFalse(outside.exists())


if __name__ == '__main__':
    unittest.main()

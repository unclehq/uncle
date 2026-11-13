#!/usr/bin/env python3
"""The preview build has no off switch, and the removed preview variables are gone from the shell and Python libs."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class AlwaysOn(unittest.TestCase):
    def test_workflow_preview_build_does_not_gate_the_start(self):
        text = (ROOT / 'scripts/lib/preview-build.sh').read_text()
        self.assertIsNone(re.search(r'\bWORKFLOW_PREVIEW_BUILD\b', text))
        self.assertNotIn('"$PREVIEW_BUILD"', text)

    def test_the_off_switch_does_not_stop_it_starting(self):
        script = ('cd "$1"; . "%s/scripts/lib/preview-build.sh"; PREVIEW_STARTED=0; preview_existing_project() { return 1; }; '
                  'preview_build_defer() { echo reached-defer; return 0; }; preview_build_start') % ROOT
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = subprocess.run(['bash', '-c', script, 'x', d], env={'PATH': '/usr/bin:/bin', 'WORKFLOW_PREVIEW_BUILD': '0'},
                                 capture_output=True, text=True, timeout=30).stdout
        self.assertIn('reached-defer', out)

    def test_removed_variables_are_not_read(self):
        for path in ('scripts/lib/stage-config.sh', 'scripts/lib/host_preview.py', 'scripts/lib/preview_server.py',
                     'scripts/lib/headless_preview.py', 'scripts/lib/host_preview_hook.sh'):
            text = (ROOT / path).read_text()
            for name in ('UNCLE_PREVIEW_MODE', 'UNCLE_NOUI_PREVIEW=', "'UNCLE_NOUI_PREVIEW'", 'UNCLE_NOUI_PREVIEW_SECONDS'):
                self.assertNotIn(name, text, '%s still mentions %s' % (path, name))


if __name__ == '__main__':
    unittest.main()

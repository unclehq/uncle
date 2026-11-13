#!/usr/bin/env python3
"""A final-audit worker whose evidence is too large to embed is still told which files to read.

The run that found this: UPDATED_PROJECT_PLAN.json was over worker_prompt.py's embed limit, so the prompt fell back to
"read only the artifacts named in your assigned prompt" while naming none and barring exploration. Every lens answered "verification
could not be assessed" as a blocking High finding, and a finished build ended NOT_READY."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPT = 'You are a read-only specialist.\n\n## Assigned audit lens\n\nFocus only on **verification**.\n'


def gated(files):
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        (base / '.uncle/workflow/documents').mkdir(parents=True)
        (base / 'logs').mkdir()
        for name, body in files.items():
            (base / '.uncle/workflow/documents' / name).write_text(json.dumps(body))
        (base / 'p.md').write_text(PROMPT)
        script = ('ROOT="%s"; GATES_LIB_DIR="$ROOT/scripts/lib"; LOG_DIR="$PWD/logs"; . "$ROOT/scripts/lib/gates.sh"; '
                  'out="$(gated_prompt "$PWD/p.md" final-audit-review-worker-verification reviewer)" && cat "$out"') % ROOT
        done = subprocess.run(['bash', '-c', script], cwd=base, capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stderr
        return done.stdout


class FinalAuditWorkerInputs(unittest.TestCase):
    def test_oversize_evidence_falls_back_to_a_prompt_that_names_the_files(self):
        text = gated({'UPDATED_PROJECT_PLAN.json': {'plan': 'x' * 200000}, 'VERIFICATION_REPORT.json': {'rows': []}})
        self.assertIn('`.uncle/workflow/documents/UPDATED_PROJECT_PLAN.json`', text)
        self.assertIn('`.uncle/workflow/documents/VERIFICATION_REPORT.json`', text)
        self.assertNotIn('named in your assigned prompt', text)
        self.assertIn('Focus only on **verification**', text)

    def test_small_evidence_is_still_embedded(self):
        text = gated({'UPDATED_PROJECT_PLAN.json': {'plan': 'small'}, 'VERIFICATION_REPORT.json': {'rows': []}})
        self.assertIn('"plan":"small"', text)
        self.assertIn('Do not read them again', text)


if __name__ == '__main__':
    unittest.main()

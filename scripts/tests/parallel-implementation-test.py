"""The supervised parallel executor merges only declared files and cleans success."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
EXECUTOR = ROOT / 'scripts/lib/parallel_steps.py'


class ParallelImplementationTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
        subprocess.run(['git', 'config', 'commit.gpgsign', 'false'], cwd=root, check=True)
        (root / 'a.txt').write_text('base\n')
        (root / 'b.txt').write_text('base\n')
        subprocess.run(['git', 'add', '.'], cwd=root, check=True)
        subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
                        'commit', '--no-gpg-sign', '-qm', 'fixture'], cwd=root, check=True)
        worker = root / 'worker.sh'
        worker.write_text(
            '#!/usr/bin/env bash\nset -euo pipefail\n'
            'n="$1"\nprintf "step-%s\\n" "$n" > "${n}.txt"\n'
            'mkdir -p .uncle/workflow/parallel/notes\n'
            'printf "step %s handoff\\n" "$n" > ".uncle/workflow/parallel/notes/step-${n}.md"\n')
        worker.chmod(0o755)
        return temp, root, worker

    def test_merges_declared_files_captures_notes_and_removes_worktrees(self):
        temp, root, worker = self.fixture()
        with temp:
            request = {
                'project': str(root),
                'owned': {'1': ['1.txt'], '2': ['2.txt']},
                'steps': [
                    {'number': 1, 'log': str(root / 'one.log'),
                     'note': '.uncle/workflow/parallel/notes/step-1.md',
                     'command': ['bash', str(worker), '1']},
                    {'number': 2, 'log': str(root / 'two.log'),
                     'note': '.uncle/workflow/parallel/notes/step-2.md',
                     'command': ['bash', str(worker), '2']},
                ],
            }
            path = root / 'request.json'
            path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['merged'], [1, 2])
            self.assertEqual(summary['worktrees'], 'removed')
            self.assertEqual(set(summary['step_seconds']), {'1', '2'})
            self.assertEqual((root / '1.txt').read_text(), 'step-1\n')
            self.assertEqual((root / '2.txt').read_text(), 'step-2\n')
            self.assertTrue((root / '.uncle/workflow/parallel/notes/step-1.md').is_file())
            self.assertFalse((root / '.uncle/workflow/parallel/step-1').exists())
            self.assertFalse((root / '.uncle/workflow/parallel/step-2').exists())


if __name__ == '__main__':
    unittest.main()

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

    def test_unborn_or_plain_project_uses_copy_sandboxes_without_recursion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.txt').write_text('base\n')
            # A failed earlier fan-out may leave a preserved parallel.* tree.
            # It must never be copied into the next worker sandbox.
            stale = root / '.uncle/workflow/parallel.failed-old'
            stale.mkdir(parents=True)
            (stale / 'large-stale-artifact').write_text('do not copy\n')
            (root / '.pw-browsers').mkdir()
            (root / '.pw-browsers' / 'browser-cache').write_text('do not copy\n')
            (root / 'node_modules').mkdir()
            (root / 'node_modules' / 'dependency-cache').write_text('do not copy\n')
            worker = root / 'worker.sh'
            worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\n'
                              'test ! -e .pw-browsers\n'
                              'test ! -e node_modules\n'
                              'printf copied > a.txt\n'
                              'mkdir -p .uncle/workflow/parallel/notes\n'
                              'printf handoff > .uncle/workflow/parallel/notes/step-1.md\n')
            worker.chmod(0o755)
            request = {'project': str(root), 'owned': {'1': ['a.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'a.txt').read_text(), 'copied')

    def test_missing_agent_handoff_is_synthesized_without_blocking_merge(self):
        temp, root, worker = self.fixture()
        with temp:
            worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\nprintf changed > 1.txt\n')
            request = {'project': str(root), 'owned': {'1': ['1.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / '1.txt').read_text(), 'changed')
            handoff = (root / '.uncle/workflow/parallel/notes/step-1.md').read_text()
            self.assertIn('synthesized by the driver', handoff)

    def test_worker_completion_uses_the_normal_persisted_metrics_path(self):
        temp, root, worker = self.fixture()
        with temp:
            request = {'project': str(root), 'owned': {'1': ['1.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker), '1']} ]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            records = list((root / '.uncle/workflow/metrics').glob('parallel-worker-*.json'))
            self.assertEqual(len(records), 1)
            row = json.loads(records[0].read_text())
            self.assertEqual((row['stage'], row['process_exit']), ('implementation-step-1', 0))
            self.assertIn(row, json.loads((root / '.uncle/workflow/session-totals.json').read_text())['records'])


if __name__ == '__main__':
    unittest.main()

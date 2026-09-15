import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('execution_context', Path(__file__).resolve().parents[1] / 'lib/execute-checklist-context.py')
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


class Evidence(unittest.TestCase):
    def test_current_results_and_bounded_checklist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / '.uncle/workflow'
            checks = state / 'checklist-driver-checks'
            checks.mkdir(parents=True)
            (root / 'MANUAL_CHECKLIST.md').write_text('MC-1\n' + 'x' * 20000)
            (checks / 'results.tsv').write_text('command failed')
            first = context.render(root, state)
            self.assertIn('command failed', first)
            self.assertIn('Read remaining', first)
            self.assertLess(len(first), 18000)
            (checks / 'results.tsv').write_text('command succeeded')
            second = context.render(root, state)
            self.assertNotIn('command failed', second)
            self.assertIn('command succeeded', second)
            self.assertNotEqual(first, second)


if __name__ == '__main__':
    unittest.main()

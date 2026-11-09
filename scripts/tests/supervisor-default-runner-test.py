"""supervision.runner defaults to the global runner, not Claude Code (issue 200)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'lib'))
import supervisor


def load(text):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'config')
        Path(path).write_text(text)
        return supervisor.load_config(path)


class DefaultRunner(unittest.TestCase):
    def test_follows_global_runner_and_model(self):
        c = load('runner self-hosted\nmodel gpt-x\n')
        self.assertEqual((c.runner, c.model), ('self-hosted', 'gpt-x'))

    def test_explicit_supervision_runner_wins(self):
        self.assertEqual(load('runner self-hosted\nsupervision.runner codex\n').runner, 'codex')

    def test_no_global_runner_stays_claude(self):
        c = load('')
        self.assertEqual((c.runner, c.model), ('claude', 'sonnet'))

    def test_invalid_global_runner_falls_back(self):
        self.assertEqual(load('runner bad!value\n').runner, 'claude')


if __name__ == '__main__':
    unittest.main()

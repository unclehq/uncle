"""A launch.json a worker wrote in the common wrong shapes is repaired; the prompts say what the right shape is."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import completion_preview as cp


class Manifest(unittest.TestCase):
    def normalized(self, data, package=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.uncle').mkdir()
            (root / '.uncle/launch.json').write_text(json.dumps(data))
            if package:
                (root / 'package.json').write_text(json.dumps(package))
            changed = cp.normalize_launch_manifest(root)
            fixed = json.loads((root / '.uncle/launch.json').read_text())
            try:
                spec = cp.launch_spec(root)
            except ValueError:
                spec = None
            return changed, fixed, spec

    def test_the_calculator_shape_is_repaired(self):
        # The file a worker actually wrote: a command string, no kind.
        changed, fixed, spec = self.normalized({'command': 'npx vite --host 127.0.0.1 --port 5173 --strictPort',
                                                'url': 'http://127.0.0.1:5173'})
        self.assertTrue(changed)
        self.assertEqual(fixed['kind'], 'webpage')
        self.assertEqual(fixed['command'], ['npx', 'vite', '--host', '127.0.0.1', '--port', '5173', '--strictPort'])
        self.assertEqual(spec['kind'], 'webpage')

    def test_a_terminal_command_with_no_url_becomes_kind_command(self):
        changed, fixed, _ = self.normalized({'command': 'python3 app.py'})
        self.assertTrue(changed)
        self.assertEqual((fixed['kind'], fixed['command']), ('command', ['python3', 'app.py']))

    def test_the_legacy_npm_script_shape_still_works(self):
        changed, fixed, _ = self.normalized({'command': 'npm run dev', 'url': 'http://localhost:5173'},
                                            {'scripts': {'dev': 'vite'}})
        self.assertTrue(changed)
        self.assertEqual(fixed['command'], ['npm', 'run', 'dev'])

    def test_a_command_that_needs_a_shell_is_left_alone(self):
        for command in ('npm run build && node serve.js', 'cat x | sh', 'node a.js; rm -rf /', 'echo $HOME', 'a `b`'):
            changed, fixed, _ = self.normalized({'command': command, 'url': 'http://127.0.0.1:1'})
            self.assertFalse(changed, command)
            self.assertEqual(fixed['command'], command)

    def test_a_valid_manifest_is_untouched(self):
        valid = {'kind': 'webpage', 'command': ['npx', 'vite'], 'url': 'http://127.0.0.1:5173'}
        changed, fixed, _ = self.normalized(valid)
        self.assertFalse(changed)
        self.assertEqual(fixed, valid)

    def test_every_prompt_that_writes_the_file_states_the_schema(self):
        for name in ('implement.md', 'implement-investigate.md', 'project-plan.md', 'project-plan-investigate.md'):
            text = (ROOT / 'prompts' / name).read_text()
            self.assertIn('## Launch metadata', text, name)
            self.assertIn('"kind": "webpage"', text, name)
            self.assertIn('never one string', text, name)


if __name__ == '__main__':
    unittest.main()

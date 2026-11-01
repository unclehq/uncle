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


class Fallback(unittest.TestCase):
    def project(self, launch, package=None, vite=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / '.uncle/workflow').mkdir(parents=True)
        if launch is not None:
            (root / '.uncle/launch.json').write_text(launch if isinstance(launch, str) else json.dumps(launch))
        if package is not None:
            (root / 'package.json').write_text(json.dumps(package))
        if vite is not None:
            (root / 'vite.config.js').write_text(vite)
        return root

    def test_the_vs_code_shape_from_the_second_calculator_run_is_repaired_in_place(self):
        root = self.project({'version': '0.0.1', 'configurations': [{
            'name': 'vite-dev', 'runtimeExecutable': 'npx', 'runtimeArgs': ['vite', '--port', '5173', '--strictPort'],
            'port': 5173}]})
        cp.repair_launch_manifest(root)
        self.assertEqual(cp.launch_spec(root), {'kind': 'webpage', 'url': 'http://127.0.0.1:5173',
                                                'command': ['npx', 'vite', '--port', '5173', '--strictPort']})
        self.assertFalse((root / '.uncle/launch.json.invalid').exists())

    def test_an_unrepairable_file_is_replaced_by_one_derived_from_the_project(self):
        root = self.project({'run': 'whatever', 'configurations': 'nope'},
                            {'scripts': {'dev': 'vite --port 4321', 'build': 'vite build'}})
        message = cp.repair_launch_manifest(root)
        self.assertIn('Replaced an unusable .uncle/launch.json', message)
        self.assertEqual(cp.launch_spec(root), {'kind': 'webpage', 'command': ['npm', 'run', 'dev'], 'url': 'http://127.0.0.1:4321'})
        self.assertIn('configurations', (root / '.uncle/launch.json.invalid').read_text())
        self.assertIn('Replaced', (root / '.uncle/workflow/launch-repair.txt').read_text())

    def test_the_port_comes_from_the_vite_config_then_the_default(self):
        root = self.project('not json at all', {'scripts': {'dev': 'vite'}}, 'export default { server: { port: 3999 } }')
        cp.repair_launch_manifest(root)
        self.assertEqual(cp.launch_spec(root)['url'], 'http://127.0.0.1:3999')
        root = self.project('[]', {'scripts': {'dev': 'vite'}})
        cp.repair_launch_manifest(root)
        self.assertEqual(cp.launch_spec(root)['url'], 'http://127.0.0.1:5173')

    def test_a_project_with_nothing_to_launch_gets_kind_none(self):
        root = self.project({'junk': 1})
        cp.repair_launch_manifest(root)
        self.assertEqual(cp.launch_spec(root), {'kind': 'none'})
        root = self.project({'junk': 1}, {'scripts': {'test': 'vitest'}})
        cp.repair_launch_manifest(root)
        self.assertEqual(cp.launch_spec(root), {'kind': 'none'})

    def test_no_launch_file_is_not_created(self):
        root = self.project(None, {'scripts': {'dev': 'vite'}})
        self.assertEqual(cp.repair_launch_manifest(root), '')
        self.assertFalse((root / '.uncle/launch.json').exists())

    def test_a_valid_file_is_never_touched(self):
        valid = {'kind': 'command', 'command': ['python3', 'app.py']}
        root = self.project(valid, {'scripts': {'dev': 'vite'}})
        self.assertEqual(cp.repair_launch_manifest(root), '')
        self.assertEqual(json.loads((root / '.uncle/launch.json').read_text()), valid)

    def test_the_cli_exits_zero_for_a_file_it_had_to_replace(self):
        import subprocess
        root = self.project({'junk': 1}, {'scripts': {'dev': 'vite'}})
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/lib/completion_preview.py'), '--normalize', str(root)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('Replaced', done.stdout)


if __name__ == '__main__':
    unittest.main()

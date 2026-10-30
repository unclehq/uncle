#!/usr/bin/env python3
"""The workflow harness has explicit dependencies and fails on missing exports."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

import fixture_repo

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts/tests/workflow_fixture.sh'


class WorkflowFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='workflow fixture ')
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)

    def run_bash(self, script, env=None):
        return subprocess.run(['/bin/bash', '-eu', '-c',
                               f'ROOT={shlex.quote(str(ROOT))}\n. {shlex.quote(str(HELPER))}\n' + script],
                              cwd=self.tmp, env=env or fixture_repo.isolated_env(),
                              capture_output=True, text=True)

    def test_explicit_order_and_injected_hook_survive_generated_harness(self):
        (self.tmp / 'first module.sh').write_text('answer() { hook first; }\n')
        (self.tmp / 'second module.sh').write_text('answer() { hook second; }\n')
        result = self.run_bash('''workflow_fixture_write entry.sh "$PWD/first module.sh" "$PWD/second module.sh"
hook() { printf 'injected:%s\\n' "$1"; }
. ./entry.sh
answer
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'injected:second\n')
        entry = (self.tmp / 'entry.sh').read_text()
        self.assertIn('workflow_fixture_source', entry)
        self.assertNotIn('stagegate.sh', entry)

    def test_missing_module_and_empty_lists_fail(self):
        for script in ('workflow_fixture_source ./missing.sh',
                       'workflow_fixture_write entry.sh',
                       'extract_fns missing.sh extracted.sh'):
            with self.subTest(script=script):
                self.assertNotEqual(self.run_bash(script).returncode, 0)

    def test_extraction_preserves_bodies_and_rejects_missing_functions(self):
        source = 'first() {\n    printf "one"\n}\n\nsecond() {\n    printf "two"\n}\n'
        (self.tmp / 'driver.sh').write_text(source)
        result = self.run_bash('''extract_fns driver.sh extracted.sh first second
workflow_fixture_write entry.sh "$PWD/extracted.sh"
. ./entry.sh
first
second
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'onetwo')
        self.assertEqual((self.tmp / 'extracted.sh').read_text(), source + '\n')
        result = self.run_bash('extract_fns driver.sh extracted.sh first missing')
        self.assertEqual(result.returncode, 2)
        self.assertIn('could not extract missing', result.stderr)

    def test_source_has_no_environment_or_filesystem_side_effects(self):
        result = subprocess.run(['/bin/bash', '-eu', '-c', '''
PATH=/no-executables
before_pwd=$PWD
before_options=$-
before_traps=$(trap -p)
. "$1"
[[ "$PWD" == "$before_pwd" && "$-" == "$before_options" && "$(trap -p)" == "$before_traps" ]]
''', '_', str(HELPER)], cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_fixture_creation_never_invokes_inherited_signer(self):
        env, log = fixture_repo.fake_signer(self.tmp)
        repo = fixture_repo.init_repo(self.tmp / 'repo', env=env)
        fixture_repo.commit(repo, 'fixture', env=env)
        for key in ('commit.gpgsign', 'tag.gpgsign'):
            self.assertEqual(fixture_repo.git(repo, 'config', '--bool', key, env=env), 'false')
        (self.tmp / 'module.sh').write_text('answer() { printf ready; }\n')
        result = self.run_bash('''workflow_fixture_write entry.sh "$PWD/module.sh"
. ./entry.sh
answer
''', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'ready')
        self.assertFalse(log.exists(), 'ordinary fixture creation invoked the fake signer')

    def test_production_layers_source_without_runtime_state_or_executables(self):
        for name in ('prompt-io.sh', 'prompt-io-app.sh', 'prompt-io-change.sh',
                     'workflow-paths-app.sh', 'approval-gates-app.sh',
                     'workflow-paths-change.sh', 'approval-gates-change.sh',
                     'workflow-records.sh'):
            with self.subTest(module=name):
                result = subprocess.run(['/bin/bash', '-eu', '-c', '''
PATH=/no-executables
before_pwd=$PWD
before_options=$-
before_traps=$(trap -p)
. "$1"
[[ "$PWD" == "$before_pwd" && "$-" == "$before_options" && "$(trap -p)" == "$before_traps" ]]
''', '_', str(ROOT / 'scripts/lib' / name)], cwd=self.tmp,
                    env=fixture_repo.isolated_env(), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, '')
                self.assertEqual(list(self.tmp.iterdir()), [])

    def test_prompt_paths_preserve_project_and_install_identity(self):
        install = self.tmp / 'read only install'
        (install / 'prompts').mkdir(parents=True)
        (install / 'prompts/template.md').write_text('installed\n')
        (self.tmp / 'project local.md').write_text('project\n')
        install.chmod(0o555)
        try:
            for name in ('workflow-paths-app.sh', 'workflow-paths-change.sh'):
                with self.subTest(module=name):
                    result = self.run_bash(
                        '. ' + shlex.quote(str(ROOT / 'scripts/lib' / name)) + '\n' +
                        'ROOT=' + shlex.quote(str(install)) + '\n' + '''
for prompt in '/missing absolute/prompt.md' 'project local.md' 'prompts/template.md' 'missing.md'; do
    resolve_prompt "$prompt"
    printf '\\n'
done
''')
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, '\n'.join([
                        '/missing absolute/prompt.md', 'project local.md',
                        str(install / 'prompts/template.md'), str(install / 'missing.md'), '']))
                    self.assertEqual(result.stderr, '')
                    self.assertEqual(sorted(p.relative_to(install).as_posix() for p in install.rglob('*')),
                                     ['prompts', 'prompts/template.md'])
        finally:
            install.chmod(0o755)



if __name__ == '__main__':
    unittest.main()

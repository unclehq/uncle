"""Configure AWS Bedrock: self_hosted.py profile argument, apply-all, TUI apply-to-all, cross-surface runner.

Covers AC-3 (TUI), AC-4 (CLI profile arg), AC-6 (fallback-written config read by the TUI's stage_runner).
"""
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
sys.path.insert(0, str(ROOT))
SH = ROOT / 'scripts' / 'lib' / 'self_hosted.py'
TOKEN = 'bedrock-sentinel-token-7731'
OTHER = 'selfhosted-sentinel-token-1188'
URL = 'https://bedrock.example.com/openai/v1'
STAGES = ('requirements change-spec project-plan change-plan adversarial-review updated-plan '
          'updated-change-plan preflight implementation repair test-review manual-checklist '
          'execute-checklist final-audit').split()


def load_tui():
    spec = importlib.util.spec_from_file_location('uncle_tui_configure_test', ROOT / 'uncle_tui.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / '.uncle'
        self.dir.mkdir()
        self.config = self.dir / 'config'
        self.bk = self.dir / 'aws-bedrock-keys.json'
        self.sk = self.dir / 'self-hosted-keys.json'

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, stdin=''):
        return subprocess.run([sys.executable, str(SH), *args], input=stdin, capture_output=True, text=True,
                              env={**os.environ, 'UNCLE_CONFIG': str(self.config)}, timeout=60)

    def snap(self):
        return {p.name: (p.read_bytes() if p.exists() else None) for p in (self.config, self.bk, self.sk)}

    def seed_bedrock(self, **extra):
        keys = {'__opencode_models__': {'anthropic.claude-x': {'model': 'anthropic.claude-x', 'base_url': URL}},
                '__opencode_connection__': {'base_url': URL}, 'implementation': TOKEN}
        keys.update(extra)
        self.bk.write_text(json.dumps(keys))

    def assertNoLeak(self, result):
        self.assertNotIn(TOKEN, result.stdout)
        self.assertNotIn(TOKEN, result.stderr)


class InvalidProfile(Base):
    def test_unknown_profile_rejected_and_writes_nothing(self):
        self.config.write_text('implementation.runner aws-bedrock\n')
        self.seed_bedrock()
        self.sk.write_text(json.dumps({'implementation': OTHER}))
        before = self.snap()
        for args, stdin in ((('models', str(self.config), 'aws-bedrok'), ''),
                            (('choose-model', str(self.config), 'aws-bedrok'), 'anthropic.claude-x\n'),
                            (('set-key', str(self.config), 'implementation', 'aws-bedrok'), TOKEN + '\n'),
                            (('set-key', str(self.config), 'implementation', 'aws-bedrok'), '')):
            r = self.cli(*args, stdin=stdin)
            self.assertNotEqual(r.returncode, 0, args)
            self.assertNoLeak(r)
            self.assertEqual(self.snap(), before, args)

    def test_unknown_profile_with_no_key_files_creates_none(self):
        for args in (('set-key', str(self.config), 'implementation', 'aws-bedrok'),):
            r = self.cli(*args, stdin=TOKEN + '\n')
            self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.bk.exists())
        self.assertFalse(self.sk.exists())


class BedrockProfile(Base):
    def test_default_profile_still_uses_self_hosted_store(self):
        self.config.write_text('')
        r = self.cli('set-key', str(self.config), 'implementation', stdin=OTHER + '\n')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.sk.read_text())['implementation'], OTHER)
        self.assertFalse(self.bk.exists())

    def test_set_key_bedrock_writes_bedrock_store_only_with_mode_0600(self):
        self.config.write_text('')
        self.sk.write_text(json.dumps({'implementation': OTHER}))
        sk_before = self.sk.read_bytes()
        r = self.cli('set-key', str(self.config), 'implementation', 'aws-bedrock', stdin=TOKEN + '\n')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNoLeak(r)
        self.assertEqual(json.loads(self.bk.read_text())['implementation'], TOKEN)
        self.assertEqual(stat.S_IMODE(self.bk.stat().st_mode), 0o600)
        self.assertEqual(self.sk.read_bytes(), sk_before)
        self.assertNotIn(TOKEN, self.config.read_text())

    def test_empty_stdin_removes_only_named_stage_key(self):
        self.config.write_text('')
        self.seed_bedrock(repair='other-stage-token')
        self.sk.write_text(json.dumps({'implementation': OTHER}))
        sk_before = self.sk.read_bytes()
        r = self.cli('set-key', str(self.config), 'implementation', 'aws-bedrock', stdin='')
        self.assertEqual(r.returncode, 0, r.stderr)
        keys = json.loads(self.bk.read_text())
        self.assertNotIn('implementation', keys)
        self.assertEqual(keys['repair'], 'other-stage-token')
        self.assertEqual(self.sk.read_bytes(), sk_before)

    def test_removing_absent_key_leaves_file_byte_identical_or_absent(self):
        self.config.write_text('')
        r = self.cli('set-key', str(self.config), 'implementation', 'aws-bedrock', stdin='')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.bk.exists())
        self.seed_bedrock()
        before = self.bk.read_bytes()
        r = self.cli('set-key', str(self.config), 'final-audit', 'aws-bedrock', stdin='')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.bk.read_bytes(), before)

    def test_choose_model_matches_exact_stored_name_without_prefix(self):
        self.config.write_text('')
        self.seed_bedrock()
        r = self.cli('choose-model', str(self.config), 'aws-bedrock', stdin='anthropic.claude-x\n')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), 'anthropic.claude-x')
        self.assertNotIn('local/', r.stdout)

    def test_choose_model_failures_exit_nonzero_with_empty_stdout_and_bedrock_wording(self):
        self.config.write_text('')
        self.seed_bedrock()
        for stdin in ('nope\n', '\n', ''):
            r = self.cli('choose-model', str(self.config), 'aws-bedrock', stdin=stdin)
            self.assertNotEqual(r.returncode, 0, repr(stdin))
            self.assertEqual(r.stdout, '')
            self.assertIn('Bedrock', r.stderr)
            self.assertNotIn('OpenCode', r.stderr)
        self.bk.write_text(json.dumps({'__opencode_models__': {}}))
        r = self.cli('choose-model', str(self.config), 'aws-bedrock', stdin='x\n')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, '')
        self.assertIn('Bedrock', r.stderr)

    def test_models_with_bad_base_url_rejected_and_nothing_written(self):
        self.config.write_text('')
        self.seed_bedrock()
        before = self.snap()
        for bad in ('ftp://host/x', 'https://', 'https://user:pw@host/x', 'https://host/x?q=1', 'https://host/x#f'):
            r = self.cli('models', str(self.config), 'aws-bedrock', stdin=bad + '\n')
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertNoLeak(r)
            self.assertEqual(self.snap(), before, bad)


class ApplyAll(Base):
    def test_apply_all_copies_token_inside_python_for_exact_stage_set(self):
        self.config.write_text('')
        self.seed_bedrock(repair='stale-bedrock-token')
        self.sk.write_text(json.dumps({'implementation': OTHER}))
        sk_before = self.sk.read_bytes()
        r = self.cli('apply-all', str(self.config), 'aws-bedrock', 'implementation')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNoLeak(r)
        keys = json.loads(self.bk.read_text())
        self.assertEqual({k for k in keys if not k.startswith('__')}, set(STAGES))
        for stage in STAGES:
            self.assertEqual(keys[stage], TOKEN, stage)
        self.assertEqual(self.sk.read_bytes(), sk_before)
        self.assertEqual(stat.S_IMODE(self.bk.stat().st_mode), 0o600)

    def test_apply_all_without_source_token_fails_and_writes_nothing(self):
        self.config.write_text('')
        self.seed_bedrock()
        keys = json.loads(self.bk.read_text())
        keys.pop('implementation')
        self.bk.write_text(json.dumps(keys))
        before = self.snap()
        r = self.cli('apply-all', str(self.config), 'aws-bedrock', 'implementation')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.snap(), before)

    def test_apply_all_rejects_unknown_profile(self):
        self.config.write_text('')
        self.seed_bedrock()
        self.sk.write_text(json.dumps({'implementation': OTHER}))
        before = self.snap()
        r = self.cli('apply-all', str(self.config), 'aws-bedrok', 'implementation')
        self.assertNotEqual(r.returncode, 0)
        self.assertNoLeak(r)
        self.assertEqual(self.snap(), before)


class TuiSurface(Base):
    def make_tui(self, mod):
        class Stub:
            notice = ''
            stage_target = 'implementation'
            maybe_reload = lambda self: None
            save_config = lambda self: None
            _stage_value = mod.UncleTUI._stage_value
            stage_runner = mod.UncleTUI.stage_runner
            _keys_for = mod.UncleTUI._keys_for
            _apply_opencode_to_all_stages = mod.UncleTUI._apply_opencode_to_all_stages
        tui = Stub()
        tui.stage_runners = {'implementation': 'aws-bedrock', 'requirements': 'claude', 'repair': 'codex',
                             'final-audit': 'self-hosted'}
        tui.stage_models = {'implementation': 'anthropic.claude-x', 'requirements': 'stale'}
        tui.stage_base_urls = {'implementation': URL}
        tui.stage_efforts, tui.stage_networks = {}, {}
        tui.stage_api_keys = {'final-audit': OTHER, 'requirements': OTHER}
        tui.bedrock_keys = {'implementation': TOKEN, 'repair': 'stale-bedrock', '__opencode_connection__': {'base_url': URL}}
        return tui

    def test_apply_to_all_on_bedrock_stage_uses_bedrock_store_only(self):
        mod = load_tui()
        tui = self.make_tui(mod)
        self_hosted_before = json.dumps(tui.stage_api_keys, sort_keys=True)
        tui._apply_opencode_to_all_stages()
        for stage in mod.CONFIG_STAGES:
            self.assertEqual(tui.stage_runners[stage], 'aws-bedrock', stage)
            self.assertEqual(tui.stage_models[stage], 'anthropic.claude-x', stage)
            self.assertEqual(tui.stage_base_urls[stage], URL, stage)
        stage_keys = {k for k in tui.bedrock_keys if not k.startswith('__')}
        self.assertEqual(stage_keys, set(mod.CONFIG_STAGES))
        for stage in mod.CONFIG_STAGES:
            self.assertEqual(tui.bedrock_keys[stage], TOKEN, stage)
        self.assertEqual(json.dumps(tui.stage_api_keys, sort_keys=True), self_hosted_before)
        self.assertNotIn('Self hosted', tui.notice)
        self.assertIn('Bedrock', tui.notice)

    def test_apply_to_all_on_self_hosted_stage_unchanged(self):
        mod = load_tui()
        tui = self.make_tui(mod)
        tui.stage_target = 'final-audit'
        bedrock_before = json.dumps(tui.bedrock_keys, sort_keys=True)
        tui._apply_opencode_to_all_stages()
        self.assertEqual(tui.stage_runners['requirements'], 'self-hosted')
        self.assertEqual(tui.stage_api_keys['requirements'], OTHER)
        self.assertEqual(json.dumps(tui.bedrock_keys, sort_keys=True), bedrock_before)


class CrossSurface(Base):
    def test_ac6_tui_stage_runner_reads_fallback_written_bedrock_config(self):
        """Config written by the real `uncle` fallback is read by the TUI's real stage_runner."""
        project = Path(self.tmp.name)
        self.config.write_text('requirements.runner self-hosted\nrequirements.model local/foo\n')
        self.seed_bedrock()
        # Menu: 4 Configure, 1 Stages, 1 requirements, r + runner, then back out.
        stdin = '4\n1\n1\nr\naws-bedrock\nq\nq\nq\nq\n'
        env = {**os.environ, 'UNCLE_CONFIG': str(self.config), 'HOME': str(project)}
        for key in ('UNCLE_STARTUP_ACTION', 'UNCLE_RUNTIME_ROOT'):
            env.pop(key, None)
        proc = subprocess.run(['bash', str(ROOT / 'uncle')], input=stdin, capture_output=True, text=True,
                              cwd=project, env=env, timeout=120)
        self.assertIn('requirements.runner aws-bedrock', self.config.read_text(), proc.stdout + proc.stderr)
        mod = load_tui()
        values = {}
        for line in self.config.read_text().splitlines():
            if line and not line.startswith('#'):
                key, _, value = line.partition(' ')
                values[key] = value

        class Stub:
            notice = ''
            _stage_value = mod.UncleTUI._stage_value
            stage_runner = mod.UncleTUI.stage_runner
        tui = Stub()
        tui.stage_runners = {k[:-len('.runner')]: v for k, v in values.items() if k.endswith('.runner')}
        self.assertEqual(tui.stage_runner('requirements'), 'aws-bedrock')
        self.assertEqual(values.get('requirements.model'), 'local/foo')
        self.assertNotIn(TOKEN, proc.stdout + proc.stderr + self.config.read_text())


if __name__ == '__main__':
    unittest.main()

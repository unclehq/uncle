#!/usr/bin/env python3
"""The requirements row is editable: its own runner/model/effort win, otherwise requirements follow project-plan."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import self_hosted


class RequirementsStageConfig(unittest.TestCase):
    def shell(self, config, expr):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / '.uncle').mkdir()
            (Path(root) / '.uncle' / 'config').write_text(config)
            env = {k: v for k, v in os.environ.items() if not k.startswith('WORKFLOW_')}
            script = 'cd "$1"; source "$2/scripts/lib/stage-config.sh"; source "$2/scripts/lib/stage-runtime.sh"; ' + expr
            out = subprocess.run(['bash', '-c', script, 'x', root, str(ROOT)], env=env, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            return out.stdout.strip()

    def test_follows_project_plan_when_row_unset(self):
        cfg = 'project-plan.model opus\n'
        for stage in ('requirements', 'requirements-investigate'):
            self.assertEqual(self.shell(cfg, 'app_stage_runner_config_name ' + stage), 'project-plan')
            self.assertEqual(self.shell(cfg, 'uncle_config_stage ' + stage), 'project-plan')
            self.assertEqual(self.shell(cfg, 'uncle_stage_model ' + stage + ' claude'), 'opus')

    def test_own_row_wins_when_any_key_set(self):
        cfg = 'project-plan.model opus\nrequirements.model haiku\n'
        for stage in ('requirements', 'requirements-investigate'):
            self.assertEqual(self.shell(cfg, 'app_stage_runner_config_name ' + stage), 'requirements')
            self.assertEqual(self.shell(cfg, 'uncle_stage_model ' + stage + ' claude'), 'haiku')
        self.assertEqual(self.shell(cfg, 'uncle_stage_model project-plan claude'), 'opus')

    def test_self_hosted_profile_lookup_matches(self):
        for stage in ('requirements', 'requirements-investigate'):
            self.assertEqual(self_hosted.config_stage(stage, {'project-plan.model': 'a'}), 'project-plan')
            self.assertEqual(self_hosted.config_stage(stage, {'requirements.model': 'b', 'project-plan.model': 'a'}), 'requirements')
            self.assertEqual(self_hosted.config_stage(stage, {'requirements.effort': 'low'}), 'requirements')


if __name__ == '__main__':
    unittest.main()

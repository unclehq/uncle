#!/usr/bin/env python3
"""Configure -> Configure self hosting -> Temperature: the on/off switch, its storage and its preservation."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
os.environ.setdefault('UNCLE_MODEL_REFRESH', '0')

import uncle_tui as tui  # noqa: E402
import self_hosted_http as http  # noqa: E402


def screen(config_path):
    ui = tui.UncleTUI.__new__(tui.UncleTUI)
    ui.stage_api_keys, ui.bedrock_keys = {}, {}
    ui.config_section, ui.config_sel, ui.state = 'opencode', 2, 'config'
    ui.load_config()
    return ui


class TemperatureConfigTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / '.uncle').mkdir()
        self.config = root / '.uncle' / 'config'
        env = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_SELF_HOSTED', 'UNCLE_'))}
        env.update(UNCLE_CONFIG=str(self.config), UNCLE_MODEL_REFRESH='0')
        for patcher in (mock.patch.dict(os.environ, env, clear=True),
                        mock.patch.object(tui, 'CONFIG_PATH', str(self.config)),
                        mock.patch.object(tui, '_project_root', lambda: str(root))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.config.write_text('requirements.runner claude\n')

    def test_row_is_off_by_default(self):
        self.assertEqual(screen(self.config)._config_items()[2], 'Temperature: off')

    def test_toggle_writes_the_key_the_driver_reads(self):
        ui = screen(self.config)
        ui._toggle_use_temperature()
        self.assertIn('self-hosted.use-temperature on', self.config.read_text())
        self.assertEqual(http.temperature('implementation'), 0.0)
        ui._toggle_use_temperature()
        self.assertIn('self-hosted.use-temperature off', self.config.read_text())
        self.assertIsNone(http.temperature('implementation'))

    def test_the_setting_survives_a_reload(self):
        screen(self.config)._toggle_use_temperature()
        self.assertEqual(screen(self.config)._config_items()[2], 'Temperature: on')

    def test_hand_written_self_hosted_lines_survive_a_save(self):
        self.config.write_text('requirements.runner claude\nself-hosted.temperature 0.7\nself-hosted.prefetch on\n')
        ui = screen(self.config)
        ui._toggle_use_temperature()
        text = self.config.read_text()
        self.assertIn('self-hosted.temperature 0.7', text)
        self.assertIn('self-hosted.prefetch on', text)
        self.assertEqual(http.temperature('implementation'), 0.7)

    def test_the_row_has_its_own_description(self):
        ui = screen(self.config)
        self.assertIn('self-hosted.use-temperature', ui._config_desc())


if __name__ == '__main__':
    unittest.main()

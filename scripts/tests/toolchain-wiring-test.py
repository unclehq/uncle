#!/usr/bin/env python3
"""Source-level wiring: each driver calls the toolchain installer at PREFLIGHT (hosted only) and the four prompts carry the hosted-toolchain paragraph."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / 'scripts' / 'change-workflow.sh'
PROMPTS = [
    ROOT / 'prompts' / 'change' / 'baseline.md',
    ROOT / 'prompts' / 'change' / 'change-plan.md',
    ROOT / 'prompts' / 'change' / 'implement-change.md',
    ROOT / 'prompts' / 'implement.md',
]


class DriverWiring(unittest.TestCase):
    def setUp(self):
        self.src = DRIVER.read_text(encoding='utf-8')

    def test_driver_calls_installer(self):
        self.assertIn('toolchain_install.py', self.src)

    def test_installer_call_is_hosted_gated(self):
        m = re.search(r'toolchain_install\.py', self.src)
        window = self.src[max(0, m.start() - 1500):m.start()]
        self.assertRegex(window, r'(?i)hosted')

    def test_installer_record_feeds_preflight_narrative(self):
        self.assertIn('toolchain-install.json', self.src)

    def test_installer_runs_before_preflight_probe(self):
        self.assertIn('change_preflight_run', self.src)
        call = self.src.index('toolchain_install.py')
        # the installer call must be wired into the preflight path, not unrelated code
        window = self.src[max(0, call - 3000):call + 3000]
        self.assertRegex(window, r'(?i)preflight')

    def test_preflight_failure_still_blocked_setup(self):
        self.assertIn('BLOCKED-SETUP', self.src)


class StagegateWiring(unittest.TestCase):
    """The new-application driver installs missing toolchains at PREFLIGHT the same way (hosted only, never fatal)."""

    def setUp(self):
        self.src = (ROOT / 'scripts' / 'stagegate.sh').read_text(encoding='utf-8')
        self.install = self.src.index('toolchain_install.py')

    def test_driver_calls_installer_before_the_probe(self):
        probe = self.src.index('preflight.py" "$GREEN_CMDS"')
        self.assertLess(self.install, probe)
        self.assertLess(probe - self.install, 1500)

    def test_installer_runs_on_the_approved_verification_commands(self):
        call = self.src[self.install:self.install + 200]
        self.assertIn('$GREEN_CMDS', call)
        self.assertIn('toolchain-install.json', call)

    def test_installer_call_is_documented_as_hosted_gated_and_never_fatal(self):
        window = self.src[self.install - 900:self.install + 500]
        self.assertRegex(window, r'(?i)hosted')
        self.assertIn('|| echo "Toolchain install: helper exited nonzero', window)

    def test_driver_never_names_the_hosted_switch(self):
        # tests/host-preview-test.py: only the shared hook may read it; the helper decides hosted mode itself.
        self.assertNotIn('UNCLE_HOSTED', self.src[self.install - 900:self.install + 500])


class PromptParagraph(unittest.TestCase):
    def test_each_prompt_has_hosted_toolchain_paragraph(self):
        for p in PROMPTS:
            with self.subTest(prompt=p.name):
                text = p.read_text(encoding='utf-8')
                paras = [x for x in re.split(r'\n\s*\n', text)
                         if re.search(r'(?i)hosted', x) and re.search(r'(?i)toolchain|compiler', x)
                         and re.search(r'(?i)install', x)]
                self.assertTrue(paras, f'{p} lacks a hosted toolchain install paragraph')

    def test_prompts_forbid_hand_tracing_for_missing_toolchain(self):
        for p in PROMPTS:
            with self.subTest(prompt=p.name):
                self.assertRegex(p.read_text(encoding='utf-8'), r'(?i)hand-trac')


if __name__ == '__main__':
    unittest.main()

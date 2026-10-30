#!/usr/bin/env python3
"""Ecosystem detection for the once-per-stage .gitignore check reads whole words only."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import project_plan_stage as stage


class DetectTests(unittest.TestCase):
    def probes(self, text):
        return set(stage.required_paths(text))

    def test_prose_words_do_not_select_other_ecosystems(self):
        paths = self.probes('Build a React app with Vite. The next step is to trust the tests; then pipe output.')
        self.assertIn('node_modules/probe', paths)
        self.assertNotIn('.next/probe', paths)      # "next step"
        self.assertNotIn('target/probe', paths)     # "trust"
        self.assertNotIn('.venv/probe', paths)      # "pipe"

    def test_real_signals_still_select(self):
        self.assertIn('.next/probe', self.probes('Use Next.js app router'))
        self.assertIn('.next/probe', self.probes('package.json has "next": "14.2.0"'))
        self.assertIn('.next/probe', self.probes('nextjs project'))
        self.assertIn('target/probe', self.probes('A Rust CLI built with cargo'))
        self.assertIn('.venv/probe', self.probes('Python service tested with pytest'))
        self.assertIn('test-results/probe', self.probes('E2E with Playwright'))
        self.assertIn('.svelte-kit/probe', self.probes('SvelteKit site'))

    def test_universal_entries_always_present(self):
        self.assertTrue({'.env', '.env.local', '.DS_Store'} <= self.probes('anything'))


if __name__ == '__main__':
    unittest.main()

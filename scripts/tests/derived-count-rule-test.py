#!/usr/bin/env python3
"""The derived-count rule reaches the prompts that write the plan, the tests, and the repair."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import project_plan_sections as sections


class DerivedCounts(unittest.TestCase):
    def read(self, name):
        return (ROOT / 'prompts' / name).read_text(encoding='utf-8')

    def test_plan_authors_are_told_never_to_write_a_derived_total(self):
        for name in ('project-plan.md', 'project-plan-section-shared.md'):
            text = self.read(name)
            self.assertIn('## Counts and totals', text, name)
            self.assertIn('Never write a total you derived from a list as a literal', text, name)

    def test_every_section_worker_gets_the_rule(self):
        base = self.read('project-plan-investigate.md')
        with tempfile.TemporaryDirectory() as directory:
            for name in ('design', 'behaviors', 'tests', 'invariants'):
                prompt = sections.build_prompt(name, directory, base, blocks=True)
                self.assertIn('## Counts and totals', prompt, name)

    def test_test_writers_derive_counts_from_the_list(self):
        text = self.read('implement.md')
        self.assertIn('## Counts in tests come from the list, not from prose', text)
        self.assertIn('the list is right', text)

    def test_repair_sides_with_the_list(self):
        text = self.read('repair.md')
        self.assertIn('## A count that disagrees with its own list', text)
        self.assertIn('Do not change the implementation to produce the', text)


if __name__ == '__main__':
    unittest.main()

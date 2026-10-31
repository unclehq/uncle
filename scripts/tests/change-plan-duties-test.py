#!/usr/bin/env python3
"""The change plan's consistency check: deterministic, quiet about files a plan merely reads, and applied as a patch to the canonical plan."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('change_plan_duties', ROOT / 'scripts/lib/change_plan_duties.py')
cpd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpd)

PLAN = ('# Change plan\n\n## 1. Implementation sequence\n\n1. Style the page — Owns: `src/styles.css`, `src/App.jsx` '
        '— Depends on: 0\n\n## 2. Notes\n\nThe theme lives in `src/theme.css`; `App.jsx` renders it; see `README.md` and `src/main.jsx`.\n')


def project(test, plan=PLAN, canonical=True):
    d = tempfile.TemporaryDirectory()
    test.addCleanup(d.cleanup)
    root = Path(d.name)
    (root / '.uncle/docs').mkdir(parents=True)
    (root / '.uncle/workflow/documents').mkdir(parents=True)
    (root / 'src').mkdir()
    (root / 'src/styles.css').write_text('x')
    (root / 'src/main.jsx').write_text('x')
    (root / 'README.md').write_text('x')
    (root / '.uncle/docs/CHANGE_PLAN.md').write_text(plan)
    if canonical:
        (root / '.uncle/workflow/documents/CHANGE_PLAN.json').write_text(json.dumps(
            {'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': plan}))
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    return root


class Findings(unittest.TestCase):
    def test_one_file_with_two_names_is_found(self):
        found = cpd.findings(project(self))
        self.assertEqual(len(found), 1)
        self.assertIn('`src/theme.css`', found[0])
        self.assertIn('`src/styles.css` is owned beside it', found[0])

    def test_existing_files_the_plan_only_reads_are_not_findings(self):
        # README.md and src/main.jsx exist and are not owned: context, not a contradiction.
        self.assertNotIn('main.jsx', ' '.join(cpd.findings(project(self))))
        self.assertNotIn('README', ' '.join(cpd.findings(project(self))))

    def test_a_bare_file_name_that_is_an_owned_files_basename_is_not_a_finding(self):
        self.assertNotIn('App.jsx', ' '.join(cpd.findings(project(self))))

    def test_a_consistent_plan_has_no_findings(self):
        plan = PLAN.replace('`src/theme.css`', '`src/styles.css`')
        self.assertEqual(cpd.findings(project(self, plan)), [])

    def test_a_plan_that_declares_no_ownership_is_not_judged(self):
        self.assertEqual(cpd.findings(project(self, '# Plan\n\n## 1. Notes\n\nSee `src/theme.css`.\n')), [])

    def test_a_missing_directory_owner_is_found(self):
        plan = PLAN.replace('`src/theme.css`', '`src/extra/util.js`').replace('`src/App.jsx`', '`src/extra/other.js`')
        found = cpd.findings(project(self, plan))
        self.assertTrue(any('src/extra/util.js' in line for line in found), found)

    def test_the_canonical_narrative_is_what_is_checked(self):
        root = project(self)
        (root / '.uncle/workflow/documents/CHANGE_PLAN.json').write_text(json.dumps(
            {'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': PLAN.replace('`src/theme.css`', '`src/styles.css`')}))
        self.assertEqual(cpd.findings(root), [])


class Apply(unittest.TestCase):
    PATCH = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan-duties',
             'patch': {'replace_text': [{'heading': '## 2. Notes', 'old': 'src/theme.css', 'new': 'src/styles.css'}]}}

    def test_a_patch_fixes_the_canonical_plan_and_its_view(self):
        root = project(self)
        delivery = root / 'answer.json'
        delivery.write_text(json.dumps(self.PATCH))
        self.assertEqual(cpd.apply(root, delivery), [])
        canonical = json.loads((root / '.uncle/workflow/documents/CHANGE_PLAN.json').read_text())
        self.assertIn('src/styles.css', canonical['narrative'])
        self.assertNotIn('theme.css', canonical['narrative'])
        self.assertNotIn('theme.css', (root / '.uncle/docs/CHANGE_PLAN.md').read_text())
        self.assertEqual(canonical['kind'], 'change-plan')

    def test_everything_else_in_the_plan_is_untouched(self):
        root = project(self)
        delivery = root / 'answer.json'
        delivery.write_text(json.dumps(self.PATCH))
        cpd.apply(root, delivery)
        after = json.loads((root / '.uncle/workflow/documents/CHANGE_PLAN.json').read_text())['narrative']
        self.assertEqual(after, PLAN.replace('src/theme.css', 'src/styles.css'))

    def test_the_answer_may_arrive_only_as_the_runners_text(self):
        root = project(self)
        log = root / 'run.jsonl'
        log.write_text(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': json.dumps(self.PATCH)}]}}) + '\n')
        self.assertEqual(cpd.apply(root, root / 'missing.json', log=log), [])

    def test_a_bad_patch_is_an_error_and_leaves_the_plan_alone(self):
        root = project(self)
        delivery = root / 'answer.json'
        delivery.write_text(json.dumps({'kind': 'change-plan-duties', 'patch': {'replace_text': [
            {'heading': '## 9. Nope', 'old': 'x', 'new': 'y'}]}}))
        before = (root / '.uncle/workflow/documents/CHANGE_PLAN.json').read_text()
        with self.assertRaises(ValueError):
            cpd.apply(root, delivery)
        self.assertEqual((root / '.uncle/workflow/documents/CHANGE_PLAN.json').read_text(), before)

    def test_an_empty_patch_changes_nothing_and_keeps_the_findings(self):
        root = project(self)
        delivery = root / 'answer.json'
        delivery.write_text(json.dumps({'kind': 'change-plan-duties', 'patch': {}, 'note': 'fine'}))
        before = (root / '.uncle/workflow/documents/CHANGE_PLAN.json').read_text()
        self.assertEqual(len(cpd.apply(root, delivery)), 1)
        self.assertEqual((root / '.uncle/workflow/documents/CHANGE_PLAN.json').read_text(), before)

    def test_something_that_is_not_the_packet_is_rejected(self):
        root = project(self)
        for text in ('not json', json.dumps({'kind': 'other', 'patch': {}}), json.dumps({'kind': 'change-plan-duties'})):
            (root / 'answer.json').write_text(text)
            with self.assertRaises(ValueError):
                cpd.apply(root, root / 'answer.json')

    def test_the_prompt_lists_the_findings_and_the_patch_format(self):
        root = project(self)
        out = root / 'prompt.md'
        cpd.prompt(root, '.uncle/docs/CHANGE_PLAN.md', out)
        text = out.read_text()
        self.assertIn('`src/theme.css`', text)
        self.assertIn('"kind":"change-plan-duties"', text)
        self.assertIn('replace_text', text)


if __name__ == '__main__':
    unittest.main()

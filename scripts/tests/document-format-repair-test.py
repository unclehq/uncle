#!/usr/bin/env python3
"""The format repairer fixes only shape, and only when the reading is certain.

Runs have been lost to documents that were right in substance and wrong in
shape. These check both halves of the contract: the repairable cases really are
repaired into something the production validator accepts, and everything
needing judgment is left alone so the stage still fails.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts/lib' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repair_module = _load('repair_document_format', 'repair_document_format.py')
adversarial = _load('adversarial_context', 'adversarial-context.py')


def write(name, text):
    path = Path(tempfile.mkdtemp()) / name
    path.write_text(text, encoding='utf-8')
    return path


FINDING = ('## AR-001: Plan omits the rollback path\n\n'
           '- Severity: high\n'
           '- References: CHANGE_PLAN.md:41\n'
           '- Failure: a failed migration leaves the schema half-applied\n'
           '- Fix: state the rollback step\n'
           '- Verify: run the migration and roll back\n')


# These tests write the canonical workflow artifacts under the current directory (project='.'). Run from a scratch directory so
# running one of them inside a live worktree (a model worker's narrow check, the baseline) can never overwrite that run's files.
def setUpModule():
    import os, tempfile
    global _scratch, _previous_cwd
    _scratch = tempfile.TemporaryDirectory(prefix='uncle-test-cwd-')
    _previous_cwd = os.getcwd()
    os.chdir(_scratch.name)


def tearDownModule():
    import os
    os.chdir(_previous_cwd)
    _scratch.cleanup()


class Repairs(unittest.TestCase):
    def test_leaked_reasoning_and_bold_label_are_repaired(self):
        # The failure observed on unclehq/uncle#59: a local model wrote its
        # think-aloud above the document and made the assessment a bold label.
        path = write('ADVERSARIAL_REVIEW.md',
                     'Good, I can confirm from CHANGE_TEST_REPORT.md the tests pass.\n'
                     'Let me finalize my writing now...\n\n'
                     '# ADVERSARIAL_REVIEW.md\n\n### Summary\n\n'
                     '**Overall assessment:** The plan is structurally sound.\n\n' + FINDING)
        with self.assertRaises(ValueError):
            adversarial.validate(path)
        self.assertEqual(len(repair_module.repair(path)), 2)
        adversarial.validate(path)              # must now pass the real validator
        self.assertNotIn('Let me finalize', path.read_text())
        self.assertIn('The plan is structurally sound.', path.read_text())

    def test_colon_outside_the_bold_markers_is_also_repaired(self):
        path = write('ADVERSARIAL_REVIEW.md',
                     '# R\n\n**Overall assessment**: Sound.\n\n' + FINDING)
        self.assertTrue(repair_module.repair(path))
        adversarial.validate(path)

    def test_verdict_pushed_off_the_last_line_is_restored(self):
        path = write('FINAL_AUDIT.md',
                     '| ID | Blocks |\n|---|---|\n| FA-1 | NO |\n\nREADY\n\nSigned, the reviewer.\n')
        self.assertTrue(repair_module.repair(path))
        self.assertEqual(path.read_text().rstrip().splitlines()[-1], 'READY')


class Refusals(unittest.TestCase):
    """Anything needing judgment must be left for the stage to reject."""

    def test_valid_document_is_untouched(self):
        text = FINDING + '\n## Overall assessment\n\nFine.\n'
        path = write('ADVERSARIAL_REVIEW.md', text)
        self.assertEqual(repair_module.repair(path), [])
        self.assertEqual(path.read_text(), text)

    def test_unknown_document_is_ignored(self):
        text = 'junk\n\n# CHANGE_PLAN.md\n\nbody\n'
        path = write('CHANGE_PLAN.md', text)
        self.assertEqual(repair_module.repair(path), [])
        self.assertEqual(path.read_text(), text)

    def test_missing_assessment_entirely_is_not_invented(self):
        # No assessment text anywhere: repairing would mean writing the
        # reviewer's conclusion for it, which must never happen.
        path = write('ADVERSARIAL_REVIEW.md', '# R\n\n' + FINDING)
        self.assertEqual(repair_module.repair(path), [])
        with self.assertRaises(ValueError):
            adversarial.validate(path)

    def test_substantial_prose_after_a_verdict_is_left_alone(self):
        text = 'READY\n\na\nb\nc\nd\ne\n'
        path = write('FINAL_AUDIT.md', text)
        self.assertEqual(repair_module.repair(path), [])
        self.assertEqual(path.read_text(), text)

    def test_document_without_headings_is_left_alone(self):
        text = 'prose with no headings at all\n'
        path = write('ADVERSARIAL_REVIEW.md', text)
        self.assertEqual(repair_module.repair(path), [])
        self.assertEqual(path.read_text(), text)


class LayoutExamples(unittest.TestCase):
    """Every layout example must satisfy the validator it teaches."""

    def test_adversarial_example_passes_its_own_validator(self):
        import re
        import subprocess
        block = subprocess.run(
            ['bash', '-c', '. scripts/lib/document-layout.sh; _layout_adversarial_review'],
            cwd=ROOT, capture_output=True, text=True).stdout
        start = re.search(r'^## AR-001: Plan omits', block, re.M)
        self.assertIsNotNone(start, 'example finding not found in the layout block')
        document = block[start.start():block.index('Every finding needs')].rstrip() + '\n'
        adversarial.validate(write('ADVERSARIAL_REVIEW.md', document))


class ReviewerOutput(unittest.TestCase):
    """A reply that only talks about the document must not become the document."""

    def setUp(self):
        self.mod = _load('reviewer_output', 'reviewer_output.py')

    def test_announcement_is_rejected(self):
        # The unclehq/uncle#59 shape: the model ends its turn having listed what
        # it still intends to do, and the runner reports success.
        with self.assertRaises(ValueError) as caught:
            self.mod.check('I will now analyze CHANGE_PLAN.md.\n'
                           '- Confirm the signature\n'
                           '- Produce ADVERSARIAL_REVIEW.md with concrete findings\n', 'kimi')
        self.assertIn('no document', str(caught.exception))
        self.assertIn('kimi', str(caught.exception))

    def test_chat_answer_is_rejected(self):
        with self.assertRaises(ValueError):
            self.mod.check('The user asked "What did we do so far?" Here is a summary.\n')

    def test_empty_is_rejected(self):
        with self.assertRaises(ValueError):
            self.mod.check('')

    def test_heading_document_is_accepted(self):
        text = '# ADVERSARIAL_REVIEW.md\n\n## AR-001: X\n'
        self.assertEqual(self.mod.check(text), text)

    def test_table_only_document_is_accepted(self):
        # A findings table with no heading is still a document.
        text = '| ID | Blocks |\n|---|---|\n| FA-1 | NO |\n'
        self.assertEqual(self.mod.check(text), text)

PLAN_PROMPT_LINES = (
    "## Verification commands\n\n$ sh -c '\n  set -e\n  npm ci\n  npx vite build\n'\n\n"
    "## 1. Architecture\n\nA static React app.\n")


class VerificationCommandsFence(unittest.TestCase):
    """A plan whose commands are `$ cmd` lines gets the fence the exporter requires."""

    def export(self, path):
        plan_context = _load('plan_context', 'plan_context.py')
        return plan_context.export_project_plan(str(path), tempfile.mkdtemp())

    def test_prompt_lines_are_fenced_and_the_plan_then_exports(self):
        path = write('PROJECT_PLAN.md', PLAN_PROMPT_LINES)
        with self.assertRaisesRegex(ValueError, 'Verification commands fenced block'):
            self.export(path)
        self.assertTrue(repair_module.repair(path))
        payload = self.export(path)
        self.assertEqual(payload['verification_commands'], "sh -c '\n  set -e\n  npm ci\n  npx vite build\n'")
        self.assertIn('## 1. Architecture', payload['narrative'])
        self.assertNotIn('$ ', payload['verification_commands'])

    def test_any_shell_fence_tag_exports(self):
        # A bare ``` (or ```bash) fence for the commands used to stop a run: only ```sh parsed.
        for tag in ('', 'sh', 'bash', 'shell'):
            text = '## Verification commands\n\n```%s\nsh -c \'\n  set -e\n  npm test\n\'\n```\n\n## 1. Architecture\n\nx\n' % tag
            payload = self.export(write('PROJECT_PLAN.md', text))
            self.assertEqual(payload['verification_commands'], "sh -c '\n  set -e\n  npm test\n'", tag)
        with self.assertRaisesRegex(ValueError, 'Verification commands fenced block'):
            self.export(write('PROJECT_PLAN.md', '## Verification commands\n\n```python\nprint(1)\n```\n'))

    def test_a_correct_fence_is_left_alone(self):
        text = '## Verification commands\n\n```sh\nnpm test\n```\n'
        path = write('PROJECT_PLAN.md', text)
        self.assertEqual(repair_module.repair(path), [])
        self.assertEqual(path.read_text(encoding='utf-8'), text)

    def test_prose_instead_of_commands_is_not_guessed_at(self):
        text = '## Verification commands\n\nRun the usual build and tests.\n\n## 1. Architecture\n'
        path = write('PROJECT_PLAN.md', text)
        self.assertEqual(repair_module.repair(path), [])
        self.assertEqual(path.read_text(encoding='utf-8'), text)

    def test_other_documents_are_not_touched(self):
        path = write('MANUAL_CHECKLIST.md', PLAN_PROMPT_LINES)
        self.assertEqual(repair_module.repair(path), [])


if __name__ == '__main__':
    unittest.main(verbosity=0)

"""Updated-plan fast path: a clean (or skipped) review carries the approved plan forward without a model call."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import updated_plan_fast_path as fast  # noqa: E402

NARRATIVE = '''# Project plan

## 1. Architecture

Text.

### Protected verification paths

- tests/verify.sh
- `tests/mutations/run.mjs`

## 2. Next section

- not/a/protected/path
'''


def write(directory, name, payload):
    path = Path(directory) / name
    path.write_text(json.dumps(payload), encoding='utf-8')
    return str(path)


def plan(narrative=NARRATIVE, **extra):
    return dict({'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': narrative,
                 'verification_commands': 'sh tests/verify.sh'}, **extra)


REVIEW = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review', 'findings': [],
          'overall_assessment': 'skipped: class small, no risk hits'}


class FastPath(unittest.TestCase):
    def run_build(self, project_plan, review=REVIEW):
        with tempfile.TemporaryDirectory() as directory:
            source = write(directory, 'plan.json', project_plan)
            reviewed = write(directory, 'review.json', review)
            output, view = str(Path(directory) / 'out.json'), str(Path(directory) / 'out.md')
            ok = fast.build(source, reviewed, output, view)
            return ok, (json.loads(Path(output).read_text()) if ok else None), (Path(view).read_text() if ok else '')

    def test_paths_listed_in_the_plans_own_section_are_carried_forward(self):
        ok, result, view = self.run_build(plan())
        self.assertTrue(ok)
        self.assertEqual(result['protected_verification_paths'], 'tests/verify.sh\ntests/mutations/run.mjs')
        self.assertEqual(result['dispositions'], [])
        self.assertIn('## Protected verification paths', view)

    def test_fenced_block_under_the_heading_is_read(self):
        ok, result, _ = self.run_build(plan('## Protected paths\n\n```text\ntests/a.sh\ntests/b.sh\n```\n\n## Next\n'))
        self.assertTrue(ok)
        self.assertEqual(result['protected_verification_paths'], 'tests/a.sh\ntests/b.sh')

    def test_dedicated_field_wins_over_the_section(self):
        ok, result, _ = self.run_build(plan(protected_verification_paths='tests/only.sh'))
        self.assertTrue(ok)
        self.assertEqual(result['protected_verification_paths'], 'tests/only.sh')

    def test_no_paths_anywhere_still_declines(self):
        with self.assertRaises(ValueError):
            self.run_build(plan('# Project plan\n\n## 1. Architecture\n\nNothing protected here.\n'))

    def test_a_review_with_findings_declines(self):
        ok, _, _ = self.run_build(plan(), dict(REVIEW, findings=[{'id': 'AR-1'}]))
        self.assertFalse(ok)


if __name__ == '__main__':
    unittest.main()

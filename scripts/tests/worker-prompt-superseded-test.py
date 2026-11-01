"""A worker handed both the original and the updated plan is given only the updated one, so its inputs fit and are embedded."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import worker_prompt as w


def prompt(inputs):
    return ('Review the build.\n\n## Canonical inputs (binding)\n\nRead only these canonical JSON artifacts: %s. Do not inspect '
            'anything else.\n\n## Assigned checklist lens\n\nFocus on coverage.\n' % ', '.join('`%s`' % i for i in inputs))


class Superseded(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'documents').mkdir()

    def make(self, name, size=10):
        path = self.root / 'documents' / name
        path.write_text(json.dumps({'text': 'x' * size}))
        return str(path)

    def run_worker(self, names, sizes=None):
        sizes = sizes or {}
        paths = [self.make(n, sizes.get(n, 10)) for n in names]
        source, out = self.root / 'prompt.md', self.root / 'out.md'
        source.write_text(prompt(paths))
        code = w.main([str(source), str(out)])
        return code, out.read_text() if out.exists() else ''

    def test_the_original_plan_is_left_out_when_the_updated_plan_is_named(self):
        code, text = self.run_worker(['PROJECT_PLAN.json', 'UPDATED_PROJECT_PLAN.json', 'ADVERSARIAL_REVIEW.json'])
        self.assertEqual(code, 0)
        self.assertIn('### `%s/documents/UPDATED_PROJECT_PLAN.json`' % self.root, text)
        self.assertIn('ADVERSARIAL_REVIEW.json', text)
        self.assertNotIn('### `%s/documents/PROJECT_PLAN.json`' % self.root, text)
        self.assertIn('is superseded by the updated plan embedded above', text)

    def test_that_is_what_lets_a_small_applications_workers_be_embedded_at_all(self):
        big = {'PROJECT_PLAN.json': 90 * 1024, 'UPDATED_PROJECT_PLAN.json': 100 * 1024}
        code, text = self.run_worker(['PROJECT_PLAN.json', 'UPDATED_PROJECT_PLAN.json'], big)
        self.assertEqual(code, 0)                 # 190 KB named, 100 KB embedded: under the limit
        self.assertLess(len(text), w.LIMIT_BYTES)

    def test_an_input_set_that_is_still_too_large_is_left_alone(self):
        code, _ = self.run_worker(['UPDATED_PROJECT_PLAN.json'], {'UPDATED_PROJECT_PLAN.json': w.LIMIT_BYTES + 1024})
        self.assertEqual(code, 3)

    def test_the_original_plan_alone_is_embedded_as_before(self):
        code, text = self.run_worker(['PROJECT_PLAN.json', 'ADVERSARIAL_REVIEW.json'])
        self.assertEqual(code, 0)
        self.assertIn('### `%s/documents/PROJECT_PLAN.json`' % self.root, text)
        self.assertNotIn('superseded', text)

    def test_other_inputs_are_never_dropped(self):
        paths = ['a/REQUIREMENTS_INTERPRETATION.json', 'a/PROJECT_PLAN.json', 'a/UPDATED_PROJECT_PLAN.json', 'a/TEST_REVIEW.json']
        kept, dropped = w.drop_superseded(paths)
        self.assertEqual(dropped, ['a/PROJECT_PLAN.json'])
        self.assertEqual(kept, ['a/REQUIREMENTS_INTERPRETATION.json', 'a/UPDATED_PROJECT_PLAN.json', 'a/TEST_REVIEW.json'])

    def test_a_plan_in_another_directory_is_not_mistaken_for_the_superseded_one(self):
        kept, dropped = w.drop_superseded(['x/PROJECT_PLAN.json', 'y/UPDATED_PROJECT_PLAN.json'])
        self.assertEqual(dropped, [])
        self.assertEqual(len(kept), 2)


if __name__ == '__main__':
    unittest.main()

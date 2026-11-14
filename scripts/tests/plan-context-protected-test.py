#!/usr/bin/env python3
"""AC-5: Markdown project-plan ingest derives protected verification paths."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'


def load(name):
    spec = importlib.util.spec_from_file_location(name, LIB / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PLAN = """# Project plan

Tests live in `scripts/tests/widget-test.py` and are run by the commands below.

## Verification commands

```sh
python3 scripts/tests/widget-test.py
```
"""


class MarkdownIngestProtectedPaths(unittest.TestCase):
    def test_markdown_ingest_derives_and_marks_paths(self):
        pc, aj = load('plan_context'), load('artifact_json')
        with tempfile.TemporaryDirectory() as project:
            plan = Path(project) / 'PROJECT_PLAN.md'
            plan.write_text(PLAN, encoding='utf-8')
            payload = pc.export_project_plan(str(plan), project)
            self.assertEqual(payload['protected_verification_paths'], 'scripts/tests/widget-test.py')
            self.assertEqual(payload['protected_verification_paths_source'], 'ingest-derived')
            stored = aj.read(project, 'PROJECT_PLAN.md')
            self.assertEqual(stored['protected_verification_paths'], 'scripts/tests/widget-test.py')

    def test_explicit_paths_untouched(self):
        pc = load('plan_context')
        payload = {'protected_verification_paths': 'tests/explicit.py'}
        out = pc.apply_derived_protected_paths(payload, 'see `scripts/tests/widget-test.py`', '')
        self.assertEqual(out['protected_verification_paths'], 'tests/explicit.py')
        self.assertNotIn('protected_verification_paths_source', out)

    def test_nothing_derived_leaves_payload_unchanged(self):
        pc = load('plan_context')
        out = pc.apply_derived_protected_paths({}, 'no tests named', 'true')
        self.assertNotIn('protected_verification_paths', out)


if __name__ == '__main__':
    unittest.main()

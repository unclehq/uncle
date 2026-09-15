#!/usr/bin/env python3
"""Current hidden evidence must reach the reviewer, with bounded context."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "context", Path(__file__).resolve().parents[1] / "lib/test-review-context.py"
)
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


class ReviewContextTest(unittest.TestCase):
    def test_current_evidence_is_inline_and_history_is_only_referenced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / ".uncle/workflow"
            state.mkdir(parents=True)
            (state / "green-check.md").write_text("All verification commands passed.")
            (state / "green-check.tsv").write_text("PASS\tbash tests/browser.sh\n")
            (root / "VERIFICATION_REPORT.md").write_text("Old socket PermissionError")
            (state / "TEST_CHANGES.diff").write_text("large test diff" * 10000)
            output = context.render(root, state)
            self.assertIn("PASS\tbash tests/browser.sh", output)
            self.assertIn("All verification commands passed.", output)
            self.assertIn(str(state / "TEST_CHANGES.diff"), output)
            self.assertIn("SHA-256", output)
            self.assertNotIn("Old socket PermissionError", output)
            self.assertNotIn("large test diff", output)
            # A later invocation must pick up changed results, never cached passes.
            (state / "green-check.tsv").write_text("REGRESSION\tbash tests/browser.sh\n")
            self.assertIn("REGRESSION\tbash tests/browser.sh", context.render(root, state))

    def test_requirement_assertion_and_failure_locations_are_included(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / '.uncle/workflow'
            (state / 'logs').mkdir(parents=True)
            (root / 'tests').mkdir()
            test = root / 'tests/page.js'
            test.write_text("test('centering', () => {\n  expect(center).toBe(50);\n});\n")
            (root / 'UPDATED_PROJECT_PLAN.md').write_text('| AC-1 | Center text |\n')
            (state / 'verification.manifest').write_text(hashlib.sha256(test.read_bytes()).hexdigest() + '\ttests/page.js\n')
            (state / 'logs/green-check.log').write_text('not ok 1 centering\n')
            output = context.render(root, state)
            self.assertIn('UPDATED_PROJECT_PLAN.md:1: | AC-1', output)
            self.assertIn('tests/page.js:2:   expect(center)', output)
            self.assertIn('green-check.log:1: not ok 1', output)
            test.write_text('assert(newValue);\n')
            self.assertIn('tests/page.js:1: assert(newValue)', context.render(root, state))

    def test_index_is_bounded_and_does_not_follow_external_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project'
            root.mkdir()
            state = root / '.uncle/workflow'
            state.mkdir(parents=True)
            (Path(tmp) / 'outside.py').write_text('assert(private_marker);')
            (state / 'verification.manifest').write_text('a' * 64 + '\t../outside.py\n')
            output = context.focused_evidence(root.resolve(), state.resolve())
            self.assertNotIn('private_marker', output)
            (root / 'UPDATED_PROJECT_PLAN.md').write_text('| AC-1 | ' + 'x' * 500 + '\n' +
                ('| AC-2 | ' + 'x' * 500 + '\n') * 1000)
            self.assertLess(len(context.focused_evidence(root.resolve(), state.resolve()).encode()), 13000)

    def test_missing_empty_and_truncated_results_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / ".uncle/workflow"
            state.mkdir(parents=True)
            output = context.render(root, state)
            self.assertIn("MISSING", output)
            (state / "green-check.tsv").touch()
            (state / "green-check.md").write_text("x" * 20000 + "unread tail")
            output = context.render(root, state)
            self.assertIn("EMPTY", output)
            self.assertIn("Excerpt truncated", output)
            self.assertNotIn("unread tail", output)
            self.assertLess(len(output), 22000)


if __name__ == "__main__":
    unittest.main()

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

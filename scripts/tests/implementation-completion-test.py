#!/usr/bin/env python3
"""Acceptance handoffs must not turn partial delivery into stage success."""
import importlib.util
from pathlib import Path
import unittest

module = importlib.util.spec_from_file_location(
    "completion", Path(__file__).resolve().parents[1] / "lib/implementation-completion.py")
completion = importlib.util.module_from_spec(module)
module.loader.exec_module(completion)

SPEC = """## 5. Acceptance criteria
| ID | Criterion | Verification |
|---|---|---|
| AC-1 | Chat composer | UI check |
| AC-2 | File picker | Picker check |
## 6. Other section
| AC-99 | Not an acceptance criterion | Other |
"""
NOTES = """## Acceptance delivery
| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | ui.py composer | UI check PASS |
| AC-2 | IMPLEMENTED | ui.py picker | Picker check PASS |
"""


class CompletionTests(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(completion.check(SPEC, NOTES), [])
        self.assertEqual(completion.check(SPEC, NOTES.replace("UI check PASS", r"check \| tail: PASS")), [])

    def test_partial_or_blocked(self):
        for status in ("INCOMPLETE", "BLOCKED", "PASS", "NOT RUN", ""):
            with self.subTest(status=status):
                self.assertTrue(completion.check(SPEC, NOTES.replace("AC-2 | IMPLEMENTED", "AC-2 | " + status)))

    def test_missing_extra_and_empty_evidence(self):
        for notes in (NOTES.replace("AC-2", "AC-3"),
                      NOTES[:NOTES.index("| AC-2")],
                      NOTES.replace("Picker check PASS", "")):
            self.assertTrue(completion.check(SPEC, notes))

    def test_missing_duplicate_and_legacy_sections_fail_closed(self):
        for spec, notes in ((SPEC, "Old report: INCOMPLETE"),
                            ("Old specification", NOTES),
                            (SPEC, NOTES + NOTES),
                            (SPEC, NOTES + "| AC-2 | IMPLEMENTED | x | y |\n")):
            with self.assertRaises(ValueError):
                completion.check(spec, notes)

    def test_malformed_table(self):
        with self.assertRaises(ValueError):
            completion.check(SPEC, NOTES.replace("| ID | Status", "| Wrong | Status"))
        self.assertTrue(completion.check(SPEC.replace("Chat composer", ""), NOTES))


if __name__ == "__main__":
    unittest.main()

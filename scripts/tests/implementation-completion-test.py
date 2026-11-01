#!/usr/bin/env python3
"""Acceptance handoffs must not turn partial delivery into stage success."""
import importlib.util
import json
from pathlib import Path
import tempfile
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

    def test_canonical_json_is_authoritative_over_rendered_markdown(self):
        spec = {"schema": "uncle.artifact/v1", "kind": "change-spec",
                "acceptance_criteria": [
                    {"id": "AC-1", "criterion": "Chat composer", "verification": "UI check"},
                    {"id": "AC-2", "criterion": "File picker", "verification": "Picker check"},
                ]}
        notes = {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "fragments": [
            {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [
                {"id": "AC-1", "status": "IMPLEMENTED", "changed_code": "ui.py", "observed_verification": "PASS"},
                {"id": "AC-2", "status": "IMPLEMENTED", "changed_code": "picker.py", "observed_verification": "PASS"},
            ]}
        ]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec_path, notes_path = root / 'CHANGE_SPEC.json', root / 'IMPLEMENTATION_NOTES.json'
            spec_path.write_text(json.dumps(spec)); notes_path.write_text(json.dumps(notes))
            required, delivered = completion.canonical_rows(spec_path, notes_path)
        self.assertEqual(completion.check_rows(required, delivered), [])

    def test_cross_fragment_duplicate_delivery_is_merged_not_rejected(self):
        # Live incident, issue 116: AC-3 was genuinely delivered twice --
        # step 2 pointed at an existing test that already covered it, step 5
        # did its own separate, real work on the same criterion. Rejecting
        # this sent the whole implementation phase back to redo every step
        # from scratch, discarding completed, correct work over a bookkeeping
        # disagreement. Two different fragments agreeing the criterion is
        # IMPLEMENTED must merge into one row, combining the evidence.
        notes = {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "fragments": [
            {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [
                {"id": "AC-3", "status": "IMPLEMENTED", "changed_code": "none; covered by step 2",
                 "observed_verification": "runner-default-deny-test.sh passed"},
            ]},
            {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [
                {"id": "AC-3", "status": "IMPLEMENTED", "changed_code": "legacy-removal-gate-test.sh",
                 "observed_verification": "gate test passed"},
            ]},
        ]}
        delivered = completion.json_delivered(notes)
        self.assertIn("AC-3", delivered)
        status, changed_code, observed = delivered["AC-3"]
        self.assertEqual(status, "IMPLEMENTED")
        self.assertIn("step 2", changed_code)
        self.assertIn("legacy-removal-gate-test.sh", changed_code)
        self.assertIn("runner-default-deny-test.sh", observed)
        self.assertIn("gate test passed", observed)

    def test_same_fragment_duplicate_delivery_still_rejected(self):
        # One step claiming its own id twice is a real mistake, not two
        # steps' independent evidence -- still a hard failure.
        notes = {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "fragments": [
            {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [
                {"id": "AC-3", "status": "IMPLEMENTED", "changed_code": "a", "observed_verification": "x"},
                {"id": "AC-3", "status": "IMPLEMENTED", "changed_code": "b", "observed_verification": "y"},
            ]},
        ]}
        with self.assertRaises(ValueError):
            completion.json_delivered(notes)

    def test_self_contradictory_implemented_claim_is_normalized_not_trusted(self):
        # Live incident, issue 119: the final step claimed AC-6 was
        # IMPLEMENTED while its own evidence admitted "Full suite DRIVER
        # PENDING" -- a self-contradiction, not an independent second claim.
        # Three other, honest fragments had already deferred the same check.
        # The step's own stated evidence is authoritative over its stated
        # status, never the reverse: this must bring the row back in line
        # with the honest fragments (merge as INCOMPLETE/pending), not trust
        # the rosier status or raise an unresolvable self-conflict.
        notes = {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "fragments": [
            {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [
                {"id": "AC-6", "status": "INCOMPLETE", "changed_code": "scripts/from-issue.sh edited",
                 "observed_verification": "DRIVER PENDING: bash scripts/run-shell-tests.sh runs in the final step"},
            ]},
            {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [
                {"id": "AC-6", "status": "IMPLEMENTED", "changed_code": "No changes to other suites",
                 "observed_verification": "Full suite DRIVER PENDING; narrow worktree-run-test.sh passes 205 checks"},
            ]},
        ]}
        delivered = completion.json_delivered(notes)
        status, changed_code, observed = delivered["AC-6"]
        self.assertEqual(status, "INCOMPLETE")
        self.assertIn("DRIVER PENDING", observed)
        # Never silently dropped: the "IMPLEMENTED" claim's own evidence
        # still appears, just no longer taken as proof the check passed.
        self.assertIn("worktree-run-test.sh passes 205 checks", observed)
        # And the early, pre-verification check accepts the result exactly
        # like any other honest DRIVER PENDING row.
        required = {"AC-6": ["Existing shell suites still pass", "bash scripts/run-shell-tests.sh"]}
        self.assertEqual(completion.check_rows(required, delivered, allow_driver_pending=True), [])

    def test_conflicting_status_across_fragments_still_rejected(self):
        # One step claims the criterion is done, another says it is not --
        # a real disagreement neither side can resolve alone, unlike two
        # fragments that agree.
        notes = {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "fragments": [
            {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [
                {"id": "AC-3", "status": "IMPLEMENTED", "changed_code": "a", "observed_verification": "x"},
            ]},
            {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [
                {"id": "AC-3", "status": "INCOMPLETE", "changed_code": "b", "observed_verification": "y"},
            ]},
        ]}
        with self.assertRaises(ValueError):
            completion.json_delivered(notes)

    # ---- a later step finishing what an earlier one honestly reported as not done (issue 117) ----

    @staticmethod
    def fragment(*rows):
        return {"schema": "uncle.artifact/v1", "kind": "implementation-notes",
                "deliveries": [dict(zip(("id", "status", "changed_code", "observed_verification"), row)) for row in rows]}

    def notes(self, *fragments):
        return {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "fragments": list(fragments)}

    def test_a_later_implemented_supersedes_an_earlier_incomplete(self):
        merged = completion.json_delivered(self.notes(
            self.fragment(("AC-2", "INCOMPLETE", "bug_report.py: attribution", "TUI preview not yet built")),
            self.fragment(("AC-2", "IMPLEMENTED", "uncle_tui.py: preview", "test_preview_confirm_publishes_once: ok"))))
        status, changed, observed = merged["AC-2"]
        self.assertEqual(status, "IMPLEMENTED")
        self.assertEqual(changed, "bug_report.py: attribution; uncle_tui.py: preview", "what each step changed accumulates")
        self.assertEqual(observed, "test_preview_confirm_publishes_once: ok")
        self.assertNotIn("not yet built", observed, "the stale 'what is missing' evidence must not survive into an IMPLEMENTED row")

    def test_the_issue_117_shape_four_steps_two_criteria_passes_the_completion_check(self):
        # Steps 1 and 2 built the module and said the TUI half was not there yet; steps 3 and 4 built it.
        merged = completion.json_delivered(self.notes(
            self.fragment(("AC-2", "INCOMPLETE", "a", "TUI not built"), ("AC-4", "INCOMPLETE", "a", "TUI not built")),
            self.fragment(("AC-2", "INCOMPLETE", "b", "TUI not built"), ("AC-4", "INCOMPLETE", "b", "TUI not built")),
            self.fragment(("AC-2", "IMPLEMENTED", "c", "preview test: ok"), ("AC-4", "IMPLEMENTED", "c", "confirm test: ok")),
            self.fragment(("AC-2", "IMPLEMENTED", "d", "attribution test: ok"), ("AC-4", "IMPLEMENTED", "d", "tamper test: ok"))))
        for criterion in ("AC-2", "AC-4"):
            self.assertEqual(merged[criterion][0], "IMPLEMENTED", criterion)
            self.assertNotIn("not built", merged[criterion][2], criterion)
        required = {"AC-2": ["criterion", "verification"], "AC-4": ["criterion", "verification"]}
        self.assertEqual(completion.check_rows(required, merged), [])

    def test_an_earlier_implemented_then_a_later_incomplete_is_still_a_conflict_at_any_position(self):
        for fragments in ([("IMPLEMENTED",), ("INCOMPLETE",)],
                          [("INCOMPLETE",), ("IMPLEMENTED",), ("INCOMPLETE",)]):        # superseded, then regressed
            notes = self.notes(*[self.fragment(("AC-1", status, "x", "y")) for (status,) in fragments])
            with self.assertRaises(ValueError, msg=str(fragments)):
                completion.json_delivered(notes)

    def test_an_incomplete_between_two_implemented_claims_is_settled_by_the_last_one(self):
        # Issue 117, AC-1: the test step reported "handler test pending step 3" between the module step's
        # and the TUI step's IMPLEMENTED claims. Parallel steps cannot see each other; only the last word counts.
        merged = completion.json_delivered(self.notes(
            self.fragment(("AC-1", "IMPLEMENTED", "module", "imports")),
            self.fragment(("AC-1", "INCOMPLETE", "tests", "handler test pending step 3")),
            self.fragment(("AC-1", "IMPLEMENTED", "tui", "smoke ok"))))
        self.assertEqual(merged["AC-1"][0], "IMPLEMENTED")
        self.assertEqual(merged["AC-1"][2], "smoke ok")
        self.assertEqual(completion.check_rows({"AC-1": ["c", "v"]}, merged), [])
        # ...but if the last word is itself pending, the row never settles and stays a conflict.
        with self.assertRaises(ValueError):
            completion.json_delivered(self.notes(
                self.fragment(("AC-1", "IMPLEMENTED", "module", "imports")),
                self.fragment(("AC-1", "INCOMPLETE", "tests", "x")),
                self.fragment(("AC-1", "IMPLEMENTED", "tui", "Full suite DRIVER PENDING"))))

    def test_supersession_only_ever_moves_toward_done_never_hides_a_pending_check(self):
        # A later step that claims IMPLEMENTED while its own evidence says the full suite is still pending is
        # demoted to INCOMPLETE before merging, so it supersedes nothing and the criterion stays incomplete.
        merged = completion.json_delivered(self.notes(
            self.fragment(("AC-1", "INCOMPLETE", "a", "TUI not built")),
            self.fragment(("AC-1", "IMPLEMENTED", "b", "Full suite DRIVER PENDING"))))
        self.assertEqual(merged["AC-1"][0], "INCOMPLETE")
        self.assertNotEqual(completion.check_rows({"AC-1": ["c", "v"]}, merged), [])

    def test_two_incomplete_fragments_stay_incomplete_and_fail_the_check(self):
        merged = completion.json_delivered(self.notes(
            self.fragment(("AC-1", "INCOMPLETE", "a", "not built")), self.fragment(("AC-1", "INCOMPLETE", "b", "still not built"))))
        self.assertEqual(merged["AC-1"][0], "INCOMPLETE")
        self.assertNotEqual(completion.check_rows({"AC-1": ["c", "v"]}, merged), [])

    def test_a_row_the_later_step_leaves_without_evidence_does_not_pass(self):
        merged = completion.json_delivered(self.notes(
            self.fragment(("AC-1", "INCOMPLETE", "a", "not built")), self.fragment(("AC-1", "IMPLEMENTED", "b", ""))))
        self.assertNotEqual(completion.check_rows({"AC-1": ["c", "v"]}, merged), [], "IMPLEMENTED still needs observed verification")

    def test_driver_pending_row_passes_only_when_explicitly_allowed(self):
        # Live incident, issue 119: a step correctly followed instructions
        # (prompts/change/implement.md) and recorded DRIVER PENDING for a
        # check it does not own -- the full regression suite the driver runs
        # later. The very first completion check (WAIT_IMPLEMENT_APPROVAL)
        # runs before that driver run has ever executed, so this row could
        # never pass it as written -- rejecting it sent the whole
        # implementation phase back to redo every step from scratch, every
        # cycle. allow_driver_pending lets that one early check accept it;
        # without the flag (every later, post-verification check) it still
        # fails, since by then driver verification should have resolved it.
        required = {"AC-7": ["Full suite passes", "bash scripts/run-shell-tests.sh"]}
        delivered = {"AC-7": ["INCOMPLETE", "none; full suite owned by driver",
                              "DRIVER PENDING: bash scripts/run-shell-tests.sh not run in this stage"]}
        self.assertEqual(completion.check_rows(required, delivered, allow_driver_pending=True), [])
        problems = completion.check_rows(required, delivered, allow_driver_pending=False)
        self.assertEqual(len(problems), 1)
        self.assertIn("AC-7", problems[0])

    def test_driver_pending_does_not_excuse_a_genuinely_missing_row(self):
        # The leniency is specifically for the DRIVER PENDING placeholder,
        # not a blanket pass on anything non-IMPLEMENTED at the early check.
        required = {"AC-7": ["Full suite passes", "bash scripts/run-shell-tests.sh"]}
        delivered = {"AC-7": ["INCOMPLETE", "", ""]}
        problems = completion.check_rows(required, delivered, allow_driver_pending=True)
        self.assertEqual(len(problems), 1)

    def test_lettered_sub_criterion_is_accepted_not_treated_as_malformed(self):
        # issue 97: CHANGE_SPEC.json regenerated with an "AC-4b" id every
        # ANALYZE cycle -- a reasonable sub-criterion convention, not a
        # malformed schema. Rejecting it as unevaluable sent the whole run
        # back through ANALYZE to rebuild baseline/spec/plan/review from
        # scratch, every cycle, with no way out.
        spec = {"schema": "uncle.artifact/v1", "kind": "change-spec",
                "acceptance_criteria": [
                    {"id": "AC-4", "criterion": "Base case", "verification": "UI check"},
                    {"id": "AC-4b", "criterion": "Related sub-case", "verification": "UI check"},
                ]}
        notes = {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "fragments": [
            {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [
                {"id": "AC-4", "status": "IMPLEMENTED", "changed_code": "ui.py", "observed_verification": "PASS"},
                {"id": "AC-4b", "status": "IMPLEMENTED", "changed_code": "ui.py", "observed_verification": "PASS"},
            ]}
        ]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec_path, notes_path = root / 'CHANGE_SPEC.json', root / 'IMPLEMENTATION_NOTES.json'
            spec_path.write_text(json.dumps(spec)); notes_path.write_text(json.dumps(notes))
            required, delivered = completion.canonical_rows(spec_path, notes_path)
        self.assertEqual(completion.check_rows(required, delivered), [])

    def test_nested_legacy_accumulator_is_flattened(self):
        leaf = {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "deliveries": [
            {"id": "AC-1", "status": "IMPLEMENTED", "changed_code": "ui.py", "observed_verification": "PASS"}
        ]}
        payload = {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "fragments": [
            {"schema": "uncle.artifact/v1", "kind": "implementation-notes", "fragments": [leaf]}
        ]}
        self.assertEqual(completion.json_delivered(payload)['AC-1'][0], 'IMPLEMENTED')


if __name__ == "__main__":
    unittest.main()

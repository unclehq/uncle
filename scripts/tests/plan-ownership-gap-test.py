import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('plan_ownership_gap', ROOT / 'scripts/lib/plan_ownership_gap.py')
gap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gap)


class PlanOwnershipGapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state_dir = self.root / '.uncle/workflow'
        (self.state_dir / 'documents').mkdir(parents=True)
        self.plan = self.root / 'UPDATED_PROJECT_PLAN.md'

    def write_plan(self, sequence):
        self.plan.write_text('# Plan\n\n## 12. Implementation order\n\n' + sequence + '\n')

    def write_protected(self, paths):
        payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan',
                   'protected_verification_paths': '\n'.join(paths)}
        (self.state_dir / 'documents/UPDATED_PROJECT_PLAN.json').write_text(json.dumps(payload))

    def test_unowned_new_file_is_a_gap(self):
        # calculator-local (2026-09-28): package.json was listed as a frozen
        # protected path, referenced throughout the plan's prose, but no step
        # in the Implementation order owned creating it -- only a Reconcile
        # step's `Owns: *`, whose own description said "no new behavior".
        self.write_plan(
            '1. Arithmetic core — Owns: `src/arithmetic.js`\n'
            '2. Reconcile — Owns: `*` — Depends on: 1\n'
        )
        self.write_protected(['src/arithmetic.js', 'package.json'])
        gaps = gap.unowned_protected_paths(self.plan, self.root, gap.load_protected_paths(self.plan, self.state_dir))
        self.assertEqual(gaps, ['package.json'])

    def test_explicitly_owned_path_is_not_a_gap(self):
        self.write_plan('1. Scaffold — Owns: `package.json`, `package-lock.json`\n')
        self.write_protected(['package.json', 'package-lock.json'])
        protected = gap.load_protected_paths(self.plan, self.state_dir)
        self.assertEqual(gap.unowned_protected_paths(self.plan, self.root, protected), [])

    def test_lockfile_of_an_owned_manifest_is_not_a_gap(self):
        self.write_plan('1. Scaffold — Owns: `package.json`\n')
        self.write_protected(['package.json', 'package-lock.json'])
        protected = gap.load_protected_paths(self.plan, self.state_dir)
        self.assertEqual(gap.unowned_protected_paths(self.plan, self.root, protected), [])

    def test_already_existing_file_is_not_a_gap_even_if_unowned(self):
        self.write_plan('1. Reconcile — Owns: `*`\n')
        (self.root / 'package.json').write_text('{}')
        self.write_protected(['package.json'])
        protected = gap.load_protected_paths(self.plan, self.state_dir)
        self.assertEqual(gap.unowned_protected_paths(self.plan, self.root, protected), [])

    def test_uncle_paths_are_never_flagged(self):
        self.write_plan('1. Reconcile — Owns: `*`\n')
        self.write_protected(['.uncle/docs/CHANGE_SPEC.md'])
        protected = gap.load_protected_paths(self.plan, self.state_dir)
        self.assertEqual(gap.unowned_protected_paths(self.plan, self.root, protected), [])

    def test_missing_canonical_json_yields_no_protected_paths(self):
        self.write_plan('1. Reconcile — Owns: `*`\n')
        self.assertEqual(gap.load_protected_paths(self.plan, self.state_dir), [])

    def test_main_exits_nonzero_and_prints_each_gap(self):
        self.write_plan('1. Reconcile — Owns: `*`\n')
        self.write_protected(['package.json', 'playwright.config.js'])
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = gap.main([str(self.plan), str(self.root), str(self.state_dir)])
        self.assertEqual(status, 1)
        self.assertEqual(set(out.getvalue().split()), {'package.json', 'playwright.config.js'})

    def test_main_exits_zero_when_nothing_is_unowned(self):
        self.write_plan('1. Scaffold — Owns: `package.json`\n')
        self.write_protected(['package.json'])
        status = gap.main([str(self.plan), str(self.root), str(self.state_dir)])
        self.assertEqual(status, 0)

    # noinit: the plan froze the directory `tests/` and assigned every file under it to steps 5-8.  The check asked
    # whether an owned file covers the directory, which it never does, so three triage rounds chased a plan that
    # was right.
    def gaps_for(self, protected):
        self.write_protected(protected)
        return gap.unowned_protected_paths(self.plan, self.root, gap.load_protected_paths(self.plan, self.state_dir))

    def test_a_protected_directory_is_owned_when_steps_own_files_inside_it(self):
        self.write_plan(
            '1. Scaffold — Owns: `package.json`, `vitest.config.js`\n'
            '5. Unit tests — Owns: `tests/unit/calc.test.js`, `tests/unit/keymap.test.js`\n'
            '7. Browser tests — Owns: `tests/e2e/theme.spec.js`\n'
        )
        self.assertEqual(self.gaps_for(['tests/', 'vitest.config.js']), [])
        # A bare name with no slash that is not on disk cannot be told from a file called `tests`: still reported.
        self.assertEqual(self.gaps_for(['tests']), ['tests'])

    def test_a_protected_directory_with_nothing_owned_inside_it_is_still_a_gap(self):
        self.write_plan('1. Core — Owns: `src/calc.js`\n')
        self.assertEqual(self.gaps_for(['tests/']), ['tests/'])

    def test_files_owned_in_a_different_directory_do_not_satisfy_it(self):
        self.write_plan('1. Core — Owns: `src/tests/calc.test.js`, `testsupport/x.js`\n')
        self.assertEqual(self.gaps_for(['tests/']), ['tests/'])

    def test_a_wildcard_owner_still_does_not_count_for_a_directory(self):
        self.write_plan('1. Core — Owns: `src/calc.js`\n2. Reconcile — Owns: `*` — Depends on: 1\n')
        self.assertEqual(self.gaps_for(['tests/']), ['tests/'])

    def test_a_glob_owned_under_the_directory_counts(self):
        self.write_plan('1. Tests — Owns: `tests/unit/*.test.js`\n')
        self.assertEqual(self.gaps_for(['tests/']), [])

    def test_only_the_unowned_entries_of_a_mixed_list_are_reported(self):
        self.write_plan('1. Tests — Owns: `tests/unit/calc.test.js`, `vitest.config.js`\n')
        self.assertEqual(self.gaps_for(['tests/', 'vitest.config.js', 'playwright.config.js', 'scripts/']),
                         ['playwright.config.js', 'scripts/'])

    def test_an_existing_directory_is_not_a_gap(self):
        (self.root / 'tests').mkdir()
        self.write_plan('1. Core — Owns: `src/calc.js`\n')
        self.assertEqual(self.gaps_for(['tests/']), [])


if __name__ == '__main__':
    unittest.main()

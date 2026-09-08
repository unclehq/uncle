#!/usr/bin/env bash
# The checklist's parallel-execution plan, derived from the reviewer's per-check
# declarations.
#
# The property under test is not "it finds parallelism". It is that it never
# claims two checks are safe to overlap unless the reviewer said so: a missing
# declaration, a bad declaration, or a dependency edge all have to end in less
# concurrency, never more.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export UNCLE_TEST_ROOT="$ROOT"

if ! command -v python3 > /dev/null 2>&1; then
    echo "checklist-groups-test.sh: skipped, python3 is not available"
    exit 0
fi

python3 -B - <<'PY'
import os, subprocess, sys, tempfile, textwrap, unittest

ROOT = os.environ['UNCLE_TEST_ROOT']
SCRIPT = ROOT + '/scripts/lib/checklist_groups.py'


class Groups(unittest.TestCase):
    def derive(self, body, name='MANUAL_CHECKLIST.md'):
        """Run the deriver over a checklist and return (groups, readme, exit)."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, name)
        with open(path, 'w') as fh:
            fh.write(textwrap.dedent(body))
        out = os.path.join(tmp.name, 'out')
        r = subprocess.run([sys.executable, '-B', SCRIPT, '--checklist', path,
                            '--out-dir', out], capture_output=True, text=True,
                           timeout=30)
        groups_file = os.path.join(out, 'groups.txt')
        groups = []
        if os.path.exists(groups_file):
            with open(groups_file) as fh:
                groups = [l.split() for l in fh.read().splitlines() if l.strip()]
        with open(os.path.join(out, 'README.md')) as fh:
            readme = fh.read()
        return groups, readme, r.returncode

    def check(self, cid, resources, depends='none', extra=''):
        return ('\n### %s\n- Priority: Critical\n- Exclusive resources: %s\n'
                '- Depends on: %s\n- Exact action: run it\n%s'
                % (cid, resources, depends, extra))

    # --- the conservative direction -----------------------------------------

    def test_a_checklist_without_declarations_runs_serially(self):
        # Every checklist written before these fields existed. Nothing here
        # says two checks may overlap, so nothing may overlap.
        body = ''.join('\n### MC-00%d\n- Priority: Critical\n- Exact action: run it\n' % i
                       for i in (1, 2, 3))
        groups, readme, code = self.derive(body)
        self.assertEqual(code, 0)
        self.assertEqual(groups, [['MC-001'], ['MC-002'], ['MC-003']])
        self.assertIn('scheduled alone', readme)

    def test_one_undeclared_check_does_not_ride_along(self):
        # Two safe checks and one that never said what it touches. The unknown
        # one gets a group to itself rather than joining either.
        body = (self.check('MC-001', 'none') +
                '\n### MC-002\n- Priority: Critical\n- Exact action: run it\n' +
                self.check('MC-003', 'none'))
        groups, readme, code = self.derive(body)
        self.assertEqual(code, 0)
        self.assertEqual(groups, [['MC-001'], ['MC-002'], ['MC-003']])

    def test_an_unknown_dependency_falls_back_to_serial(self):
        body = self.check('MC-001', 'none') + self.check('MC-002', 'none', 'MC-099')
        groups, readme, code = self.derive(body)
        self.assertEqual(code, 2)
        self.assertEqual(groups, [])
        self.assertIn('NOT DECLARED', readme)
        self.assertIn('MC-099', readme)
        self.assertIn('one at a time', readme)

    def test_a_dependency_cycle_falls_back_to_serial(self):
        body = (self.check('MC-001', 'none', 'MC-002') +
                self.check('MC-002', 'none', 'MC-001'))
        groups, readme, code = self.derive(body)
        self.assertEqual(code, 2)
        self.assertEqual(groups, [])
        self.assertIn('cycle', readme)

    def test_a_check_that_depends_on_itself_is_rejected(self):
        groups, readme, code = self.derive(self.check('MC-001', 'none', 'MC-001'))
        self.assertEqual(code, 2)
        self.assertIn('itself', readme)

    def test_a_missing_checklist_declares_nothing(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = os.path.join(tmp.name, 'out')
        r = subprocess.run([sys.executable, '-B', SCRIPT,
                            '--checklist', os.path.join(tmp.name, 'absent.md'),
                            '--out-dir', out], capture_output=True, text=True,
                           timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(out, 'groups.txt')))
        with open(os.path.join(out, 'README.md')) as fh:
            self.assertIn('NOT DECLARED', fh.read())

    def test_stale_groups_are_removed_rather_than_left_behind(self):
        # A previous checklist's grouping read as current would overlap checks
        # nobody cleared. The file has to disappear, not persist.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = os.path.join(tmp.name, 'out')
        os.makedirs(out)
        with open(os.path.join(out, 'groups.txt'), 'w') as fh:
            fh.write('MC-900 MC-901\n')
        path = os.path.join(tmp.name, 'MANUAL_CHECKLIST.md')
        with open(path, 'w') as fh:
            fh.write(self.check('MC-001', 'none', 'MC-099'))
        subprocess.run([sys.executable, '-B', SCRIPT, '--checklist', path,
                        '--out-dir', out], capture_output=True, text=True, timeout=30)
        self.assertFalse(os.path.exists(os.path.join(out, 'groups.txt')))

    # --- the useful direction ------------------------------------------------

    def test_checks_with_no_shared_resource_overlap(self):
        body = ''.join(self.check('MC-00%d' % i, 'none') for i in (1, 2, 3))
        groups, _, code = self.derive(body)
        self.assertEqual(code, 0)
        self.assertEqual(groups, [['MC-001', 'MC-002', 'MC-003']])

    def test_a_shared_resource_splits_a_group(self):
        body = (self.check('MC-001', 'port:5173') +
                self.check('MC-002', 'port:5173') +
                self.check('MC-003', 'port:8080'))
        groups, _, code = self.derive(body)
        self.assertEqual(code, 0)
        # MC-003 holds a different port and no dependency, so it joins the
        # first group; MC-002, which wants MC-001's port, waits for the next.
        self.assertEqual(groups, [['MC-001', 'MC-003'], ['MC-002']])

    def test_resource_tokens_are_matched_case_insensitively(self):
        body = (self.check('MC-001', 'Port:5173, Browser') +
                self.check('MC-002', 'browser'))
        groups, _, _ = self.derive(body)
        self.assertEqual(groups, [['MC-001'], ['MC-002']])

    def test_a_dependency_lands_in_a_later_group(self):
        body = (self.check('MC-001', 'none') +
                self.check('MC-002', 'none', 'MC-001') +
                self.check('MC-003', 'none', 'MC-002'))
        groups, _, _ = self.derive(body)
        self.assertEqual(groups, [['MC-001'], ['MC-002'], ['MC-003']])

    def test_a_forward_dependency_defers_the_dependent_check(self):
        # A reviewer who writes `Depends on: MC-002` on a check sitting above
        # MC-002 is naming a fact the section ordering could not express. It is
        # the more reliable of the two signals, so the check waits.
        body = (self.check('MC-001', 'none', 'MC-002') +
                self.check('MC-002', 'none'))
        groups, _, code = self.derive(body)
        self.assertEqual(code, 0)
        self.assertEqual(groups, [['MC-002'], ['MC-001']])

    def test_a_shared_resource_keeps_checks_in_document_order(self):
        body = (self.check('MC-001', 'db') + self.check('MC-002', 'db') +
                self.check('MC-003', 'db'))
        groups, _, _ = self.derive(body)
        self.assertEqual(groups, [['MC-001'], ['MC-002'], ['MC-003']])

    def test_nothing_is_deferred_across_an_undeclared_check(self):
        # MC-001 needs MC-003, but MC-002 never said what it touches. Pulling
        # MC-003 forward would reorder it around the one check whose needs are
        # unknown, which is precisely the reordering that is not allowed.
        body = (self.check('MC-001', 'none', 'MC-003') +
                '\n### MC-002\n- Priority: Critical\n- Exact action: run it\n' +
                self.check('MC-003', 'none'))
        groups, readme, code = self.derive(body)
        self.assertEqual(code, 2)
        self.assertEqual(groups, [])
        self.assertIn('Exclusive resources', readme)

    # --- the layout a dense checklist actually uses --------------------------

    def test_a_table_checklist_parses(self):
        # What the reviewer prompt's "keep it dense" instruction produces: one
        # row per check, with the two declarations as abbreviated columns.
        body = """
        | ID | Pri | Prereq | Excl | Deps | Action | Status |
        |---|---|---|---|---|---|---|
        | MC-1 | P0 | clean checkout | port:8000, chrome-user-profile | none | serve and load | NOT RUN |
        | MC-2 | P0 | MC-1 | port:8000, chrome-user-profile | MC-1 | follow the footer link | NOT RUN |
        | MC-3 | P1 | none | none | none | read the README | NOT RUN |
        """
        groups, _, code = self.derive(body)
        self.assertEqual(code, 0)
        self.assertEqual(groups, [['MC-1', 'MC-3'], ['MC-2']])

    def test_a_table_traceability_matrix_is_not_read_as_checks(self):
        # The matrix has an ID column full of check IDs and no declarations.
        # Read through the previous table's columns it would invent checks, and
        # a grouping that lists rows nobody wrote is worse than no grouping.
        body = """
        | ID | Excl | Deps | Action |
        |---|---|---|---|
        | MC-1 | none | none | run it |
        | MC-2 | none | none | run it |

        ## Traceability

        | Check | Requirement | Behavior |
        |---|---|---|
        | MC-1 | R-1 | B-1 |
        | MC-9 | R-9 | B-9 |
        """
        groups, _, code = self.derive(body)
        self.assertEqual(code, 0)
        self.assertEqual(groups, [['MC-1', 'MC-2']])

    def test_a_table_row_without_declarations_is_scheduled_alone(self):
        body = """
        | ID | Excl | Deps |
        |---|---|---|
        | MC-1 | none | none |
        | MC-2 |  |  |
        | MC-3 | none | none |
        """
        # An empty Excl cell is a declaration of nothing shared, not a missing
        # declaration: the reviewer filled the row in. It reads as `none`.
        groups, _, code = self.derive(body)
        self.assertEqual(code, 0)
        self.assertEqual(groups, [['MC-1', 'MC-2', 'MC-3']])

    def test_the_full_column_spellings_work_too(self):
        body = """
        | Check ID | Exclusive resources | Depends on |
        |---|---|---|
        | MC-1 | browser | none |
        | MC-2 | browser | MC-1 |
        """
        groups, _, code = self.derive(body)
        self.assertEqual(code, 0)
        self.assertEqual(groups, [['MC-1'], ['MC-2']])

    def test_every_check_appears_exactly_once(self):
        body = ''.join(self.check('MC-%03d' % i, 'none' if i % 2 else 'db')
                       for i in range(1, 12))
        groups, _, _ = self.derive(body)
        flat = [cid for g in groups for cid in g]
        self.assertEqual(sorted(flat), sorted(set(flat)))
        self.assertEqual(len(flat), 11)

    # --- reading what reviewers actually write -------------------------------

    def test_the_check_id_field_layout_parses(self):
        body = '''
        - Check ID: MC-001
        - Exclusive resources: none
        - Depends on: none

        - Check ID: MC-002
        - Exclusive resources: none
        - Depends on: MC-001
        '''
        groups, _, _ = self.derive(body)
        self.assertEqual(groups, [['MC-001'], ['MC-002']])

    def test_bold_fields_parse(self):
        body = ('\n### MC-001\n- **Exclusive resources:** none\n- **Depends on:** none\n'
                '\n### MC-002\n- **Exclusive resources:** none\n- **Depends on:** MC-001\n')
        groups, _, _ = self.derive(body)
        self.assertEqual(groups, [['MC-001'], ['MC-002']])

    def test_a_traceability_matrix_does_not_invent_checks(self):
        # The matrix at the end of every checklist is full of ID tokens. A bare
        # token is not a check, or the grouping would list rows that do not exist.
        body = (self.check('MC-001', 'none') + self.check('MC-002', 'none') +
                '\n## Traceability\n\n| Check | Requirement |\n|---|---|\n'
                '| MC-001 | R-1 |\n| MC-002 | R-2 |\n| MC-404 | R-3 |\n')
        groups, _, code = self.derive(body)
        self.assertEqual(code, 0)
        self.assertEqual(groups, [['MC-001', 'MC-002']])

    def test_none_is_spelled_several_ways(self):
        for word in ('none', 'None', 'N/A', '-', 'none.'):
            body = (self.check('MC-001', word) + self.check('MC-002', word))
            groups, _, _ = self.derive(body)
            self.assertEqual(groups, [['MC-001', 'MC-002']],
                             'resources spelled %r' % word)

    def test_a_prefix_other_than_mc_works(self):
        body = ('\n### CHK-1\n- Exclusive resources: none\n- Depends on: none\n'
                '\n### CHK-2\n- Exclusive resources: none\n- Depends on: CHK-1\n')
        groups, _, _ = self.derive(body)
        self.assertEqual(groups, [['CHK-1'], ['CHK-2']])

    def test_the_readme_tells_the_agent_the_barrier_rule(self):
        groups, readme, _ = self.derive(
            self.check('MC-001', 'none') + self.check('MC-002', 'port:1'))
        self.assertIn('before starting the next', readme)
        self.assertIn('permission, not obligation', readme)
        self.assertIn('```', readme)


res = unittest.TextTestRunner(verbosity=0).run(
    unittest.TestLoader().loadTestsFromTestCase(Groups))
if not res.wasSuccessful():
    raise SystemExit(1)
print('checklist-groups-test.sh: %d checks passed' % res.testsRun)
PY

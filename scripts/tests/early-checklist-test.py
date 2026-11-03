"""Early checklist rows: identity, failures, what the real stage may reuse, and how results merge.

The rule that matters: a result is reused only for the same row, against the same application files, and only a PASS. Everything else runs
again, so a wrong guess here costs time and never a missed failure."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import early_checklist as ec  # noqa: E402


def row(identifier, action='open the page', expected='it loads', resources=()):
    return {'id': identifier, 'exact_action': action, 'expected_result': expected, 'exclusive_resources': list(resources)}


def checklist(*rows):
    return {'schema': 'uncle.artifact/v1', 'kind': 'manual-checklist', 'checks': list(rows)}


def result(identifier, status='PASS', source='group-1-batch-1', action='a', expected='e'):
    return {'id': identifier, 'status': status, 'action': action, 'expected_result': expected, 'actual_result': 'did it',
            'evidence': 'shot.png', 'defect_reference': '', 'source': source}


def workers(*results, kind='checklist-execution-worker-packets'):
    return {'schema': 'uncle.artifact/v1', 'kind': kind, 'workers': [{'source': 'group-1-batch-1', 'status': 'ok', 'result_count': len(results)}],
            'results': list(results)}


class RowKey(unittest.TestCase):
    def test_the_same_row_has_the_same_key(self):
        self.assertEqual(ec.row_key(row('MC-1')), ec.row_key(row('MC-1')))

    def test_the_id_is_not_part_of_the_key(self):
        self.assertEqual(ec.row_key(row('MC-1')), ec.row_key(row('MC-9')))

    def test_a_changed_action_expected_result_or_resource_changes_it(self):
        base = ec.row_key(row('MC-1'))
        self.assertNotEqual(base, ec.row_key(row('MC-1', action='open another page')))
        self.assertNotEqual(base, ec.row_key(row('MC-1', expected='it loads fast')))
        self.assertNotEqual(base, ec.row_key(row('MC-1', resources=['port 5173'])))

    def test_surrounding_whitespace_and_resource_order_do_not(self):
        self.assertEqual(ec.row_key(row('a', action='x ', resources=['b', 'a'])), ec.row_key(row('b', action=' x', resources=['a', 'b'])))


class Slice(unittest.TestCase):
    def test_keeps_only_the_named_rows_in_their_original_order(self):
        doc = checklist(row('MC-1'), row('MC-2'), row('MC-3'))
        self.assertEqual([r['id'] for r in ec.slice_document(doc, ['MC-3', 'MC-1'])['checks']], ['MC-1', 'MC-3'])

    def test_no_ids_keeps_everything(self):
        self.assertEqual(len(ec.slice_document(checklist(row('MC-1'), row('MC-2')))['checks']), 2)

    def test_the_rest_of_the_document_is_kept(self):
        self.assertEqual(ec.slice_document(checklist(row('MC-1')), ['MC-1'])['kind'], 'manual-checklist')

    def test_an_unknown_id_is_ignored(self):
        self.assertEqual(ec.slice_document(checklist(row('MC-1')), ['MC-1', 'MC-404'])['checks'], [row('MC-1')])


class Failures(unittest.TestCase):
    def test_only_fail_rows_are_returned_with_their_evidence(self):
        found = ec.failures(workers(result('MC-1'), result('MC-2', 'FAIL'), result('MC-3', 'BLOCKED-HUMAN'), result('MC-4', 'NOT RUN')))
        self.assertEqual([f['id'] for f in found], ['MC-2'])
        self.assertEqual(found[0]['evidence'], 'shot.png')
        self.assertEqual(found[0]['actual_result'], 'did it')

    def test_none_failed_is_empty(self):
        self.assertEqual(ec.failures(workers(result('MC-1'))), [])
        self.assertEqual(ec.failures(None), [])


class Plan(unittest.TestCase):
    def setUp(self):
        self.early = checklist(row('MC-1'), row('MC-2', action='click'), row('MC-3', action='type'))
        self.early_workers = workers(result('MC-1'), result('MC-2'), result('MC-3', 'FAIL'))
        self.manifest = ec.manifest(self.early, self.early_workers, 'fp-A')

    def test_identical_rows_on_an_identical_application_are_reused(self):
        reused, reduced = ec.plan(self.early, self.manifest, self.early_workers, 'fp-A')
        self.assertEqual(sorted(reused), ['MC-1', 'MC-2'])
        self.assertEqual([r['id'] for r in reduced['checks']], ['MC-3'])

    def test_a_failed_early_row_is_never_reused(self):
        reused, reduced = ec.plan(self.early, self.manifest, self.early_workers, 'fp-A')
        self.assertNotIn('MC-3', reused)
        self.assertIn('MC-3', [r['id'] for r in reduced['checks']])

    def test_a_changed_application_reuses_nothing(self):
        reused, reduced = ec.plan(self.early, self.manifest, self.early_workers, 'fp-B')
        self.assertEqual(reused, {})
        self.assertEqual(len(reduced['checks']), 3)

    def test_a_missing_fingerprint_reuses_nothing(self):
        self.assertEqual(ec.plan(self.early, self.manifest, self.early_workers, '')[0], {})

    def test_no_manifest_reuses_nothing(self):
        self.assertEqual(ec.plan(self.early, None, self.early_workers, 'fp-A')[0], {})

    def test_a_row_the_reconciliation_changed_runs_again(self):
        final = checklist(row('MC-1'), row('MC-2', action='click the other button'), row('MC-3', action='type'))
        reused, reduced = ec.plan(final, self.manifest, self.early_workers, 'fp-A')
        self.assertEqual(sorted(reused), ['MC-1'])
        self.assertEqual([r['id'] for r in reduced['checks']], ['MC-2', 'MC-3'])

    def test_a_row_the_reconciliation_added_runs(self):
        final = checklist(row('MC-1'), row('MC-2', action='click'), row('MC-3', action='type'), row('MC-4', action='new'))
        _, reduced = ec.plan(final, self.manifest, self.early_workers, 'fp-A')
        self.assertIn('MC-4', [r['id'] for r in reduced['checks']])

    def test_a_row_the_reconciliation_dropped_is_not_carried_over(self):
        final = checklist(row('MC-1'))
        reused, reduced = ec.plan(final, self.manifest, self.early_workers, 'fp-A')
        self.assertEqual(sorted(reused), ['MC-1'])
        self.assertEqual(reduced['checks'], [])

    def test_a_row_whose_id_was_reused_for_different_work_runs_again(self):
        final = checklist(row('MC-1', action='something else entirely'))
        reused, _ = ec.plan(final, self.manifest, self.early_workers, 'fp-A')
        self.assertEqual(reused, {})

    def test_a_pass_missing_from_the_manifest_is_not_trusted_even_if_the_results_say_pass(self):
        manifest = dict(self.manifest, passed=['MC-1'])
        reused, _ = ec.plan(self.early, manifest, self.early_workers, 'fp-A')
        self.assertEqual(sorted(reused), ['MC-1'])


class BlockedRows(unittest.TestCase):
    """Run 24: a row for a person to judge ended BLOCKED-HUMAN in the early run, and the real stage spent a worker (17 s) finding that out again."""

    def setUp(self):
        self.early = checklist(row('MC-1'), row('MC-2', action='look'), row('MC-3', action='setup'), row('MC-4', action='fail'))
        self.workers = workers(result('MC-1'), result('MC-2', 'BLOCKED-HUMAN'), result('MC-3', 'BLOCKED-SETUP'), result('MC-4', 'FAIL'))
        self.manifest = ec.manifest(self.early, self.workers, 'fp-A')

    def test_a_row_for_a_person_is_reused_as_it_was(self):
        reused, reduced = ec.plan(self.early, self.manifest, self.workers, 'fp-A')
        self.assertEqual(reused['MC-2']['status'], 'BLOCKED-HUMAN')
        self.assertNotIn('MC-2', [r['id'] for r in reduced['checks']])

    def test_it_stays_blocked_it_is_never_turned_into_a_pass(self):
        reused, _ = ec.plan(self.early, self.manifest, self.workers, 'fp-A')
        self.assertNotEqual(reused['MC-2']['status'], 'PASS')
        merged = ec.merge(self.early, reused, None)
        self.assertEqual({r['id']: r['status'] for r in merged['results']}['MC-2'], 'BLOCKED-HUMAN')

    def test_a_setup_blocked_row_and_a_failed_row_run_again(self):
        reused, reduced = ec.plan(self.early, self.manifest, self.workers, 'fp-A')
        self.assertNotIn('MC-3', reused)
        self.assertNotIn('MC-4', reused)
        self.assertEqual([r['id'] for r in reduced['checks']], ['MC-3', 'MC-4'])

    def test_a_changed_application_runs_it_again(self):
        reused, reduced = ec.plan(self.early, self.manifest, self.workers, 'fp-B')
        self.assertEqual(reused, {})
        self.assertEqual(len(reduced['checks']), 4)

    def test_a_changed_row_runs_again(self):
        final = checklist(row('MC-1'), row('MC-2', action='look at something else'))
        reused, _ = ec.plan(final, self.manifest, self.workers, 'fp-A')
        self.assertEqual(sorted(reused), ['MC-1'])

    def test_a_blocked_result_the_manifest_does_not_name_is_not_trusted(self):
        manifest = dict(self.manifest, blocked_human=[])
        reused, _ = ec.plan(self.early, manifest, self.workers, 'fp-A')
        self.assertNotIn('MC-2', reused)

    def test_a_result_whose_status_was_edited_to_blocked_after_a_pass_is_not_trusted(self):
        edited = workers(result('MC-1', 'BLOCKED-HUMAN'), result('MC-2', 'BLOCKED-HUMAN'))
        reused, _ = ec.plan(checklist(row('MC-1'), row('MC-2', action='look')), self.manifest, edited, 'fp-A')
        self.assertNotIn('MC-1', reused)

    def test_a_row_the_manifest_lists_as_for_a_person_is_not_reused_if_its_result_says_setup(self):
        edited = workers(result('MC-1'), result('MC-2', 'BLOCKED-SETUP'))
        reused, _ = ec.plan(checklist(row('MC-1'), row('MC-2', action='look')), self.manifest, edited, 'fp-A')
        self.assertNotIn('MC-2', reused)

    def test_the_manifest_lists_them_apart_from_the_passes(self):
        self.assertEqual(self.manifest['passed'], ['MC-1'])
        self.assertEqual(self.manifest['blocked_human'], ['MC-2'])


class ChangedAndExclude(unittest.TestCase):
    """Run 27: the reconciliation reworded one row, which then ran for 99 s after a 45 s wait for the early rows. Which rows changed is known the
    moment the reconciled checklist exists."""

    def setUp(self):
        self.draft = checklist(row('MC-1'), row('MC-2', action='click'), row('MC-3', action='type'))

    def test_a_reworded_row_is_changed(self):
        final = checklist(row('MC-1'), row('MC-2', action='click the other button'), row('MC-3', action='type'))
        self.assertEqual([r['id'] for r in ec.changed(self.draft, final)['checks']], ['MC-2'])

    def test_an_added_row_is_changed(self):
        final = checklist(row('MC-1'), row('MC-2', action='click'), row('MC-3', action='type'), row('MC-901', action='new'))
        self.assertEqual([r['id'] for r in ec.changed(self.draft, final)['checks']], ['MC-901'])

    def test_an_identical_checklist_changes_nothing(self):
        self.assertEqual(ec.changed(self.draft, self.draft)['checks'], [])

    def test_a_dropped_row_is_not_a_changed_row(self):
        self.assertEqual(ec.changed(self.draft, checklist(row('MC-1')))['checks'], [])

    def test_a_changed_expected_result_or_resource_counts(self):
        final = checklist(row('MC-1', expected='different'), row('MC-2', action='click', resources=['port']), row('MC-3', action='type'))
        self.assertEqual([r['id'] for r in ec.changed(self.draft, final)['checks']], ['MC-1', 'MC-2'])

    def test_an_id_reused_for_different_work_is_changed(self):
        final = checklist(row('MC-1', action='something else entirely'), row('MC-2', action='click'), row('MC-3', action='type'))
        self.assertEqual([r['id'] for r in ec.changed(self.draft, final)['checks']], ['MC-1'])

    def test_exclude_removes_the_rows_that_already_have_results(self):
        reduced = checklist(row('MC-2'), row('MC-3'), row('MC-4'))
        done = workers(result('MC-2'), result('MC-4', 'FAIL'))
        self.assertEqual([r['id'] for r in ec.exclude(reduced, done)['checks']], ['MC-3'])

    def test_exclude_with_no_results_keeps_everything(self):
        reduced = checklist(row('MC-2'), row('MC-3'))
        self.assertEqual(len(ec.exclude(reduced, workers())['checks']), 2)
        self.assertEqual(len(ec.exclude(reduced, None)['checks']), 2)

    def test_the_rest_of_the_document_is_kept_by_both(self):
        final = dict(checklist(row('MC-9', action='n')), extra='kept')
        self.assertEqual(ec.changed(self.draft, final)['extra'], 'kept')
        self.assertEqual(ec.exclude(final, workers())['extra'], 'kept')

    def test_the_command_line_exits_three_when_nothing_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'd.json').write_text(json.dumps(self.draft))
            run = lambda *a: subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/lib/early_checklist.py'), *a], capture_output=True, text=True)
            self.assertEqual(run('changed', str(root / 'd.json'), str(root / 'd.json'), str(root / 'o.json')).returncode, 3)
            final = checklist(row('MC-1'), row('MC-2', action='reworded'), row('MC-3', action='type'))
            (root / 'f.json').write_text(json.dumps(final))
            done = run('changed', str(root / 'd.json'), str(root / 'f.json'), str(root / 'o.json'))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual([r['id'] for r in json.loads((root / 'o.json').read_text())['checks']], ['MC-2'])
            (root / 'w.json').write_text(json.dumps(workers(result('MC-2'))))
            self.assertEqual(run('exclude', str(root / 'o.json'), str(root / 'w.json'), str(root / 'x.json')).returncode, 0)
            self.assertEqual(json.loads((root / 'x.json').read_text())['checks'], [])


class Merge(unittest.TestCase):
    def test_reused_and_fresh_results_come_together_in_id_order(self):
        final = checklist(row('MC-1'), row('MC-2'), row('MC-3'))
        merged = ec.merge(final, {'MC-1': result('MC-1'), 'MC-3': result('MC-3')}, workers(result('MC-2', source='group-1-batch-1')))
        self.assertEqual([r['id'] for r in merged['results']], ['MC-1', 'MC-2', 'MC-3'])

    def test_reused_rows_are_marked_as_early(self):
        merged = ec.merge(checklist(row('MC-1')), {'MC-1': result('MC-1')}, None)
        self.assertEqual(merged['results'][0]['source'], 'early-checklist')
        self.assertIn({'source': 'early-checklist', 'status': 'ok', 'result_count': 1}, merged['workers'])

    def test_a_fresh_result_wins_over_a_reused_one(self):
        merged = ec.merge(checklist(row('MC-1')), {'MC-1': result('MC-1', 'PASS')}, workers(result('MC-1', 'FAIL')))
        self.assertEqual(merged['results'][0]['status'], 'FAIL')
        self.assertNotEqual(merged['results'][0]['source'], 'early-checklist')

    def test_nothing_reused_and_nothing_fresh_is_empty(self):
        self.assertEqual(ec.merge(checklist(row('MC-1')), {}, None)['results'], [])

    def test_a_result_for_a_row_no_longer_in_the_checklist_is_dropped(self):
        merged = ec.merge(checklist(row('MC-1')), {'MC-1': result('MC-1'), 'MC-9': result('MC-9')}, None)
        self.assertEqual([r['id'] for r in merged['results']], ['MC-1'])

    def test_the_merged_document_has_the_kind_the_collator_writes(self):
        self.assertEqual(ec.merge(checklist(row('MC-1')), {'MC-1': result('MC-1')}, None)['kind'], 'checklist-execution-worker-packets')

    def test_merge_early_lets_a_rerun_replace_the_earlier_result(self):
        old = workers(result('MC-1', 'FAIL'), result('MC-2'))
        new = workers(result('MC-1', 'PASS'), kind='checklist-execution-worker-packets')
        merged = ec.merge_early(old, new)
        self.assertEqual({r['id']: r['status'] for r in merged['results']}, {'MC-1': 'PASS', 'MC-2': 'PASS'})


class Command(unittest.TestCase):
    """The shell calls these, so the command line is tested as the shell uses it."""

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/lib/early_checklist.py'), *map(str, args)], capture_output=True, text=True)

    def write(self, folder, name, value):
        path = Path(folder) / name
        path.write_text(json.dumps(value))
        return path

    def test_manifest_then_plan_reuses_the_passes(self):
        folder = tempfile.mkdtemp()
        early = self.write(folder, 'early.json', checklist(row('MC-1'), row('MC-2', action='x')))
        early_workers = self.write(folder, 'ew.json', workers(result('MC-1'), result('MC-2', 'FAIL')))
        manifest = Path(folder) / 'manifest.json'
        self.assertEqual(self.run_cli('manifest', early, early_workers, 'fp1', manifest).returncode, 0)
        reused, reduced = Path(folder) / 'reused.json', Path(folder) / 'reduced.json'
        done = self.run_cli('plan', early, manifest, early_workers, 'fp1', reused, reduced)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('reusing 1 of 2', done.stdout)
        self.assertEqual(sorted(json.loads(reused.read_text())), ['MC-1'])
        self.assertEqual([r['id'] for r in json.loads(reduced.read_text())['checks']], ['MC-2'])

    def test_plan_exits_three_when_nothing_is_reusable(self):
        folder = tempfile.mkdtemp()
        early = self.write(folder, 'early.json', checklist(row('MC-1')))
        early_workers = self.write(folder, 'ew.json', workers(result('MC-1')))
        manifest = Path(folder) / 'manifest.json'
        self.run_cli('manifest', early, early_workers, 'fp1', manifest)
        done = self.run_cli('plan', early, manifest, early_workers, 'fp2', Path(folder) / 'r.json', Path(folder) / 'd.json')
        self.assertEqual(done.returncode, 3)

    def test_failures_prints_nothing_when_nothing_failed(self):
        folder = tempfile.mkdtemp()
        done = self.run_cli('failures', self.write(folder, 'w.json', workers(result('MC-1'))))
        self.assertEqual((done.returncode, done.stdout), (0, ''))

    def test_failures_prints_a_json_list(self):
        folder = tempfile.mkdtemp()
        done = self.run_cli('failures', self.write(folder, 'w.json', workers(result('MC-1', 'FAIL'))))
        self.assertEqual([f['id'] for f in json.loads(done.stdout)], ['MC-1'])

    def test_slice_and_merge_round_trip_through_files(self):
        folder = tempfile.mkdtemp()
        final = self.write(folder, 'final.json', checklist(row('MC-1'), row('MC-2')))
        reused = self.write(folder, 'reused.json', {'MC-1': result('MC-1')})
        out = Path(folder) / 'out.json'
        self.assertEqual(self.run_cli('merge', final, reused, '-', out).returncode, 0)
        self.assertEqual([r['id'] for r in json.loads(out.read_text())['results']], ['MC-1'])
        sliced = Path(folder) / 's.json'
        self.run_cli('slice', final, sliced, 'MC-2')
        self.assertEqual([r['id'] for r in json.loads(sliced.read_text())['checks']], ['MC-2'])

    def test_a_bad_command_line_is_a_usage_error_not_a_crash(self):
        self.assertNotEqual(self.run_cli('plan', 'only-one-argument').returncode, 0)


if __name__ == '__main__':
    unittest.main()

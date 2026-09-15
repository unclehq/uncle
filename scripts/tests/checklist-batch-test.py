import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from checklist_batch import run, report_draft
from checklist_groups import parse


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checklist = self.root / 'MANUAL_CHECKLIST.md'
        self.checklist.write_text('''## MC-001
Exclusive resources: none
Depends on: none
## MC-002
Exclusive resources: none
Depends on: none
## MC-003
Exclusive resources: none
Depends on: MC-001, MC-002
''')
        self.groups = self.root / 'groups.txt'
        self.groups.write_text('MC-001 MC-002\nMC-003\n')
        self.mapping = self.root / 'commands.json'

    def execute(self, commands, **kwargs):
        self.mapping.write_text(json.dumps({'checklist_sha256': hashlib.sha256(self.checklist.read_bytes()).hexdigest(), 'commands': commands}))
        return run(self.mapping, self.checklist, self.groups, self.root/'results', **kwargs)

    def command(self, code):
        return [sys.executable, '-c', code]

    def test_parallel_group_and_dependency_barrier(self):
        # Each independent command requires its peer to have started: serial
        # execution cannot pass. The dependent check requires both completions.
        commands = {}
        for cid, peer in [('MC-001','MC-002'), ('MC-002','MC-001')]:
            commands[cid] = self.command(f'''from pathlib import Path
import time
p=Path({str(self.root)!r}); (p/{cid!r}).touch()
end=time.monotonic()+3
while not (p/{peer!r}).exists() and time.monotonic()<end: time.sleep(.01)
assert (p/{peer!r}).exists()
(p/({cid!r}+'.done')).touch()
''')
        commands['MC-003'] = self.command(f'from pathlib import Path; p=Path({str(self.root)!r}); assert (p/"MC-001.done").exists() and (p/"MC-002.done").exists()')
        results = self.execute(commands)
        self.assertTrue(all(r['status']=='EXIT_0' for r in results.values()))
        self.assertEqual(len({r['log'] for r in results.values()}),3)

    def test_failure_retains_independent_results_blocks_dependent(self):
        results = self.execute({'MC-001':self.command('raise SystemExit(2)'), 'MC-002':self.command('print("ok")'), 'MC-003':self.command('raise Exception("must not run")')})
        self.assertEqual([results[c]['status'] for c in ('MC-001','MC-002','MC-003')], ['FAILED','EXIT_0','NOT_RUN'])

    def test_report_retains_unmapped_checks_without_inventing_acceptance(self):
        checks, _, _ = parse(self.checklist.read_text())
        draft = report_draft(checks, {'MC-001': {'status': 'EXIT_0', 'exit_code': 0,
                                               'log': 'path|with\nseparator'}})
        self.assertIn('MC-001 | EXIT_0 | 0 | path&#124;with separator', draft)
        self.assertIn('MC-002 | NOT_RUN', draft)
        self.assertIn('MC-003 | NOT_RUN', draft)
        self.assertNotIn('| PASS |', draft)

    def test_timeout_is_recorded(self):
        results = self.execute({'MC-001':self.command('import time; time.sleep(30)')}, timeout=.1)
        self.assertEqual(results['MC-001']['status'], 'TIMEOUT')
        self.assertEqual(results['MC-003']['status'], 'NOT_RUN')

    def test_stale_groups_and_unknown_ids_rejected(self):
        self.groups.write_text('MC-001 MC-002 MC-003\n')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.execute({})
        with self.assertRaisesRegex(ValueError, 'known checklist'):
            self.execute({'MC-404':self.command('pass')})

    def test_stale_mapping_rejected(self):
        self.mapping.write_text(json.dumps({'checklist_sha256':'old','commands':{}}))
        with self.assertRaisesRegex(ValueError, 'Checklist changed'):
            run(self.mapping,self.checklist,self.groups,self.root/'results')


if __name__=='__main__': unittest.main()

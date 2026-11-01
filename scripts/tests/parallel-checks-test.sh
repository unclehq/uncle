#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export UNCLE_TEST_ROOT="$ROOT"
python3 -B - <<'PY'
import os, pathlib, signal, subprocess, sys, tempfile, time, unittest
sys.path.insert(0, os.environ['UNCLE_TEST_ROOT']+'/scripts/lib')
from verification_manifest import manifest
from process_tree import bash_executable, group_options, kill_tree

class Checks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
    def native_literal_cr(self):
        # Git Bash's MSYS parser discards literal CRs, even inside quotes:
        # git-for-windows/MSYS2-packages/bash/0005-bash-4.3-msys2-fix-lineendings.patch
        # Execution must match the host shell; file bytes must stay unchanged.
        return subprocess.run([bash_executable(), '-c', "printf 'A\rB'"],
                              capture_output=True, check=True).stdout
    def diagnostics(self):
        return '\n'.join(f'{name}:\n{(self.root/name).read_text(errors="replace")}'
                         for name in ('results','log','integrity') if (self.root/name).exists())
    def run_checks(self, commands, groups, protected=False):
        (self.root/'commands').write_text('\n'.join(commands)+'\n')
        (self.root/'groups').write_text(groups)
        argv=[sys.executable, '-B', os.environ['UNCLE_TEST_ROOT']+'/scripts/lib/parallel_checks.py',
              '--commands','commands','--groups','groups','--out','results','--log','log','--jobs','2']
        if protected:
            (self.root/'scopes').write_text('fixture\n')
            import hashlib
            (self.root/'expected').write_text(hashlib.sha256(b'original\n').hexdigest()+'\tfixture\n')
            argv+=['--paths','scopes','--expected','expected','--integrity-log','integrity']
        return subprocess.run(argv, cwd=self.root, capture_output=True, text=True, timeout=15)
    def test_approved_baseline_schedule_fallback(self):
        commands = "echo 1 >> order\ntest -f order && echo 2 >> order; exit 7\necho 3 >> order\n"
        # Exercise native Windows line endings on every host.
        raw_commands = commands.replace('\n', '\r\n').encode()
        (self.root/'commands').write_bytes(raw_commands)
        for declaration, expected in [('1 3', ''), ('1 2\n2 3', ''),
                                      ('1 2', '1 2\n'), ('', '')]:
            report = '## Parallel verification groups\n\n```text\n' + declaration + '\n```\n' if declaration else '# Baseline\n'
            (self.root/'report').write_text(report)
            (self.root/'groups').write_text('stale schedule\n')
            script = '. "$1/scripts/lib/green-check.sh"; resolve_baseline_parallel_groups report commands groups'
            if not expected:
                script += '; green_run commands results log "" groups'
            result = subprocess.run([bash_executable(), '-euc', script, 'test',
                                     os.environ['UNCLE_TEST_ROOT']], cwd=self.root,
                                    capture_output=True, text=True, timeout=15,
                                    env=dict(os.environ, WORKFLOW_METRICS='0'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.root/'groups').read_text(), expected)
            self.assertEqual((self.root/'report').read_text(), report)
            self.assertEqual((self.root/'commands').read_bytes(), raw_commands)
            if not expected:
                self.assertTrue((self.root/'order').exists(), self.diagnostics())
                self.assertEqual((self.root/'order').read_text(), '1\n2\n3\n')
                self.assertEqual([row.split('\t')[0] for row in
                                  (self.root/'results').read_text().splitlines()], ['0', '7', '0'])
                (self.root/'order').unlink()

    def test_serial_crlf_preserves_embedded_cr_and_final_unterminated_line(self):
        commands = b"printf 'A\rB' > embedded\r\nprintf last > last"
        (self.root/'commands').write_bytes(commands)
        script = '. "$1/scripts/lib/green-check.sh"; green_run commands results log'
        result = subprocess.run([bash_executable(), '-euc', script, 'test', os.environ['UNCLE_TEST_ROOT']],
                                cwd=self.root, capture_output=True, text=True, timeout=15,
                                env=dict(os.environ, WORKFLOW_METRICS='0'))
        self.assertEqual(result.returncode, 0, result.stderr + self.diagnostics())
        self.assertEqual((self.root/'embedded').read_bytes(), self.native_literal_cr())
        self.assertEqual((self.root/'last').read_bytes(), b'last')
        self.assertEqual((self.root/'commands').read_bytes(), commands)

    def test_escaped_cr_output_is_preserved_in_serial_and_parallel(self):
        for groups in ('', '1 2\n'):
            r=self.run_checks(["printf 'A\\rB' > escaped", 'true'], groups)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((self.root/'escaped').read_bytes(), b'A\rB')

    def test_overlap_and_barrier(self):
        commands=[]
        for i,other in [(1,2),(2,1)]:
            commands.append(f'touch ready{i}; for n in {{1..50}}; do if test -f ready{other}; then touch done{i}; echo check{i}; exit 0; fi; sleep .1; done; exit 7')
        commands.append('test -f done1 && test -f done2 && echo barrier')
        r=self.run_checks(commands, '1 2\n')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual([s.split('\t')[0] for s in (self.root/'results').read_text().splitlines()], ['0']*3, self.diagnostics())
        log=(self.root/'log').read_text()
        self.assertLess(log.index('\ncheck1\n'),log.index('\ncheck2\n'))
    def test_parallel_commands_preserve_embedded_cr(self):
        r=self.run_checks(["printf 'A\rB' > embedded", 'printf last > last'], '1 2\n')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual((self.root/'embedded').read_bytes(), self.native_literal_cr())
        self.assertEqual((self.root/'last').read_bytes(), b'last')
    def test_test_failure_is_recorded(self):
        r=self.run_checks(['exit 7','echo still-runs'], '1 2\n')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue((self.root/'results').read_text().startswith('7\t'), self.diagnostics())
        self.assertIn('Verification summary: 1 passed, 1 failed;', r.stdout)
        self.assertIn('Full output: log', r.stdout)
    def test_failed_build_skips_later_browser_and_mutation_commands(self):
        r=self.run_checks(['false # vite build', 'touch browser-ran # playwright test',
                           'touch mutation-ran # mutation test'], '')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.root/'browser-ran').exists(), self.diagnostics())
        self.assertFalse((self.root/'mutation-ran').exists(), self.diagnostics())
        rows=(self.root/'results').read_text().splitlines()
        self.assertEqual([row.split('\t', 1)[0] for row in rows], ['1', '125', '125'], self.diagnostics())
        self.assertIn('earlier build command failed', (self.root/'log').read_text())
    def test_failed_browser_suite_skips_mutation_controls(self):
        r=self.run_checks(['true # vite build', 'false # playwright test',
                           'touch mutation-ran # mutation test'], '')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.root/'mutation-ran').exists(), self.diagnostics())
        self.assertEqual([row.split('\t', 1)[0] for row in
                          (self.root/'results').read_text().splitlines()], ['0', '1', '125'])
        self.assertIn('earlier build, unit, or browser command failed', (self.root/'log').read_text())
    def test_mutations_wait_for_baseline_even_if_plan_groups_them_together(self):
        result = self.run_checks(['sleep .2; exit 1 # playwright test',
                                  'touch mutation-ran # mutation test'], '1 2\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root/'mutation-ran').exists())
        self.assertEqual([row.split('\t')[0] for row in (self.root/'results').read_text().splitlines()], ['1','125'])

    def test_browser_suites_get_a_small_failure_budget_but_keep_the_reported_command(self):
        r=self.run_checks(["printf '%s' \"$*\" > args # playwright test"], '')
        self.assertEqual(r.returncode, 0, r.stderr)
        # The helper's shell comment intentionally keeps this fixture command
        # inert; validate the execution transformation directly instead.
        import parallel_checks
        self.assertEqual(parallel_checks.execution_command('npx playwright test'),
                         'npx playwright test --max-failures=5')
        self.assertEqual(parallel_checks.execution_command('npx playwright test --max-failures=3'),
                         'npx playwright test --max-failures=3')
        self.assertEqual(parallel_checks.execution_command('npx playwright test e2e/a.spec.js'),
                         'npx playwright test --max-failures=5 e2e/a.spec.js')
        # The flag goes on Playwright, never on the trailing `wait` of a compound command.
        self.assertEqual(parallel_checks.execution_command('(npx vitest run) & (PORT=4180 npx playwright test) & wait'),
                         '(npx vitest run) & (PORT=4180 npx playwright test --max-failures=5) & wait')
        self.assertEqual(parallel_checks.execution_command('npx vitest run'), 'npx vitest run')
    def test_the_default_budget_lets_an_ordinary_failing_suite_report_everything(self):
        # One failure used to stop the run with most of the suite unrun, and made blank-page detection (two or more
        # missing-element failures) impossible. The budget must be above that detection threshold and overridable.
        import parallel_checks
        from unittest.mock import patch
        self.assertGreater(parallel_checks.DEFAULT_E2E_MAX_FAILURES, 2)
        with patch.dict(os.environ, WORKFLOW_GREEN_E2E_MAX_FAILURES='0'):
            self.assertEqual(parallel_checks.execution_command('npx playwright test'), 'npx playwright test')
        with patch.dict(os.environ, WORKFLOW_GREEN_E2E_MAX_FAILURES='2'):
            self.assertEqual(parallel_checks.execution_command('npx playwright test'), 'npx playwright test --max-failures=2')
    def test_npm_wrapper_uses_the_actual_script_and_preserves_other_runners(self):
        import parallel_checks, json
        from unittest.mock import patch
        project = self.root / 'calculator'
        project.mkdir()
        (project / 'package.json').write_text(json.dumps({'scripts': {
            'test:browser': 'playwright test', 'test': 'node --test',
            'other': 'pytest', 'chain': 'playwright test && echo done'}}))
        with patch('parallel_checks.Path.cwd', return_value=self.root):
            command = 'npm --prefix calculator run test:browser'
            self.assertEqual(parallel_checks.execution_command(command), command + ' -- --max-failures=5')
            self.assertIn('mutation controls', parallel_checks.prerequisite_skip('node mutation.mjs', False, False, True))
            self.assertIn('playwright test', parallel_checks.command_evidence(command))
            for name in ('test', 'other', 'chain', 'missing'):
                command = 'npm --prefix calculator run ' + name
                self.assertEqual(parallel_checks.execution_command(command), command)
            command = 'npm --prefix calculator run test:browser && echo done'
            self.assertEqual(parallel_checks.execution_command(command), command)

    def test_failed_npm_browser_wrapper_skips_mutations_and_keeps_evidence(self):
        import json
        from unittest.mock import patch
        (self.root/'package.json').write_text(json.dumps({'scripts': {'test:browser': 'playwright test'}}))
        binary = self.root/'npm'
        binary.write_text('#!/bin/sh\nprintf "args: %s\\n" "$*"\nexit 1\n')
        binary.chmod(0o755)
        with patch.dict(os.environ, PATH=str(self.root)+os.pathsep+os.environ['PATH']):
            result = self.run_checks(['npm run test:browser', 'touch mutation-ran # mutation test'], '')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root/'mutation-ran').exists())
        self.assertIn('args: run test:browser -- --max-failures=5', (self.root/'log').read_text())
        self.assertEqual((self.root/'results').read_text().splitlines()[0], '1\tnpm run test:browser')

    def test_output_is_visible_before_command_finishes(self):
        import shlex
        (self.root/'commands').write_text("echo startup-failure; while ! test -f release; do sleep .1; done\n")
        (self.root/'groups').write_text('')
        child = subprocess.Popen([sys.executable, '-B', os.environ['UNCLE_TEST_ROOT']+'/scripts/lib/parallel_checks.py',
                                  '--commands','commands','--groups','groups','--out','results','--log','log','--jobs','2'],
                                 cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if (self.root/'log').exists() and 'startup-failure\n' in (self.root/'log').read_text():
                    break
                time.sleep(.05)
            else:
                self.fail('command output was buffered until completion')
            self.assertIsNone(child.poll())
        finally:
            (self.root/'release').touch()
            out, err = child.communicate(timeout=10)
        self.assertEqual(child.returncode, 0, err)
        self.assertIn('RUNNING', out)
        self.assertEqual((self.root/'log').read_text().count('\nstartup-failure\n'), 1)

    def test_missing_browser_root_is_reported_as_an_unrunnable_application(self):
        r=self.run_checks(["printf '%s\\n' '#root element(s) not found element(s) not found' >&2; exit 1 # playwright test"], '')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('APPLICATION_RUNTIME_UNRUNNABLE', (self.root/'log').read_text())
    def test_invalid_groups_execute_nothing(self):
        for groups in ['0 1\n','2 1\n','1 3\n','1 2\n1 2\n']:
            r=self.run_checks(['touch ran','touch ran'],groups)
            self.assertEqual(r.returncode,2,r.stderr)
            self.assertFalse((self.root/'ran').exists())
    def test_restored_peer_cannot_hide_a_mutation(self):
        (self.root/'fixture').write_bytes(b'original\n')
        r=self.run_checks(["sleep .1; printf 'changed\\n' > fixture",
                           "sleep .5; printf 'original\\n' > fixture",'touch must-not-run'],
                          '1 2\n',protected=True)
        self.assertEqual(r.returncode,3,r.stderr + self.diagnostics())
        self.assertFalse((self.root/'must-not-run').exists())
        self.assertIn('changed',(self.root/'integrity').read_text())
    def absent_case(self, commands, allow):
        import hashlib
        (self.root/'fixture').write_bytes(b'original\n')
        (self.root/'scopes').write_text('fixture\nlock.json\n')
        (self.root/'expected').write_text('ABSENT\tlock.json\n'+hashlib.sha256(b'original\n').hexdigest()+'\tfixture\n')
        (self.root/'absent').write_text('lock.json\n')
        (self.root/'commands').write_text('\n'.join(commands)+'\n')
        (self.root/'groups').write_text('1 2\n')
        env=dict(os.environ)
        env.pop('WORKFLOW_ALLOW_ABSENT_PROTECTED_DIRECTORIES',None)
        if allow:
            env['WORKFLOW_ALLOW_ABSENT_PROTECTED_DIRECTORIES']='absent'
        return subprocess.run([sys.executable,'-B',os.environ['UNCLE_TEST_ROOT']+'/scripts/lib/parallel_checks.py',
                               '--commands','commands','--groups','groups','--out','results','--log','log','--jobs','2',
                               '--paths','scopes','--expected','expected','--integrity-log','integrity'],
                              cwd=self.root,capture_output=True,text=True,timeout=15,env=env)
    def test_a_protected_path_absent_at_the_first_snapshot_is_allowed_to_stay_absent(self):
        r=self.absent_case(['true','true'],allow=True)
        self.assertEqual(r.returncode,0,r.stderr+self.diagnostics())
    def test_without_the_allowance_an_absent_protected_path_reads_as_missing(self):
        r=self.absent_case(['true','true'],allow=False)
        self.assertEqual(r.returncode,3,r.stderr+self.diagnostics())
        self.assertIn('Missing protected verification path: lock.json',(self.root/'integrity').read_text())
    def test_an_absent_protected_path_that_appears_is_still_a_change(self):
        r=self.absent_case(['touch lock.json','true'],allow=True)
        self.assertEqual(r.returncode,3,r.stderr+self.diagnostics())
    def test_the_driver_passes_the_allowance_to_the_parallel_runner(self):
        text=pathlib.Path(os.environ['UNCLE_TEST_ROOT']+'/scripts/lib/green-check.sh').read_text()
        self.assertIn('WORKFLOW_ALLOW_ABSENT_PROTECTED_DIRECTORIES="${STATE_DIR:-.uncle/workflow}/verification.absent-paths"',text)
    def test_interruption_stops_children(self):
        (self.root/'commands').write_text('echo $$ > pid1; sleep 30 & echo $! > child1; wait\necho $$ > pid2; sleep 30 & echo $! > child2; wait\ntouch must-not-run\n')
        (self.root/'groups').write_text('1 2\n')
        p=subprocess.Popen([sys.executable,'-B',os.environ['UNCLE_TEST_ROOT']+'/scripts/lib/parallel_checks.py',
                            '--commands','commands','--groups','groups','--out','results','--log','log'],
                           cwd=self.root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True, **group_options())
        try:
            deadline=time.monotonic()+5
            names = ('pid1','pid2','child1','child2')
            while not all((self.root/name).exists() and (self.root/name).stat().st_size for name in names) and time.monotonic()<deadline:
                time.sleep(.02)
            self.assertTrue((self.root/'pid2').exists(), self.diagnostics())
            p.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGTERM)
            _,errors=p.communicate(timeout=5)
            self.assertEqual(p.returncode,130,errors)
            self.assertFalse((self.root/'must-not-run').exists())
            for name in names:
                pid = int((self.root/name).read_text())
                if os.name == 'nt':
                    check = subprocess.run([bash_executable(), '-c', f'kill -0 {pid}'], capture_output=True)
                    self.assertNotEqual(check.returncode, 0)
                else:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(pid, 0)
        finally:
            if p.poll() is None:
                # Do not retry the same failed graceful stop and leave files
                # locked, masking the original timeout during temp cleanup.
                kill_tree(p)
                p.communicate(timeout=15)

unittest.main()
PY

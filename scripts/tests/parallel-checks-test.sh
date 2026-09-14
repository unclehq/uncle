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

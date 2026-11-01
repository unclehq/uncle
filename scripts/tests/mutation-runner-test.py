#!/usr/bin/env python3
"""The driver-supplied defect-injection runner: catches what the tests catch, reports what they miss, trusts nothing unproven."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / 'scripts' / 'lib' / 'mutation_runner.mjs'
HAS_NODE = shutil.which('node') is not None

SOURCE = "export const add = (a, b) => a + b;\nexport const label = 'sum';\n"
CHECK = """import { add } from '../src/a.js';
if (add(2, 3) !== 5) { console.error('FAIL add(2,3) should be 5'); process.exit(1); }
console.log('ok');
"""


@unittest.skipUnless(HAS_NODE, 'node is not installed')
class Runner(unittest.TestCase):
    def test_environment_ports_and_outputs_are_isolated_for_controls_and_mutants(self):
        log = self.root / 'ports.jsonl'
        (self.root / 'tests/check.mjs').write_text("""import fs from 'node:fs';
import net from 'node:net';
import {add} from '../src/a.js';
const server=net.createServer();
server.listen(Number(process.env.TEST_PORT), '127.0.0.1', () => {
  fs.appendFileSync(process.env.PORT_LOG, JSON.stringify({port:server.address().port, output:process.env.TEST_OUTPUT_DIR})+'\\n');
  setTimeout(()=>server.close(()=>{if(add(2,3)!==5){console.error('FAIL arithmetic');process.exit(1);}}),150);
});
""")
        self.entries({'id':'DI-1','file':'src/a.js','find':'a + b','replace':'a - b',
                      'command':'node tests/check.mjs first'},
                     {'id':'DI-2','file':'src/a.js','find':'a + b','replace':'a * b',
                      'command':'node tests/check.mjs second'})
        done = self.run_runner(env={'PORT_LOG':str(log), 'TEST_PORT':'4174', 'TEST_OUTPUT_DIR':'shared'})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({row['port'] for row in rows}), 4)
        self.assertEqual(len({row['output'] for row in rows}), 4)
        self.assertNotIn(4174, [row['port'] for row in rows])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'src').mkdir()
        (self.root / 'tests/mutations').mkdir(parents=True)
        (self.root / 'package.json').write_text('{"type":"module"}')
        (self.root / 'src/a.js').write_text(SOURCE)
        (self.root / 'tests/check.mjs').write_text(CHECK)
        shutil.copy(RUNNER, self.root / 'tests/mutations/run.mjs')

    def tearDown(self):
        self.tmp.cleanup()

    def entries(self, *rows):
        body = ',\n'.join(json.dumps(dict({'command': 'node tests/check.mjs'}, **row)) for row in rows)
        (self.root / 'tests/mutations/list.mjs').write_text('export default [\n%s\n];\n' % body)

    def run_runner(self, *extra, env=None):
        import os
        return subprocess.run(['node', 'tests/mutations/run.mjs', *extra], cwd=self.root, capture_output=True, text=True,
                              timeout=120, env=dict(os.environ, **(env or {})))

    def summary(self):
        return json.loads((self.root / '.test-out/mutations.json').read_text())

    def test_nested_package_uses_its_runner_and_links_its_dependencies(self):
        import os
        app = self.root / "nested app"
        (app/'src').mkdir(parents=True)
        (app/'tests').mkdir()
        (app/'package.json').write_text('{"type":"module"}')
        (app/'playwright.config.js').write_text('export default {}')
        (app/'src/a.js').write_text(SOURCE)
        dependency = app/'node_modules/oracle'
        dependency.mkdir(parents=True)
        (dependency/'package.json').write_text('{"type":"module","exports":"./index.js"}')
        (dependency/'index.js').write_text('export default 5;')
        (app/'tests/example.spec.js').write_text("import expected from 'oracle';\n" + CHECK.replace('!== 5', '!== expected'))
        binpath = self.root/'bin'
        binpath.mkdir()
        fake = binpath/'npx'
        fake.write_text('#!/bin/sh\n[ "$1 $2" = "playwright test" ] || exit 99\nshift 2\nexec node "$@"\n')
        fake.chmod(0o755)
        self.entries({'id':'DI-NESTED','file':'nested app/src/a.js', 'find':'a + b',
                      'replace':'a - b', 'spec':'nested app/tests/example.spec.js', 'command':None})
        result = self.run_runner(env={'PATH':str(binpath)+os.pathsep+os.environ['PATH']})
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('CAUGHT', result.stdout)

    def test_a_defect_the_tests_catch_passes_the_run(self):
        self.entries({'id': 'DI-1', 'file': 'src/a.js', 'find': 'a + b', 'replace': 'a - b'})
        done = self.run_runner()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('CAUGHT', done.stdout)
        self.assertIn('Mutations: 1 caught, 0 survived', done.stdout)
        self.assertIn('controls 1/1 passed', done.stdout)

    def test_a_defect_the_tests_miss_fails_the_run_and_names_it(self):
        self.entries({'id': 'DI-1', 'file': 'src/a.js', 'find': 'a + b', 'replace': 'a - b'},
                     {'id': 'DI-2', 'file': 'src/a.js', 'find': "'sum'", 'replace': "'total'"})
        done = self.run_runner()
        self.assertEqual(done.returncode, 1)
        self.assertRegex(done.stdout, r'SURVIVED\s+DI-2')
        self.assertEqual((self.summary()['caught'], self.summary()['survived']), (1, 1))

    def test_a_find_that_does_not_occur_once_is_invalid_not_a_pass(self):
        self.entries({'id': 'DI-1', 'file': 'src/a.js', 'find': 'not there', 'replace': 'x'},
                     {'id': 'DI-2', 'file': 'src/a.js', 'find': 'export', 'replace': 'export /* */'})
        done = self.run_runner()
        self.assertEqual(done.returncode, 1)
        self.assertRegex(done.stdout, r'INVALID\s+DI-1.*occurs 0 times')
        self.assertRegex(done.stdout, r'INVALID\s+DI-2.*occurs 2 times')

    def test_the_project_is_never_changed_and_nothing_is_left_behind(self):
        self.entries({'id': 'DI-1', 'file': 'src/a.js', 'find': 'a + b', 'replace': 'a - b'})
        self.run_runner()
        self.assertEqual((self.root / 'src/a.js').read_text(), SOURCE)
        self.assertFalse((self.root / '.mutation-scratch').exists())

    def test_a_failing_control_makes_every_result_unreliable(self):
        (self.root / 'tests/check.mjs').write_text("console.error('broken'); process.exit(1);\n")
        self.entries({'id': 'DI-1', 'file': 'src/a.js', 'find': 'a + b', 'replace': 'a - b'})
        done = self.run_runner()
        self.assertEqual(done.returncode, 1)
        self.assertIn('CONTROL FAIL', done.stdout)
        self.assertRegex(done.stdout, r'UNRELIABLE\s+DI-1')

    def test_the_usual_aliases_and_a_named_export_are_accepted(self):
        (self.root / 'tests/mutations/list.mjs').write_text(
            "export const mutations = [{ name: 'DI-9', path: 'src/a.js', search: 'a + b', replacement: 'a * b', "
            "specs: ['tests/check.mjs'], command: 'node tests/check.mjs' }];\n")
        done = self.run_runner()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('DI-9', done.stdout)

    def test_a_path_that_leaves_the_project_is_refused(self):
        self.entries({'id': 'DI-1', 'file': '../outside.js', 'find': 'x', 'replace': 'y'})
        done = self.run_runner()
        self.assertEqual(done.returncode, 1)
        self.assertRegex(done.stdout, r'INVALID\s+DI-1')

    def test_only_runs_one_defect(self):
        self.entries({'id': 'DI-1', 'file': 'src/a.js', 'find': 'a + b', 'replace': 'a - b'},
                     {'id': 'DI-2', 'file': 'src/a.js', 'find': "'sum'", 'replace': "'total'"})
        done = self.run_runner('--only', 'DI-1')
        self.assertEqual(done.returncode, 0)
        self.assertNotIn('DI-2', done.stdout)

    def test_strict_mode_wants_the_expected_test_to_be_the_one_that_failed(self):
        self.entries({'id': 'DI-1', 'file': 'src/a.js', 'find': 'a + b', 'replace': 'a - b', 'expected': 'a different test'})
        self.assertEqual(self.run_runner().returncode, 0)
        done = self.run_runner(env={'MUTATION_STRICT': '1'})
        self.assertEqual(done.returncode, 1)
        self.assertRegex(done.stdout, r'SURVIVED\s+DI-1.*not in the expected test')

    def test_every_mutant_gets_its_own_port_in_its_copy(self):
        (self.root / 'playwright.config.js').write_text("export default { webServer: { command: 'vite preview --port 4173', url: 'http://127.0.0.1:4173' } };\n")
        (self.root / 'tests/check.mjs').write_text(
            "import fs from 'node:fs';\nconst m = fs.readFileSync('playwright.config.js', 'utf8').match(/--port (\\d+)/);\n"
            "console.log('PORT=' + m[1]);\nif (process.env.WANT_PORT && m[1] === ['41', '73'].join('')) process.exit(1);\n")
        self.entries({'id': 'DI-1', 'file': 'src/a.js', 'find': 'a + b', 'replace': 'a - b'},
                     {'id': 'DI-2', 'file': 'src/a.js', 'find': "'sum'", 'replace': "'total'"})
        done = self.run_runner(env={'WANT_PORT': '1'})
        # the unmutated project keeps 4173; each copy was given another, so the check (which fails on 4173) passes in the copies
        self.assertEqual((self.root / 'playwright.config.js').read_text().count('4173'), 2)
        self.assertRegex(done.stdout, r'SURVIVED\s+DI-1')

    def test_the_default_command_is_derived_from_the_project(self):
        import os
        (self.root / 'package.json').write_text('{"type":"module","devDependencies":{"vitest":"2"},"scripts":{"build":"true"}}')
        script = ("import fs from 'node:fs';\nconst text = fs.readFileSync('tests/mutations/list.mjs', 'utf8');\nprocess.exit(0);\n")
        (self.root / 'tests/mutations/list.mjs').write_text(
            "export default [{ id: 'DI-1', file: 'src/a.js', find: 'a + b', replace: 'a - b', spec: 'tests/unit/a.test.js' }];\n")
        # no vitest is installed in the fixture, so the derived command cannot succeed; what matters is which command it chose
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        fake = bin_dir / 'npx'
        fake.write_text('#!/bin/sh\necho "NPX $@" >> "$LOGFILE"\nexit 1\n')
        fake.chmod(0o755)
        done = self.run_runner(env={'PATH': str(bin_dir) + ':' + os.environ['PATH'], 'LOGFILE': str(self.root / 'npx.log')})
        self.assertEqual(done.returncode, 1)
        self.assertIn('NPX vitest run tests/unit/a.test.js', (self.root / 'npx.log').read_text())


@unittest.skipUnless(HAS_NODE, 'node is not installed')
class Provided(unittest.TestCase):
    def test_the_driver_step_copies_the_runner_to_the_planned_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run(['bash', str(ROOT / 'scripts/lib/parallel-provided.sh'), '10', 'tests/mutations/run.mjs'],
                                  cwd=tmp, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual((Path(tmp) / 'tests/mutations/run.mjs').read_text(), RUNNER.read_text())


if __name__ == '__main__':
    unittest.main()

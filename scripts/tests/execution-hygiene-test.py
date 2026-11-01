"""Hermetic process, browser-cache, step-check, and scaffold regressions."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import browser_install as browser
import execution_options as options
import implementation_fast_check as fast
import install_warm
import scaffold_templates as scaffold
from process_tree import start_check, wait_check, finish_check, kill_tree


class Temporary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.old = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.old)
        self.env = patch.dict(os.environ, {
            'UNCLE_CONFIG': str(self.root / 'config'),
            'WORKFLOW_INSTALL_LOCK': str(self.root / 'cache/install.lock'),
            'WORKFLOW_PLAYWRIGHT_AUTO_INSTALL': '0',
            'WORKFLOW_PLAYWRIGHT_BROWSERS': 'chromium',
            'WORKFLOW_CHECK_IDLE_SECONDS': '.4',
        })
        self.env.start()
        self.addCleanup(self.env.stop)


class Idle(Temporary):
    def run_child(self, code, timeout=8):
        with tempfile.TemporaryFile() as output:
            child = start_check([sys.executable, '-u', '-c', code], stdout=output, stderr=output)
            try:
                status = wait_check(child, timeout, output)
                output.seek(0)
                return status, output.read()
            finally:
                kill_tree(child)
                child.wait()
                finish_check(child)

    def test_stall_retains_last_output_and_differs_from_timeout(self):
        started = time.monotonic()
        status, log = self.run_child("import time; print('last evidence'); time.sleep(30)")
        self.assertEqual(status, 123)
        self.assertIn(b'last evidence', log)
        self.assertIn(b'STALLED', log)
        self.assertNotIn(b'TIMEOUT', log)
        self.assertLess(time.monotonic() - started, 4)

    def test_output_activity_resets_idle_window(self):
        status, log = self.run_child("import time\nfor i in range(15):\n print(i); time.sleep(.1)")
        self.assertEqual(status, 0, log)

    def test_busy_grandchild_is_not_an_idle_parent(self):
        code = "import subprocess,sys; subprocess.run([sys.executable,'-c', 'import time; end=time.monotonic()+2\\nwhile time.monotonic()<end: pass'])"
        # POSIX ps on Linux reports whole CPU seconds, so allow one sampling tick.
        with patch.dict(os.environ, WORKFLOW_CHECK_IDLE_SECONDS='1.5'):
            status, log = self.run_child(code)
        self.assertEqual(status, 0, log)

    def test_tiny_periodic_cpu_use_still_counts_as_stalled(self):
        child = Mock(pid=123, returncode=0)
        child.poll.side_effect = [None] * 4 + [0]
        child.wait.side_effect = [subprocess.TimeoutExpired('fixture', 1)] * 3 + [0]
        samples = [(value, frozenset({123})) for value in (0, .2, .4, .6)]
        with tempfile.TemporaryFile() as output, \
                patch('process_tree.time.monotonic', side_effect=[0, 0, 30, 60, 90]), \
                patch('process_tree.tree_cpu', side_effect=samples), \
                patch('process_tree.kill_tree') as kill, \
                patch.dict(os.environ, WORKFLOW_CHECK_IDLE_CPU_PERCENT='1'):
            self.assertEqual(wait_check(child, 900, output, idle=90), 123)
            kill.assert_called_once_with(child)

    def test_unknown_cpu_never_falsely_stalls(self):
        with patch('process_tree.tree_cpu', return_value=None):
            status, log = self.run_child('import time; time.sleep(.8)')
        self.assertEqual(status, 0, log)

    def test_disable_idle_keeps_total_timeout(self):
        with patch.dict(os.environ, WORKFLOW_CHECK_IDLE_SECONDS='0'):
            status, log = self.run_child('import time; time.sleep(30)', .3)
        self.assertEqual(status, 124)
        self.assertIn(b'TIMEOUT', log)

    def test_config_and_environment_precedence(self):
        (self.root / 'config').write_text('execution.check-idle-seconds 12\nexecution.check-idle-seconds 22\n')
        with patch.dict(os.environ):
            os.environ.pop('WORKFLOW_CHECK_IDLE_SECONDS')
            self.assertEqual(options.seconds('check-idle-seconds', 90), 12)
            os.environ['WORKFLOW_CHECK_IDLE_SECONDS'] = '3'
            self.assertEqual(options.seconds('check-idle-seconds', 90), 3)
        for invalid in ('nan', 'inf', '-1'):
            with patch.dict(os.environ, WORKFLOW_CHECK_IDLE_SECONDS=invalid):
                with self.assertRaises(ValueError):
                    options.seconds('check-idle-seconds', 90, allow_zero=True)

    def test_serial_and_parallel_report_stalled(self):
        command = "printf 'last evidence\\n'; sleep 30"
        (self.root / 'commands').write_text(command + '\n')
        (self.root / 'groups').write_text('')
        for argv in (
            [sys.executable, str(LIB / 'run_check.py'), '--', 'bash', '-c', command],
            [sys.executable, str(LIB / 'parallel_checks.py'), '--commands', 'commands', '--groups', 'groups',
             '--out', 'results', '--log', 'log'],
        ):
            result = subprocess.run(argv, capture_output=True, timeout=10)
            if 'parallel_checks.py' in argv[1]:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(Path('results').read_text().startswith('123\t'))
                self.assertIn(b'STALLED', result.stdout)
                self.assertIn('last evidence', Path('log').read_text())
            else:
                self.assertEqual(result.returncode, 123, result.stderr)
                self.assertIn(b'last evidence', result.stdout)
                self.assertIn(b'STALLED', result.stdout)

    def test_child_config_argument_is_not_a_driver_option(self):
        result = subprocess.run([sys.executable, str(LIB / 'run_check.py'), '--', sys.executable,
                                 '-c', "import os; print(os.environ.get('UNCLE_CONFIG', 'sanitized'))",
                                 '--config', 'child-config'], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), b'sanitized')

    def test_failed_browser_warmup_is_not_cached_as_complete(self):
        state = self.root / 'warm-state'
        state.mkdir()
        names = ['@playwright/test']
        marker = state / ('install-warm-' + install_warm.fingerprint(names))
        with patch('install_warm.shutil.which', return_value='/fixture'), \
                patch('install_warm.run', side_effect=[0, 1]):
            self.assertIn('not downloaded', install_warm.warm(names, state))
        self.assertFalse(marker.exists())
        with patch('install_warm.shutil.which', return_value='/fixture'), \
                patch('install_warm.run', side_effect=[0, 0]):
            self.assertIn('chromium ready', install_warm.warm(names, state))
        self.assertTrue(marker.exists())

    def test_warm_timeout_stops_descendant_without_touching_peer(self):
        peer = start_check([sys.executable, '-c', 'import time; time.sleep(30)'])
        code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c', \"import time,pathlib; time.sleep(1); pathlib.Path('orphan').touch()\"]); time.sleep(30)"
        try:
            self.assertNotEqual(install_warm.run([sys.executable, '-c', code], self.root, .2), 0)
            time.sleep(1.1)
            self.assertFalse(Path('orphan').exists())
            self.assertIsNone(peer.poll())
        finally:
            kill_tree(peer)
            peer.wait()
            finish_check(peer)


@unittest.skipUnless(shutil.which('node'), 'local Node is required for the disposable Playwright registry fixture')
class Browsers(Temporary):
    def setUp(self):
        super().setUp()
        package = self.root / 'node_modules/playwright-core'
        registry = package / 'lib/server/registry'
        registry.mkdir(parents=True)
        (package / 'package.json').write_text('{"name":"playwright-core","version":"0.0.0-fixture"}')
        self.executable = self.root / 'shared/chromium-123/browser'
        self.executable.parent.mkdir(parents=True)
        (registry / 'index.js').write_text('exports.registry = {executables: () => [{name:"chromium", executablePath: () => ' + json.dumps(str(self.executable)) + '}]};')
        (package / 'cli.js').write_text('''const fs = require('fs');
if (process.env.PLAYWRIGHT_SKIP_BROWSER_GC !== '1') process.exit(9);
fs.appendFileSync('install-count', 'install\\n');
setTimeout(() => fs.writeFileSync(''' + json.dumps(str(self.executable)) + ''', 'browser'), 300);
''')

    def checked(self, marker):
        return [sys.executable, str(LIB / 'run_check.py'), '--shell-command', 'npx playwright test',
                '--', sys.executable, '-c', "from pathlib import Path; Path(%r).touch()" % marker]

    def test_mixed_setup_and_browser_commands_run_as_before(self):
        # Plans that install and test in one command keep working: no preflight, no refusal.
        argv = self.checked('ran')
        argv[argv.index('--shell-command') + 1] = 'npm ci && npx playwright test'
        result = subprocess.run(argv, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(Path('ran').exists())
        self.assertTrue(Path('ran').exists())

    def test_uninspectable_playwright_runs_as_before(self):
        # A setup the probe cannot read (here: no local playwright-core at all) is not refused.
        shutil.rmtree(self.root / 'node_modules')
        result = subprocess.run(self.checked('ran'), capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(Path('ran').exists())
        self.assertIn(b'Browser preflight skipped', result.stdout)

    def test_missing_executable_fails_before_test_launch(self):
        started = time.monotonic()
        result = subprocess.run(self.checked('ran'), capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 126, result.stderr)
        self.assertIn(str(self.executable).encode(), result.stdout)
        self.assertIn(b'BROWSER_MISSING', result.stdout)
        self.assertFalse(Path('ran').exists())
        self.assertLess(time.monotonic() - started, 5)

    def test_ready_browser_runs_and_registry_version_change_is_detected(self):
        self.executable.write_text('ready')
        result = subprocess.run(self.checked('ran'), capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(Path('ran').exists())
        registry = self.root / 'node_modules/playwright-core/lib/server/registry/index.js'
        registry.write_text(registry.read_text().replace('chromium-123', 'chromium-456'))
        result = subprocess.run(self.checked('new-version-ran'), capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 126)
        self.assertIn(b'chromium-456', result.stdout)
        self.assertFalse(Path('new-version-ran').exists())

    def test_two_runs_install_once_and_preserve_another_partial_download(self):
        Path('shared/other-run.partial').write_text('keep')
        with patch.dict(os.environ, WORKFLOW_PLAYWRIGHT_AUTO_INSTALL='1', WORKFLOW_CHECK_IDLE_SECONDS='5'):
            children = [subprocess.Popen(self.checked('ran-' + str(i)), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        for i in range(2)]
            for child in children:
                out, err = child.communicate(timeout=12)
                self.assertEqual(child.returncode, 0, out + err)
        self.assertEqual(Path('install-count').read_text(), 'install\n')
        self.assertEqual(Path('shared/other-run.partial').read_text(), 'keep')
        self.assertTrue(Path('ran-0').exists() and Path('ran-1').exists())

    def test_busy_lock_fails_bounded_without_deleting_lock(self):
        with browser.install_lock(io.BytesIO()):
            with patch.dict(os.environ, WORKFLOW_INSTALL_LOCK_SECONDS='.2'):
                result = subprocess.run(self.checked('ran'), capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 126)
        self.assertIn(b'INSTALL_BUSY', result.stdout)
        self.assertTrue(Path(os.environ['WORKFLOW_INSTALL_LOCK']).exists())

    def test_parallel_cancellation_stops_only_its_browser_install(self):
        import signal
        from process_tree import group_options
        cli = Path('node_modules/playwright-core/cli.js')
        cli.write_text("const fs=require('fs'); fs.writeFileSync('installer-started', 'yes'); "
                       "setTimeout(() => fs.writeFileSync('orphan-browser', 'bad'), 1500); setInterval(()=>{}, 1000);")
        Path('commands').write_text('npx playwright test\n')
        Path('groups').write_text('')
        env = dict(os.environ, WORKFLOW_PLAYWRIGHT_AUTO_INSTALL='1', WORKFLOW_CHECK_IDLE_SECONDS='10')
        child = subprocess.Popen([sys.executable, str(LIB / 'parallel_checks.py'), '--commands', 'commands',
                                  '--groups', 'groups', '--out', 'results', '--log', 'log'],
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **group_options())
        try:
            deadline = time.monotonic() + 5
            while not Path('installer-started').exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(Path('installer-started').exists())
            child.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGTERM)
            out, err = child.communicate(timeout=5)
            self.assertEqual(child.returncode, 130, out + err)
            time.sleep(1.6)
            self.assertFalse(Path('orphan-browser').exists())
            with browser.install_lock(io.BytesIO()):
                pass
        finally:
            if child.poll() is None:
                kill_tree(child)
                child.communicate(timeout=5)

    def test_script_and_subdirectory_detection_ignores_comments(self):
        Path('package.json').write_text('{"scripts":{"test:e2e":"playwright test","setup":"npm ci"}}')
        self.assertEqual(browser.command_needs('npm run test:e2e')[:2], (False, True))
        self.assertEqual(browser.command_needs('npm run setup')[:2], (True, False))
        self.assertEqual(browser.command_needs('echo ok # playwright test')[:2], (False, False))
        self.assertEqual(browser.command_needs('cd nested && npx --no-install playwright test')[2], self.root / 'nested')


class StepAndScaffold(Temporary):
    def test_template_is_opt_in_and_requires_first_step_ownership(self):
        with self.assertRaises(ValueError):
            scaffold.apply(self.root, 'vite-react', ['package.json'])
        self.assertFalse(Path('package.json').exists())
        files = scaffold.apply(self.root, 'vite-react', list(scaffold.FILES))
        self.assertEqual(set(files), set(scaffold.FILES))
        package = json.loads(Path('package.json').read_text())
        self.assertEqual(package['scripts']['test:unit'], 'vitest run')
        self.assertIn('tests/unit/', Path('vite.config.js').read_text())
        self.assertIn("testDir: './tests/e2e'", Path('playwright.config.js').read_text())
        self.assertIn('npm run build\n', Path('.uncle/workflow/scaffold-verification-commands.txt').read_text())
        Path('package.json').write_text('user changes after application')
        self.assertEqual(scaffold.apply(self.root, 'vite-react', ['*']), [])
        self.assertEqual(Path('package.json').read_text(), 'user changes after application')

    def test_template_preflights_all_files_and_preserves_existing_content(self):
        Path('playwright.config.js').write_text('existing')
        with self.assertRaises(ValueError):
            scaffold.apply(self.root, 'vite-react', ['*'])
        self.assertFalse(Path('package.json').exists())
        self.assertEqual(Path('playwright.config.js').read_text(), 'existing')

    def test_template_cli_disabled_without_selection(self):
        Path('owns').write_text('1\t*\n')
        result = subprocess.run([sys.executable, str(LIB / 'scaffold_templates.py'), '--ownership-file', 'owns'],
                                capture_output=True, timeout=5, env=dict(os.environ, WORKFLOW_SCAFFOLD_TEMPLATE=''))
        self.assertEqual(result.returncode, 0)
        self.assertFalse(Path('package.json').exists())

    def test_fast_checks_use_ready_nonwatch_unit_target(self):
        scaffold.apply(self.root, 'vite-react', ['*'])
        self.assertEqual(fast.command(self.root), '')
        Path('src').mkdir()
        Path('src/example.test.jsx').write_text('// fixture')
        self.assertEqual(fast.command(self.root), 'npm run test:unit')
        Path('package.json').write_text('{"scripts":{"test":"vitest"}}')
        self.assertEqual(fast.command(self.root), '')

    def test_fast_checks_are_opt_in_and_surface_failure(self):
        command = '"%s" -c "raise SystemExit(7)"' % sys.executable
        with patch.dict(os.environ, WORKFLOW_STEP_TEST_COMMAND=command):
            self.assertEqual(fast.main('one', 'claude'), 0)
            self.assertEqual(fast.main('one', 'self-hosted'), 0)
            self.assertFalse(Path('.uncle/workflow/logs/step-fast-one.log').exists())
        with patch.dict(os.environ, WORKFLOW_STEP_TESTS='1', WORKFLOW_STEP_TEST_COMMAND=command):
            self.assertEqual(fast.main('two', 'self-hosted'), 7)
            self.assertTrue(Path('.uncle/workflow/logs/step-fast-two.log').exists())
        with patch.dict(os.environ, WORKFLOW_STEP_TESTS='0', WORKFLOW_STEP_TEST_COMMAND=command):
            self.assertEqual(fast.main('three', 'self-hosted'), 0)

    def test_serial_step_failure_prevents_next_step_and_checkpoint(self):
        text = (LIB.parent / 'change-workflow.sh').read_text()
        function = text.split('run_stepwise_implementation() {', 1)[1].split('\n}\n', 1)[0]
        Path('state').mkdir()
        script = """
STATE_DIR=state; MODEL_IMPLEMENT=fake; BUDGET_IMPLEMENT=1
plan_steps() { printf '%s\\n' one two; }
run_supervised_parallel_implementation() { return 2; }
compose_implementation_prompt() { : > "$2"; }
plan_assess() { :; }
check_document_budget() { :; }
require_file() { :; }
python3() { :; }
run_claude() { printf '%s\\n' "$2" >> calls; }
implementation_fast_check() { printf '%s\\n' "$1" >> checks; return 7; }
""" + 'run_stepwise_implementation() {' + function + '\n}\nrun_stepwise_implementation base || exit $?\n'
        result = subprocess.run(['bash', '-c', script], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertEqual(Path('calls').read_text(), 'implementation-step-1\n')
        self.assertEqual(Path('checks').read_text(), 'step-1\n')
        self.assertFalse(Path('state/implement-step-done').exists())

    def test_template_driver_rejects_later_step_ownership(self):
        script = '. "$1/parallel-implement.sh"; ROOT="$2"; STATE_DIR=.uncle/workflow; '                 'plan_step_owns() { printf "2\\t*\\n"; }; implementation_scaffold_template plan'
        env = dict(os.environ, WORKFLOW_SCAFFOLD_TEMPLATE='vite-react')
        result = subprocess.run(['bash', '-c', script, 'fixture', str(LIB), str(LIB.parent.parent)],
                                env=env, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'first-step ownership', result.stderr)
        self.assertFalse(Path('package.json').exists())
        result = subprocess.run(['bash', '-c', script.replace('2\\t', '1\\t'), 'fixture', str(LIB), str(LIB.parent.parent)],
                                env=env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(Path('package.json').exists())

    def test_driver_hooks_precede_step_checkpoints(self):
        shared = (LIB / 'parallel-implement.sh').read_text()
        self.assertIn('implementation_fast_check "group-$*"', shared)
        change = (LIB.parent / 'change-workflow.sh').read_text()
        step = change.split('run_stepwise_implementation() {', 1)[1].split('recover_missing_implementation_reports()', 1)[0]
        # A step skipped as verification-only records its checkpoint early (no code changed, nothing to check);
        # the checkpoint after real work is the last one, and the fast check must come before it.
        self.assertLess(step.index('implementation_fast_check "step-$i"'), step.rindex('printf \'%s\\n\' "$i" > "$done_file"'))
        for driver, plan in [('stagegate.sh', 'UPDATED_PROJECT_PLAN'), ('change-workflow.sh', 'CHANGE_PLAN')]:
            text = (LIB.parent / driver).read_text()
            self.assertIn('implementation_scaffold_template .uncle/docs/' + plan + '.md', text)
            self.assertIn('implementation_fast_check serial', text)


if __name__ == '__main__':
    unittest.main()

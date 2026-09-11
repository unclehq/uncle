#!/usr/bin/env python3
"""Selection-time input gates; all launches are mocked or isolated stubs."""
import json
import os
import queue
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import uncle_tui as tui

INPUTS = {0: 'REQUIREMENTS.md', 2: 'CHANGE_REQUEST.md'}


class MenuInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='menu input ')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.project = self.base / 'project space'
        self.project.mkdir()
        self.ui = tui.UncleTUI.__new__(tui.UncleTUI)
        self.ui.maybe_reload = Mock()
        self.ui.start_workflow = Mock()
        self.ui.prompt_text = ''
        self.ui.color = dict.fromkeys(('title', 'sel', 'accent'), 0)
        self.ui.stdscr = Mock()
        self.root_patch = patch.object(tui, '_project_root', return_value=str(self.project))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def select(self, index):
        self.ui.state, self.ui.sel = 'menu', index
        self.ui._confirm()

    def test_missing_and_nonfiles_block(self):
        for index, name in INPUTS.items():
            path = self.project / name
            for kind in ('missing', 'directory', 'broken', 'denied'):
                with self.subTest(index=index, kind=kind):
                    if kind == 'directory':
                        path.mkdir()
                    elif kind == 'broken':
                        path.symlink_to(self.base / 'absent')
                    with patch('os.stat', side_effect=PermissionError) if kind == 'denied' else patch.object(tui, '_project_root', return_value=str(self.project)):
                        self.select(index)
                    if kind == 'directory':
                        path.rmdir()
                    elif kind == 'broken':
                        path.unlink()
                    self.assertEqual(self.ui.state, 'notice')
                    self.ui.start_workflow.assert_not_called()
                    self.ui.maybe_reload.assert_not_called()
                    self.assertIsNone(self.ui.workflow_idx)
                    self.assertEqual(self.ui.sel, 0)
                    self.assertIn(name + ' is needed', '\n'.join(self.ui.notice_lines))

    def test_presence_empty_and_external_symlinks(self):
        for index, name in INPUTS.items():
            path = self.project / name
            other = self.project / INPUTS[2 - index]
            other.touch()
            self.select(index)
            self.assertEqual(self.ui.state, 'notice')
            other.unlink()
            for kind in ('empty', 'content', 'external_link', 'both'):
                with self.subTest(index=index, kind=kind):
                    if kind == 'external_link':
                        target = self.base / name
                        target.touch()
                        path.symlink_to(target)
                    else:
                        path.write_text('input' if kind == 'content' else '')
                    if kind == 'both':
                        other.touch()
                    self.select(index)
                    self.assertEqual(self.ui.state, 'running')
                    self.assertEqual(self.ui.workflow_idx, index)
                    path.unlink()
                    if other.exists():
                        other.unlink()

    def test_dismiss_retry_and_legacy_notice(self):
        for key in (27, 10, ord('x')):
            self.select(0)
            self.assertIn('menu', self.ui._title())
            self.ui._draw_notice(24, 80)
            rendered = ' '.join(str(c.args) for c in self.ui.stdscr.addnstr.call_args_list)
            self.assertIn('Required input', rendered)
            self.ui.handle_key(key)
            self.assertEqual(self.ui.state, 'menu')
            self.ui.state = 'notice'
            self.assertIn('Configure', self.ui._title())
            self.ui.handle_key(key)
            self.assertEqual(self.ui.state, 'config')
        (self.project / 'REQUIREMENTS.md').touch()
        self.select(0)
        self.ui.start_workflow.assert_called_once()

    def test_issue_selection_precedes_launch(self):
        self.select(1)
        self.assertEqual(self.ui.state, 'issue')
        self.ui.start_workflow.assert_not_called()
        self.ui.input_buf = '123'
        self.ui._confirm_text()
        self.assertEqual(self.ui.state, 'issue_mode')
        self.ui.start_workflow.assert_not_called()
        self.ui._confirm()
        self.ui.start_workflow.assert_called_once()

    def test_issue_new_forwarding(self):
        self.select(1)
        self.ui.input_buf = '123'
        self.ui._confirm_text()
        self.ui.sel = 2
        self.ui._confirm()
        self.ui.start_workflow.assert_called_once()
        self.assertEqual(self.ui.cmd_for()[-2:], ['123', '--new'])
        install, env = self.shell_fixture()
        result = subprocess.run(['bash', str(install / 'uncle')], cwd=self.project,
                                env=env, input='2\n123\nn\nq\n', text=True,
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(env['CALLS']).read_text().splitlines(),
                         [f'from-issue.sh|{self.project}|123 --new'])

    def test_issue_new_seeds_requirements(self):
        install, env = self.shell_fixture()
        shutil.copy2(ROOT / 'scripts/from-issue.sh', install / 'scripts/from-issue.sh')
        url = 'https://github.com/example/project/issues/42'
        body = 'Exact issue body\n\n## Details\nKeep this text.'
        metadata = json.dumps(dict(title='Selected issue', body=body, url=url))
        bin_dir = self.base / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'gh').write_text(
            '#!/bin/bash\n'
            '[[ "$*" == "issue view 42 --repo example/project --json title,body,url,state,labels" ]] '
            '|| { echo unexpected-gh-call >> "$CALLS"; exit 1; }\n'
            "printf '%s\\n' '" + metadata + "'\n")
        (bin_dir / 'curl').write_text(
            '#!/bin/bash\necho unexpected-curl-call >> "$CALLS"\nexit 1\n')
        for stub in bin_dir.iterdir():
            stub.chmod(0o755)
        env.update(PATH=str(bin_dir) + os.pathsep + env['PATH'],
                   UNCLE_PROJECT_ROOT=str(self.project), GIT_CONFIG_NOSYSTEM='1',
                   TMPDIR=str(self.base))
        subprocess.run(['git', 'init', '-q', str(self.project)], env=env, check=True)
        (self.project / 'app.py').write_text('# Existing application\n')
        subprocess.run(['git', '-C', str(self.project), 'add', 'app.py'],
                       env=env, check=True)
        sentinels = {name: (name + ' install sentinel\n').encode() for name in INPUTS.values()}
        for name, content in sentinels.items():
            (install / name).write_bytes(content)
        workflows = [(label, [str(install / 'scripts' / Path(cmd[0]).name)])
                     for label, cmd in tui.WORKFLOWS]
        del self.ui.start_workflow
        self.ui.stage_env = Mock(return_value={})
        self.ui.proc = None
        self.ui.status_path = ''
        real_thread = threading.Thread
        for menu in ('tui', 'shell'):
            for existing in (False, True):
                with self.subTest(menu=menu, existing=existing):
                    brief = self.project / 'REQUIREMENTS.md'
                    brief.unlink(missing_ok=True)
                    request = self.project / 'CHANGE_REQUEST.md'
                    request.unlink(missing_ok=True)
                    sentinel = b'User change request\n\x00Keep exact bytes\n'
                    if existing:
                        request.write_bytes(sentinel)
                    output = ''
                    if menu == 'tui':
                        threads = []
                        self.ui.out_q = queue.Queue()

                        def reader_thread(*args, **kwargs):
                            thread = real_thread(*args, **kwargs)
                            threads.append(thread)
                            return thread

                        deadline = time.monotonic() + 20
                        try:
                            with patch.dict(os.environ, env, clear=True), \
                                    patch.object(tui, 'WORKFLOWS', workflows), \
                                    patch.object(tui.threading, 'Thread', side_effect=reader_thread):
                                self.select(1)
                                self.ui.input_buf = url
                                self.ui._confirm_text()
                                self.ui.sel = 2
                                self.ui._confirm()
                            self.ui.proc.stdin.close()  # Never confirm RUN.
                            code = self.ui.proc.wait(timeout=max(0.01, deadline - time.monotonic()))
                            self.assertEqual(len(threads), 1)
                            threads[0].join(timeout=max(0.01, deadline - time.monotonic()))
                            self.assertFalse(threads[0].is_alive(), 'reader did not reach EOF')
                            chunks = []
                            while not self.ui.out_q.empty():
                                chunks.append(self.ui.out_q.get_nowait())
                            output = ''.join(chunk for chunk in chunks if chunk is not None)
                            self.assertTrue(chunks and chunks[-1] is None, output)
                            self.assertEqual(code, 0, output)
                        finally:
                            if self.ui.proc is not None:
                                if self.ui.proc.poll() is None:
                                    self.ui.proc.kill()
                                self.ui.proc.wait(timeout=20)
                            for thread in threads:
                                thread.join(timeout=20)
                            if self.ui.proc is not None:
                                self.ui.proc.stdin.close()
                                self.ui.proc.stdout.close()
                            if self.ui.status_path:
                                Path(self.ui.status_path).unlink(missing_ok=True)
                            for thread in threads:
                                self.assertFalse(thread.is_alive(), 'reader survived cleanup')
                    else:
                        result = subprocess.run(['bash', str(install / 'uncle')],
                            cwd=self.project, env=env, input='2\n' + url + '\nn\n',
                            text=True, capture_output=True, timeout=20)
                        output = result.stdout + result.stderr
                        self.assertEqual(result.returncode, 0, output)
                    self.assertTrue(brief.is_file(), output)
                    seed = brief.read_text()
                    for expected in ('# Project brief\n', 'Selected issue', body, url):
                        self.assertIn(expected, seed, output)
                    if existing:
                        self.assertEqual(request.read_bytes(), sentinel, output)
                    else:
                        self.assertFalse(os.path.lexists(request), output)
                    for name, content in sentinels.items():
                        self.assertEqual((install / name).read_bytes(), content, output)
                    self.assertFalse((install / '.uncle').exists(), output)
                    self.assertEqual(list((self.project / '.uncle').iterdir()),
                                     [Path(env['UNCLE_CONFIG'])], output)
                    self.assertFalse(Path(env['CALLS']).exists(), output)

    def test_launch_cwd(self):
        self.ui.stage_env = Mock(return_value={})
        self.ui._restore_session_totals = Mock()
        self.ui.cmd_for = Mock(return_value=['stub'])
        with patch.object(tui.subprocess, 'Popen') as popen, patch.object(tui.threading, 'Thread'):
            tui.UncleTUI.start_workflow(self.ui)
        self.addCleanup(lambda: os.unlink(self.ui.status_path))
        self.assertEqual(popen.call_args.kwargs['cwd'], str(self.project))

    def shell_fixture(self, race=False):
        install = self.base / 'install'
        install.mkdir(exist_ok=True)
        shutil.copy2(ROOT / 'uncle', install / 'uncle')
        shutil.copytree(ROOT / 'scripts', install / 'scripts', dirs_exist_ok=True)
        if race:
            shutil.copytree(ROOT / 'prompts', install / 'prompts', dirs_exist_ok=True)
            shutil.copytree(ROOT / 'lib', install / 'lib', dirs_exist_ok=True)
        else:
            for script in ('stagegate.sh', 'change-workflow.sh', 'from-issue.sh'):
                (install / 'scripts' / script).write_text(
                    '#!/bin/bash\ncd "$UNCLE_PROJECT_ROOT" || exit\nprintf "%s|%s|%s\\n" "${0##*/}" "$PWD" "$*" >> "$CALLS"\n')
        config = self.project / '.uncle/config'
        config.parent.mkdir(exist_ok=True)
        config.write_text('requirements.runner kimi\nrequirements.effort medium\n')
        env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin',
               'HOME': str(self.base), 'UNCLE_CONFIG': str(config),
               'CALLS': str(self.base / 'calls'), 'PYTHONDONTWRITEBYTECODE': '1', 'NO_COLOR': '1'}
        return install, env

    def test_shell_missing_retry_eof_and_arguments(self):
        install, env = self.shell_fixture()
        for unattended in (False, True):
            args = ['--unattended'] if unattended else []
            result = subprocess.run(['bash', str(install / 'uncle'), *args], cwd=self.project,
                                    env=env, input='1\n3\n1\n', text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count('REQUIREMENTS.md is needed'), 2)
            self.assertIn('CHANGE_REQUEST.md is needed', result.stdout)
            self.assertFalse(Path(env['CALLS']).exists())
            for name in INPUTS.values():
                (self.project / name).touch()
            result = subprocess.run(['bash', str(install / 'uncle'), *args], cwd=self.project,
                                    env=env, input='1\n3\n2\n123\nc\nq\n', text=True,
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = Path(env['CALLS']).read_text().splitlines()
            self.assertEqual(calls, [
                f'stagegate.sh|{self.project}|{" ".join(args)}',
                f'change-workflow.sh|{self.project}|{" ".join(args)}',
                f'from-issue.sh|{self.project}|123 --change'])
            Path(env['CALLS']).unlink()
            for name in INPUTS.values():
                (self.project / name).unlink()

    def test_shell_file_types_and_auto_mode(self):
        install, env = self.shell_fixture()
        with Path(env['UNCLE_CONFIG']).open('a') as config:
            config.write('misc.auto_mode true\n')
        for index, name in INPUTS.items():
            path = self.project / name
            for kind in ('directory', 'broken', 'external_link', 'empty'):
                with self.subTest(index=index, kind=kind):
                    if kind == 'directory':
                        path.mkdir()
                    elif kind == 'broken':
                        path.symlink_to(self.base / 'absent')
                    elif kind == 'external_link':
                        target = self.base / name
                        target.touch()
                        path.symlink_to(target)
                    else:
                        path.touch()
                    result = subprocess.run(['bash', str(install / 'uncle')], cwd=self.project,
                        env=env, input=f'{index + 1}\nq\n', text=True,
                        capture_output=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    calls = Path(env['CALLS'])
                    if kind in ('directory', 'broken'):
                        self.assertIn(name + ' is needed', result.stdout)
                        self.assertFalse(calls.exists())
                    else:
                        driver = 'stagegate.sh' if index == 0 else 'change-workflow.sh'
                        self.assertEqual(calls.read_text().strip(),
                                         f'{driver}|{self.project}|--unattended')
                        calls.unlink()
                    if kind == 'directory':
                        path.rmdir()
                    else:
                        path.unlink()

    def test_selection_race_actual_drivers(self):
        install, env = self.shell_fixture(race=True)
        stub = self.base / 'agent-stub'
        stub.write_text('#!/bin/bash\n[ ! -e REQUIREMENTS.md ] || exit 98\nprintf "agent|%s\\n" "$PWD" >> "$CALLS"\nexit 73\n')
        stub.chmod(0o755)
        env.update(WORKFLOW_AGENT_CMD=str(stub), WORKFLOW_REVIEWER_CMD=str(stub),
                   UNCLE_PROJECT_ROOT=str(self.project))
        hook = self.base / 'race-hook'
        hook.write_text("trap 'case \"$BASH_COMMAND\" in run_new_application) rm -f \"$UNCLE_PROJECT_ROOT/REQUIREMENTS.md\" ;; run_change_workflow) rm -f \"$UNCLE_PROJECT_ROOT/CHANGE_REQUEST.md\" ;; esac' DEBUG\n")
        for menu in ('tui', 'shell'):
            for index, filename in INPUTS.items():
                with self.subTest(menu=menu, index=index):
                    shutil.rmtree(self.project / '.uncle/workflow', ignore_errors=True)
                    calls = Path(env['CALLS'])
                    calls.unlink(missing_ok=True)
                    path = self.project / filename
                    path.write_text('input')
                    if menu == 'shell':
                        result = subprocess.run(['bash', str(install / 'uncle')],
                            cwd=self.project, env=dict(env, BASH_ENV=str(hook)),
                            input=str(index + 1) + '\n', text=True,
                            capture_output=True, timeout=30)
                    else:
                        results = []
                        def launch():
                            path.unlink()
                            driver = 'stagegate.sh' if index == 0 else 'change-workflow.sh'
                            results.append(subprocess.run(['bash', str(install / 'scripts' / driver)],
                                cwd=self.project, env=env, input='', text=True,
                                capture_output=True, timeout=30))
                        self.ui.start_workflow = Mock(side_effect=launch)
                        self.select(index)
                        self.ui.start_workflow.assert_called_once()
                        result = results[0]
                    self.assertFalse(path.exists())
                    if index == 0:
                        self.assertTrue(calls.exists(), result.stdout + result.stderr)
                        self.assertEqual(calls.read_text().strip(), f'agent|{self.project}')
                        self.assertEqual(result.returncode, 0 if menu == 'shell' else 73, result.stdout + result.stderr)
                        if menu == 'shell':
                            self.assertIn('exited with status 73', result.stdout)
                    else:
                        self.assertFalse(calls.exists(), result.stdout + result.stderr)
                        self.assertEqual(result.returncode, 0 if menu == 'shell' else 1, result.stdout + result.stderr)
                        if menu == 'shell':
                            self.assertIn('exited with status 1', result.stdout)
                        self.assertIn('CHANGE_REQUEST.md', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()

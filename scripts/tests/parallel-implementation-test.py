"""The supervised parallel executor merges only declared files and cleans success."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
EXECUTOR = ROOT / 'scripts/lib/parallel_steps.py'


class ParallelImplementationTests(unittest.TestCase):
    def test_stream_json_string_error_flag_is_parsed_as_a_boolean(self):
        """A Codex ``is_error: \"false\"`` result must not make a red dot."""
        sys.path.insert(0, str(ROOT / 'scripts/lib'))
        import parallel_steps
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'worker.jsonl'
            log.write_text(json.dumps({'type': 'result', 'is_error': 'false', 'usage': {}}) + '\n')
            self.assertFalse(parallel_steps.extract_usage(log)['reported_error'])
            log.write_text(json.dumps({'type': 'result', 'is_error': 'true', 'usage': {}}) + '\n')
            self.assertTrue(parallel_steps.extract_usage(log)['reported_error'])

    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
        subprocess.run(['git', 'config', 'commit.gpgsign', 'false'], cwd=root, check=True)
        (root / 'a.txt').write_text('base\n')
        (root / 'b.txt').write_text('base\n')
        subprocess.run(['git', 'add', '.'], cwd=root, check=True)
        subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
                        'commit', '--no-gpg-sign', '-qm', 'fixture'], cwd=root, check=True)
        worker = root / 'worker.sh'
        worker.write_text(
            '#!/usr/bin/env bash\nset -euo pipefail\n'
            'n="$1"\nprintf "step-%s\\n" "$n" > "${n}.txt"\n'
            'mkdir -p .uncle/workflow/parallel/notes\n'
            'printf "step %s handoff\\n" "$n" > ".uncle/workflow/parallel/notes/step-${n}.md"\n')
        worker.chmod(0o755)
        return temp, root, worker

    def prewarmed_run(self, change=None):
        """Prewarm step 1's sandbox, drop a marker file in it, optionally change the tree, then run the group."""
        temp, root, _ = self.fixture()
        worker = root / 'prewarm-worker.sh'
        worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\nn="$1"\n'
                          'if [ -e early-sentinel ]; then echo reused > "${n}.txt"; else echo rebuilt > "${n}.txt"; fi\n')
        with temp:
            pre = subprocess.run([sys.executable, str(EXECUTOR), 'prewarm', str(root), '1'], cwd=root, text=True, capture_output=True)
            self.assertEqual(pre.returncode, 0, pre.stderr)
            sandbox = root / '.uncle/workflow/parallel/step-1'
            self.assertTrue(sandbox.is_dir())
            self.assertTrue((root / '.uncle/workflow/parallel/prewarm.json').is_file())
            (sandbox / 'early-sentinel').write_text('x')
            (root / '.uncle/docs').mkdir(parents=True, exist_ok=True)
            (root / '.uncle/docs/UPDATED_PROJECT_PLAN.md').write_text('final plan\n')     # written after the sandbox was made
            if change:
                change(root)
            request = {'project': str(root), 'owned': {'1': ['1.txt']},
                       'steps': [{'number': 1, 'log': str(root / 'one.log'), 'note': '.uncle/workflow/parallel/notes/step-1.md',
                                  'command': ['bash', str(worker), '1']}]}
            path = Path(tempfile.mkdtemp()) / 'request.json'     # outside the tree: a new file in it is a changed tree
            path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return (root / '1.txt').read_text().strip(), (root / '.uncle/workflow/parallel/prewarm.json').exists()

    def test_a_sandbox_made_early_is_used_when_the_tree_has_not_changed(self):
        text, marker = self.prewarmed_run()
        self.assertEqual(text, 'reused')
        self.assertFalse(marker)

    def test_the_plan_written_after_the_sandbox_was_made_reaches_it(self):
        temp, root, _ = self.fixture()
        with temp:
            subprocess.run([sys.executable, str(EXECUTOR), 'prewarm', str(root), '1'], cwd=root, check=True)
            sandbox = root / '.uncle/workflow/parallel/step-1'
            (root / '.uncle/docs').mkdir(parents=True, exist_ok=True)
            (root / '.uncle/docs/UPDATED_PROJECT_PLAN.md').write_text('final plan\n')
            (sandbox / 'early-sentinel').write_text('x')
            worker = Path(tempfile.mkdtemp()) / 'w.sh'
            worker.write_text('#!/usr/bin/env bash\ntest -e early-sentinel || exit 7\ncp .uncle/docs/UPDATED_PROJECT_PLAN.md 1.txt\n')
            request = {'project': str(root), 'owned': {'1': ['1.txt']},
                       'steps': [{'number': 1, 'log': str(root / 'l.log'), 'note': '.uncle/workflow/parallel/notes/step-1.md',
                                  'command': ['bash', str(worker)]}]}
            req = Path(tempfile.mkdtemp()) / 'r.json'
            req.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(req)], cwd=root, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / '1.txt').read_text(), 'final plan\n')
            self.assertTrue(sandbox.parent.exists())

    def test_a_changed_tree_discards_the_early_sandbox_and_makes_a_fresh_one(self):
        text, marker = self.prewarmed_run(lambda root: (root / 'a.txt').write_text('changed after the sandbox was made\n'))
        self.assertEqual(text, 'rebuilt')
        self.assertFalse(marker)

    def test_refresh_overlay_copies_dirty_application_inputs(self):
        """A later group must baseline the previous group's dirty files.

        In particular, a stale .gitignore used to be reported as a write by
        every later test worker, aborting the fan-out and causing a full serial
        implementation retry.
        """
        temp, root, _ = self.fixture()
        with temp:
            sys.path.insert(0, str(ROOT / 'scripts/lib'))
            import parallel_steps
            sandbox = root / 'sandbox'
            sandbox.mkdir()
            (root / '.gitignore').write_text('.test-out/\n')
            (sandbox / '.gitignore').write_text('.uncle\n')
            parallel_steps.refresh_overlay(root, sandbox)
            self.assertEqual((sandbox / '.gitignore').read_text(), '.test-out/\n')

    def test_a_moved_head_discards_the_early_sandbox(self):
        def commit(root):
            (root / 'a.txt').write_text('base\n')
            (root / 'c.txt').write_text('new\n')
            subprocess.run(['git', 'add', '.'], cwd=root, check=True)
            subprocess.run(['git', '-c', 'user.name=F', '-c', 'user.email=f@example.test', 'commit', '--no-gpg-sign', '-qm', 'more'],
                           cwd=root, check=True)
        text, _ = self.prewarmed_run(commit)
        self.assertEqual(text, 'rebuilt')

    def test_merges_declared_files_captures_notes_and_removes_worktrees(self):
        temp, root, worker = self.fixture()
        with temp:
            request = {
                'project': str(root),
                'owned': {'1': ['1.txt'], '2': ['2.txt']},
                'steps': [
                    {'number': 1, 'log': str(root / 'one.log'),
                     'note': '.uncle/workflow/parallel/notes/step-1.md',
                     'command': ['bash', str(worker), '1']},
                    {'number': 2, 'log': str(root / 'two.log'),
                     'note': '.uncle/workflow/parallel/notes/step-2.md',
                     'command': ['bash', str(worker), '2']},
                ],
            }
            path = root / 'request.json'
            path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['merged'], [1, 2])
            self.assertEqual(summary['worktrees'], 'removed')
            self.assertEqual(set(summary['step_seconds']), {'1', '2'})
            self.assertEqual((root / '1.txt').read_text(), 'step-1\n')
            self.assertEqual((root / '2.txt').read_text(), 'step-2\n')
            self.assertTrue((root / '.uncle/workflow/parallel/notes/step-1.md').is_file())
            self.assertFalse((root / '.uncle/workflow/parallel/step-1').exists())
            self.assertFalse((root / '.uncle/workflow/parallel/step-2').exists())

    def test_merges_the_declared_uncle_launch_manifest(self):
        """The launch manifest is application output, not disposable state.

        Keeping all of `.uncle/` out of snapshots made a correctly declared
        scaffold step look as though it had produced no launch manifest.  The
        later serial fallback then repeated the whole implementation.
        """
        temp, root, _ = self.fixture()
        with temp:
            worker = root / 'launch-worker.sh'
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'mkdir -p .uncle\n'
                "printf '{\\\"kind\\\":\\\"webpage\\\"}\\n' > .uncle/launch.json\n")
            worker.chmod(0o755)
            request = {'project': str(root), 'owned': {'1': ['.uncle/launch.json']}, 'steps': [
                {'number': 1, 'log': str(root / 'launch.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.json',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((root / '.uncle/launch.json').read_text())['kind'], 'webpage')

    def test_many_sandboxes_are_made_together_and_leave_out_driver_state(self):
        sys.path.insert(0, str(ROOT / 'scripts/lib'))
        import parallel_steps
        import triage_guard
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'src/app.js').write_text('app\n')
            (root / '.uncle/docs').mkdir(parents=True)
            (root / '.uncle/docs/PLAN.md').write_text('plan\n')
            for name in ('performance', 'metrics', 'updated-plan-edits', 'read-cache'):
                (root / '.uncle/workflow' / name).mkdir(parents=True)
                (root / '.uncle/workflow' / name / 'big.json').write_text('{}')
            (root / '.uncle/workflow/documents').mkdir(parents=True)
            (root / '.uncle/workflow/documents/PLAN.json').write_text('{}')
            worker = root / 'worker.sh'
            worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\nprintf "x\\n" > "$1.txt"\n')
            steps = [{'number': n, 'log': str(root / ('s%d.log' % n)), 'command': ['bash', str(worker), str(n)]}
                     for n in range(1, 9)]
            request = {'project': str(root), 'owned': {str(n): ['%d.txt' % n] for n in range(1, 9)}, 'steps': steps}
            path = root / 'request.json'
            path.write_text(json.dumps(request))
            seen = []
            real = triage_guard.make_sandbox

            def spy(project, sandbox, extra=()):
                seen.append(tuple(extra))
                result = real(project, sandbox, extra)
                if len(seen) == 1:      # inspect one finished mirror while the run is still going
                    sandboxes.append(Path(sandbox))
                    self.assertTrue((Path(sandbox) / 'src/app.js').is_file())
                    self.assertTrue((Path(sandbox) / '.uncle/docs/PLAN.md').is_file())
                    self.assertTrue((Path(sandbox) / '.uncle/workflow/documents/PLAN.json').is_file())
                    for name in ('performance', 'metrics', 'updated-plan-edits', 'read-cache'):
                        self.assertFalse((Path(sandbox) / '.uncle/workflow' / name).exists(), name)
                return result

            sandboxes = []
            old_argv, parallel_steps.make_sandbox = sys.argv, spy
            sys.argv = ['parallel_steps.py', str(path)]
            try:
                import io, contextlib
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = parallel_steps.main()
            finally:
                sys.argv, parallel_steps.make_sandbox = old_argv, real
            self.assertEqual(code, 0)
            self.assertEqual(len(seen), 8)
            self.assertTrue(all(extra == parallel_steps.STEP_EXCLUDES for extra in seen))
            self.assertEqual(json.loads(out.getvalue())['merged'], list(range(1, 9)))
            for n in range(1, 9):
                self.assertEqual((root / ('%d.txt' % n)).read_text(), 'x\n')

    def test_a_sandbox_that_cannot_be_made_stops_the_group_with_code_2(self):
        sys.path.insert(0, str(ROOT / 'scripts/lib'))
        import parallel_steps
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.txt').write_text('base\n')
            request = {'project': str(root), 'owned': {'1': ['1.txt']},
                       'steps': [{'number': 1, 'log': str(root / 'one.log'), 'command': ['true']}]}
            path = root / 'request.json'
            path.write_text(json.dumps(request))

            def broken(project, sandbox, extra=()):
                raise OSError('no space left')

            real, old_argv, parallel_steps.make_sandbox = parallel_steps.make_sandbox, sys.argv, broken
            sys.argv = ['parallel_steps.py', str(path)]
            try:
                self.assertEqual(parallel_steps.main(), 2)
            finally:
                sys.argv, parallel_steps.make_sandbox = old_argv, real

    def test_unborn_or_plain_project_uses_copy_sandboxes_without_recursion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.txt').write_text('base\n')
            # A failed earlier fan-out may leave a preserved parallel.* tree.
            # It must never be copied into the next worker sandbox.
            stale = root / '.uncle/workflow/parallel.failed-old'
            stale.mkdir(parents=True)
            (stale / 'large-stale-artifact').write_text('do not copy\n')
            (root / '.pw-browsers').mkdir()
            (root / '.pw-browsers' / 'browser-cache').write_text('do not copy\n')
            (root / 'node_modules').mkdir()
            (root / 'node_modules' / 'dependency-cache').write_text('do not copy\n')
            worker = root / 'worker.sh'
            worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\n'
                              'test ! -e .pw-browsers\n'
                              'test ! -e node_modules\n'
                              'printf copied > a.txt\n'
                              'mkdir -p .uncle/workflow/parallel/notes\n'
                              'printf handoff > .uncle/workflow/parallel/notes/step-1.md\n')
            worker.chmod(0o755)
            request = {'project': str(root), 'owned': {'1': ['a.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'a.txt').read_text(), 'copied')

    def test_missing_agent_handoff_is_synthesized_without_blocking_merge(self):
        temp, root, worker = self.fixture()
        with temp:
            worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\nprintf changed > 1.txt\n')
            request = {'project': str(root), 'owned': {'1': ['1.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / '1.txt').read_text(), 'changed')
            handoff = json.loads((root / '.uncle/workflow/parallel/notes/step-1.md').read_text())
            self.assertEqual(handoff['kind'], 'implementation-notes-fragment')
            self.assertEqual([row['path'] for row in handoff['changed_files']], ['1.txt'])
            self.assertEqual(handoff['changed_files'][0]['plan_step'], '1')
            self.assertIn('synthesized', result.stderr)

    def test_a_sandbox_does_not_copy_scratch_and_generated_output(self):
        sys.path.insert(0, str(ROOT / 'scripts/lib'))
        import triage_guard
        temp, root, worker = self.fixture()
        with temp:
            for name in ('.inject-scratch', '.uncle-scratch', '.verify-out', 'dist', 'test-results'):
                (root / name).mkdir()
                (root / name / 'big.bin').write_text('x' * 1000)
            (root / 'src').mkdir()
            (root / 'src' / 'keep.js').write_text('kept')
            sandbox = root / '.uncle' / 'workflow' / 'parallel' / 'step-9'
            triage_guard.make_sandbox(root, sandbox)
            self.assertTrue((sandbox / 'src' / 'keep.js').is_file())
            for name in ('.inject-scratch', '.uncle-scratch', '.verify-out', 'dist', 'test-results'):
                self.assertFalse((sandbox / name).exists(), name)
            triage_guard.drop_sandbox(root, sandbox)

    def test_a_file_the_project_already_holds_unchanged_is_not_a_step_write(self):
        """A step that rewrites .gitignore un-ignores old leftovers, which then appear in the `after`
        snapshot but not the `before` one; with the project's own bytes behind them they are not writes."""
        sys.path.insert(0, str(ROOT / 'scripts/lib'))
        import hashlib
        import parallel_steps
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / '.scratch').mkdir()
            (project / '.scratch' / 'old.txt').write_text('left over')
            (project / 'kept.txt').write_text('same')
            digest = lambda text: hashlib.sha256(text.encode()).hexdigest()
            after = {'.scratch/old.txt': digest('left over'), 'kept.txt': digest('same'),
                     '1.txt': digest('new'), 'edited.txt': digest('edit')}
            (project / 'edited.txt').write_text('orig')
            before = {'edited.txt': digest('orig'), 'kept.txt': digest('same')}
            self.assertEqual(parallel_steps.changed(before, after, project), {'1.txt', 'edited.txt'})
            self.assertEqual(parallel_steps.changed(before, after), {'.scratch/old.txt', '1.txt', 'edited.txt'})

    def test_a_new_file_with_other_bytes_than_the_project_is_still_a_write(self):
        sys.path.insert(0, str(ROOT / 'scripts/lib'))
        import hashlib
        import parallel_steps
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'x.txt').write_text('project bytes')
            after = {'x.txt': hashlib.sha256(b'step bytes').hexdigest()}
            self.assertEqual(parallel_steps.changed({}, after, tmp), {'x.txt'})

    def test_the_synthesized_fragment_renders_in_the_notes_like_an_agent_written_one(self):
        temp, root, worker = self.fixture()
        with temp:
            worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\nprintf changed > 1.txt\n')
            request = {'project': str(root), 'owned': {'1': ['1.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.json', 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root, text=True, capture_output=True, check=True)
            sys.path.insert(0, str(ROOT / 'scripts/lib'))
            import implementation_notes
            (root / '.uncle/docs').mkdir(parents=True, exist_ok=True)
            rendered = implementation_notes.append(str(root), str(root / '.uncle/workflow/parallel/notes/step-1.json'),
                                                   '.uncle/docs/IMPLEMENTATION_NOTES.md', 'Isolated step 1')
            self.assertIn('1.txt', rendered)
            self.assertNotIn('raw_markdown', rendered)

    def test_workers_are_told_to_skip_exploration_checks_and_routine_notes(self):
        driver = (ROOT / 'scripts/stagegate.sh').read_text()
        block = driver[driver.index('## Speed (binding)'):driver.index('## Isolated ownership boundary')]
        for phrase in ('Do not run `ls`', 'parallel Write calls', 'Do not run tests, builds or checks',
                       'unless this step has a deviation'):
            self.assertIn(phrase, block + driver[driver.index('Do not write an implementation-notes fragment'):][:400])
        self.assertNotIn('Run a narrow check', driver)
        self.assertIn('## Exact owned paths (binding)', driver)
        self.assertIn('plan_step_owns .uncle/docs/UPDATED_PROJECT_PLAN.md', driver)

    def test_inherited_dirty_gitignore_is_not_a_later_step_write(self):
        """A prior merged step may leave an uncommitted .gitignore behind.
        The next sandbox inherits it, but ownership checking must compare to
        its own pre-worker snapshot rather than Git HEAD or another step."""
        temp, root, worker = self.fixture()
        with temp:
            (root / '.gitignore').write_text('dist/\n')
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'printf changed > 2.txt\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf handoff > .uncle/workflow/parallel/notes/step-2.md\n')
            worker.chmod(0o755)
            request = {'project': str(root), 'owned': {'2': ['2.txt']}, 'steps': [
                {'number': 2, 'log': str(root / 'two.log'),
                 'note': '.uncle/workflow/parallel/notes/step-2.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / '2.txt').read_text(), 'changed')
            self.assertNotIn('.gitignore', json.loads(result.stdout)['files'])

    def test_worker_completion_uses_the_normal_persisted_metrics_path(self):
        temp, root, worker = self.fixture()
        with temp:
            request = {'project': str(root), 'owned': {'1': ['1.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker), '1']} ]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            records = list((root / '.uncle/workflow/metrics').glob('parallel-worker-*.json'))
            self.assertEqual(len(records), 1)
            row = json.loads(records[0].read_text())
            self.assertEqual((row['stage'], row['process_exit']), ('implementation-step-1', 0))
            self.assertIn(row, json.loads((root / '.uncle/workflow/session-totals.json').read_text())['records'])

    def test_gitignored_setup_output_does_not_abort_the_merge(self):
        # A step's own `npm install`-equivalent fills a gitignored directory
        # with files no plan step declared ownership of. That used to abort
        # the whole group -- "the plan's file ownership was wrong" -- for a
        # directory nobody was ever meant to own.
        temp, root, worker = self.fixture()
        with temp:
            (root / '.gitignore').write_text('vendor/\n')
            subprocess.run(['git', 'add', '.gitignore'], cwd=root, check=True)
            subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
                            'commit', '--no-gpg-sign', '-qm', 'gitignore'], cwd=root, check=True)
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'printf changed > 1.txt\n'
                'mkdir -p vendor/some-package\n'
                'printf "installed\\n" > vendor/some-package/file.js\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf handoff > .uncle/workflow/parallel/notes/step-1.md\n')
            request = {'project': str(root), 'owned': {'1': ['1.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['merged'], [1])
            self.assertEqual((root / '1.txt').read_text(), 'changed')
            self.assertNotIn('vendor/some-package/file.js', summary['files'])
            self.assertFalse((root / 'vendor').exists(), 'ignored setup output is not copied back')

    def test_gitignored_setup_output_in_an_unborn_repo_does_not_abort_the_merge(self):
        # A greenfield build's project has a `.git` (from `git init`) but no
        # commits yet -- `git rev-parse HEAD` fails, so make_sandbox uses a
        # plain file copy with no `.git` of its own. ignored_prefixes must
        # fall back to the project's own status in that case, not just
        # return empty because the sandbox itself isn't a git repository.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / '.gitignore').write_text('vendor/\n')
            (root / '1.txt').write_text('base\n')
            worker = root / 'worker.sh'
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'printf changed > 1.txt\n'
                'mkdir -p vendor/some-package\n'
                'printf "installed\\n" > vendor/some-package/file.js\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf handoff > .uncle/workflow/parallel/notes/step-1.md\n')
            worker.chmod(0o755)
            request = {'project': str(root), 'owned': {'1': ['1.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['merged'], [1])
            self.assertEqual((root / '1.txt').read_text(), 'changed')
            self.assertNotIn('vendor/some-package/file.js', summary['files'])
            self.assertFalse((root / 'vendor').exists(), 'ignored setup output is not copied back')

    def test_gitignoring_uncle_itself_does_not_break_the_ignore_exclusion(self):
        # A real run: the project's own .gitignore listed `.uncle/` (uncle's
        # own scratch directory -- reasonable hygiene), and the sandbox is an
        # unborn-repo plain copy nested inside it (project/.uncle/workflow/
        # parallel/step-N). Running `git status` from a cwd that is itself
        # inside an already-ignored directory tree made git report paths
        # relative to that cwd, not the repo root the code assumed -- so the
        # required prefix never matched, the exclusion silently did nothing,
        # and a step's own `npm install` flooded the merge with every path
        # under `node_modules/` as an "undeclared" write.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / '.gitignore').write_text('node_modules/\n.uncle/\n.uncle\n')
            (root / '1.txt').write_text('base\n')
            worker = root / 'worker.sh'
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'printf changed > 1.txt\n'
                'mkdir -p node_modules/some-package\n'
                'printf "installed\\n" > node_modules/some-package/file.js\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf handoff > .uncle/workflow/parallel/notes/step-1.md\n')
            worker.chmod(0o755)
            request = {'project': str(root), 'owned': {'1': ['1.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['merged'], [1])
            self.assertEqual((root / '1.txt').read_text(), 'changed')
            self.assertNotIn('node_modules/some-package/file.js', summary['files'])
            self.assertFalse((root / 'node_modules').exists(), 'ignored setup output is not copied back')

    def test_svelte_dist_output_never_aborts_the_merge_even_before_gitignore_says_so(self):
        # A real run: a step scaffolded a Svelte app and built it in the same
        # pass ("npm create vite@latest -- --template svelte" then a build),
        # writing dist/ before .gitignore had any chance to mention it --
        # waiting on .gitignore alone catches this one merge failure too
        # late. This must hold with no .gitignore at all.
        temp, root, worker = self.fixture()
        with temp:
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'printf changed > 1.txt\n'
                'printf \'{"devDependencies":{"svelte":"^4.0.0","vite":"^5.0.0"}}\' > package.json\n'
                'mkdir -p dist/assets\n'
                'printf "<html></html>" > dist/index.html\n'
                'printf "body{}" > dist/assets/index.css\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf handoff > .uncle/workflow/parallel/notes/step-1.md\n')
            request = {'project': str(root), 'owned': {'1': ['1.txt', 'package.json']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['merged'], [1])
            self.assertEqual((root / '1.txt').read_text(), 'changed')
            self.assertFalse(any(f.startswith('dist/') for f in summary['files']))
            self.assertFalse((root / 'dist').exists(), 'a framework build output dir is not copied back')

    def test_non_svelte_project_is_unaffected_by_the_svelte_dist_rule(self):
        temp, root, worker = self.fixture()
        with temp:
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'printf changed > 1.txt\n'
                'printf \'{"dependencies":{"react":"^18.0.0"}}\' > package.json\n'
                'mkdir -p dist\n'
                'printf "<html></html>" > dist/index.html\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf handoff > .uncle/workflow/parallel/notes/step-1.md\n')
            request = {'project': str(root), 'owned': {'1': ['1.txt', 'package.json']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 3, 'a non-Svelte project must still require dist/ to be declared')

    def test_worker_announces_itself_before_running_not_only_after(self):
        # Without a start event a fan-out group looks idle for its whole run:
        # the only signal was the one-shot completion record at the end.
        temp, root, worker = self.fixture()
        with temp:
            status_file = root / 'status.jsonl'
            request = {'project': str(root), 'owned': {'1': ['1.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker), '1']}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            env = dict(os.environ, UNCLE_STATUS_FILE=str(status_file))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            events = [json.loads(line) for line in status_file.read_text().splitlines()]
            starts = [e for e in events if e.get('event') == 'start']
            self.assertEqual([e['stage'] for e in starts], ['implementation-step-1'])

    def test_worker_completion_reports_real_usage_not_permanently_unavailable(self):
        temp, root, worker = self.fixture()
        with temp:
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'n="$1"\nprintf "step-%s\\n" "$n" > "${n}.txt"\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf "step %s handoff\\n" "$n" > ".uncle/workflow/parallel/notes/step-${n}.md"\n'
                'printf \'{"type":"result","is_error":false,"total_cost_usd":0.05,'
                '"usage":{"input_tokens":100,"output_tokens":50,"total_tokens":150}}\\n\'\n')
            worker.chmod(0o755)
            request = {'project': str(root), 'owned': {'1': ['1.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker), '1']}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            records = list((root / '.uncle/workflow/metrics').glob('parallel-worker-*.json'))
            row = json.loads(records[0].read_text())
            self.assertEqual(row['input_tokens'], 100)
            self.assertEqual(row['output_tokens'], 50)
            self.assertEqual(row['reported_total_tokens'], 150)
            self.assertEqual(row['reported_cost_usd'], 0.05)

    def test_step_scaffolding_a_manifest_may_also_write_its_lockfile(self):
        # A real run: a step declared to own only `package.json` legitimately
        # ran `npm install`, which also wrote `package-lock.json` -- a
        # deterministic byproduct of the manifest it already owns, not new
        # scope. The merge must not abort over it.
        temp, root, worker = self.fixture()
        with temp:
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'printf \'{"name":"app"}\' > package.json\n'
                'printf \'{"lockfileVersion":3}\' > package-lock.json\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf handoff > .uncle/workflow/parallel/notes/step-1.md\n')
            request = {'project': str(root), 'owned': {'1': ['package.json']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['merged'], [1])
            self.assertIn('package-lock.json', summary['files'])
            self.assertEqual((root / 'package-lock.json').read_text(), '{"lockfileVersion":3}')

    def test_a_glob_owns_token_covers_the_matching_file_it_writes(self):
        # A real run: CHANGE_PLAN.md declared step 9 as owning
        # `scripts/tests/*.sh`, and the step wrote
        # `scripts/tests/checklist-groups-test.sh`. covers() did not
        # understand glob tokens and rejected the legitimate write as
        # undeclared, aborting a merge whose partition was actually correct.
        temp, root, worker = self.fixture()
        with temp:
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'mkdir -p scripts/tests\n'
                'printf \'#!/usr/bin/env bash\\n\' > scripts/tests/checklist-groups-test.sh\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf handoff > .uncle/workflow/parallel/notes/step-1.md\n')
            request = {'project': str(root), 'owned': {'1': ['scripts/tests/*.sh']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['merged'], [1])
            self.assertIn('scripts/tests/checklist-groups-test.sh', summary['files'])

    def test_an_undeclared_file_that_is_not_a_lockfile_still_aborts_the_merge(self):
        # The lockfile inference must stay narrow: a step writing something
        # the plan never mentioned at all -- not a manifest's own lockfile --
        # is still a real ownership violation.
        temp, root, worker = self.fixture()
        with temp:
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'printf \'{"name":"app"}\' > package.json\n'
                'printf "ignored\\n" > .gitignore\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf handoff > .uncle/workflow/parallel/notes/step-1.md\n')
            request = {'project': str(root), 'owned': {'1': ['package.json']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker)]}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 3)
            self.assertIn('.gitignore', result.stderr)

    def test_files_allowlist_exempts_a_manifest_no_step_declared(self):
        # The real failure this covers: step 1 declared and wrote
        # package.json/package-lock.json from its scaffold. Step 2 owns
        # something unrelated but its own `npm install` (adding test
        # tooling) also rewrote both files, which it never declared. Without
        # an allowlist that aborts the whole group even though both steps'
        # work is otherwise sound. supervision.files_allowlist exempts these
        # specific paths from the ownership check for every step, not just
        # the one that declared them.
        temp, root, worker = self.fixture()
        with temp:
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'n="$1"\n'
                'printf \'{"name":"app","step":"%s"}\' "$n" > package.json\n'
                'printf \'{"lockfileVersion":3,"step":"%s"}\' "$n" > package-lock.json\n'
                'printf "step-%s\\n" "$n" > "${n}.txt"\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf "step %s handoff\\n" "$n" > ".uncle/workflow/parallel/notes/step-${n}.md"\n')
            request = {'project': str(root), 'owned': {'1': ['1.txt'], '2': ['2.txt']},
                      'files_allowlist': ['package.json', 'package-lock.json', 'vite.config.js'],
                      'steps': [
                          {'number': 1, 'log': str(root / 'one.log'),
                           'note': '.uncle/workflow/parallel/notes/step-1.md',
                           'command': ['bash', str(worker), '1']},
                          {'number': 2, 'log': str(root / 'two.log'),
                           'note': '.uncle/workflow/parallel/notes/step-2.md',
                           'command': ['bash', str(worker), '2']}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['merged'], [1, 2])
            self.assertIn('package.json', summary['files'])
            self.assertEqual(json.loads((root / 'package.json').read_text())['step'], '2')

    def test_without_files_allowlist_the_same_collision_still_aborts(self):
        # The allowlist must be opt-in via config, not automatic: an
        # otherwise-identical request that omits files_allowlist keeps the
        # existing protective refusal.
        temp, root, worker = self.fixture()
        with temp:
            worker.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                'n="$1"\n'
                'printf \'{"name":"app","step":"%s"}\' "$n" > package.json\n'
                'printf "step-%s\\n" "$n" > "${n}.txt"\n'
                'mkdir -p .uncle/workflow/parallel/notes\n'
                'printf "step %s handoff\\n" "$n" > ".uncle/workflow/parallel/notes/step-${n}.md"\n')
            request = {'project': str(root), 'owned': {'1': ['1.txt'], '2': ['2.txt']}, 'steps': [
                {'number': 1, 'log': str(root / 'one.log'),
                 'note': '.uncle/workflow/parallel/notes/step-1.md',
                 'command': ['bash', str(worker), '1']},
                {'number': 2, 'log': str(root / 'two.log'),
                 'note': '.uncle/workflow/parallel/notes/step-2.md',
                 'command': ['bash', str(worker), '2']}]}
            path = root / 'request.json'; path.write_text(json.dumps(request))
            result = subprocess.run([sys.executable, str(EXECUTOR), str(path)], cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 3)
            self.assertIn('package.json', result.stderr)


if __name__ == '__main__':
    unittest.main()

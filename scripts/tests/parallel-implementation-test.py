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
            handoff = (root / '.uncle/workflow/parallel/notes/step-1.md').read_text()
            self.assertIn('synthesized by the driver', handoff)

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

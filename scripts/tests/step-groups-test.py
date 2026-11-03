#!/usr/bin/env python3
"""covers() decides whether a step's declared ownership accounts for a written
path. A step that owns a manifest also owns its lockfile -- a real merge
aborted repeatedly over `package-lock.json` beside a declared `package.json`,
which is not new scope, just an inseparable byproduct of installing what the
plan already authorized."""
import importlib.util
import os
from pathlib import Path
import sys
import unittest
import unittest.mock

spec = importlib.util.spec_from_file_location('step_groups', Path(__file__).resolve().parents[1] / 'lib/step_groups.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
covers = module.covers


class CoversTests(unittest.TestCase):
    def test_exact_and_directory_tokens_unchanged(self):
        self.assertTrue(covers({'a.txt'}, 'a.txt'))
        self.assertFalse(covers({'a.txt'}, 'b.txt'))
        self.assertTrue(covers({'src/'}, 'src/calc.js'))
        self.assertTrue(covers({'src'}, 'src/calc.js'))
        self.assertTrue(covers({'*'}, 'anything/at/all'))

    def test_owning_a_manifest_covers_its_root_lockfile(self):
        self.assertTrue(covers({'package.json'}, 'package-lock.json'))
        self.assertTrue(covers({'package.json'}, 'yarn.lock'))
        self.assertTrue(covers({'package.json'}, 'pnpm-lock.yaml'))
        self.assertTrue(covers({'Cargo.toml'}, 'Cargo.lock'))
        self.assertTrue(covers({'pyproject.toml'}, 'poetry.lock'))
        self.assertTrue(covers({'Gemfile'}, 'Gemfile.lock'))

    def test_manifest_in_a_subdirectory_covers_the_lockfile_beside_it_only(self):
        self.assertTrue(covers({'app/package.json'}, 'app/package-lock.json'))
        self.assertFalse(covers({'app/package.json'}, 'package-lock.json'),
                          'a lockfile in a different directory is not the same install')
        self.assertFalse(covers({'package.json'}, 'app/package-lock.json'),
                          'declaring the root manifest does not reach into a subdirectory')

    def test_lockfile_inference_never_covers_an_unrelated_file(self):
        self.assertFalse(covers({'package.json'}, 'index.html'))
        self.assertFalse(covers({'package.json'}, '.gitignore'),
                          '.gitignore is not a lockfile of any manifest; it must still be declared')
        self.assertFalse(covers({'package.json'}, 'Cargo.lock'),
                          'the wrong ecosystem lockfile is not inferred')

    def test_owning_only_the_lockfile_does_not_cover_the_manifest(self):
        self.assertFalse(covers({'package-lock.json'}, 'package.json'))

    def test_glob_token_covers_matching_files_in_that_directory(self):
        self.assertTrue(covers({'scripts/tests/*.sh'}, 'scripts/tests/checklist-groups-test.sh'))
        self.assertFalse(covers({'scripts/tests/*.sh'}, 'scripts/tests/checklist-groups-test.py'),
                          'the extension must match, not just the directory')
        self.assertFalse(covers({'scripts/tests/*.sh'}, 'scripts/lib/checklist-groups-test.sh'),
                          'a glob only reaches into its own directory')
        self.assertFalse(covers({'scripts/tests/*.sh'}, 'scripts/tests/nested/checklist-groups-test.sh'),
                          'a single-star glob does not cross a path separator')


class GroupTests(unittest.TestCase):
    OWNED = {n: {'f%d' % n} for n in range(1, 10)}
    DEPS = {9: [1, 2, 3, 4, 8], 8: []}

    def test_a_dependency_splits_a_group_by_default_in_the_function(self):
        self.assertEqual(module.group(9, self.OWNED, self.DEPS), [[1, 2, 3, 4, 5, 6, 7, 8], [9]])

    def test_ignoring_dependencies_groups_by_ownership_alone(self):
        self.assertEqual(module.group(9, self.OWNED, self.DEPS, ignore_deps=True), [list(range(1, 10))])

    def test_a_shared_file_still_splits_when_dependencies_are_ignored(self):
        owned = {**self.OWNED, 9: {'f8'}}
        self.assertEqual(module.group(9, owned, self.DEPS, ignore_deps=True), [list(range(1, 9)), [9]])

    def test_a_step_that_declared_nothing_still_runs_alone(self):
        owned = {1: {'a'}, 2: set(), 3: {'c'}}
        self.assertEqual(module.group(3, owned, {}, ignore_deps=True), [[1], [2], [3]])

    def test_the_driver_ignores_dependencies_unless_told_not_to(self):
        import os, subprocess, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / 'plan.md'
            plan.write_text('# Plan\n\n## 12. Implementation order\n\n1. A\n   Owns: `a.js`\n2. B\n   Owns: `b.js`\n'
                            '   Depends on: 1\n')
            lib = Path(__file__).resolve().parents[1] / 'lib'
            def groups(flag):
                env = dict(os.environ, WORKFLOW_IMPLEMENT_IGNORE_DEPENDS=flag)
                out = subprocess.run([sys.executable, str(lib / 'step_groups.py'), str(plan), tmp],
                                     capture_output=True, text=True, env=env).stdout
                import json
                return json.loads(out)['groups']
            self.assertEqual(groups('1'), [[1, 2]])
            self.assertEqual(groups('0'), [[1], [2]])


class MergeSteps(unittest.TestCase):
    """The product code is one worker and what builds and verifies it is another; mixed steps and the driver's runner stay alone."""
    OWNED = {1: {'package.json', 'index.html', '.uncle/launch.json', '.gitignore', 'vite.config.js', 'vitest.config.js'},
             2: {'src/calc.js'}, 3: {'src/App.jsx', 'src/main.jsx'}, 4: {'src/styles.css'},
             5: {'tests/calc.test.js'}, 6: {'e2e/theme.spec.js'}, 7: {'tests/mutations/list.mjs'},
             8: {'tests/mutations/run.mjs'}, 9: {'src/helpers.js', 'tests/helpers.test.js'}, 10: {'*'}}
    GROUP = list(range(1, 11))

    def merged(self, mode, group=None):
        env = {} if mode is None else {'WORKFLOW_IMPLEMENT_MERGE_APP': mode}
        with unittest.mock.patch.dict(os.environ, env):
            if mode is None:
                os.environ.pop('WORKFLOW_IMPLEMENT_MERGE_APP', None)
            return module.merge_map(self.OWNED, group or self.GROUP)

    def test_roles_follow_the_files_a_step_owns(self):
        roles = {step: module.role(paths) for step, paths in self.OWNED.items()}
        self.assertEqual(roles, {1: 'scaffold', 2: 'app', 3: 'app', 4: 'app', 5: 'test', 6: 'test', 7: 'test', 8: 'test',
                                 9: 'mixed', 10: 'mixed'})

    def test_the_entry_page_beside_application_source_belongs_to_the_application(self):
        self.assertEqual(module.role({'index.html', 'src/App.jsx', 'src/main.jsx'}), 'app')

    def test_the_entry_page_alone_or_beside_config_stays_scaffold(self):
        self.assertEqual(module.role({'index.html'}), 'scaffold')
        self.assertEqual(module.role({'index.html', 'package.json', 'vite.config.js'}), 'scaffold')

    def test_a_scaffold_step_that_also_writes_the_entry_files_belongs_to_the_application(self):
        self.assertEqual(module.role({'package.json', 'index.html', 'src/App.jsx', 'src/main.jsx'}), 'app')

    def test_a_manifest_beside_application_source_with_no_entry_file_is_still_mixed(self):
        self.assertEqual(module.role({'package.json', 'src/helpers.js'}), 'mixed')

    def test_an_entry_file_beside_tests_is_still_mixed(self):
        self.assertEqual(module.role({'src/App.jsx', 'tests/app.test.js'}), 'mixed')

    def test_the_entry_step_merges_with_the_steps_whose_files_it_imports(self):
        owned = {1: {'src/calc.js'}, 2: {'src/Calculator.jsx'}, 3: {'index.html', 'src/App.jsx', 'src/main.jsx'},
                 4: {'src/theme.css'}}
        with unittest.mock.patch.dict(os.environ, {'WORKFLOW_IMPLEMENT_MERGE_APP': '1'}):
            self.assertEqual(module.merge_map(owned, [1, 2, 3, 4]), {1: [2, 3, 4]})

    def test_a_test_path_is_a_test_whatever_directory_holds_it(self):
        for path in ('src/App.test.jsx', 'src/__tests__/a.js', 'tests/e2e/keyboard.spec.js', 'scripts/mutate.mjs',
                     'tests/mutations/run.mjs'):
            self.assertEqual(module.role({path}), 'test', path)

    def test_mode_0_is_the_old_one_worker_per_step(self):
        self.assertEqual(self.merged('0'), {})

    def test_mode_1_merges_only_the_application_steps(self):
        self.assertEqual(self.merged('1'), {2: [3, 4]})

    def test_mode_2_is_two_workers_the_application_and_everything_that_verifies_it(self):
        # step 8 is only the defect-injection runner, which the driver supplies; 9 mixes roles; 10 owns everything.
        self.assertEqual(self.merged('2'), {2: [3, 4], 1: [5, 6, 7]})

    def test_independent_test_workers_are_the_default(self):
        self.assertEqual(self.merged(None), {2: [3, 4]})

    def test_an_unknown_mode_is_the_default_not_a_silent_off(self):
        self.assertEqual(self.merged('banana'), self.merged('1'))

    def test_a_unit_of_one_step_has_nothing_to_merge(self):
        self.assertEqual(self.merged('2', [1, 2]), {})                          # one application step, one harness step
        self.assertEqual(self.merged('2', [1, 2, 5]), {1: [5]})                 # scaffold and a test are both the harness
        self.assertEqual(self.merged('2', [2, 3, 5]), {2: [3]})                 # two application steps, one harness step
        self.assertEqual(self.merged('2', [9, 10]), {})

    def test_the_groups_own_order_decides_the_first(self):
        self.assertEqual(self.merged('1', [4, 3]), {4: [3]})

    def test_only_a_defect_runner_that_owns_nothing_else_is_the_drivers(self):
        self.assertTrue(module.provided_runner({'tests/mutations/run.mjs'}))
        self.assertTrue(module.provided_runner({'scripts/mutate.mjs'}))
        self.assertFalse(module.provided_runner({'tests/mutations/list.mjs'}))
        self.assertFalse(module.provided_runner({'tests/mutations/run.mjs', 'tests/mutations/list.mjs'}))
        self.assertFalse(module.provided_runner({'src/run.mjs'}))               # not a mutation path

class WaveTests(unittest.TestCase):
    OWNED = {1: {'package.json'}, 2: {'src/calc.js'}, 3: {'src/App.jsx'}, 4: {'tests/calc.test.js'},
             5: {'tests/e2e/a.spec.js'}, 6: {'tests/mutations/list.mjs'}, 7: {'tests/mutations/run.mjs'}, 8: set()}

    def test_tests_wait_for_the_source_and_the_mutation_list_waits_for_the_tests(self):
        self.assertEqual(module.waves([[1, 2, 3, 4, 5, 6, 7]], self.OWNED), [[1, 2, 3], [4, 5], [6, 7]])

    def test_a_step_that_declared_nothing_stays_with_the_source(self):
        self.assertEqual(module.waves([[8, 4]], self.OWNED), [[8], [4]])

    def test_the_opt_out_restores_one_group(self):
        with unittest.mock.patch.dict(os.environ, {'WORKFLOW_IMPLEMENT_TEST_WAVES': '0'}):
            self.assertEqual(module.waves([[1, 4, 6]], self.OWNED), [[1, 4, 6]])

    def test_groups_without_tests_are_untouched(self):
        self.assertEqual(module.waves([[1, 2], [3]], self.OWNED), [[1, 2], [3]])


class ModuleTests(unittest.TestCase):
    def test_source_with_its_own_tests_is_a_module(self):
        self.assertTrue(module.is_module({'src/engine/engine.js', 'src/engine/engine.test.js', 'src/engine/CONTRACT.md'}))

    def test_a_module_may_own_its_styles_too(self):
        self.assertTrue(module.is_module({'src/keypad/Keypad.jsx', 'src/keypad/keypad.css', 'src/keypad/keypad.test.jsx'}))

    def test_layers_are_not_modules(self):
        self.assertFalse(module.is_module({'src/engine.js'}))                         # source alone
        self.assertFalse(module.is_module({'tests/engine.test.js'}))                  # tests alone
        self.assertFalse(module.is_module({'package.json', 'vite.config.js'}))        # scaffold alone
        self.assertFalse(module.is_module({'package.json', 'tests/a.test.js'}))       # scaffold and a test, no source

    def test_nothing_declared_and_star_are_not_modules(self):
        self.assertFalse(module.is_module(set()))
        self.assertFalse(module.is_module({'*'}))

    def test_a_step_that_declared_a_test_runner_config_is_not_made_a_module_by_it(self):
        self.assertFalse(module.is_module({'vitest.config.js', 'tests/setup.js'}))


class ModuleWaveTests(unittest.TestCase):
    OWNED = {1: {'package.json', 'vite.config.js'}, 2: {'src/engine/engine.js', 'src/engine/engine.test.js'},
             3: {'src/keyboard/keyboard.js', 'src/keyboard/keyboard.test.js'}, 4: {'src/App.jsx', 'index.html'},
             5: {'e2e/calc.spec.js'}, 6: {'tests/mutations/list.mjs'}}

    def test_with_modules_the_scaffold_lands_first_alone(self):
        self.assertEqual(module.waves([[1, 2, 3, 4, 5, 6]], self.OWNED), [[1], [2, 3, 4], [5], [6]])

    def test_without_modules_the_scaffold_stays_beside_the_source(self):
        layers = {1: {'package.json'}, 2: {'src/engine.js'}, 3: {'tests/engine.test.js'}}
        self.assertEqual(module.waves([[1, 2, 3]], layers), [[1, 2], [3]])

    def test_modules_and_a_shell_share_a_wave(self):
        self.assertIn([2, 3, 4], module.waves([[1, 2, 3, 4, 5, 6]], self.OWNED))

    def test_with_waves_off_nothing_is_split(self):
        with unittest.mock.patch.dict(os.environ, {'WORKFLOW_IMPLEMENT_TEST_WAVES': '0'}):
            self.assertEqual(module.waves([[1, 2, 3, 4, 5, 6]], self.OWNED), [[1, 2, 3, 4, 5, 6]])
            self.assertFalse(module.waves_enabled())

    def test_the_manifest_owner_is_the_scaffold_even_with_files_the_scaffold_pattern_does_not_know(self):
        """Live run 12: the scaffold also owned `vitest.setup.js`, was not separated, and the modules ran their tests with nothing installed."""
        owned = dict(self.OWNED); owned[1] = {'package.json', 'vite.config.js', 'vitest.setup.js'}
        self.assertEqual(module.waves([[1, 2, 3, 4, 5, 6]], owned), [[1], [2, 3, 4], [5], [6]])

    def test_a_manifest_owner_with_entry_files_still_lands_first_when_modules_are_present(self):
        owned = dict(self.OWNED); owned[1] = {'package.json', 'src/main.jsx'}
        self.assertEqual(module.waves([[1, 2, 3]], owned), [[1], [2, 3]])

    def test_without_modules_a_manifest_owner_stays_with_the_source(self):
        layers = {1: {'package.json', 'vitest.setup.js'}, 2: {'src/engine.js'}, 3: {'tests/engine.test.js'}}
        self.assertEqual(module.waves([[1, 2, 3]], layers), [[1, 2], [3]])

    def test_the_manifest_rule_recognizes_other_ecosystems(self):
        for name in ('package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod', 'Gemfile', 'composer.json', 'app/package.json'):
            self.assertTrue(module.owns_manifest({name}), name)
        self.assertFalse(module.owns_manifest({'package-lock.json', 'src/package.js', 'tests/a.test.js'}))


class WaveGroupsFromAPlan(unittest.TestCase):
    """The command the prompt builder calls, end to end through a real plan file."""
    PLAN = (
        '# Plan\n\n## 12. Implementation steps\n\n'
        '1. Scaffold. Owns: `package.json`\n'
        '2. Engine module. Owns: `src/engine.js`, `src/engine.test.js`\n'
        '3. Shell. Owns: `src/App.jsx`\n'
    )

    def command(self, *args, env=None):
        import subprocess, tempfile
        plan = Path(tempfile.mkdtemp()) / 'plan.md'
        plan.write_text(self.PLAN)
        full = dict(os.environ); full.update(env or {})
        return subprocess.run([sys.executable, str(Path(module.__file__)), *args[:1], str(plan), *args[1:]], capture_output=True,
                              text=True, env=full).stdout.split()

    def test_module_step_flags_only_the_module(self):
        self.assertEqual(self.command('module-step', '1', '2', '3'), ['0', '1', '0'])

    def test_module_step_is_zero_everywhere_when_waves_are_off(self):
        self.assertEqual(self.command('module-step', '1', '2', '3', env={'WORKFLOW_IMPLEMENT_TEST_WAVES': '0'}), ['0', '0', '0'])


class WritesSourceTests(unittest.TestCase):
    def test_application_source_is_source(self):
        self.assertTrue(module.writes_source({'src/App.jsx'}))
        self.assertTrue(module.writes_source({'src/engine/engine.js', 'src/engine/engine.test.js'}))

    def test_the_scaffold_alone_is_not(self):
        self.assertFalse(module.writes_source({'package.json', 'vite.config.js', '.gitignore'}))

    def test_tests_alone_are_not(self):
        self.assertFalse(module.writes_source({'tests/a.test.js', 'e2e/a.spec.js', 'tests/mutations/list.mjs'}))

    def test_star_and_nothing_are_not(self):
        self.assertFalse(module.writes_source({'*'}))
        self.assertFalse(module.writes_source(set()))

    def test_the_entry_page_counts_as_source_beside_nothing_else(self):
        self.assertFalse(module.writes_source({'index.html'}))             # scaffold by itself

    def test_has_source_reads_a_real_plan(self):
        plan = ('# Plan\n\n## 12. Implementation steps\n\n1. Scaffold. Owns: `package.json`\n'
                '2. Engine. Owns: `src/engine.js`\n3. Tests. Owns: `tests/engine.test.js`\n')
        import subprocess, tempfile
        path = Path(tempfile.mkdtemp()) / 'plan.md'
        path.write_text(plan)
        out = subprocess.run([sys.executable, str(Path(module.__file__)), 'has-source', str(path), '1', '2', '3'],
                             capture_output=True, text=True).stdout.split()
        self.assertEqual(out, ['0', '1', '0'])


class HasModuleTests(unittest.TestCase):
    """The module-interfaces stage runs, in `auto` mode, only for a plan with a vertical module."""

    def run_plan(self, plan):
        import subprocess, tempfile
        path = Path(tempfile.mkdtemp()) / 'plan.md'
        path.write_text(plan)
        return subprocess.run([sys.executable, str(Path(module.__file__)), 'has-module', str(path)], capture_output=True, text=True).stdout.split()

    def test_a_step_owning_source_and_its_tests_is_a_module(self):
        self.assertEqual(self.run_plan('# Plan\n\n## 12. Implementation steps\n\n1. Scaffold. Owns: `package.json`\n'
                                       '2. Engine. Owns: `src/engine.js`, `tests/engine.test.js`\n'), ['1'])

    def test_separate_source_and_test_steps_are_not(self):
        self.assertEqual(self.run_plan('# Plan\n\n## 12. Implementation steps\n\n1. Scaffold. Owns: `package.json`\n'
                                       '2. Engine. Owns: `src/engine.js`\n3. Tests. Owns: `tests/engine.test.js`\n'), ['0'])

    def test_a_scaffold_alone_or_a_step_owning_everything_is_not(self):
        self.assertEqual(self.run_plan('# Plan\n\n## 12. Implementation steps\n\n1. Everything. Owns: `*`\n'), ['0'])

    def test_one_module_among_many_steps_is_enough(self):
        self.assertEqual(self.run_plan('# Plan\n\n## 12. Implementation steps\n\n1. Scaffold. Owns: `package.json`\n2. View. Owns: `src/App.jsx`\n'
                                       '3. Keys. Owns: `src/keymap.js`, `tests/keymap.test.js`\n4. Spec. Owns: `e2e/a.spec.js`\n'), ['1'])


if __name__ == '__main__':
    unittest.main()

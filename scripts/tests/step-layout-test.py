#!/usr/bin/env python3
"""Independent regressions for the step layouts that stopped DS4 runs 11, 19 and 20."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'scripts/lib'
sys.path.insert(0, str(LIB))
import plan_model as pm
import plan_records
import plan_ownership_gap as gap
import step_groups
import artifact_json
import publish_agent_artifact as publisher

spec = importlib.util.spec_from_file_location('plan_executability', LIB / 'plan-executability.py')
executability = importlib.util.module_from_spec(spec)
spec.loader.exec_module(executability)

FIXTURES = Path(__file__).resolve().parent / 'fixtures/step-layout'
EXPECTED = {
    11: [
        ['package.json', 'vite.config.js', 'playwright.config.js', 'index.html', 'src/main.jsx',
         'src/index.css', 'src/theme.css', '.gitignore', '.eslintrc.cjs'],
        ['src/calcReducer.js', 'src/calcReducer.test.js'],
        ['src/Display.jsx', 'src/CalcButton.jsx', 'src/Keypad.jsx', 'src/Calculator.jsx', 'src/App.jsx', 'src/App.test.jsx'],
        ['tests/theme.spec.js', 'tests/calculator.spec.js'],
        ['tests/injections/manifest.json', 'tests/injections/run.js'],
        ['.uncle/launch.json', '.github/workflows/ci.yml'],
    ],
    19: [
        ['package.json', 'playwright.config.js', 'tests/calculator.test.js', 'tests/injections/run.js',
         'tests/injections/mutations.js', '.gitignore'],
        ['src/calc.js'], ['src/ui.js', 'index.html'],
        ['tests/calculator.test.js', 'tests/injections/run.js', 'tests/injections/mutations.js'],
        ['.uncle/launch.json'],
    ],
    20: [
        ['package.json', 'vite.config.js', 'playwright.config.js', 'index.html', '.gitignore'],
        ['src/calc.js', 'tests/calc.test.js'],
        ['src/App.jsx', 'src/Calculator.jsx', 'src/Display.jsx', 'src/Keypad.jsx', 'src/Button.jsx', 'src/index.css'],
        ['tests/calculator.spec.js'],
        ['tests/defect-injections/mutations.json', 'tests/defect-injections/apply-mutation.js', 'tests/run-defect-injections.js'],
    ],
}
PROTECTED = {
    19: ['tests/calculator.test.js', 'tests/injections/run.js', 'playwright.config.js', 'tests/injections/mutations.js'],
    20: ['tests/calc.test.js', 'tests/calculator.spec.js', 'tests/run-defect-injections.js',
         'playwright.config.js', 'tests/defect-injections/apply-mutation.js'],
}
TITLES = {
    11: ['Project scaffold and theme', 'Calculator logic (reducer)', 'UI components', 'Browser tests',
         'Defect injection runner', 'Launch metadata'],
    19: ['Scaffold', 'Calculator logic', 'UI components', 'Test suite and injection runner', 'Launch metadata'],
    20: ['Scaffold', 'Arithmetic core', 'UI components', 'Browser tests', 'Defect injection runner'],
}


class StepLayouts(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.plan = self.root / 'PLAN.md'
        config = self.root / '.uncle/config'
        config.parent.mkdir()
        config.write_text('runner claude\n')
        values = {'PATH': os.environ['PATH'], 'HOME': str(self.root), 'UNCLE_CONFIG': str(config)}
        values.update({'WORKFLOW_' + runner + '_PLAN_STEP_RECOVERY': 'off'
                       for runner in ('CLAUDE', 'CODEX', 'SELF_HOSTED')})
        env = patch.dict(os.environ, values, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def command(self, args):
        result = subprocess.run(args, cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def shell(self, function):
        return self.command(['bash', '-c', '. "$1/plan-scope.sh"; "$2" "$3"',
                             'step-layout', str(LIB), function, str(self.plan)]).splitlines()

    def assert_readers(self, text, owners, deps=None):
        self.plan.write_text(text)
        expected = {n: set(paths) for n, paths in enumerate(owners, 1)}
        model = pm.import_markdown(text)
        steps, owned, depends = plan_records.step_data(model)
        self.assertEqual(len(steps), len(owners))
        self.assertEqual(owned, expected)
        if deps is not None:
            self.assertEqual(depends, deps)
        rows = self.command([sys.executable, '-I', str(LIB / 'plan_records.py'), 'owns', str(self.plan)]).splitlines()
        self.assertEqual(step_groups.owns(rows), expected)
        self.assertEqual(step_groups.owns(self.shell('plan_step_owns')), expected)
        self.assertEqual(len(self.shell('plan_steps')), len(owners))
        shell_deps = step_groups.depends(self.shell('plan_step_depends'))
        self.assertEqual(shell_deps, {n: refs for n, refs in depends.items() if refs})
        self.assertEqual(gap.specifically_owned(self.plan), list(expected.values()))
        report = json.loads(self.command([sys.executable, '-I', str(LIB / 'step_groups.py'), str(self.plan), str(self.root)]))
        self.assertEqual(report['steps'], len(owners))
        self.assertEqual(report['declared_paths'], sorted(set().union(*expected.values())))
        return model

    def test_real_layouts_have_identical_readers(self):
        for run, owners in EXPECTED.items():
            with self.subTest(run=run):
                model = self.assert_readers((FIXTURES / ('run-%d.md' % run)).read_text(), owners)
                self.assertEqual([s['title'] for s in pm.steps_of(model)], TITLES[run])

    def test_run_19_and_20_protected_paths_have_creators(self):
        for run, protected in PROTECTED.items():
            with self.subTest(run=run):
                self.plan.write_text((FIXTURES / ('run-%d.md' % run)).read_text())
                self.assertEqual(gap.unowned_protected_paths(self.plan, self.root, protected), [])

    def test_section_levels_and_names(self):
        for level in range(1, 7):
            for name in ('order', 'steps', 'sequence', 'plan'):
                with self.subTest(level=level, name=name):
                    text = '#' * level + ' 12. Implementation ' + name + '\n\n**Step 0: Core** — Owns: `src/core.py`\n'
                    self.assertEqual([s['owns'] for s in pm.steps_of(pm.import_markdown(text))], [['src/core.py']])

    def test_bullets_bold_fields_and_letter_dependencies(self):
        text = '''# Implementation plan

- **Step 0: Scaffold** — **Owns**: `package.json`
  Keep this initialization instruction.
- Step 3b: Browser suite
  - **Owns:** `tests/browser.spec.js`
  - **Depends on**: Step 0
+ **Step 4: Unit suite**
  Owns: `tests/unit.test.js`
  Depends on: Step 3b, Step 0
'''
        self.assert_readers(text, [['package.json'], ['tests/browser.spec.js'], ['tests/unit.test.js']],
                            {1: set(), 2: {1}, 3: {1, 2}})

    def test_numbered_steps_with_bold_ownership(self):
        self.assert_readers('## Implementation steps\n\n0. Scaffold\n   **Owns:** `package.json`\n'
                            '3. Tests\n   **Owns**: `tests/unit.js`\n   **Depends on:** 0\n',
                            [['package.json'], ['tests/unit.js']], {1: set(), 2: {1}})

    def test_fenced_examples_and_following_sections_are_not_steps(self):
        text = '''# Plan

## Implementation order

### Step 1: Core
Owns: `src/core.py`

```markdown
### Step 9: Example only
Owns: `never-owned.py`
```

## Review options

### Step 8: Human review
Owns: `also-not-owned.py`
'''
        model = self.assert_readers(text, [['src/core.py']])
        self.assertIn('never-owned.py', pm.steps_of(model)[0]['text'])

    def test_publication_preserves_surroundings_and_is_idempotent_for_all_runners(self):
        before = '# Plan\n\nKeep this prose  exactly.\n\n'
        after = '\n# Review options\n\nKeep /approve, /do, /resume and human review.\n'
        for runner in ('claude', 'codex', 'self-hosted'):
            (self.root / '.uncle/config').write_text('runner ' + runner + '\n')
            for run, owners in EXPECTED.items():
                for stage in ('project-plan', 'updated-plan', 'change-plan', 'updated-change-plan'):
                    with self.subTest(runner=runner, run=run, stage=stage):
                        text = before + (FIXTURES / ('run-%d.md' % run)).read_text() + after
                        plan = dict(schema='uncle.artifact/v1', kind='change-plan' if 'change' in stage else 'plan',
                                    narrative=text, verification_commands='true')
                        published = pm.publish_records(plan, self.root, stage=stage)
                        self.assertTrue(published['narrative'].startswith(before))
                        self.assertTrue(published['narrative'].endswith(after))
                        self.assertRegex(published['narrative'], r'(?m)^1\. \*\*')
                        self.assertEqual([s['owns'] for s in pm.steps_of(published)], owners)
                        self.assertEqual(pm.publish_records(published, self.root, stage=stage), published)
                        self.assertEqual(plan['narrative'], text)

    def test_canonical_packet_and_markdown_readers_agree(self):
        text = (FIXTURES / 'run-20.md').read_text()
        published = pm.publish_records(dict(narrative=text), self.root)
        self.plan.with_suffix('.json').write_text(json.dumps(published))
        self.assert_readers(published['narrative'], EXPECTED[20])

    def test_run_20_project_plan_retains_step_instructions(self):
        text = (FIXTURES / 'run-20-project.md').read_text()
        self.assert_readers(text, EXPECTED[20])
        published = pm.publish_records(dict(narrative=text), self.root, stage='project-plan')
        self.assertEqual([s['owns'] for s in pm.steps_of(published)], EXPECTED[20])
        for instruction in ('Steps are designed to run in parallel where possible.',
                            'Create Vite React project structure', 'evaluateExpression',
                            'data-testid', 'Parallel runner'):
            self.assertIn(instruction, published['narrative'])
        self.assertEqual(pm.publish_records(published, self.root, stage='project-plan'), published)

    def test_multiline_fields_and_nested_numbered_instructions(self):
        text = '''## Implementation sequence

1. **Scaffold**
   1. Write the manifest.
   2. Document local commands.
   **Owns:**
   - `package.json`
   - `README.md`
2. **Tests**
   **Depends on:**
   - Step 1
   **Owns:**
   - `tests/test_core.py`
'''
        model = self.assert_readers(text, [['package.json', 'README.md'], ['tests/test_core.py']],
                                    {1: set(), 2: {1}})
        self.assertIn('Write the manifest.', pm.steps_of(model)[0]['text'])
        self.assertIn('Document local commands.', pm.steps_of(model)[0]['text'])

    def test_table_layout_and_letter_label_dependencies(self):
        text = '''## Implementation order

| Step | Description | Owns | Depends on |
|---|---|---|---|
| Step 0 | Scaffold | `package.json` | none |
| Step 3b | Browser tests | `tests/browser.spec.js` | Step 0 |
'''
        self.assert_readers(text, [['package.json'], ['tests/browser.spec.js']], {1: set(), 2: {1}})

    def test_missing_label_never_crashes_the_step_reader(self):
        text = '## Implementation order\n\n### Step : Scaffold\nOwns: `package.json`\n'
        self.assert_readers(text, [['package.json']])

    def test_executability_uses_the_same_step_boundaries(self):
        for run, owners in EXPECTED.items():
            with self.subTest(run=run):
                text = (FIXTURES / ('run-%d.md' % run)).read_text()
                self.assertEqual(len(executability._implementation_step_blocks(text)), len(owners))
        self.plan.write_text('# Implementation order\n\n**Step 0: Scaffold** — Owns: `package.json`\n'
                             'Run `npx create-vite@latest . --overwrite`.\n')
        findings = executability.scaffold_generator_findings(str(self.plan))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]['step'], 1)
        self.assertEqual(findings[0]['owns'], ['package.json'])

    def test_step_headings_at_the_section_level_are_not_section_ends(self):
        for heading in ('0. Scaffold', '**0. Scaffold**', 'Step : Scaffold'):
            with self.subTest(heading=heading):
                text = '## Implementation order\n\n## ' + heading + '\nOwns: `package.json`\n\n## Review\nKeep this.\n'
                self.assert_readers(text, [['package.json']])

    def test_fenced_examples_cannot_set_the_real_step_indentation(self):
        text = ('## Implementation order\n\n```markdown\nStep 9: example\n```\n\n'
                '  1. **Scaffold**\n     Owns: `package.json`\n')
        self.assert_readers(text, [['package.json']])

    def test_normalization_keeps_ownership_annotations(self):
        text = ('## Implementation order\n\n### Step 1: Scaffold\n'
                'Owns: `package.json` (preserve existing dependency versions)\n')
        published = pm.publish_records(dict(narrative=text), self.root)
        self.assertIn('preserve existing dependency versions', published['narrative'])
        self.assertEqual(pm.steps_of(published)[0]['owns'], ['package.json'])

    def test_bare_paths_in_ownership_bullets(self):
        self.assert_readers('## Implementation order\n### Step 1: Scaffold\n'
                            'Owns:\n- package.json\n- vite.config.js\n',
                            [['package.json', 'vite.config.js']])

    def test_explicit_extensionless_owners(self):
        self.assert_readers('## Implementation order\n### Step 1: Scaffold\n'
                            'Owns: Makefile, Dockerfile\n', [['Makefile', 'Dockerfile']])

    def test_published_documents_and_canonical_packets_share_the_same_steps(self):
        for run in (19, 20):
            for stage, (name, kind) in publisher.ARTIFACT.items():
                if stage == 'requirements':
                    continue
                with self.subTest(run=run, stage=stage):
                    payload = dict(schema='uncle.artifact/v1', kind=kind,
                                   narrative=(FIXTURES / ('run-%d.md' % run)).read_text(),
                                   verification_commands='true', protected_verification_paths='\n'.join(PROTECTED[run]))
                    if stage.startswith('updated'):
                        payload['dispositions'] = [dict(finding='AR-001', disposition='Accepted',
                                                       reason='Preserve ownership.', plan_change='Implementation steps.')]
                    delivery = self.root / 'delivery.json'
                    delivery.write_text(json.dumps(payload))
                    self.assertTrue(publisher.publish(stage, 'unused', self.root, delivery))
                    canonical = artifact_json.read(self.root, name)
                    self.assertEqual([s['owns'] for s in pm.steps_of(canonical)], EXPECTED[run])
                    view = self.root / '.uncle/docs' / name
                    self.assertEqual([s['owns'] for s in pm.steps_of(pm.import_markdown(view.read_text()))], EXPECTED[run])
                    self.assertEqual(gap.unowned_protected_paths(view, self.root, PROTECTED[run]), [])


if __name__ == '__main__':
    unittest.main()

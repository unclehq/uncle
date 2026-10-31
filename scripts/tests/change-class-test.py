#!/usr/bin/env python3
"""The build classifier: deterministic floor, clamped model proposal, runner-independent extraction, config precedence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('change_class', ROOT / 'scripts/lib/change_class.py')
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def plan(*steps):
    rows = '\n'.join('%d. Step %d — Owns: %s — Depends on: 0' % (n, n, ', '.join('`%s`' % p for p in paths))
                     for n, paths in enumerate(steps, 1))
    return '# Change plan\n\n## Implementation sequence\n\n%s\n\n## Verification\n\nRun the tests.\n' % rows


class Project:
    def __init__(self, test, request='Fix the greeting.', family='change', body=None, criteria=2):
        self.dir = tempfile.TemporaryDirectory()
        test.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        (self.root / '.uncle/workflow/documents').mkdir(parents=True)
        (self.root / ('CHANGE_REQUEST.md' if family == 'change' else 'REQUIREMENTS.md')).write_text(request)
        self.plan = self.root / 'PLAN.md'
        self.plan.write_text(body if body is not None else plan(['src/app.py']))
        (self.root / '.uncle/workflow/documents/CHANGE_SPEC.json').write_text(json.dumps(
            {'acceptance_criteria': [{'id': 'AC-%d' % n} for n in range(criteria)]}))
        self.family = family

    def features(self):
        return cc.features(self.family, self.root, self.plan)

    def build(self, proposal=None, source='model'):
        return cc.build(self.family, self.root, self.plan, proposal, source)


class Floor(unittest.TestCase):
    def test_docs_and_tests_only_changes(self):
        self.assertEqual(Project(self, body=plan(['README.md', 'docs/guide.md'])).build()['floor_class'], 'docs')
        self.assertEqual(Project(self, body=plan(['scripts/tests/a-test.py'])).build()['floor_class'], 'test-only')

    def test_small_standard_large(self):
        self.assertEqual(Project(self).build()['floor_class'], 'small')
        self.assertEqual(Project(self, body=plan(*[['src/m%d.py' % n] for n in range(4)])).build()['floor_class'], 'standard')
        self.assertEqual(Project(self, body=plan(*[['src/m%d.py' % n] for n in range(8)])).build()['floor_class'], 'large')

    def test_risk_keywords_force_risky_and_security(self):
        built = Project(self, request='Sanitize the API token before it is published.').build()
        self.assertEqual(built['floor_class'], 'risky')
        self.assertIn('security', built['adversarial_lenses'])
        self.assertIn('api token', built['features']['risk_hits'])

    def test_an_application_build_is_never_docs_or_small(self):
        built = Project(self, request='A calculator page.', family='app').build()
        self.assertEqual(built['floor_class'], 'standard')
        self.assertIn('testability', built['adversarial_lenses'])

    def test_boilerplate_in_the_plan_does_not_make_a_plan_risky(self):
        # A calculator's plan mentions concurrency, injection tests, design tokens and Uncle's waiver vocabulary; none of that is
        # a risk in the request, and counting it made every plan risky (the live calculator build).
        body = plan(['src/App.jsx'], ['src/App.css']) + ('\n## Notes\n\nTests run concurrently. Add XSS injection tests. '
                                                       'Design tokens live in :root. Waiver rows are Uncle bookkeeping.\n')
        built = Project(self, request='A groovy calculator page.', family='app', body=body).build()
        self.assertEqual(built['features']['risk_hits'], [])
        self.assertEqual(built['floor_class'], 'standard')

    def test_a_risky_request_is_still_risky(self):
        for request in ('Store the user password.', 'Delete the account.', 'Add an OAuth token refresh.',
                        'Sign each commit with gpg.', 'Publish the report to a public repo.', 'Fix the sql injection.'):
            self.assertEqual(Project(self, request=request).build()['floor_class'], 'risky', request)

    def test_a_risky_file_path_or_criterion_is_risky(self):
        self.assertEqual(Project(self, body=plan(['src/auth/login.py'])).build()['floor_class'], 'risky')
        project = Project(self)
        (project.root / '.uncle/workflow/documents/CHANGE_SPEC.json').write_text(json.dumps(
            {'acceptance_criteria': [{'id': 'AC-1', 'criterion': 'Secrets are redacted from the draft.', 'verification': 'test'}]}))
        self.assertEqual(project.build()['floor_class'], 'risky')


class Clamp(unittest.TestCase):
    def test_the_model_cannot_lower_the_class(self):
        built = Project(self, request='Rotate the signing key.').build({'class': 'docs', 'adversarial_lenses': ['requirements'],
                                                                        'edit_slice': 8})
        self.assertEqual(built['class'], 'risky')
        self.assertEqual(built['adversarial_lenses'], list(cc.LENSES))
        self.assertLessEqual(built['edit_slice'], 2)

    def test_the_model_can_raise_the_class(self):
        self.assertEqual(Project(self).build({'class': 'large'})['class'], 'large')

    def test_a_small_change_may_trim_optional_lenses_but_never_the_floor(self):
        built = Project(self).build({'class': 'small', 'adversarial_lenses': ['requirements'], 'edit_slice': 4})
        self.assertEqual(built['class'], 'small')
        self.assertEqual(built['adversarial_lenses'], ['requirements', 'regression', 'testability'])
        self.assertNotIn('security', built['adversarial_lenses'])
        self.assertEqual(built['edit_slice'], 4)

    def test_standard_plans_always_get_every_lens(self):
        built = Project(self, body=plan(*[['src/m%d.py' % n] for n in range(4)])).build(
            {'class': 'standard', 'adversarial_lenses': ['requirements'], 'edit_slice': 8})
        self.assertEqual(built['adversarial_lenses'], list(cc.LENSES))
        self.assertEqual(built['edit_slice'], 2)

    def test_garbage_in_the_proposal_is_ignored(self):
        built = Project(self).build({'class': 'galactic', 'adversarial_lenses': ['vibes', 7], 'edit_slice': True})
        self.assertEqual(built['class'], 'small')
        self.assertTrue(set(built['adversarial_lenses']) <= set(cc.LENSES))
        self.assertEqual(built['edit_slice'], 4)

    def test_no_proposal_is_the_deterministic_profile(self):
        built = Project(self).build(None, 'fallback')
        self.assertEqual((built['class'], built['source']), ('small', 'fallback'))
        self.assertEqual(built['adversarial_lenses'], ['requirements', 'regression', 'testability'])


class TestScope(unittest.TestCase):
    def scope(self, **kwargs):
        return Project(self, **kwargs).build()['test_scope']

    def test_the_class_decides_how_much_of_the_suite_the_final_check_runs(self):
        self.assertEqual(self.scope(body=plan(['README.md', 'docs/guide.md'])), 'impacted')            # docs
        self.assertEqual(self.scope(body=plan(['scripts/tests/a-test.py'])), 'impacted')                # test-only
        self.assertEqual(self.scope(), 'impacted')                                                      # small
        self.assertEqual(self.scope(body=plan(*[['src/m%d.py' % n] for n in range(4)])), 'ask')         # standard
        self.assertEqual(self.scope(body=plan(*[['src/m%d.py' % n] for n in range(8)])), 'full')        # large
        self.assertEqual(self.scope(request='Rotate the signing key.'), 'full')                         # risky

    def test_a_new_application_always_uses_the_full_suite(self):
        self.assertEqual(self.scope(request='A calculator page.', family='app'), 'full')

    def test_the_model_cannot_widen_the_scope(self):
        built = Project(self, request='Rotate the signing key.').build({'class': 'docs', 'test_scope': 'impacted'})
        self.assertEqual((built['class'], built['test_scope']), ('risky', 'full'))


class Extraction(unittest.TestCase):
    PACKET = {'schema': 'uncle.artifact/v1', 'kind': 'change-class', 'class': 'small', 'rationale': 'tiny'}

    def test_from_the_delivery_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'out.json'
            path.write_text(json.dumps(self.PACKET))
            self.assertEqual(cc.proposal_from(str(path))['class'], 'small')

    def test_from_a_fenced_or_surrounded_answer(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'out.json'
            path.write_text('Here you go:\n```json\n%s\n```\n' % json.dumps(self.PACKET))
            self.assertEqual(cc.proposal_from(str(path))['rationale'], 'tiny')

    def test_from_the_runners_final_text_when_nothing_was_written(self):
        # Any runner's event log: Claude-style stream events and Codex-style agent messages are both read.
        for event in ({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': json.dumps(self.PACKET)}]}},
                      {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(self.PACKET)}}):
            with tempfile.TemporaryDirectory() as d:
                log = Path(d) / 'run.jsonl'
                log.write_text(json.dumps({'type': 'system'}) + '\n' + json.dumps(event) + '\n')
                found = cc.proposal_from(str(Path(d) / 'missing.json'), str(log))
                self.assertIsNotNone(found, event)
                self.assertEqual(found['class'], 'small')

    def test_other_packets_and_nonsense_are_not_a_proposal(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'out.json'
            path.write_text(json.dumps({'kind': 'module-interfaces'}))
            self.assertIsNone(cc.proposal_from(str(path)))
            path.write_text('not json at all')
            self.assertIsNone(cc.proposal_from(str(path)))


class Files(unittest.TestCase):
    def test_finish_writes_and_get_reads_back(self):
        project = Project(self)
        delivery = project.root / 'd.json'
        delivery.write_text(json.dumps({'kind': 'change-class', 'class': 'small', 'adversarial_lenses': ['requirements'],
                                        'edit_slice': 3, 'rationale': 'r'}))
        result = cc.build('change', project.root, project.plan, cc.proposal_from(str(delivery)), 'model')
        cc.write(project.root, result)
        self.assertEqual(cc.get(project.root, 'class'), 'small')
        self.assertEqual(cc.get(project.root, 'edit_slice'), '3')
        self.assertEqual(cc.get(project.root, 'lenses').split(), ['requirements', 'regression', 'testability'])
        self.assertEqual(cc.get(project.root, 'nope', 'dflt'), 'dflt')

    def test_get_with_no_file_returns_the_default(self):
        self.assertEqual(cc.get('/no/such/project', 'class', 'standard'), 'standard')

    def test_prompt_carries_the_request_and_the_features(self):
        project = Project(self, request='Please add a retry to the uploader.')
        out = project.root / 'prompt.md'
        cc.prompt('change', project.root, project.plan, out, ROOT / 'prompts/classify-change.md')
        text = out.read_text()
        self.assertIn('Please add a retry to the uploader.', text)
        self.assertIn('"owned_files"', text)
        self.assertIn('"kind":"change-class"', text)


if __name__ == '__main__':
    unittest.main()

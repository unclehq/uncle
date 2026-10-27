#!/usr/bin/env python3
"""The plan stages say how serial a plan is; the prompts ask for steps that can run together."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import plan_parallelism as pp


def plan(steps):
    body = '\n'.join('%d. %s' % (n + 1, text) for n, text in enumerate(steps))
    path = Path(tempfile.mkdtemp()) / 'plan.md'
    path.write_text('# Plan\n\n## 12. Implementation order\n\n%s\n\n## 13. Traceability\n' % body)
    return str(path)


CHAIN = ['Core — Owns: `a.js`', 'Next — Owns: `b.js` — Depends on: 1', 'Then — Owns: `c.js` — Depends on: 2',
         'After — Owns: `d.js` — Depends on: 3', 'Last — Owns: `e.js` — Depends on: 4']
WIDE = ['Core — Owns: `a.js`', 'Tests — Owns: `a.test.js`', 'Styles — Owns: `s.css`', 'Page — Owns: `p.html`',
        'Reconcile — Owns: `*` — Depends on: 1, 2, 3, 4']


class Parallelism(unittest.TestCase):
    def test_a_chain_is_reported_with_the_reason_each_step_waits(self):
        text = pp.report(plan(CHAIN))
        self.assertIn('5 steps run in 5 groups', text)
        self.assertIn('almost one step at a time', text)
        self.assertIn('step 2 depends on step 1', text)

    def test_independent_steps_share_a_group_and_draw_no_warning(self):
        text = pp.report(plan(WIDE))
        self.assertIn('5 steps run in 2 groups', text)
        self.assertNotIn('almost one step at a time', text)

    def test_a_shared_file_is_named_as_the_reason(self):
        text = pp.report(plan(['One — Owns: `x.js`', 'Two — Owns: `x.js`', 'Three — Owns: `x.js`',
                               'Four — Owns: `x.js`', 'Five — Owns: `x.js`']))
        self.assertIn('shares x.js', text)

    def test_a_step_with_no_owns_is_named_as_such(self):
        _, _, reasons = pp.analyse(plan(['One — Owns: `a.js`', 'Two', 'Three — Owns: `c.js`', 'Four — Owns: `d.js`',
                                         'Five — Owns: `e.js`']))
        self.assertIn('declares no `Owns:`', reasons[2])

    def test_a_step_that_waits_for_everything_and_a_final_reconcile_are_named(self):
        steps = ['Scaffold — Owns: `package.json`', 'Engine — Owns: `a.js`', 'View — Owns: `v.js`', 'Tests — Owns: `t.js`',
                 'Mutation script — Owns: `m.sh` — Depends on: 2, 3, 4',
                 'Reconcile — Owns: `*` — Depends on: 1, 2, 3, 4, 5']
        text = pp.report(plan(steps))
        self.assertIn('Serial tail', text)
        self.assertIn('serial tail; if it only runs or checks', text)
        self.assertIn('final step that owns every file', text)
        self.assertIn('can be dropped', text)

    def test_a_short_plan_is_never_nagged(self):
        self.assertNotIn('almost one step', pp.report(plan(CHAIN[:3])))

    def test_missing_or_unreadable_plans_never_raise(self):
        self.assertEqual(pp.main(['/nonexistent/plan.md']), 0)
        self.assertEqual(pp.main([plan([])]), 0)
        self.assertIn('no implementation steps', pp.report(plan([])))


class Prompts(unittest.TestCase):
    def read(self, name):
        return (ROOT / 'prompts' / name).read_text()

    def test_both_plan_prompts_ask_for_steps_that_run_together(self):
        for name in ('project-plan.md', 'project-plan-investigate.md'):
            text = self.read(name)
            self.assertIn('Shape the steps so they can run together', text, name)
            self.assertIn('Depends on:', text)

    def test_both_implementation_prompts_ask_for_small_output(self):
        for name in ('implement.md', 'implement-investigate.md'):
            text = self.read(name)
            self.assertIn('## Keep the output small', text, name)
            self.assertIn('Edit', text)

    def test_the_new_section_does_not_collide_with_the_worker_prompt_split(self):
        sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
        import worker_prompt
        text = self.read('implement.md') + '\n## Assigned isolated implementation step 3\nwork\n'
        head, _, tail, _ = worker_prompt.split_prompt(text)
        self.assertIn('## Keep the output small', head)
        self.assertTrue(tail.startswith('## Assigned isolated implementation step 3'))


if __name__ == '__main__':
    unittest.main()

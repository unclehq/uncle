#!/usr/bin/env python3
"""A section the plan model holds one level down is patched inside its parent heading, so editing a step no longer fails the merge.

The run that found this: the importer makes `### Implementation steps` (under `## 12. Implementation order`) its own model section,
and to_patch asked the Markdown for `## Implementation steps`, which it does not have. Every step edit then raised
'edit_sections: no existing section with heading', the merge failed and the stage ended 'writer attempts exhausted'."""
import copy
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import plan_model as pm  # noqa: E402
import updated_plan_ops as ops  # noqa: E402
from plan_patch import apply_patch  # noqa: E402

NARRATIVE = '''# Plan

## 1. Architecture

One crate.

## 12. Implementation order

All steps run together.

### Implementation steps

1. **Scaffold** — Write `a.js`.
   Owns: `a.js`
2. **Server** — Write `b.js`.
   Owns: `b.js`

## 14. Risks

Risk text.
'''


def headings(text, marks='##'):
    return re.findall(r'(?m)^%s .+$' % marks, text)


class NestedSection(unittest.TestCase):
    def setUp(self):
        self.model = pm.import_markdown(NARRATIVE)
        steps = next(s for s in self.model['sections'] if s['heading'] == 'Implementation steps')
        self.step = steps['blocks'][0]['items'][0]['id']

    def edit(self, **fields):
        return pm.apply_ops(copy.deepcopy(self.model), [pm.typed_op(self.model, {'op': 'set_step', 'id': self.step, 'fields': fields})])

    def test_the_importer_really_makes_the_nested_span_a_section(self):
        self.assertIn('Implementation steps', [s['heading'] for s in self.model['sections']])
        self.assertNotIn('## Implementation steps', headings(NARRATIVE))

    def test_a_step_edit_patches_inside_the_parent_section(self):
        patch = ops.to_patch(self.model, self.edit(text='Write `a.js` with the new rule.'), NARRATIVE)
        self.assertEqual([e['heading'] for e in patch['edit_sections']], ['## 12. Implementation order'])
        patched = apply_patch(NARRATIVE, patch)
        self.assertIn('new rule', patched)
        self.assertEqual(headings(patched), headings(NARRATIVE))                       # no new `##` section
        self.assertEqual(headings(patched, '###'), ['### Implementation steps'])         # the nested heading is kept, once
        self.assertIn('All steps run together.', patched)                              # the parent's own text is kept
        self.assertIn('Risk text.', patched)                                           # so are the other sections

    def test_the_other_steps_are_untouched(self):
        patched = apply_patch(NARRATIVE, ops.to_patch(self.model, self.edit(text='Changed.'), NARRATIVE))
        self.assertEqual(len(re.findall(r'(?m)^\d+\. \*\*', patched)), 2)
        self.assertIn('Write `b.js`.', patched)

    def test_an_edit_to_the_parent_keeps_the_nested_span(self):
        parent = next(s for s in self.model['sections'] if s['heading'] == '12. Implementation order')
        new = copy.deepcopy(self.model)
        next(s for s in new['sections'] if s['id'] == parent['id'])['blocks'][0]['text'] = 'Steps run in order now.'
        patched = apply_patch(NARRATIVE, ops.to_patch(self.model, new, NARRATIVE))
        self.assertIn('Steps run in order now.', patched)
        self.assertIn('### Implementation steps', patched)
        self.assertIn('Write `a.js`.', patched)                                          # the nested steps survive a parent edit

    def test_an_unchanged_model_makes_no_patch(self):
        patch = ops.to_patch(self.model, copy.deepcopy(self.model), NARRATIVE)
        self.assertEqual((patch['edit_sections'], patch['insert_sections']), ([], []))

    def test_plans_with_only_top_level_sections_are_patched_as_before(self):
        flat = '# P\n\n## 1. A\n\nOne.\n\n## 2. B\n\nTwo.\n'
        model = pm.import_markdown(flat)
        new = copy.deepcopy(model)
        new['sections'][1]['blocks'][0]['text'] = 'Changed.'
        for narrative in (flat, None):
            patch = ops.to_patch(model, new, narrative)
            self.assertEqual([e['heading'] for e in patch['edit_sections']], ['## 2. B'])
            self.assertIn('Changed.', apply_patch(flat, patch))


if __name__ == '__main__':
    unittest.main()

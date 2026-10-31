#!/usr/bin/env python3
"""module_interfaces.py's ui_contract: names the page's files share by string."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import module_interfaces as mi

MODULE = {'file': 'src/calc.js', 'exports': [{'name': 'reduce', 'kind': 'function', 'signature': 'reduce(state, action): State'}]}
KEYPAD = {'kind': 'class', 'name': 'keypad', 'element': 'div around all keys', 'used_by': ['src/App.jsx', 'src/styles.css'],
          'note': '4-column grid'}


def payload(**extra):
    return dict({'schema': 'uncle.artifact/v1', 'kind': 'module-interfaces', 'modules': [MODULE]}, **extra)


class UiContract(unittest.TestCase):
    def test_a_payload_without_a_contract_renders_exactly_as_before(self):
        text = mi.render_section(mi.validate(payload()))
        self.assertIn('## Fixed module interfaces (binding)', text)
        self.assertNotIn('Fixed UI contract', text)

    def test_the_contract_is_rendered_with_its_element_users_and_note(self):
        text = mi.render_section(mi.validate(payload(ui_contract=[KEYPAD])))
        self.assertIn('## Fixed UI contract (binding)', text)
        self.assertIn('- class `keypad` on div around all keys; used by `src/App.jsx`, `src/styles.css` -- 4-column grid', text)
        self.assertIn('a stylesheet defines a rule for every `class` listed', text)

    def test_a_page_only_plan_may_have_no_modules(self):
        text = mi.render_section(mi.validate(payload(modules=[], ui_contract=[KEYPAD])))
        self.assertNotIn('Fixed module interfaces', text)
        self.assertIn('Fixed UI contract', text)

    def test_no_modules_and_no_contract_is_still_invalid(self):
        with self.assertRaises(ValueError):
            mi.validate(payload(modules=[]))
        with self.assertRaises(ValueError):
            mi.validate(payload(modules=[], ui_contract=[]))
        with self.assertRaises(ValueError):                                  # every entry unusable: nothing is left
            mi.validate(payload(modules=[], ui_contract=[dict(KEYPAD, kind='nonsense')]))

    def test_a_bad_ui_contract_never_costs_the_exports_beside_it(self):
        # Live: the model wrote kind `aria-label`; the strict check rejected the whole payload, the stage discarded the
        # exports too, and the parallel steps ran with no contract at all.
        for bad in ('keypad', [KEYPAD, 'oops'], [dict(KEYPAD, kind='nonsense')], [dict(KEYPAD, name='')], [dict(KEYPAD, used_by=[])]):
            checked = mi.validate(payload(ui_contract=bad))
            self.assertEqual(checked['modules'], [MODULE])
            self.assertIn('Fixed module interfaces', mi.render_section(checked))

    def test_unusable_entries_are_dropped_and_the_rest_kept(self):
        checked = mi.validate(payload(ui_contract=[KEYPAD, dict(KEYPAD, kind='nonsense'), dict(KEYPAD, name='')]))
        self.assertEqual([(e['kind'], e['name']) for e in checked['ui_contract']], [('class', 'keypad')])

    def test_the_spellings_a_model_uses_are_understood(self):
        spellings = {'aria-label': 'aria', 'data-testid': 'test-id', 'testid': 'test-id', 'css-class': 'class', 'Class': 'class',
                     'data': 'data-attribute', 'keyboard': 'key', 'element-id': 'id'}
        for written, canonical in spellings.items():
            checked = mi.validate(payload(ui_contract=[dict(KEYPAD, kind=written)]))
            self.assertEqual(checked['ui_contract'][0]['kind'], canonical, written)

    def test_used_by_may_be_a_comma_separated_string(self):
        checked = mi.validate(payload(ui_contract=[dict(KEYPAD, used_by='src/App.jsx, src/styles.css')]))
        self.assertEqual(checked['ui_contract'][0]['used_by'], ['src/App.jsx', 'src/styles.css'])

    def test_the_same_name_twice_keeps_the_first(self):
        checked = mi.validate(payload(ui_contract=[KEYPAD, dict(KEYPAD, note='second')]))
        self.assertEqual(len(checked['ui_contract']), 1)
        self.assertEqual(checked['ui_contract'][0]['note'], '4-column grid')

    def test_the_same_name_may_appear_under_two_kinds(self):
        checked = mi.validate(payload(ui_contract=[KEYPAD, dict(KEYPAD, kind='id')]))
        self.assertEqual(len(checked['ui_contract']), 2)

if __name__ == '__main__':
    unittest.main()

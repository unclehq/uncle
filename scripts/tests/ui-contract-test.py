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

    def test_bad_entries_are_rejected(self):
        bad = [dict(KEYPAD, kind='selector'), dict(KEYPAD, name=''), dict(KEYPAD, used_by=[]), dict(KEYPAD, used_by='src/App.jsx'),
               'keypad']
        for entry in bad:
            with self.assertRaises(ValueError, msg=str(entry)):
                mi.validate(payload(ui_contract=[entry]))
        with self.assertRaises(ValueError):
            mi.validate(payload(ui_contract=[KEYPAD, dict(KEYPAD)]))      # the same kind and name twice
        with self.assertRaises(ValueError):
            mi.validate(payload(ui_contract='keypad'))

    def test_the_same_name_may_appear_under_two_kinds(self):
        mi.validate(payload(ui_contract=[KEYPAD, dict(KEYPAD, kind='id')]))


if __name__ == '__main__':
    unittest.main()

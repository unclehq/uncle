"""--no-footprint mode (Issue 280): pure footprint.py logic plus wiring checks (AC-1..AC-8)."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('footprint', ROOT / 'scripts/lib/footprint.py')
fp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fp)

DISCLOSURE = 'Assisted-by: AI tooling'


class Disclosure(unittest.TestCase):
    def test_default_when_unset(self):
        self.assertTrue(str(fp.resolve_disclosure({}, {})).strip())

    def test_env_beats_config(self):
        got = fp.resolve_disclosure({'footprint.disclosure': 'From config'},
                                    {'UNCLE_FOOTPRINT_DISCLOSURE': 'From env'})
        self.assertIn('From env', str(got))
        self.assertNotIn('From config', str(got))

    def test_empty_or_blank_disclosure_rejected(self):
        for env in ({'UNCLE_FOOTPRINT_DISCLOSURE': ''}, {'UNCLE_FOOTPRINT_DISCLOSURE': '  \t '}):
            with self.assertRaises(ValueError):
                fp.resolve_disclosure({}, env)
        for cfg in ({'footprint.disclosure': ''}, {'footprint.disclosure': '   '}):
            with self.assertRaises(ValueError):
                fp.resolve_disclosure(cfg, {})


class Rendering(unittest.TestCase):
    def test_body_contains_sections_and_disclosure(self):
        body = fp.render_body('Add a widget', 'Users need widgets', 'make test', '', '', DISCLOSURE)
        for part in ('Add a widget', 'Users need widgets', 'make test', DISCLOSURE):
            self.assertIn(part, body)

    def test_message_has_title_and_trailer(self):
        msg = fp.render_message('Add widget', 'Summary', 'Assisted-by: AI tooling')
        self.assertTrue(msg.startswith('Add widget'))
        self.assertIn('Assisted-by: AI tooling', msg)

    def test_empty_trailer_yields_no_trailer(self):
        msg = fp.render_message('Add widget', 'Summary', '')
        self.assertNotIn('Assisted-by', msg)

    def test_strip_vendor_lines(self):
        text = 'Fix bug\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n' \
               '🤖 Generated with [Claude Code](https://claude.com/claude-code)\nKeep this line\n'
        out = fp.strip_vendor_lines(text)
        self.assertIn('Keep this line', out)
        self.assertNotIn('Co-Authored-By', out)
        self.assertNotIn('Claude', out)


class Scan(unittest.TestCase):
    def fields(self, **over):
        base = {'title': 'Add widget', 'body': 'Plain body', 'message': 'Add widget', 'branch': 'widget'}
        base.update(over)
        return base

    def test_clean_fields_pass(self):
        fp.scan(self.fields(), False)

    def test_leak_in_each_field_rejected(self):
        for key, bad in (('title', 'Uncle workflow change'), ('body', 'See .uncle/docs/CHANGE_PLAN.md'),
                         ('message', 'uncle: add widget'), ('branch', 'uncle/widget'),
                         ('body', 'Reviewed by Codex CLI and Claude Code'),
                         ('body', 'ADVERSARIAL_REVIEW passed')):
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                fp.scan(self.fields(**{key: bad}), False)

    def test_allow_uncle_does_not_exempt_publication_fields(self):
        for key in ('title', 'message', 'branch'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                fp.scan(self.fields(**{key: 'uncle thing'}), True)


class Wiring(unittest.TestCase):
    def test_cli_flag_and_stagegate_guard(self):
        self.assertIn('--no-footprint', (ROOT / 'uncle').read_text())
        self.assertIn('UNCLE_NO_FOOTPRINT', (ROOT / 'scripts/stagegate.sh').read_text())

    def test_engine_uses_journal_flag(self):
        src = (ROOT / 'scripts/lib/change-pr.sh').read_text()
        self.assertIn('no_footprint', src)
        self.assertIn('footprint', src)

    def test_readme_documents_mode(self):
        readme = (ROOT / 'README.md').read_text()
        self.assertIn('--no-footprint', readme)

    def test_suite_registered_in_critical_tier(self):
        lines = [l.strip() for l in (ROOT / 'scripts/tests/critical-suites.txt').read_text().splitlines()]
        self.assertIn('no-footprint', lines)


if __name__ == '__main__':
    unittest.main()

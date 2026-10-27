#!/usr/bin/env python3
"""The tab opens on a themed placeholder painted from the brief, with no model, and a real page replaces it."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import preview_placeholder as placeholder


def project(brief='# Application brief\n\n## Summary\nbuild a groovy 1970s calculator\n', interpretation=None):
    root = Path(tempfile.mkdtemp())
    (root / 'REQUIREMENTS.md').write_text(brief)
    if interpretation is not None:
        folder = root / '.uncle' / 'workflow' / 'documents'
        folder.mkdir(parents=True)
        (folder / 'REQUIREMENTS_INTERPRETATION.json').write_text(interpretation)
    return root


class Placeholder(unittest.TestCase):
    def test_it_is_painted_from_the_brief_and_the_interpretations_palette(self):
        root = project(interpretation='{"theme":"orange #CC5500, mustard #E1AD01, avocado #568203"}')
        self.assertTrue(placeholder.write_if_absent(root))
        text = (root / 'index.html').read_text()
        self.assertIn('<!doctype html>', text)
        self.assertIn('build a groovy 1970s calculator', text)
        for color in ('#cc5500', '#e1ad01', '#568203'):
            self.assertIn(color, text)
        self.assertIn('Building the first look', text)

    def test_a_generic_heading_is_not_the_title(self):
        title, lines = placeholder.brief_parts('# Application brief\n\n## Summary\nbuild a groovy calculator\n')
        self.assertEqual(title, 'build a groovy calculator')

    def test_a_real_heading_is_kept_and_text_is_escaped(self):
        title, _ = placeholder.brief_parts('# <b>Ledger</b> & Co\nsome text')
        self.assertEqual(title, '<b>Ledger</b> & Co')
        root = project(brief='# <script>alert(1)</script>\nline <b>bold</b>')
        placeholder.write_if_absent(root)
        text = (root / 'index.html').read_text()
        self.assertNotIn('<script>alert', text)
        self.assertIn('&lt;script&gt;', text)

    def test_text_stays_readable_on_light_and_dark_backgrounds(self):
        dark = placeholder.page('t', [], ['#101010'])
        light = placeholder.page('t', [], ['#f5f0e0'])
        self.assertIn('color:#fafafa', dark)
        self.assertIn('color:#1b1b1b', light)

    def test_it_never_replaces_an_existing_page(self):
        root = project()
        (root / 'index.html').write_text('<h1>real</h1>')
        self.assertFalse(placeholder.write_if_absent(root))
        self.assertEqual((root / 'index.html').read_text(), '<h1>real</h1>')

    def test_no_brief_and_no_palette_still_make_a_page(self):
        root = Path(tempfile.mkdtemp())
        self.assertTrue(placeholder.write_if_absent(root))
        self.assertIn('Preview', (root / 'index.html').read_text())

    def test_it_is_instant_and_leaves_no_temp_file(self):
        root = project(interpretation='{"a":"#abc"}')
        started = time.monotonic()
        subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/lib/preview_placeholder.py'), str(root)], check=True)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(sorted(p.name for p in root.iterdir() if p.is_file()), ['REQUIREMENTS.md', 'index.html'])
        self.assertIn('#aabbcc', (root / 'index.html').read_text())      # a short hex is expanded

    def test_the_command_never_fails(self):
        self.assertEqual(placeholder.main(['/nonexistent/dir']), 0)
        self.assertEqual(placeholder.main([]), 0)


class Prompt(unittest.TestCase):
    def test_the_page_goes_to_the_staging_path_the_driver_publishes(self):
        text = (ROOT / 'prompts' / 'preview-build.md').read_text()
        self.assertIn('.uncle/workflow/preview/index.html', text)
        self.assertIn('do not read, write or look for a root', text)


if __name__ == '__main__':
    unittest.main()

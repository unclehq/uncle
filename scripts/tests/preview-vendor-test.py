#!/usr/bin/env python3
"""React and Babel arrive beside the preview build, and the page falls back to the CDN when they do not."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import preview_vendor as vendor


def source(directory, name, text):
    path = Path(directory) / name
    path.write_text(text)
    return path.as_uri()


class Vendor(unittest.TestCase):
    def setUp(self):
        self.origin = tempfile.mkdtemp()
        self.cache = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.libs = {'a.js': source(self.origin, 'a.js', 'A'), 'b.js': source(self.origin, 'b.js', 'B')}

    def test_libraries_are_copied_into_the_project_uncle_directory(self):
        got = vendor.fetch(self.project, self.libs, self.cache)
        self.assertEqual(sorted(got), ['a.js', 'b.js'])
        self.assertEqual((Path(self.project) / '.uncle/vendor/a.js').read_text(), 'A')

    def test_a_second_project_reuses_the_machine_cache_without_downloading(self):
        vendor.fetch(self.project, self.libs, self.cache)
        for name in self.libs:
            (Path(self.origin) / name).unlink()           # the network is gone
        other = tempfile.mkdtemp()
        self.assertEqual(sorted(vendor.fetch(other, self.libs, self.cache)), ['a.js', 'b.js'])
        self.assertEqual((Path(other) / '.uncle/vendor/b.js').read_text(), 'B')

    def test_one_failed_download_does_not_lose_the_others(self):
        self.libs['c.js'] = (Path(self.origin) / 'missing.js').as_uri()
        self.assertEqual(sorted(vendor.fetch(self.project, self.libs, self.cache)), ['a.js', 'b.js'])
        self.assertFalse((Path(self.project) / '.uncle/vendor/c.js').exists())

    def test_a_failed_download_leaves_no_partial_file_in_the_cache(self):
        self.libs['c.js'] = (Path(self.origin) / 'missing.js').as_uri()
        vendor.fetch(self.project, self.libs, self.cache)
        self.assertEqual(sorted(p.name for p in Path(self.cache).iterdir()), ['a.js', 'b.js'])

    def test_an_empty_download_is_not_kept(self):
        self.libs = {'e.js': source(self.origin, 'e.js', '')}
        self.assertEqual(vendor.fetch(self.project, self.libs, self.cache), [])

    def test_missing_libraries_are_pointed_at_the_cdn(self):
        page = Path(self.project) / 'index.html'
        page.write_text('<script src=".uncle/vendor/a.js"></script><script src=".uncle/vendor/b.js"></script>')
        vendor.fetch(self.project, {'a.js': self.libs['a.js']}, self.cache)       # only a.js arrives
        libraries = {'a.js': 'https://cdn.example/a.js', 'b.js': 'https://cdn.example/b.js'}
        self.assertEqual(vendor.rewrite(self.project, libraries), 1)
        text = page.read_text()
        self.assertIn('.uncle/vendor/a.js', text)
        self.assertIn('https://cdn.example/b.js', text)

    def test_rewrite_leaves_a_page_without_local_references_alone(self):
        page = Path(self.project) / 'index.html'
        page.write_text('<h1>plain</h1>')
        self.assertEqual(vendor.rewrite(self.project, self.libs), 0)
        self.assertEqual(page.read_text(), '<h1>plain</h1>')
        self.assertEqual(vendor.rewrite(tempfile.mkdtemp(), self.libs), 0)      # no page at all

    def test_the_real_pins_are_exact_versions_the_prompt_names(self):
        for url in vendor.LIBRARIES.values():
            self.assertRegex(url, r'@\d+\.\d+\.\d+/')
        prompt = (ROOT / 'prompts' / 'preview-build.md').read_text()
        for name in vendor.LIBRARIES:
            self.assertIn(vendor.LOCAL_PREFIX + name, prompt)


if __name__ == '__main__':
    unittest.main()

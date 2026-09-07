#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('prereqs', Path(__file__).parents[1] / 'lib/early-prerequisites.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PrerequisitesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / '.uncle').mkdir()

    def write(self, name, value):
        (self.root / name).write_text(value)

    def check(self, source='REQUIREMENTS.md'):
        return module.check(source, self.root)

    def test_authoritative_input_blocks_until_available(self):
        self.write('REQUIREMENTS.md', '- Use `resume.pdf` in the project root as the authoritative source for all content.')
        self.assertEqual(self.check(), ['missing or empty source file: resume.pdf'])
        self.write('resume.pdf', '')
        self.assertTrue(self.check())
        self.write('resume.pdf', 'PDF fixture')
        self.assertEqual(self.check(), [])

    def test_outputs_and_examples_are_not_prerequisites(self):
        self.write('REQUIREMENTS.md', 'Create `index.html`.\nFor example use `example.pdf`.\nDo not create `missing.md`.\nDo not use `old.pdf` as the authoritative source.')
        self.assertEqual(self.check(), [])

    def test_change_source_is_separate(self):
        self.write('REQUIREMENTS.md', 'Use `old.pdf` as the authoritative source.')
        self.write('CHANGE_REQUEST.md', 'Update the existing page.')
        self.assertEqual(self.check('CHANGE_REQUEST.md'), [])

    def test_manifest_checks_commands_without_execution(self):
        self.write('.uncle/prerequisites.json', json.dumps({'files': ['data.csv'], 'commands': ['pdftotext']}))
        with patch.object(module.shutil, 'which', return_value=None):
            self.assertEqual(len(self.check()), 2)
        self.write('data.csv', 'input')
        with patch.object(module.shutil, 'which', return_value='/bin/pdftotext'):
            self.assertEqual(self.check(), [])

    def test_invalid_manifest_fails(self):
        for data in [{'files': '../outside'}, {'files': ['../outside']}, {'commands': ['echo hacked']}, {'unknown': []}, []]:
            self.write('.uncle/prerequisites.json', json.dumps(data))
            with self.assertRaises(ValueError):
                self.check()


if __name__ == '__main__':
    unittest.main()

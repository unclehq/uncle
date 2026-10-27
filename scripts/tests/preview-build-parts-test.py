#!/usr/bin/env python3
"""The preview page is written in parts and assembled into the one index.html the rest of the workflow expects."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import preview_build_parts as parts


def write(directory, **files):
    for name, text in files.items():
        (Path(directory) / parts.PARTS[name]).write_text(text)


class Assemble(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def vanilla(self, **override):
        files = dict(contract='framework: vanilla\ntitle: Groovy Calc\n\n## Elements\n- #display\n',
                     markup='<div id="display">0</div>', styles='#display{color:red}', script='document.title="x"')
        files.update(override)
        write(self.dir, **files)

    def test_a_vanilla_page_is_one_document_with_inline_parts(self):
        self.vanilla()
        page = parts.assemble(self.dir)
        self.assertTrue(page.startswith('<!doctype html>'))
        self.assertIn('<title>Groovy Calc</title>', page)
        self.assertIn('<style>\n#display{color:red}\n</style>', page)
        self.assertIn('<div id="display">0</div>', page)
        self.assertIn('<script>\ndocument.title="x"\n</script>', page)
        self.assertNotIn('.uncle/vendor', page)
        self.assertNotIn('<link', page)

    def test_a_react_page_loads_the_local_libraries_and_babel_script(self):
        self.vanilla(contract='framework: react\ntitle: R', script='const App=()=><b/>;')
        (Path(self.dir) / parts.PARTS['markup']).unlink()      # react writes no markup
        page = parts.assemble(self.dir)
        self.assertIn('<div id="root"></div>', page)
        for name in parts.VENDOR:
            self.assertIn('<script src=".uncle/vendor/%s"></script>' % name, page)
        self.assertIn('<script type="text/babel">', page)
        self.assertLess(page.index('babel.min.js'), page.index('const App'))

    def test_workers_for_react_skip_the_markup(self):
        self.vanilla(contract='framework: react')
        self.assertEqual(parts.phase_names(self.dir, 2), ('styles', 'script'))
        self.vanilla()
        self.assertEqual(parts.phase_names(self.dir, 2), ('markup', 'styles', 'script'))
        self.assertEqual(parts.phase_names(self.dir, 1), ('contract',))

    def test_a_part_wrapped_in_its_own_tag_or_a_fence_is_repaired(self):
        self.vanilla(markup='<html><body><p>hi</p></body></html>', styles='<style>p{x:1}</style>',
                     script='```js\nvar a = 1;\n```')
        page = parts.assemble(self.dir)
        self.assertIn('<p>hi</p>', page)
        self.assertEqual(page.count('<style>'), 1)
        self.assertEqual(page.count('<body>'), 1)
        self.assertIn('var a = 1;', page)
        self.assertNotIn('```', page)

    def test_a_script_cannot_close_its_own_tag(self):
        self.vanilla(script='document.write("</script>")')
        page = parts.assemble(self.dir)
        self.assertEqual(page.count('</script>'), 1)

    def test_a_missing_or_empty_part_is_refused(self):
        self.vanilla()
        (Path(self.dir) / parts.PARTS['styles']).unlink()
        with self.assertRaisesRegex(ValueError, 'styles.css'):
            parts.assemble(self.dir)
        self.vanilla(script='   ')
        with self.assertRaisesRegex(ValueError, 'empty'):
            parts.assemble(self.dir)

    def test_a_missing_contract_is_vanilla_and_a_hostile_title_is_cleaned(self):
        self.vanilla(contract='title: <script>alert(1)</script>')
        self.assertEqual(parts.framework(self.dir), 'vanilla')
        self.assertNotIn('<script>alert', parts.assemble(self.dir).split('<style>')[0])


class Prompts(unittest.TestCase):
    def test_every_worker_shares_the_preview_prompt_as_a_prefix_and_writes_one_part(self):
        base = (ROOT / 'prompts' / 'preview-build.md').read_text()
        for name in parts.PARTS:
            text = parts.build_prompt(name, 'd', base)
            self.assertTrue(text.startswith(base.rstrip('\n')))
            self.assertIn('`d/%s`' % parts.PARTS[name], text)
            self.assertIn('Do not write `index.html`', text)

    def test_only_the_contract_reads_nothing_first(self):
        base = 'BASE'
        self.assertNotIn('Read `d/contract.md` first', parts.build_prompt('contract', 'd', base))
        for name in ('markup', 'styles', 'script'):
            self.assertIn('Read `d/contract.md` first', parts.build_prompt(name, 'd', base))


if __name__ == '__main__':
    unittest.main()

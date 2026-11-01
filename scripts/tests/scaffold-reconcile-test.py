import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'scaffold_reconcile', Path(__file__).resolve().parents[2] / 'scripts' / 'lib' / 'scaffold_reconcile.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ScaffoldReconcile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, relpath, text):
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    # ---- vitest discovery ----

    def test_widens_include_when_no_test_file_is_discoverable(self):
        self.write('vitest.config.js',
                    "export default { test: { include: ['tests/unit/**/*.test.{js,jsx}'] } };")
        self.write('tests/engine.test.js', "test('x', () => {})")
        change = module.fix_vitest_discovery(str(self.root))
        self.assertIsNotNone(change)
        self.assertEqual(change['file'], 'vitest.config.js')
        config = (self.root / 'vitest.config.js').read_text()
        self.assertIn("'tests/unit/**/*.test.{js,jsx}'", config, 'the existing pattern must survive, not be replaced')
        self.assertIn('tests/*.test.js', config)

    # ---- the Vitest config in vite.config.* (the calculator case: tests/calc.test.js, include globs for tests/unit and src) ----

    CALCULATOR_VITE_CONFIG = """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['tests/unit/**/*.test.{js,jsx}', 'src/**/*.test.{js,jsx}'],
    exclude: ['tests/e2e/**', 'node_modules/**'],
  },
});
"""

    def test_widens_the_include_in_a_vite_config_test_block(self):
        self.write('vite.config.js', self.CALCULATOR_VITE_CONFIG)
        self.write('tests/calc.test.js', "test('x', () => {})")
        change = module.fix_vitest_discovery(str(self.root))
        self.assertIsNotNone(change)
        self.assertEqual(change['file'], 'vite.config.js')
        config = (self.root / 'vite.config.js').read_text()
        self.assertIn("'tests/unit/**/*.test.{js,jsx}'", config, 'the existing patterns survive')
        self.assertIn("'src/**/*.test.{js,jsx}'", config)
        self.assertIn('tests/*.test.js', config)
        self.assertIn("exclude: ['tests/e2e/**', 'node_modules/**']", config, 'nothing else in the block changes')

    def test_the_widened_vite_config_discovers_the_test_it_missed(self):
        self.write('vite.config.js', self.CALCULATOR_VITE_CONFIG)
        self.write('tests/calc.test.js', "test('x', () => {})")
        module.fix_vitest_discovery(str(self.root))
        include = module.find_include_list((self.root / 'vite.config.js').read_text(), False)
        patterns = __import__('re').findall(r"""['"]([^'"]+)['"]""", include.group(1))
        self.assertTrue(any(module.glob_matches(p, 'tests/calc.test.js') for p in patterns))

    def test_an_include_that_is_not_vitests_is_never_widened(self):
        text = ("export default { optimizeDeps: { include: ['react', 'react-dom'] },\n"
                "  test: { coverage: { include: ['src/**'] }, include: ['tests/unit/**/*.test.js'] } };")
        self.write('vite.config.js', text)
        self.write('tests/calc.test.js', "test('x', () => {})")
        module.fix_vitest_discovery(str(self.root))
        config = (self.root / 'vite.config.js').read_text()
        self.assertIn("optimizeDeps: { include: ['react', 'react-dom'] }", config)
        self.assertIn("coverage: { include: ['src/**'] }", config)
        self.assertRegex(config, r"test: \{ coverage: \{ include: \['src/\*\*'\] \}, include: \['tests/unit/\*\*/\*\.test\.js',\s*'tests/\*\.test\.js'\]")

    def test_a_vite_config_with_no_test_include_is_left_alone(self):
        for text in ("export default { test: { environment: 'jsdom' } };",                       # Vitest's defaults apply
                     "export default { optimizeDeps: { include: ['react'] } };"):                  # no test block: not Vitest's list
            self.write('vite.config.js', text)
            self.write('tests/calc.test.js', "test('x', () => {})")
            self.assertIsNone(module.fix_vitest_discovery(str(self.root)), text)
            self.assertEqual((self.root / 'vite.config.js').read_text(), text)

    def test_a_dedicated_vitest_config_wins_over_vite_config(self):
        self.write('vitest.config.js', "export default { test: { include: ['tests/unit/**/*.test.js'] } };")
        vite = "export default { test: { include: ['tests/unit/**/*.test.js'] } };"
        self.write('vite.config.js', vite)
        self.write('tests/calc.test.js', "test('x', () => {})")
        change = module.fix_vitest_discovery(str(self.root))
        self.assertEqual(change['file'], 'vitest.config.js')
        self.assertEqual((self.root / 'vite.config.js').read_text(), vite)

    def test_other_config_spellings_are_found(self):
        for name in ('vitest.config.mjs', 'vitest.config.ts', 'vite.config.mjs', 'vite.config.ts', 'vite.config.mts'):
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            root = Path(tmp.name)
            (root / name).write_text("export default { test: { include: ['tests/unit/**/*.test.js'] } };", encoding='utf-8')
            (root / 'tests').mkdir()
            (root / 'tests' / 'calc.test.js').write_text("test('x', () => {})", encoding='utf-8')
            change = module.fix_vitest_discovery(str(root))
            self.assertIsNotNone(change, name)
            self.assertEqual(change['file'], name)

    def test_braces_and_brackets_inside_strings_do_not_end_the_test_block(self):
        text = ("export default { test: { setupFiles: ['./a}b.js', \"./c{d.js\"], alias: { '}': 'x' },\n"
                "  include: ['tests/unit/**/*.test.js'] } };")
        self.write('vite.config.js', text)
        self.write('tests/calc.test.js', "test('x', () => {})")
        self.assertIsNotNone(module.fix_vitest_discovery(str(self.root)))
        self.assertIn('tests/*.test.js', (self.root / 'vite.config.js').read_text())

    def test_an_already_discoverable_vite_config_is_left_alone(self):
        self.write('vite.config.js', self.CALCULATOR_VITE_CONFIG)
        self.write('tests/unit/calc.test.js', "test('x', () => {})")
        self.assertIsNone(module.fix_vitest_discovery(str(self.root)))
        self.assertEqual((self.root / 'vite.config.js').read_text(), self.CALCULATOR_VITE_CONFIG)

    def test_the_command_line_reports_the_file_it_changed(self):
        self.write('vite.config.js', self.CALCULATOR_VITE_CONFIG)
        self.write('tests/calc.test.js', "test('x', () => {})")
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(module.main([str(self.root)]), 0)
        reported = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([c['file'] for c in reported], ['vite.config.js'])

    def test_does_nothing_when_a_real_test_file_is_already_covered(self):
        self.write('vitest.config.js',
                    "export default { test: { include: ['tests/unit/**/*.test.{js,jsx}'] } };")
        self.write('tests/unit/engine.test.js', "test('x', () => {})")
        self.assertIsNone(module.fix_vitest_discovery(str(self.root)))

    def test_does_nothing_with_no_config_or_no_test_files(self):
        self.assertIsNone(module.fix_vitest_discovery(str(self.root)))
        self.write('vitest.config.js', "export default { test: { include: ['x/**/*.test.js'] } };")
        self.assertIsNone(module.fix_vitest_discovery(str(self.root)))  # no test files at all

    def test_a_spec_file_never_widens_the_vitest_include(self):
        # vitest's own convention is *.test.*; a *.spec.* file belongs to
        # Playwright. Including it would make vitest try to run a Playwright
        # spec with vitest's globals -- real new breakage.
        self.write('vitest.config.js',
                    "export default { test: { include: ['tests/unit/**/*.test.{js,jsx}'] } };")
        self.write('tests/e2e/keyboard.spec.js', "test('x', () => {})")
        self.assertIsNone(module.fix_vitest_discovery(str(self.root)))

    def test_vitest_fix_second_run_is_a_no_op(self):
        self.write('vitest.config.js',
                    "export default { test: { include: ['tests/unit/**/*.test.{js,jsx}'] } };")
        self.write('tests/engine.test.js', "test('x', () => {})")
        self.assertIsNotNone(module.fix_vitest_discovery(str(self.root)))
        self.assertIsNone(module.fix_vitest_discovery(str(self.root)), 'not idempotent')

    # ---- CJS require() in an ES module project ----

    def test_rewrites_named_and_default_require_to_import(self):
        self.write('package.json', json.dumps({'type': 'module'}))
        self.write('tests/e2e/keyboard.spec.js',
                    "const { test, expect } = require('@playwright/test');\n"
                    "test('x', async ({ page }) => { await page.goto('/'); });\n")
        self.write('tests/e2e/helper.spec.js',
                    "const helper = require('./helper.js');\n"
                    "test('y', () => { expect(helper(1)).toBe(1); });\n")
        changes = module.fix_cjs_requires_in_esm(str(self.root))
        self.assertEqual(len(changes), 2)
        keyboard = (self.root / 'tests/e2e/keyboard.spec.js').read_text()
        self.assertIn("import { test, expect } from '@playwright/test';", keyboard)
        self.assertIn("test('x', async ({ page }) => { await page.goto('/'); });", keyboard,
                       'every other line, including the test body, must survive untouched')
        helper = (self.root / 'tests/e2e/helper.spec.js').read_text()
        self.assertIn("import helper from './helper.js';", helper)
        self.assertIn("test('y', () => { expect(helper(1)).toBe(1); });", helper)

    def test_does_nothing_when_package_is_not_an_es_module(self):
        self.write('package.json', json.dumps({}))  # no "type": "module"
        self.write('tests/e2e/keyboard.spec.js', "const { test } = require('@playwright/test');\n")
        self.assertEqual(module.fix_cjs_requires_in_esm(str(self.root)), [])
        self.assertIn('require(', (self.root / 'tests/e2e/keyboard.spec.js').read_text())

    def test_does_nothing_to_a_file_with_no_require(self):
        self.write('package.json', json.dumps({'type': 'module'}))
        original = "import { test, expect } from '@playwright/test';\ntest('x', () => {});\n"
        self.write('tests/e2e/keyboard.spec.js', original)
        self.assertEqual(module.fix_cjs_requires_in_esm(str(self.root)), [])
        self.assertEqual((self.root / 'tests/e2e/keyboard.spec.js').read_text(), original)

    def test_mjs_and_cjs_files_are_left_alone(self):
        # Their extension already settles module vs. CommonJS regardless of
        # package.json, so a require() in one of them is not the defect this
        # fixes.
        self.write('package.json', json.dumps({'type': 'module'}))
        original = "const { test } = require('@playwright/test');\n"
        self.write('tests/e2e/keyboard.spec.cjs', original)
        self.assertEqual(module.fix_cjs_requires_in_esm(str(self.root)), [])
        self.assertEqual((self.root / 'tests/e2e/keyboard.spec.cjs').read_text(), original)

    def test_cjs_fix_second_run_is_a_no_op(self):
        self.write('package.json', json.dumps({'type': 'module'}))
        self.write('tests/e2e/keyboard.spec.js', "const { test } = require('@playwright/test');\n")
        self.assertEqual(len(module.fix_cjs_requires_in_esm(str(self.root))), 1)
        self.assertEqual(module.fix_cjs_requires_in_esm(str(self.root)), [], 'not idempotent')

    def test_main_prints_one_json_line_per_change(self):
        self.write('vitest.config.js',
                    "export default { test: { include: ['tests/unit/**/*.test.{js,jsx}'] } };")
        self.write('tests/engine.test.js', "test('x', () => {})")
        self.write('package.json', json.dumps({'type': 'module'}))
        self.write('tests/e2e/keyboard.spec.js', "const { test } = require('@playwright/test');\n")
        import io
        import contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = module.main([str(self.root)])
        self.assertEqual(status, 0)
        lines = [l for l in out.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        for line in lines:
            payload = json.loads(line)
            self.assertIn('file', payload)
            self.assertIn('reason', payload)


if __name__ == '__main__':
    unittest.main()

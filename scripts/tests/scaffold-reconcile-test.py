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

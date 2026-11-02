"""Every module the Python host preloads (scripts/lib/pyhost.py PRELOAD) must do nothing at import time that depends on the run.

A preloaded module is imported once, in the host, before any call exists; each forked call inherits that import. A module that read the
environment, the working directory, argv, the clock, a file or the network at import time would hand every later call the host's values
instead of its own. The scan walks module and class bodies (not function bodies, and not `if __name__ == '__main__':` blocks) for such
accesses; the modules must also import cleanly with no output.
"""
import ast
import importlib
import io
import os
from pathlib import Path
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

LIB = Path(__file__).resolve().parents[1] / 'lib'
ATTRIBUTES = ('os.environ', 'os.getcwd', 'sys.argv', 'time.time', 'datetime.now', 'Path.cwd', 'os.getpid', 'random.', 'uuid.', 'tempfile.',
              'os.getenv', 'platform.', 'socket.', 'shutil.which', 'os.getuid', 'getpass', 'sys.stdin', 'sys.stdout', 'sys.stderr')
CALLS = ('open', 'subprocess', 'os.system', 'input', 'print', 'exit', 'sys.exit', 'signal.')


def preload_names():
    source = (LIB / 'pyhost.py').read_text(encoding='utf-8')
    match = re.search(r'^PRELOAD = \((.*?)\)', source, re.M | re.S)
    return re.findall(r"'([A-Za-z_][A-Za-z0-9_]*)'", match.group(1))


def import_time_accesses(tree):
    found = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            pass

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Lambda(self, node):
            pass

        def visit_If(self, node):
            test = ast.unparse(node.test)
            if '__name__' in test and '__main__' in test:
                return                                  # does not run on import
            self.generic_visit(node)

        def visit_Attribute(self, node):
            text = ast.unparse(node)
            if any(item in text for item in ATTRIBUTES):
                found.append(text)
            self.generic_visit(node)

        def visit_Call(self, node):
            text = ast.unparse(node.func)
            if text in CALLS or any(text.startswith(call + '.') for call in CALLS):
                found.append(text + '()')
            self.generic_visit(node)

    Visitor().visit(tree)
    return found


class Preload(unittest.TestCase):
    def test_the_list_is_not_empty_and_names_real_modules(self):
        names = preload_names()
        self.assertTrue(names)
        for name in names:
            self.assertTrue((LIB / f'{name}.py').is_file(), name)

    def test_no_preloaded_module_reads_the_run_at_import_time(self):
        for name in preload_names():
            with self.subTest(module=name):
                tree = ast.parse((LIB / f'{name}.py').read_text(encoding='utf-8'))
                self.assertEqual(import_time_accesses(tree), [], f'{name} touches the run at import time')

    def test_each_imports_cleanly_and_silently(self):
        for name in preload_names():
            with self.subTest(module=name):
                sys.modules.pop(name, None)
                output, errors = io.StringIO(), io.StringIO()
                sys.path.insert(0, str(LIB))
                try:
                    with redirect_stdout(output), redirect_stderr(errors):
                        importlib.import_module(name)
                finally:
                    sys.path.remove(str(LIB))
                self.assertEqual((output.getvalue(), errors.getvalue()), ('', ''))

    def test_the_scan_catches_what_it_is_meant_to(self):
        module_level = ast.parse("import os\nHOME = os.environ.get('HOME')\n")
        in_function = ast.parse("import os\ndef f():\n    return os.environ\n")
        in_main_block = ast.parse("import sys\nif __name__ == '__main__':\n    x = sys.argv\n")
        in_class_body = ast.parse("import os\nclass C:\n    home = os.getcwd()\n")
        self.assertTrue(import_time_accesses(module_level))
        self.assertTrue(import_time_accesses(in_class_body))
        self.assertEqual(import_time_accesses(in_function), [])
        self.assertEqual(import_time_accesses(in_main_block), [])


if __name__ == '__main__':
    unittest.main()

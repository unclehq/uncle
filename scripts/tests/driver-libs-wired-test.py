#!/usr/bin/env python3
"""Every function a driver calls from a sourced library must come from a library that driver actually sources.

Three feature branches each inserted their `source` line at the same spot in change-workflow.sh, and a merge conflict kept only one:
the installed driver then called `change_class_lenses`, `classify_change_stage` and `early_baseline_start` with nothing defining them,
the review panel got an empty lens list, and a run stopped at ADVERSARIAL_REVIEW with "command not found". The libraries' own tests
all passed, because each test sources its library itself. This one reads the drivers.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'scripts/lib'
SOURCE = re.compile(r'(?m)^\s*\.\s+"\$ROOT/scripts/lib/([A-Za-z0-9_.-]+\.sh)"')
DEFINE = re.compile(r'(?m)^([a-z_][a-z0-9_]*)\(\)\s*\{')


def definitions(path):
    return set(DEFINE.findall(path.read_text(encoding='utf-8')))


def sourced(driver):
    """The libraries a driver sources, transitively through other libraries' own `source` lines."""
    seen, todo = {}, [driver]
    while todo:
        text = todo.pop().read_text(encoding='utf-8')
        for name in SOURCE.findall(text):
            if name not in seen and (LIB / name).is_file():
                seen[name] = LIB / name
                todo.append(LIB / name)
    return seen


class DriversSourceWhatTheyCall(unittest.TestCase):
    # Functions owned by the optional-stage libraries added for the build classifier, the early baseline and the plan duties,
    # plus the module-interfaces one: the call sites that have to resolve in both drivers that use them.
    OWNED = {
        'change-class-stage.sh': ('classify_change_stage', 'change_class_lenses', 'change_class_edit_slice', 'change_class_test_scope',
                                  'change_class_decide_test_scope'),
        'early-baseline.sh': ('early_baseline_start', 'early_baseline_reuse'),
        'change-plan-duties-stage.sh': ('change_plan_duties_stage',),
        'module-interfaces-stage.sh': ('module_interfaces_stage', 'derive_module_interfaces'),
    }

    def test_every_library_function_a_driver_calls_is_defined_by_a_library_it_sources(self):
        for driver in ('change-workflow.sh', 'stagegate.sh'):
            path = ROOT / 'scripts' / driver
            text = path.read_text(encoding='utf-8')
            libs = sourced(path)
            own = definitions(path)
            for library, names in self.OWNED.items():
                for name in names:
                    # A call: the name at the start of a command or inside $( ), not its definition or a comment.
                    call = re.search(r'(?m)^(?!\s*#)[^#\n]*\b%s\b(?!\s*\(\))' % re.escape(name), text)
                    if not call or name in own:
                        continue
                    self.assertIn(library, libs, '%s calls %s but does not source %s' % (driver, name, library))
                    self.assertIn(name, definitions(LIB / library), '%s does not define %s' % (library, name))

    def test_the_optional_stages_can_be_rerun_by_name(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('rerun_stage', LIB / 'rerun_stage.py')
        import sys
        sys.path.insert(0, str(LIB))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in ('classify-change', 'change-plan-stage-duties'):
            self.assertTrue(module.supports(name, 'change'), name)
        self.assertTrue(module.supports('classify-change', 'app'))
        names = list(module.CHANGE)
        # Duties run right after planning, ahead of PLAN and CLASSIFY, so a rerun invalidates the right approvals.
        self.assertLess(names.index('change-plan-stage-duties'), names.index('change-plan'))
        self.assertLess(names.index('change-plan'), names.index('classify-change'))
        self.assertLess(names.index('classify-change'), names.index('adversarial-review'))

    def test_the_helper_finds_the_sourced_libraries(self):
        libs = sourced(ROOT / 'scripts/change-workflow.sh')
        self.assertIn('module-interfaces-stage.sh', libs)
        self.assertIn('green-check.sh', libs)


if __name__ == '__main__':
    unittest.main()

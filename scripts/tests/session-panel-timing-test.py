import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('uncle_tui', Path(__file__).resolve().parents[2] / 'uncle_tui.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fake_app(records, active=None):
    app = SimpleNamespace()
    app.session_stats = {'records': records, 'active': active or {}, 'live': {}}
    app._token_total = staticmethod(module.UncleTUI._token_total).__get__(app)
    app._live_cost = module.UncleTUI._live_cost.__get__(app)
    return app


class SessionPanelTiming(unittest.TestCase):
    def test_parallel_workers_report_wall_clock_not_summed_time(self):
        # Four workers of the same panel, each 100s, fully overlapping
        # (started together, ended together). The old behavior summed each
        # worker's own elapsed time -- 400s for a 100s panel. The real
        # wall-clock span a person waited is 100s.
        records = [
            {'stage': 'adversarial-review-worker-%s' % lens, 'started_at': 1000, 'ended_at': 1100,
             'elapsed_seconds': 100, 'process_exit': 0}
            for lens in ('requirements', 'regression', 'security', 'testability')
        ]
        lines = module.UncleTUI._session_panel_lines(fake_app(records))
        idx = lines.index('adversarial (4 workers)')
        self.assertEqual(lines[idx + 1], 'Time   0:01:40')

    def test_partially_overlapping_workers_span_min_start_to_max_end(self):
        records = [
            {'stage': 'test-review-worker-coverage', 'started_at': 0, 'ended_at': 60,
             'elapsed_seconds': 60, 'process_exit': 0},
            {'stage': 'test-review-worker-integrity', 'started_at': 30, 'ended_at': 150,
             'elapsed_seconds': 120, 'process_exit': 0},
        ]
        lines = module.UncleTUI._session_panel_lines(fake_app(records))
        idx = lines.index('test (2 workers)')
        # Span is 0 -> 150 = 150s, not 60+120=180s.
        self.assertEqual(lines[idx + 1], 'Time   0:02:30')

    def test_sequential_retry_attempts_include_gaps_between_them(self):
        # Two attempts of the same stage, not concurrent, with a 20s gap
        # between them (e.g. a supervision diagnosis). Wall-clock span
        # correctly includes that gap; summing each attempt's own elapsed
        # time would silently drop it.
        records = [
            {'stage': 'updated-plan', 'started_at': 0, 'ended_at': 10, 'elapsed_seconds': 10, 'process_exit': 1},
            {'stage': 'updated-plan', 'started_at': 30, 'ended_at': 40, 'elapsed_seconds': 10, 'process_exit': 0},
        ]
        lines = module.UncleTUI._session_panel_lines(fake_app(records))
        idx = lines.index('updated-plan (2 attempts)')
        self.assertEqual(lines[idx + 1], 'Time   0:00:40')

    def test_single_stage_time_is_unaffected(self):
        records = [{'stage': 'preflight', 'started_at': 0, 'ended_at': 45, 'elapsed_seconds': 45, 'process_exit': 0}]
        lines = module.UncleTUI._session_panel_lines(fake_app(records))
        idx = lines.index('preflight')
        self.assertEqual(lines[idx + 1], 'Time   0:00:45')


class RetireActiveParent(unittest.TestCase):
    """requirements, preflight and preview-build are started as genuinely
    detached background jobs the driver does not wait for before the next
    foreground stage begins. A bare stage's own entry must survive the next
    stage's start event -- only a sub-worker ("-worker-"/"-step-"/etc, where
    raw != parent) may be retired here, because the driver really does wait
    for every worker of a panel to join before moving on."""

    def retire(self, active, parent):
        app = SimpleNamespace(session_stats={'active': dict(active), 'live': {}})
        module.UncleTUI._retire_active_parent(app, parent)
        return app.session_stats['active']

    def test_a_bare_background_stage_is_not_retired_by_the_next_stage_starting(self):
        # The real call site passes parent_stage(the OLD status_stage), i.e.
        # the stage being left, not the one being entered -- status_stage was
        # "preflight" and the next foreground stage ("implementation")
        # starting is what triggers this call.
        active = self.retire({'preflight': 100.0}, 'preflight')
        self.assertIn('preflight', active, 'preflight was hidden while still actually running')

    def test_requirements_survives_the_next_stage_starting(self):
        active = self.retire({'requirements': 100.0}, 'requirements')
        self.assertIn('requirements', active)

    def test_a_sub_worker_of_the_left_parent_is_still_retired(self):
        active = self.retire({'implementation-step-3': 100.0}, 'implementation')
        self.assertNotIn('implementation-step-3', active)

    def test_a_sibling_bare_stage_is_untouched(self):
        active = self.retire({'preflight': 100.0, 'other-stage': 50.0}, 'other-stage')
        self.assertIn('preflight', active)
        self.assertIn('other-stage', active, 'the exact parent itself must not retire its own entry either')


if __name__ == '__main__':
    unittest.main()

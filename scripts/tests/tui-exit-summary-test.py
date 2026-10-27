#!/usr/bin/env python3
"""Exit token summary: totals, per-group breakdown, no dollars (Issue 113)."""
import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import uncle_tui
from uncle_tui import UncleTUI


def ui_with(records, active=None):
    ui = UncleTUI.__new__(UncleTUI)
    ui.session_stats = {'active': active or {}, 'live': {}, 'records': records}
    return ui


def row(stage, i=100, o=20, cr=10, cw=5, started=1, **extra):
    return dict(stage=stage, started_at=started, input_tokens=i, output_tokens=o,
                cache_read_tokens=cr, cache_write_tokens=cw, reported_cost_usd=0.5, **extra)


class Summary(unittest.TestCase):
    def test_totals_and_groups_without_dollars(self):
        lines = ui_with([row('implementation-step-1'), row('implementation-step-2', started=2),
                         row('synthesis', i=1000, started=3)]).exit_token_summary_lines()
        text = '\n'.join(lines)
        self.assertEqual(lines[0], 'Tokens: input 1,200  output 60  cache-read 30  cache-write 15')
        self.assertIn('  implementation: input 200  output 40  cache-read 20  cache-write 10', lines)
        self.assertIn('  synthesis: input 1,000', text)
        self.assertNotIn('$', text)
        self.assertNotIn('Cost', text)

    def test_summary_empty_session(self):
        self.assertEqual(ui_with([]).exit_token_summary_lines(), [])

    def test_summary_missing_fields_unavailable(self):
        lines = ui_with([dict(stage='a', started_at=1, input_tokens=5),
                         dict(stage='a', started_at=2, input_tokens=7, output_tokens=1)]).exit_token_summary_lines()
        self.assertEqual(lines[0], 'Tokens: input 12  output 1 (partial)  cache-read Unavailable  cache-write Unavailable')
        live = ui_with([row('a')], active={'b': 1}).exit_token_summary_lines()
        self.assertIn('input 100 (partial)', live[0])

    def test_label_control_characters_stripped(self):
        lines = ui_with([row('evil\x1b[31m\x07')]).exit_token_summary_lines()
        self.assertNotIn('\x1b', '\n'.join(lines))
        self.assertNotIn('\x07', '\n'.join(lines))

    def test_non_numeric_is_unavailable(self):
        lines = ui_with([row('a', i='lots')]).exit_token_summary_lines()
        self.assertIn('input Unavailable', lines[0])


class Emit(unittest.TestCase):
    def test_summary_after_finished_lines(self):
        out = io.StringIO()
        with redirect_stdout(out):
            uncle_tui.emit_exit_output(['Finished build: x', 'Total time: 1'], ['Tokens: input 1'])
        self.assertEqual(out.getvalue().splitlines(), ['Finished build: x', 'Total time: 1', 'Tokens: input 1'])

    def test_emit_nothing_when_empty(self):
        out = io.StringIO()
        with redirect_stdout(out):
            uncle_tui.emit_exit_output([], [])
        self.assertEqual(out.getvalue(), '')

    def test_summary_exception_swallowed(self):
        class FakeUI:
            def __init__(self, stdscr): pass
            def run(self): pass
            def finished_build_lines(self): return ['Finished build: x']
            def exit_token_summary_lines(self): raise RuntimeError('boom')
        with patch.object(uncle_tui, 'UncleTUI', FakeUI), patch.object(uncle_tui, '_tty_fd', side_effect=OSError):
            self.assertEqual(uncle_tui.main(None), ['Finished build: x'])
        self.assertEqual(uncle_tui._EXIT_SUMMARY_LINES, ['Token summary unavailable'])
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            uncle_tui._emit_summary_safely(['Finished build: x'], uncle_tui._EXIT_SUMMARY_LINES)
        self.assertEqual(out.getvalue().strip(), 'Finished build: x')
        self.assertIn('Token summary unavailable', err.getvalue())

    def test_summary_recorded_on_stopped_exit(self):
        class FakeUI:
            def __init__(self, stdscr): pass
            def run(self): raise SystemExit(3)
            def exit_token_summary_lines(self): return ['Tokens: input 1']
        with patch.object(uncle_tui, 'UncleTUI', FakeUI), patch.object(uncle_tui, '_tty_fd', side_effect=OSError):
            with self.assertRaises(SystemExit) as cm:
                uncle_tui.main(None)
        self.assertEqual(cm.exception.code, 3)
        self.assertEqual(uncle_tui._EXIT_SUMMARY_LINES, ['Tokens: input 1'])


ROOT = Path(__file__).resolve().parents[2]

# Runs the real `__main__` block of uncle_tui.py with curses.wrapper replaced by a
# shim that swaps in a fake UI inside the freshly executed module's globals.
HARNESS = r'''
import curses, runpy, sys
mode = sys.argv[2]
class FakeUI:
    def __init__(self, stdscr): pass
    def run(self):
        if mode == 'exit': raise SystemExit(3)
    def finished_build_lines(self): return ['Finished build: x', 'Total time: 1']
    def exit_token_summary_lines(self): return ['Tokens: input 1']
def wrapper(func, *a, **k):
    func.__globals__['UncleTUI'] = FakeUI
    func.__globals__['_tty_fd'] = lambda: (_ for _ in ()).throw(OSError())
    return func(None)
curses.wrapper = wrapper
runpy.run_path(sys.argv[1], run_name='__main__')
'''


class RealMain(unittest.TestCase):
    def run_main(self, mode):
        import os, subprocess, tempfile
        with tempfile.TemporaryDirectory() as project:
            env = dict(os.environ, UNCLE_PROJECT_ROOT=project)
            return subprocess.run([sys.executable, '-I', '-c', HARNESS, str(ROOT / 'uncle_tui.py'), mode],
                                  capture_output=True, text=True, env=env, cwd=project, timeout=60)

    def test_normal_exit_prints_finished_lines_before_summary(self):
        r = self.run_main('normal')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ['Finished build: x', 'Total time: 1', 'Tokens: input 1'])

    def test_system_exit_preserves_code_and_prints_summary(self):
        r = self.run_main('exit')
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ['Tokens: input 1'])


class CostPersistence(unittest.TestCase):
    def test_write_metric_still_emits_cost_fields(self):
        import json, tempfile
        sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
        import supervisor
        with tempfile.TemporaryDirectory() as state:
            supervisor.write_metric(state, 1, 'codex', 'm', 'high', 5, 0,
                                    {'input_tokens': 10, 'output_tokens': 2}, 0.25, Path(state) / 'log')
            rows = [json.loads(p.read_text()) for p in (Path(state) / 'metrics').glob('*.json')]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['reported_cost_usd'], 0.25)

    def test_session_stats_records_keep_cost_data(self):
        ui = ui_with([row('a')])
        self.assertEqual(ui.session_stats['records'][0]['reported_cost_usd'], 0.5)
        ui.exit_token_summary_lines()
        self.assertEqual(ui.session_stats['records'][0]['reported_cost_usd'], 0.5)


if __name__ == '__main__':
    unittest.main()

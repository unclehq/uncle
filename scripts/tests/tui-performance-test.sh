#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
python3 -B - <<'PY'
import curses, queue, unittest
from unittest.mock import patch
from uncle_tui import UncleTUI

class Screen:
    def __init__(self): self.tick=0
    def keypad(self, _): pass
    def timeout(self, _): pass
    def getch(self):
        self.tick+=1
        return ord('q') if self.tick==20 else -1
    def getmaxyx(self): return (30,100)

class Quiet(UncleTUI):
    def __init__(self):
        self.stdscr=Screen(); self.state='config'; self._reload_tick=0; self.draws=[]
    def _setup_colors(self): pass
    def poll_status(self): return False
    def maybe_reload(self): return False
    def handle_key(self, key): self.state='quit'
    def draw(self): self.draws.append(self.stdscr.tick)
    def stop_workflow(self): pass

class Redraws(unittest.TestCase):
    @patch('curses.curs_set')
    def test_idle_does_not_redraw(self, _):
        ui=Quiet(); ui.run(); self.assertEqual(ui.draws,[1])
    @patch('curses.curs_set')
    def test_status_and_resize_redraw(self, _):
        ui=Quiet()
        ui.poll_status=lambda: ui.stdscr.tick==4
        ui.stdscr.getmaxyx=lambda: (30,100 if ui.stdscr.tick<10 else 90)
        ui.run(); self.assertEqual(ui.draws,[1,5,10])
    @patch('curses.curs_set')
    def test_config_reload_redraws(self, _):
        ui=Quiet(); ui.maybe_reload=lambda: True
        ui.run(); self.assertEqual(ui.draws,[1,12])
    def test_partial_prompt_becomes_visible_without_more_output(self):
        ui=Quiet(); ui.out_q=queue.Queue(); ui.proc_done=False
        ui.prompt_kind=''; ui.partial='Ready? [Y/N] '; ui.prompt_seen=0
        self.assertFalse(UncleTUI.drain_output(ui))
        self.assertFalse(UncleTUI.drain_output(ui))
        self.assertTrue(UncleTUI.drain_output(ui))
        self.assertEqual(ui.prompt_kind,'confirm')

unittest.main()
PY

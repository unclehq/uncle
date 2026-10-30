#!/usr/bin/env python3
"""The early in-progress preview must never open a browser tab for a change
request -- not once, not racily, not ever.

Reported live, twice: an issue against uncle's own repo (a CLI tool, not a
web app, whose only index.html is its own build-status dashboard) still
popped a browser tab during its own "change-plan"/"implementation" stages.
_offer_support's completion preview already guarded this correctly via
.uncle/workflow/family; _poll_early_preview and _preview_after_implementation
did not (fix #1). Gating those two on the same file then still failed once
more: the child driver writes that file moments after it starts, and a
stale "app" value left over from an earlier, unrelated run in the same
directory was read and cached before the new change-request driver had a
chance to overwrite it (fix #2) -- self.workflow_idx, set to 2 by every path
that starts a change/existing-repo run before the child process is even
spawned, carries no such race and is now the primary, unconditional gate.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from uncle_tui import UncleTUI


class EarlyPreviewFamilyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, UNCLE_PROJECT_ROOT=str(self.root))
        env.start()
        self.addCleanup(env.stop)
        # A real, non-empty root index.html: _previewable_page's own
        # fallback for a project with no launch.json yet -- and, for uncle's
        # own repo, its actual build-status dashboard, not a web app.
        (self.root / 'index.html').write_text('<html></html>')

    def set_family(self, family):
        workflow = self.root / '.uncle' / 'workflow'
        workflow.mkdir(parents=True, exist_ok=True)
        if family is not None:
            (workflow / 'family').write_text(family)

    def ui(self, stage, workflow_idx=None):
        ui = UncleTUI.__new__(UncleTUI)
        ui.status_stage = stage
        ui.completion_preview = None
        ui.early_preview_shown = False
        ui._early_preview_next = 0.0
        ui.workflow_idx = workflow_idx
        return ui

    def test_a_change_request_implementation_stage_opens_nothing(self):
        self.set_family('change')
        ui = self.ui('implementation', workflow_idx=2)
        with patch('uncle_tui.UncleTUI._show_early_preview') as show:
            ui._poll_early_preview()
            show.assert_not_called()

    def test_an_app_build_implementation_stage_still_opens_it(self):
        self.set_family('app')
        ui = self.ui('implementation', workflow_idx=0)
        with patch('uncle_tui.UncleTUI._show_early_preview') as show:
            ui._poll_early_preview()
            show.assert_called_once()

    def test_a_stale_app_marker_from_an_earlier_run_does_not_fool_a_change_request(self):
        # The actual live incident: workflow_idx=2 (a change request was
        # explicitly started) but the family marker on disk is still "app",
        # left over from an earlier, unrelated run in the same directory --
        # the child driver has not yet overwritten it. workflow_idx must
        # block this outright, without ever consulting the stale file.
        self.set_family('app')
        ui = self.ui('implementation', workflow_idx=2)
        with patch('uncle_tui.UncleTUI._show_early_preview') as show:
            ui._poll_early_preview()
            show.assert_not_called()

    def test_no_marker_yet_is_treated_as_not_an_app_build(self):
        self.set_family(None)
        ui = self.ui('implementation', workflow_idx=0)
        with patch('uncle_tui.UncleTUI._show_early_preview') as show:
            ui._poll_early_preview()
            show.assert_not_called()

    def test_the_marker_is_re_read_fresh_every_time_not_cached(self):
        # Caching a transiently-stale first read is exactly what let the
        # earlier version of this fix fail: it must re-check every tick.
        self.set_family(None)
        ui = self.ui('implementation', workflow_idx=0)
        with patch('uncle_tui.UncleTUI._show_early_preview') as show:
            ui._poll_early_preview()
            show.assert_not_called()
            self.set_family('app')
            ui._early_preview_next = 0.0
            ui._poll_early_preview()
            show.assert_called_once()

    def test_preview_after_implementation_is_also_family_gated(self):
        self.set_family('change')
        ui = self.ui('implementation', workflow_idx=2)
        with patch('uncle_tui.UncleTUI._show_early_preview') as show:
            ui._preview_after_implementation('implementation')
            show.assert_not_called()
        self.set_family('app')
        ui2 = self.ui('implementation', workflow_idx=0)
        with patch('uncle_tui.UncleTUI._show_early_preview') as show:
            ui2._preview_after_implementation('implementation')
            show.assert_called_once()

    def test_preview_after_implementation_also_resists_the_stale_marker_race(self):
        self.set_family('app')
        ui = self.ui('implementation', workflow_idx=2)
        with patch('uncle_tui.UncleTUI._show_early_preview') as show:
            ui._preview_after_implementation('implementation')
            show.assert_not_called()


if __name__ == '__main__':
    unittest.main()

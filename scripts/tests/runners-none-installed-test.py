#!/usr/bin/env python3
"""With no agent installed, runners_for falls back to ["self-hosted"]."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import uncle_tui  # noqa: E402

WINDOWS = os.name == "nt"
SIDES = (uncle_tui.AGENT, uncle_tui.REVIEWER)


def fake_binary(directory, name):
    if WINDOWS:
        path = os.path.join(directory, name + ".bat")
        Path(path).write_text("@echo off\r\n")
        return path
    path = os.path.join(directory, name)
    Path(path).write_text("#!/bin/sh\nexit 0\n")
    os.chmod(path, 0o755)
    return path


class Stub:
    """Just enough of UncleTUI for stage_runner and _field_display."""
    notice = ""

    def __init__(self, runners=None):
        self.stage_runners = dict(runners or {})
        self.stage_efforts = {}
        self.stage_models = {}
        self.stage_networks = {}
        self.stage_base_urls = {}
        self.stage_api_keys = {}

    _stage_value = uncle_tui.UncleTUI._stage_value
    stage_runner = uncle_tui.UncleTUI.stage_runner
    _field_value = uncle_tui.UncleTUI._field_value
    _field_display = uncle_tui.UncleTUI._field_display


class RunnersNoneInstalled(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = os.environ.get("PATH")
        self.old_default = uncle_tui.DEFAULT_RUNNER
        os.environ["PATH"] = self.tmp.name
        uncle_tui.DEFAULT_RUNNER = ""
        self.stage = next(iter(uncle_tui.STAGE_SIDE))

    def tearDown(self):
        if self.old_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = self.old_path
        uncle_tui.DEFAULT_RUNNER = self.old_default
        self.tmp.cleanup()

    def test_no_runner_each_side(self):
        for side in SIDES:
            self.assertEqual(uncle_tui.runners_for(side), ["self-hosted"], side)

    def test_unset_and_empty_path_each_side(self):
        for value in ("", None):
            if value is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = value
            for side in SIDES:
                self.assertEqual(uncle_tui.runners_for(side), ["self-hosted"], (value, side))
            self.assertEqual(Stub().stage_runner(self.stage), "self-hosted", value)

    def test_stage_runner_default_is_self_hosted(self):
        self.assertEqual(Stub().stage_runner(self.stage), "self-hosted")

    def test_description_says_self_hosted_not_no_agents(self):
        text = Stub()._field_display(self.stage, "runner")
        self.assertIn("Self hosted", text)
        self.assertNotIn("No agents installed", text)
        self.assertNotIn("self-hosted", text)

    def test_explicit_self_hosted_description(self):
        text = Stub({self.stage: "self-hosted"})._field_display(self.stage, "runner")
        self.assertEqual(text, "Self hosted")

    def test_configured_but_uninstalled_runner_unchanged(self):
        stub = Stub({self.stage: "claude"})
        self.assertEqual(stub.stage_runner(self.stage), "claude")
        self.assertEqual(uncle_tui.runners_for(uncle_tui.AGENT), ["self-hosted"])

    def test_unconfigured_self_hosted_default_matches_explicit_selection(self):
        # No separate configuration gate exists in uncle_tui today for an
        # unconfigured self-hosted stage (the shim rejects it at run time), so
        # defaulting must at least be indistinguishable from selecting it.
        default = Stub()
        explicit = Stub({self.stage: "self-hosted"})
        self.assertEqual(default.stage_runner(self.stage), explicit.stage_runner(self.stage))
        for field in ("base_url", "api_key", "model"):
            self.assertEqual(default._field_display(self.stage, field),
                             explicit._field_display(self.stage, field), field)
        self.assertEqual(default._field_display(self.stage, "api_key"), "not set")
        self.assertEqual(default._field_display(self.stage, "base_url"), "not set")

    @unittest.skipIf(WINDOWS, "fake binaries need POSIX executable bits")
    def test_claude_and_opencode(self):
        fake_binary(self.tmp.name, "claude")
        fake_binary(self.tmp.name, "opencode")
        for side in SIDES:
            self.assertEqual(uncle_tui.runners_for(side), ["claude", "self-hosted"], side)

    @unittest.skipIf(WINDOWS, "fake binaries need POSIX executable bits")
    def test_opencode_only(self):
        fake_binary(self.tmp.name, "opencode")
        for side in SIDES:
            self.assertEqual(uncle_tui.runners_for(side), ["self-hosted"], side)


if __name__ == "__main__":
    unittest.main()

"""Hosted mode tests (step 1: standard-name fallback in self_hosted.settings)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import hosted  # noqa: E402
import self_hosted  # noqa: E402

STD = {"UNCLE_HOSTED": "1", "OPENAI_BASE_URL": "http://h.example/v1",
       "OPENAI_API_KEY": "std-key", "SEREN_MODEL": "std-model"}


def run_settings(env, config_text="", stored=None, stage="implement"):
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "config")
        with open(cfg, "w") as f:
            f.write(config_text)
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(self_hosted, "read_keys", return_value=stored or {}):
            return self_hosted.settings(cfg, stage)


class Predicate(unittest.TestCase):
    def test_exact_one_only(self):
        self.assertTrue(hosted.is_hosted({"UNCLE_HOSTED": "1"}))
        for v in (None, "", "0", "true", " 1", "1 "):
            env = {} if v is None else {"UNCLE_HOSTED": v}
            self.assertFalse(hosted.is_hosted(env), v)

    def test_model_precedence_and_blank(self):
        self.assertEqual(hosted.standard_model_settings({"SEREN_MODEL": "a", "UNCLE_MODEL": "b"})["model"], "a")
        self.assertEqual(hosted.standard_model_settings({"SEREN_MODEL": "  ", "UNCLE_MODEL": "b"})["model"], "b")


class Fallback(unittest.TestCase):
    def test_fills_when_hosted(self):
        r = run_settings(STD)
        self.assertEqual((r["base_url"], r["model"], r["api_key"]), ("http://h.example/v1", "std-model", "std-key"))

    def test_ignored_when_not_hosted(self):
        env = dict(STD, UNCLE_HOSTED="true")
        with self.assertRaises(ValueError):
            run_settings(env)

    def test_env_override_wins(self):
        r = run_settings(dict(STD, UNCLE_SELF_HOSTED_MODEL="mine", UNCLE_SELF_HOSTED_API_KEY="k"))
        self.assertEqual((r["model"], r["api_key"]), ("mine", "k"))

    def test_a_no_selection_error_not_masked(self):
        stored = {"__opencode_models__": {"m1": {"model": "m1", "base_url": "http://p/v1", "api_key": "k"}}}
        with self.assertRaises(ValueError) as cm:
            run_settings(STD, stored=stored)
        self.assertIn("No self hosted model is selected", str(cm.exception))

    def test_b_profile_empty_key_filled_only(self):
        stored = {"__opencode_models__": {"m1": {"model": "m1", "base_url": "http://p/v1", "api_key": ""}}}
        r = run_settings(STD, config_text="implement.model m1\n", stored=stored)
        self.assertEqual((r["model"], r["base_url"], r["api_key"]), ("m1", "http://p/v1", "std-key"))

    def test_c_bad_fallback_url_not_leaked(self):
        bad = "http://user:pw@h.example/v1?token=SECRETTOKEN"
        with self.assertRaises(ValueError) as cm:
            run_settings(dict(STD, OPENAI_BASE_URL=bad))
        msg = str(cm.exception)
        self.assertIn("OPENAI_BASE_URL", msg)
        for leak in ("user", "pw", "SECRETTOKEN", "h.example"):
            self.assertNotIn(leak, msg)

    def test_hosted_hint_on_missing_model(self):
        env = {"UNCLE_HOSTED": "1", "OPENAI_BASE_URL": "http://h/v1", "OPENAI_API_KEY": "k"}
        with self.assertRaises(ValueError) as cm:
            run_settings(env)
        self.assertIn("SEREN_MODEL", str(cm.exception))


class ShellResolution(unittest.TestCase):
    def sh(self, env, expr):
        import subprocess
        e = {"PATH": os.environ["PATH"], "UNCLE_CONFIG": "/dev/null"}
        e.update(env)
        script = '. "%s/scripts/lib/stage-config.sh"; %s' % (ROOT, expr)
        return subprocess.run(["bash", "-c", script], env=e, capture_output=True, text=True).stdout

    def test_hosted_defaults(self):
        out = self.sh({"UNCLE_HOSTED": "1", "SEREN_MODEL": " m "},
                      'echo "$(uncle_stage_runner implementation)|$(uncle_stage_model implementation)|$UNCLE_PUBLISH_MODE"')
        self.assertEqual(out.strip(), "self-hosted|m|handoff")

    def test_explicit_values_kept_and_uncle_model_fallback(self):
        out = self.sh({"UNCLE_HOSTED": "1", "UNCLE_MODEL": "u", "UNCLE_PUBLISH_MODE": "pr"},
                      'echo "$(uncle_stage_model implementation)|$UNCLE_PUBLISH_MODE"')
        self.assertEqual(out.strip(), "u|pr")

    def test_not_hosted_unchanged(self):
        for v in ("0", "", "true"):
            out = self.sh({"UNCLE_HOSTED": v, "SEREN_MODEL": "m"},
                          'echo "$(uncle_stage_runner implementation)|$(uncle_stage_model implementation)|${UNCLE_PUBLISH_MODE:-}"')
            self.assertEqual(out.strip(), "claude||", v)


class SupervisorDefault(unittest.TestCase):
    def load(self, env, text=""):
        import supervisor
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "config")
            open(cfg, "w").write(text)
            with mock.patch.dict(os.environ, env, clear=True):
                return supervisor.load_config(cfg)

    def test_hosted_defaults_self_hosted_model(self):
        c = self.load({"UNCLE_HOSTED": "1", "UNCLE_MODEL": "u"})
        self.assertEqual((c.runner, c.model, c.errors), ("self-hosted", "u", []))

    def test_hosted_without_model_errors_not_alias(self):
        c = self.load({"UNCLE_HOSTED": "1"})
        self.assertEqual(c.runner, "self-hosted")
        self.assertTrue(c.errors)
        self.assertNotEqual(c.model, "sonnet")

    def test_explicit_claude_kept_and_not_hosted(self):
        c = self.load({"UNCLE_HOSTED": "1", "SEREN_MODEL": "m"}, "supervision.runner claude\n")
        self.assertEqual((c.runner, c.model), ("claude", "sonnet"))
        c = self.load({"SEREN_MODEL": "m"})
        self.assertEqual((c.runner, c.model), ("claude", "sonnet"))


class ModeResolution(unittest.TestCase):
    """AC-6: hosted makes unattended the default only; explicit choices win."""

    def mode(self, env, args=""):
        import subprocess
        e = {"PATH": os.environ["PATH"], "UNCLE_STDIN_TTY": "0"}
        e.update(env)
        script = '. "%s/scripts/lib/mode.sh"; uncle_resolve_mode %s 2>/dev/null; echo "$?|${UNCLE_MODE:-}"' % (ROOT, args)
        return subprocess.run(["bash", "-c", script], env=e, capture_output=True, text=True).stdout.strip()

    def test_override_table(self):
        self.assertEqual(self.mode({"UNCLE_HOSTED": "1"}), "0|unattended")
        self.assertEqual(self.mode({"UNCLE_HOSTED": "1", "UNCLE_UNATTENDED": "1"}), "0|unattended")
        self.assertEqual(self.mode({"UNCLE_HOSTED": "1", "UNCLE_UNATTENDED": "0", "UNCLE_ATTENDED_STDIN": "1"}), "0|attended")
        self.assertEqual(self.mode({"UNCLE_HOSTED": "1", "UNCLE_ATTENDED_STDIN": "1"}, "--attended"), "0|attended")

    def test_not_hosted_unchanged(self):
        for v in ("", "0", "true"):
            self.assertEqual(self.mode({"UNCLE_HOSTED": v, "UNCLE_UNATTENDED": "0"}), "0|unattended", v)

    def test_hosted_attended_without_tty_refused(self):
        self.assertTrue(self.mode({"UNCLE_HOSTED": "1", "UNCLE_UNATTENDED": "0"}).startswith("1|"))

    def test_classifier_skips_alias_when_hosted(self):
        import subprocess
        src = open(os.path.join(ROOT, "scripts/lib/change-class-stage.sh")).read()
        self.assertIn("uncle_is_hosted", src)
        self.assertIn("uncle_stage_runner supervision", src)


class FocusedRunner(unittest.TestCase):
    """AC-7: `run-python-tests.sh -- hosted-mode` runs this file; an unmatched filter fails."""

    def run_focused(self, name):
        import subprocess
        env = dict(os.environ, HOSTED_MODE_NESTED="1")
        return subprocess.run(["bash", os.path.join(ROOT, "scripts", "run-python-tests.sh"), "--", name],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)

    @unittest.skipIf(os.environ.get("HOSTED_MODE_NESTED"), "already inside the focused run")
    def test_focused_command_runs_this_file(self):
        r = self.run_focused("hosted-mode")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("hosted-mode", r.stdout + r.stderr)

    @unittest.skipIf(os.environ.get("HOSTED_MODE_NESTED"), "already inside the focused run")
    def test_unmatched_filter_exits_nonzero(self):
        r = self.run_focused("no-such-suite-zz")
        self.assertNotEqual(r.returncode, 0)

    def test_registered_critical(self):
        names = [l.split("#")[0].strip() for l in open(os.path.join(ROOT, "scripts/tests/critical-suites.txt"))]
        self.assertIn("hosted-mode", names)


if __name__ == "__main__":
    unittest.main()

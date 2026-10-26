#!/usr/bin/env python3
"""Self-hosted Configure text must not call the default path OpenCode."""
import pathlib, re, unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILES = [ROOT / "uncle_tui.py", ROOT / "uncle"]
ALLOWED = ("__opencode_models__", "__opencode_connection__", "_apply_opencode_to_all_stages",
           '"opencode"', "'opencode'", "opencode =", "opencode)", "opencode_", "opencode\"",
           "WORKFLOW_SELF_HOSTED_TRANSPORT")


class Labels(unittest.TestCase):
    def test_no_parenthesised_opencode(self):
        for f in FILES:
            self.assertNotIn("(OpenCode)", f.read_text(), f.name)

    def test_user_visible_opencode_text_is_gone(self):
        for f in FILES:
            for n, line in enumerate(f.read_text().splitlines(), 1):
                if "OpenCode" in line and not line.lstrip().startswith("#"):
                    self.fail("%s:%d %s" % (f.name, n, line.strip()))

    def test_new_labels_and_preserved_keys(self):
        t = (ROOT / "uncle_tui.py").read_text()
        self.assertIn('return "Self hosted"', t)
        self.assertIn("a: use Self hosted for all stages", t)
        self.assertIn("__opencode_models__", t)
        self.assertIn('"self-hosted"', t)
        self.assertIn("opencode", (ROOT / "PREREQUISITES.md").read_text())


if __name__ == "__main__":
    unittest.main()

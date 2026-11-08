#!/usr/bin/env python3
"""The Claude model catalog, its defaults, and the reviewer allowlist must agree."""
import fnmatch
import importlib.util
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))

EXPECTED = [
    ("Claude Haiku 5.5", "claude-haiku-5-5"),
    ("Claude Sonnet 5.5", "claude-sonnet-5-5"),
    ("Claude Opus 5.5", "claude-opus-5-5"),
    ("Claude Fable 5.1", "claude-fable-5-1"),
    ("Claude Fable 5", "claude-fable-5"),
    ("Claude Opus 4.8", "claude-opus-4-8"),
    ("Claude Opus 4.7", "claude-opus-4-7"),
    ("Claude Sonnet 4.6", "claude-sonnet-4-6"),
    ("Claude Opus 4.6", "claude-opus-4-6"),
    ("Claude Opus 4.5", "claude-opus-4-5-20251101"),
    ("Claude Haiku 4.5", "claude-haiku-4-5-20251001"),
    ("Claude Sonnet 4.5", "claude-sonnet-4-5-20250929"),
]
DEFAULT_ID = "claude-sonnet-5-5"
BLANKED_CODEX = {"opus", "sonnet", "o3", "kimi"}

# Snapshots of the pre-change Codex and Kimi literals.
CODEX_SNAPSHOT = [("Codex", [("GPT-5.1 Codex", "gpt-5.1-codex"),
                             ("GPT-5.1 Codex Mini", "gpt-5.1-codex-mini")])]
KIMI_SNAPSHOT = [("Kimi", [("Kimi K2.7 Code Highspeed", "moonshotai/kimi-k2.7-code-highspeed"),
                           ("Kimi K2.6", "moonshotai/kimi-k2.6")])]


def load_tui():
    spec = importlib.util.spec_from_file_location('uncle_tui_under_test', os.path.join(ROOT, 'uncle_tui.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def shell_default(rel):
    text = read(rel)
    found = re.findall(r'^DEFAULT_MODEL="?(?:\$\{[A-Za-z_]+:-([^}"]*)\}|([^"\s$]+))"?\s*$', text, re.M)
    assert len(found) == 1, f'{rel}: expected exactly one DEFAULT_MODEL assignment, found {len(found)}'
    return found[0][0] or found[0][1]


def case_pattern():
    text = read('scripts/reviewer-claude.sh')
    m = re.search(r'case "\$model" in\s*\n\s*([^\n)]*?)\)\s*;;', text)
    assert m, 'could not extract the allowlist case pattern from reviewer-claude.sh'
    return m.group(1).strip()


def flat(catalog):
    return [pair for _, entries in catalog for pair in entries]


class ClaudeModelDefaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tui = load_tui()

    def test_catalog_exact(self):
        cat = self.tui.MODEL_CATALOG_CLAUDE
        self.assertEqual(len(cat), 1)
        self.assertEqual(cat[0][0], 'Claude')
        self.assertEqual(list(map(tuple, cat[0][1])), EXPECTED)
        ids = [i for _, i in cat[0][1]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_defaults_agree(self):
        self.assertEqual(self.tui.DEFAULT_MODEL_FOR_RUNNER['claude'], DEFAULT_ID)
        self.assertEqual(shell_default('scripts/stagegate.sh'), DEFAULT_ID)
        self.assertEqual(shell_default('scripts/reviewer-claude.sh'), DEFAULT_ID)
        labels = dict((i, l) for l, i in flat(self.tui.MODEL_CATALOG_CLAUDE))
        self.assertEqual(labels.get(DEFAULT_ID), 'Claude Sonnet 5.5')

    def test_allowlist(self):
        pattern = case_pattern()
        # Bash does the glob match; model id ($1) and each alternative ($2) are
        # passed as positional arguments, never interpolated into the script.
        script = '[[ "$1" == $2 ]]'
        alts = pattern.split('|')

        def accepted(mid):
            return any(subprocess.run(['bash', '-c', script, '_', mid, alt]).returncode == 0 for alt in alts)
        for _, mid in flat(self.tui.MODEL_CATALOG_CLAUDE):
            self.assertTrue(accepted(mid), f'{mid} rejected by allowlist {pattern!r}')
        # Negative control: a non-Claude id must be rejected by the same pattern.
        self.assertFalse(accepted('gpt-4'))

    def test_reviewer_env_fallback(self):
        # A non-Claude WORKFLOW_REVIEWER_CLAUDE_MODEL must fall back to the default.
        text = read('scripts/reviewer-claude.sh')
        self.assertRegex(text, r'(?m)^DEFAULT_MODEL="claude-sonnet-5-5"$')
        self.assertNotRegex(text, r'(?m)^DEFAULT_MODEL=.*WORKFLOW_REVIEWER_CLAUDE_MODEL')

    def test_comment(self):
        text = read('uncle_tui.py')
        idx = text.index('DEFAULT_MODEL_FOR_RUNNER = {')
        block = text[max(0, idx - 900):idx]
        block = block[block.rfind('\n\n') + 1:]
        self.assertGreater(len(block.strip()), 20, 'comment block is empty')
        self.assertTrue(block.lstrip().startswith('#'), 'block is not a comment')
        self.assertIn(DEFAULT_ID, block)
        self.assertNotIn('tier alias', block)

    def test_other_catalogs_unchanged(self):
        self.assertEqual([(n, list(map(tuple, e))) for n, e in self.tui.MODEL_CATALOG_CODEX],
                         [(n, list(map(tuple, e))) for n, e in CODEX_SNAPSHOT])
        self.assertEqual([(n, list(map(tuple, e))) for n, e in self.tui.MODEL_CATALOG_KIMI],
                         [(n, list(map(tuple, e))) for n, e in KIMI_SNAPSHOT])
        self.assertEqual(self.tui.DEFAULT_MODEL_FOR_RUNNER['codex'], 'codex default')
        self.assertEqual(self.tui.DEFAULT_MODEL_FOR_RUNNER['kimi'], 'moonshotai/kimi-k2.7-code-highspeed')
        for _, mid in flat(self.tui.MODEL_CATALOG_CODEX):
            self.assertNotIn(mid, BLANKED_CODEX)

    def test_stored_old_id_not_in_catalog(self):
        """D-4: a stored retired id is shown verbatim, not highlighted, not rewritten."""
        tui = self.tui
        ids = [i for _, i in flat(tui.MODEL_CATALOG_CLAUDE)]
        self.assertNotIn('claude-sonnet-5', ids)
        self.assertEqual(len(ids), 12)
        cls = [v for v in vars(tui).values() if isinstance(v, type) and hasattr(v, '_open_picker')][0]
        o = cls.__new__(cls)
        o.stage_runner = lambda s: 'claude'
        o.stage_models = {'plan': 'claude-sonnet-5'}
        o.stage_model = lambda s: o.stage_models.get(s, '')
        o.picker_kind = 'model'
        o.picker_target = 'plan'
        o.pick_filter = ''
        o.notice = ''
        o.model_catalogs = {}

        def no_write(*a, **k):
            raise AssertionError('stored model must not be rewritten')
        o._set_field = no_write
        o._open_picker('model', 'plan')
        rows = o._picker_filtered()
        models = [t for k, t in rows if k == 'model']
        self.assertEqual(len(models), 12)
        self.assertEqual([t.lower() for t in models if t.lower() == 'claude-sonnet-5'], [])
        self.assertEqual(o.stage_models, {'plan': 'claude-sonnet-5'})


    def test_picker_highlights_default_when_unset(self):
        """MC-102: with no stored model the picker opens on the default row."""
        tui = self.tui
        cls = [v for v in vars(tui).values() if isinstance(v, type) and hasattr(v, '_open_picker')][0]
        o = cls.__new__(cls)
        o.stage_runner = lambda s: 'claude'
        o.stage_models = {}
        o.stage_model = lambda s: o.stage_models.get(s, '')
        o.picker_kind = 'model'
        o.picker_target = 'plan'
        o.pick_filter = ''
        o.notice = ''
        o.model_catalogs = {}
        o._open_picker('model', 'plan')
        rows = o._picker_filtered()
        self.assertEqual(rows[o.pick_sel], ('model', DEFAULT_ID))
        self.assertEqual(o.stage_models, {})


if __name__ == '__main__':
    unittest.main()

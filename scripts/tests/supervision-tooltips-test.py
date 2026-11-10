"""Supervision configuration tooltips: row hints and picker explanations (issue 81)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import supervisor as sv  # noqa: E402

KEYS = [key for key, _kind, _default in sv.CONTROLS]
SEP = '  - '


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sup-tooltips-')
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / 'config'
        self.config.write_text('')
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.config)})
        env.start()
        self.addCleanup(env.stop)
        import uncle_tui as tui
        self.tui = tui
        p = patch.object(tui, 'CONFIG_PATH', str(self.config))
        p.start()
        self.addCleanup(p.stop)

    def ui(self, width=120):
        tui = self.tui
        ui = tui.UncleTUI.__new__(tui.UncleTUI)
        ui.stdscr = Mock()
        ui.stdscr.getmaxyx.return_value = (40, width)
        ui.color = {'title': 0, 'sel': 0, 'accent': 0}
        ui.supervision = {}
        ui.misc = {}
        ui.notice = ''
        ui.pick_filter = ''
        ui.pick_sel = 0
        ui.pick_scroll = 0
        ui.config_sel = 0
        ui.config_section = 'supervision'
        ui.state = 'config'
        ui.maybe_reload = Mock()
        ui.save_config = Mock()
        ui.stage_runners = ui.stage_models = ui.stage_efforts = ui.stage_networks = {}
        ui.stage_billings = ui.stage_base_urls = ui.stage_api_keys = {}
        return ui

    def drawn(self, ui, width=120):
        ui.stdscr.addnstr.reset_mock()
        ui._draw_picker(40, width, 0, 2)
        return [c.args[2] for c in ui.stdscr.addnstr.call_args_list]

    def open_picker(self, ui, key):
        ui.config_sel = KEYS.index(key)
        ui._supervision_enter()
        self.assertEqual(ui.state, 'picker')
        self.assertEqual(ui.picker_target, '!supervision')

    def option_texts(self, ui):
        return [t for k, t in ui._picker_filtered() if k == 'option']


class RowHints(Base):
    def test_every_control_has_a_short_hint_appended_unmodified(self):
        ui = self.ui(120)
        rows = ui._supervision_items()
        self.assertEqual(len(rows), len(KEYS))
        bare = self.ui(99)._supervision_items()
        for key, row, plain in zip(KEYS, rows, bare):
            self.assertTrue(row.startswith(key), key)
            self.assertTrue(row.startswith(plain), 'key/value text must be unmodified: ' + key)
            suffix = row[len(plain):]
            self.assertTrue(suffix.startswith(SEP), (key, suffix))
            hint = suffix[len(SEP):]
            self.assertTrue(hint.strip(), 'empty hint for ' + key)
            self.assertLessEqual(len(hint), 40, key)
            self.assertEqual(self.tui.SUPERVISION_HINT[key], hint)

    def test_width_boundary(self):
        for width, expect in ((30, False), (60, False), (99, False), (100, True), (119, True), (120, True)):
            rows = self.ui(width)._supervision_items()
            self.assertEqual(all(SEP in r for r in rows), expect, width)
            self.assertEqual(any(SEP in r for r in rows), expect, width)

    def test_unreadable_width_gives_no_hints(self):
        for bad in (RuntimeError('boom'), (40, 0), (40, -5), (40, 'wide'), ()):
            ui = self.ui(120)
            if isinstance(bad, Exception):
                ui.stdscr.getmaxyx.side_effect = bad
            else:
                ui.stdscr.getmaxyx.return_value = bad
            rows = ui._supervision_items()
            self.assertFalse(any(SEP in r for r in rows), repr(bad))

    def test_invalid_config_reason_row_is_not_hinted(self):
        self.config.write_text('supervision.max_interventions notanumber\n')
        rows = self.ui(120)._supervision_items()
        self.assertEqual(len(rows), len(KEYS) + 1)
        self.assertTrue(rows[-1].startswith('! '))
        self.assertNotIn(SEP, rows[-1])
        self.assertTrue(all(SEP in r for r in rows[:-1]))

    def test_non_controls_hint_lookup_and_values_do_not_leak(self):
        ui = self.ui(120)
        ui.supervision = {'model': '', 'runner': 'x' * 300, 'files_allowlist': 'a,b'}
        for key, row in zip(KEYS, ui._supervision_items()):
            self.assertEqual(row.count(SEP), 1, key)
        self.assertNotIn('bogus', self.tui.SUPERVISION_HINT)

    def test_enter_and_toggle_on_each_hinted_row_target_matching_key(self):
        for index, key in enumerate(KEYS):
            ui = self.ui(120)
            self.assertIn(SEP, ui._supervision_items()[index])
            ui.config_sel = index
            ui._set_field = Mock()
            ui._open_picker = Mock()
            ui._supervision_enter()
            if sv.KINDS[key] == 'bool':
                ui._open_picker.assert_not_called()
                self.assertEqual(ui._set_field.call_count, 1, key)
                self.assertEqual(ui._set_field.call_args.args[:2], ('!supervision', key))
            else:
                ui._set_field.assert_not_called()
                self.assertEqual(ui._open_picker.call_count, 1, key)
                args = ui._open_picker.call_args.args
                self.assertIn('!supervision', args, key)
                # the picker kind follows the key; delegate_gates may use its own kind name
                self.assertTrue(args[0] == key or key == 'delegate_gates', (key, args))

    def test_hints_do_not_change_selection_effect(self):
        for width in (60, 120):
            ui = self.ui(width)
            ui.config_sel = KEYS.index('enabled')
            ui._supervision_enter()
            self.assertEqual(ui.supervision.get('enabled'), 'false', width)


class PickerExplanations(Base):
    def test_effort_choices_are_explained_and_distinct(self):
        ui = self.ui()
        self.open_picker(ui, 'effort')
        lines = self.drawn(ui)
        seen = set()
        for choice in ('none', 'low', 'medium', 'high'):
            line = [t for t in lines if t.lstrip('> ').startswith(choice)]
            self.assertEqual(len(line), 1, choice)
            self.assertIn(SEP, line[0])
            explanation = line[0].split(SEP, 1)[1].strip()
            self.assertTrue(explanation, choice)
            seen.add(explanation)
        self.assertEqual(len(seen), 4)
        custom = [t for t in lines if 'Custom' in t]
        self.assertTrue(custom)
        self.assertTrue(all(SEP not in t for t in custom))

    def test_delegate_picker_offers_only_none_and_routine(self):
        ui = self.ui()
        self.open_picker(ui, 'delegate_gates')
        self.assertEqual(self.option_texts(ui), ['none', 'routine'])
        self.assertFalse([k for k, _ in ui._picker_filtered() if k == 'custom'])
        lines = self.drawn(ui)
        for choice in ('none', 'routine'):
            line = [t for t in lines if t.lstrip('> ').startswith(choice)]
            self.assertEqual(len(line), 1)
            self.assertTrue(line[0].split(SEP, 1)[1].strip())

    def test_delegate_selection_stores_value(self):
        ui = self.ui()
        self.open_picker(ui, 'delegate_gates')
        ui.pick_sel = [t for _k, t in ui._picker_filtered()].index('routine')
        ui._picker_confirm()
        self.assertEqual(ui.supervision.get('delegate_gates'), 'routine')
        self.assertEqual(ui.state, 'config')

    def test_delegate_out_of_set_stored_value(self):
        ui = self.ui()
        ui.supervision = {'delegate_gates': 'everything'}
        self.open_picker(ui, 'delegate_gates')
        self.assertEqual(self.option_texts(ui), ['none', 'routine'])
        lines = self.drawn(ui)
        for choice in ('none', 'routine'):
            line = [t for t in lines if t.lstrip('> ').startswith(choice)]
            self.assertEqual(len(line), 1)
            self.assertNotIn('<current>', line[0])
        # opening and drawing never writes; the stored value is unchanged (Esc path)
        self.assertEqual(ui.supervision['delegate_gates'], 'everything')
        ui.save_config.assert_not_called()

    def test_runner_choices_all_explained_from_the_picker_list(self):
        ui = self.ui()
        self.open_picker(ui, 'runner')
        runners = self.option_texts(ui)
        if not runners:
            self.skipTest('no runner installed')
        lines = self.drawn(ui)
        for runner in runners:
            shown = self.tui.runner_display(runner)
            line = [t for t in lines if t.lstrip('> ').startswith(shown)]
            self.assertTrue(line, runner)
            self.assertIn(SEP, line[0], runner)
            self.assertTrue(line[0].split(SEP, 1)[1].strip(), runner)

    def _runner_lines(self, names):
        ui = self.ui()
        with patch.object(self.tui, 'selectable_runners', lambda side: list(names)), \
                patch.object(sv, 'SUPPORTED_RUNNERS', tuple(names)):
            self.open_picker(ui, 'runner')
            return self.drawn(ui)

    def test_runner_name_with_control_characters_gets_static_fallback(self):
        plain = self._runner_lines(['zzplain'])
        evil = self._runner_lines(['zz\x1b[31mevil\x07\nx'])
        for text in evil:
            self.assertFalse([c for c in text if ord(c) < 32 or ord(c) == 127], repr(text))
        plain_expl = [t for t in plain if SEP in t]
        evil_expl = [t for t in evil if SEP in t]
        self.assertEqual(len(plain_expl), 1)
        self.assertEqual(len(evil_expl), 1)
        fallback = plain_expl[0].split(SEP, 1)[1]
        self.assertTrue(fallback.strip())
        self.assertEqual(evil_expl[0].split(SEP, 1)[1], fallback)
        self.assertNotIn('evil', fallback)


class NonSupervisionPickersUnchanged(Base):
    def rows(self, kind, target='plan'):
        ui = self.ui()
        ui.picker_kind = kind
        ui.picker_target = target
        ui.stage_runner = Mock(return_value='nonesuch')
        return ui, ui._picker_rows()

    def test_effort_rows_literal(self):
        _ui, rows = self.rows('effort')
        self.assertEqual(rows, [('option', 'none'), ('option', 'low'), ('option', 'medium'), ('option', 'high'),
                                ('custom', 'Custom… (type an effort)')])

    def test_network_rows_literal(self):
        _ui, rows = self.rows('network')
        self.assertEqual(rows, [('option', 'false'), ('option', 'true')])

    def test_unknown_runner_model_rows_literal(self):
        _ui, rows = self.rows('model')
        self.assertEqual(rows, [('custom', 'Custom… (type a model id)')])

    def test_runner_rows_literal(self):
        ui = self.ui()
        ui.picker_kind = 'runner'
        ui.picker_target = 'plan'
        with patch.object(self.tui, 'selectable_runners', lambda side: ['alpha', 'beta']):
            self.assertEqual(ui._picker_rows(), [('option', 'alpha'), ('option', 'beta')])

    def test_markdown_viewer_rows_literal(self):
        ui = self.ui()
        ui.picker_kind = 'markdown_viewer'
        ui.picker_target = '!misc'
        with patch.object(self.tui.shutil, 'which', lambda name: '/x/' + name if name in ('code', 'cat') else None):
            self.assertEqual(ui._picker_rows(), [('option', 'code'), ('option', 'cat'),
                                                 ('custom', 'Custom… (type a command)')])

    def test_non_supervision_pickers_draw_no_explanation(self):
        for kind, target in (('effort', 'plan'), ('network', 'plan'), ('runner', 'plan'), ('model', 'plan')):
            ui = self.ui()
            ui.picker_kind = kind
            ui.picker_target = target
            ui.stage_runner = Mock(return_value='nonesuch')
            ui.stage_effort = Mock(return_value='')
            ui.stage_network = Mock(return_value='')
            ui.stage_model = Mock(return_value='')
            with patch.object(self.tui, 'selectable_runners', lambda side: ['claude', 'codex']):
                lines = self.drawn(ui)
            self.assertTrue(lines, kind)
            for text in lines:
                self.assertNotIn(SEP, text, (kind, text))


class SmallScreens(Base):
    def test_draw_at_small_sizes_does_not_raise(self):
        for width in (30, 60):
            ui = self.ui(width)
            ui._supervision_items()
            for key in ('effort', 'delegate_gates', 'runner'):
                self.open_picker(ui, key)
                self.drawn(ui, width)


if __name__ == '__main__':
    unittest.main()

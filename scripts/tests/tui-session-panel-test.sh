#!/usr/bin/env bash
set -euo pipefail
if ! python3 -c 'import curses' >/dev/null 2>&1; then
    echo "SKIP: curses is unavailable (install windows-curses on Windows)."
    exit 0
fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
python3 -B - <<'PY'
import curses, json, os, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
from uncle_tui import UncleTUI

class Screen:
    def __init__(self,width=120): self.width=width; self.writes=[]
    def getmaxyx(self): return 30,self.width
    def erase(self): pass
    def refresh(self): pass
    def addnstr(self,y,x,text,n,*args): self.writes.append((y,x,text,n))

class Panel(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.TemporaryDirectory()
        self.addCleanup(self.project.cleanup)
        project_root = patch('uncle_tui._project_root', return_value=self.project.name)
        project_root.start()
        self.addCleanup(project_root.stop)

    def ui(self):
        ui=UncleTUI.__new__(UncleTUI)
        ui.stdscr=Screen();ui.state='running';ui.status_stage='implementation';ui.proc_done=False
        ui.session_stats={'active':{'implementation':time.time()-65},'live':{},'records':[],'tick':-1,'seen':set()}
        ui.status_model='';ui.status_mode='';ui.status_stage_index=0;ui.status_stage_total=0
        return ui

    def test_live_tokens_and_projected_cost(self):
        ui=self.ui()
        ui._apply_status(json.dumps(dict(event='usage',stage='implementation',model='moonshot-ai/kimi-k2.7-code-highspeed',total_tokens=2010,
             usage=dict(input_tokens=1000,output_tokens=10,cache_read_input_tokens=1000,cache_creation_input_tokens=0))))
        lines='\n'.join(ui._session_panel_lines())
        self.assertIn('0:01:05',lines);self.assertIn('2,010',lines);self.assertIn('$0.0024 est',lines)

    def test_live_k3_estimate_and_completed_estimate_are_labeled(self):
        ui=self.ui()
        ui._apply_status(json.dumps(dict(event='usage',stage='implementation',model='moonshot-ai/kimi-k3',total_tokens=2000,
             usage=dict(input_tokens=2000,output_tokens=0,cache_read_input_tokens=0,cache_creation_input_tokens=0))))
        self.assertIn('$0.0060 est','\n'.join(ui._session_panel_lines()))
        ui.session_stats['active']={}
        ui.session_stats['records'].append(dict(stage='preflight',started_at=1,elapsed_seconds=10,
            model='moonshot-ai/kimi-k3',input_tokens=1000000,output_tokens=100000,cache_read_tokens=0,cache_write_tokens=0,
            reported_cost_usd=None,estimated_cost_usd=4.5,cost_status='estimated'))
        text='\n'.join(ui._session_panel_lines())
        self.assertIn('Cost   $4.5000 est',text)
        self.assertNotIn('$4.5000\n',text)

    def test_partial_and_non_model_screens(self):
        ui=self.ui()
        self.assertIn('Unavailable','\n'.join(ui._session_panel_lines()))
        for state in ['menu','config','stage','picker','notice']:
            ui.state=state;self.assertFalse(ui.poll_session_stats())
            ui._draw_prompt=lambda *a:None;ui._draw_notice=lambda *a:None;ui._draw_status=lambda *a:None
            ui._draw_session_stats=lambda *a:self.fail('panel drawn outside session')
            ui.draw()

    def test_running_and_viewer_reserve_right_side(self):
        ui=self.ui();ui._draw_status=lambda *a:None
        widths=[];ui._draw_running=lambda h,w:widths.append(w)
        for state in ['running','viewer']:
            ui.state=state;ui.draw()
        self.assertEqual(widths,[86,86])
        self.assertTrue(any(x==86 and text=='│' for y,x,text,n in ui.stdscr.writes))
        ui.stdscr=Screen(50);ui.draw();self.assertEqual(widths[-1],50)

    def test_completed_record_replaces_live_without_double_count(self):
        ui=self.ui()
        with tempfile.TemporaryDirectory() as temp, patch('uncle_tui._project_root',return_value=temp):
            p=Path(temp)/'.uncle/workflow/metrics';p.mkdir(parents=True)
            row=dict(kind='agent',stage='implementation',ended_at=time.time(),elapsed_seconds=65,input_tokens=100,output_tokens=20,cache_read_tokens=10,cache_write_tokens=0,reported_cost_usd=.02)
            (p/'one.json').write_text(json.dumps(row))
            self.assertTrue(ui.poll_session_stats());self.assertFalse(ui.poll_session_stats())
            lines='\n'.join(ui._session_panel_lines())
            self.assertIn('Tokens 130',lines);self.assertIn('$0.0200',lines)
            self.assertNotIn('implementation',ui.session_stats['active'])
            self.assertEqual(len(ui.session_stats['records']),1)

    def test_each_stage_includes_cost_and_retries_are_combined(self):
        ui=self.ui();ui.session_stats['active']={}
        for n in range(7):
            ui.session_stats['records'].append(dict(stage='stage-%d'%n,started_at=n,elapsed_seconds=10,
                input_tokens=100,output_tokens=20,cache_read_tokens=0,cache_write_tokens=0,reported_cost_usd=.01))
        ui.session_stats['records'].append(dict(ui.session_stats['records'][0]))
        lines=ui._session_panel_lines();text='\n'.join(lines)
        for n in range(7): self.assertIn('stage-%d'%n,text)
        start=lines.index('stage-0 (2 attempts)')
        self.assertEqual(lines[start+1:start+4],['Time   0:00:20','Tokens 240','Cost   $0.0200'])
        ui._draw_session_stats(30,120,34)
        self.assertGreater(ui.panel_visible_offset,0)
        ui.handle_key(ord('['));self.assertEqual(ui.panel_scroll,ui.panel_visible_offset-5)
        ui.handle_key(ord('\\'));self.assertIsNone(ui.panel_scroll)

    def test_zero_reported_cost_on_a_stage_that_burned_tokens_is_unknown(self):
        # A runner that consumed millions of tokens did not do it for free.
        # Reporting the sum as $0.0000 understated a real session total with a
        # number that reads like a measurement, so a zero alongside tokens is
        # treated as "did not say" and the subtotal is marked partial.
        ui=self.ui();ui.session_stats['active']={}
        ui.session_stats['records'].append(dict(stage='execute-checklist',started_at=1,elapsed_seconds=10,
            input_tokens=4000,output_tokens=700,cache_read_tokens=0,cache_write_tokens=0,reported_cost_usd=0))
        ui.session_stats['records'].append(dict(stage='execute-checklist',started_at=2,elapsed_seconds=10,
            input_tokens=1000,output_tokens=300,cache_read_tokens=0,cache_write_tokens=0,reported_cost_usd=.5))
        text='\n'.join(ui._session_panel_lines())
        self.assertNotIn('$0.0000',text)
        self.assertIn('$0.5000 (partial)',text)

    def test_a_free_model_reporting_zero_is_reporting_a_fact(self):
        # Once a subscription is exhausted, stages run on free models, and they
        # report a real zero alongside millions of tokens. Reading that as
        # "declined to say" put Unavailable on every row of a whole session and
        # hid the total, which is the opposite of what the rule is for.
        ui=self.ui();ui.session_stats['active']={}
        ui.session_stats['records'].append(dict(stage='project-plan',started_at=1,elapsed_seconds=10,
            model='deepseek/deepseek-v4-flash',input_tokens=4000000,output_tokens=68000,
            cache_read_tokens=0,cache_write_tokens=0,reported_cost_usd=0))
        text='\n'.join(ui._session_panel_lines())
        self.assertIn('$0.0000',text)
        self.assertNotIn('partial',text)

    def test_a_paid_model_reporting_zero_is_still_unknown(self):
        ui=self.ui();ui.session_stats['active']={}
        ui.session_stats['records'].append(dict(stage='implementation',started_at=1,elapsed_seconds=10,
            model='cline-pass/qwen3.8-max',input_tokens=4000,output_tokens=700,
            cache_read_tokens=0,cache_write_tokens=0,reported_cost_usd=0))
        ui.session_stats['records'].append(dict(stage='implementation',started_at=2,elapsed_seconds=10,
            model='cline-pass/qwen3.8-max',input_tokens=1000,output_tokens=300,
            cache_read_tokens=0,cache_write_tokens=0,reported_cost_usd=.5))
        text='\n'.join(ui._session_panel_lines())
        self.assertNotIn('$0.0000',text)
        self.assertIn('(partial)',text)

    def test_zero_reported_cost_with_no_tokens_is_still_zero(self):
        # A stage that genuinely did nothing is not the same claim, and a real
        # zero stays a real zero rather than becoming an unknown.
        ui=self.ui();ui.session_stats['active']={}
        ui.session_stats['records'].append(dict(stage='noop-stage',started_at=1,elapsed_seconds=1,
            input_tokens=0,output_tokens=0,cache_read_tokens=0,cache_write_tokens=0,reported_cost_usd=0))
        text='\n'.join(ui._session_panel_lines())
        self.assertIn('$0.0000',text)
        self.assertNotIn('partial',text)

    def test_start_order_survives_overlap_and_retries(self):
        ui=self.ui()
        ui.session_stats['active']={'early-stage':100, 'late-stage':400}
        ui.session_stats['records']=[
            dict(stage='middle-stage',started_at=200,elapsed_seconds=5),
            dict(stage='earliest-stage',started_at=50,elapsed_seconds=5),
            dict(stage='earliest-stage',started_at=300,elapsed_seconds=5)]
        lines=ui._session_panel_lines()
        positions=[lines.index(name) for name in ['earliest-stage (2 attempts)', '> early-stage', 'middle-stage', '> late-stage']]
        self.assertEqual(positions,sorted(positions))

    def test_stage_and_value_colors(self):
        ui=self.ui()
        ui.color=dict(title=11,good=12,bad=13,warning=14,accent=15,muted=16)
        ui.session_stats['records']=[
            dict(stage='completed',started_at=1,elapsed_seconds=1,process_exit=0),
            dict(stage='failed',started_at=2,elapsed_seconds=1,process_exit=2),
            dict(stage='recovered',started_at=3,elapsed_seconds=1,process_exit=2),
            dict(stage='recovered',started_at=4,elapsed_seconds=1,process_exit=0)]
        lines=ui._session_panel_lines()
        self.assertEqual(ui._session_panel_attr('> implementation'),11)
        self.assertEqual(ui._session_panel_attr('completed'),12)
        self.assertIn('failed [failed]',lines)
        self.assertEqual(ui._session_panel_attr('failed [failed]'),13)
        self.assertEqual(ui._session_panel_attr('recovered (2 attempts)'),12)
        self.assertEqual(ui._session_panel_attr('Tokens Unavailable'),14)
        self.assertEqual(ui._session_panel_attr('Cost   $0.0100 (partial)'),14)
        self.assertEqual(ui._session_panel_attr('Cost   $0.0100'),15)
        self.assertEqual(ui._session_panel_attr('Cost   $0.0100 est'),14)
        self.assertEqual(ui._session_panel_attr('Reported + projected'),16)
        ui.color={}
        self.assertEqual(ui._session_panel_attr('failed [failed]'),0)

    def test_partial_status_event_is_not_lost(self):
        ui=self.ui()
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'status';p.write_text('{"event":"usage",')
            ui.status_path=str(p);ui.status_pos=0
            self.assertFalse(ui.poll_status());self.assertEqual(ui.status_pos,0)
            with p.open('a') as f:f.write('"total_tokens":42}\n')
            self.assertTrue(ui.poll_status());self.assertEqual(ui.session_stats['live']['implementation']['total_tokens'],42)

    def test_background_usage_keeps_foreground_identity(self):
        ui = self.ui()
        ui.status_model = 'foreground-model'
        ui.status_mode = 'act'
        ui._apply_status(json.dumps(dict(event='usage', stage='manual-checklist-base',
                                        model='review-model', mode='review', total_tokens=99)))
        self.assertEqual(ui.status_stage, 'implementation')
        self.assertEqual(ui.status_model, 'foreground-model')
        self.assertEqual(ui.status_mode, 'act')
        self.assertEqual(ui.session_stats['live']['manual-checklist-base']['total_tokens'], 99)

class Footer(unittest.TestCase):
    def ui(self, **fields):
        ui = UncleTUI.__new__(UncleTUI)
        ui.__dict__.update(state='running', workflow_idx=1, issue_mode='--change',
            issue='123', status_runner='codex', status_model='model',
            status_effort='high', status_mode='act', status_stage='implementation',
            status_stage_index=2, status_stage_total=4, prompt_kind='',
            color=dict(sel=11, good=12, accent=13), misc={})
        ui.__dict__.update(fields)
        return ui

    def draw(self, ui, width=160, fail=False):
        ui.stdscr = Screen(width)
        ui.stdscr.attrs = []
        ui.stdscr.attrset = ui.stdscr.attrs.append
        if fail:
            def addnstr(*args):
                raise curses.error('test write failure')
            ui.stdscr.addnstr = addnstr
        ui._draw_status(30, width)
        return ui.stdscr

    def old_parts(self, mode='Act'):
        return (' runner: codex   model: model   effort: high   mode: %s '
                '  stage: implementation (2/4)' % mode)

    def test_issue_identity_and_launch_are_preserved(self):
        inputs = ['123'] + [
            scheme + '://github.com/owner/repo/issues/123' + suffix
            for scheme in ('http', 'https')
            for suffix in ('', '/', '?q=1', '#comment', 'suffix')]
        for issue, issue_mode in ((i, m) for i in inputs for m in ('', '--change', '--new')):
            with self.subTest(issue=issue, issue_mode=issue_mode):
                ui = self.ui(issue=issue, issue_mode=issue_mode)
                command = ui.cmd_for()
                screen = self.draw(ui)
                self.assertEqual(len(screen.writes), 1)
                y, x, text, n = screen.writes[0]
                self.assertEqual((y, x, n), (29, 0, 159))
                self.assertTrue(text.startswith(self.old_parts() + ' '))
                self.assertTrue(text.endswith('change request 123'))
                self.assertEqual(ui.issue, issue)
                self.assertEqual(ui.cmd_for(), command)

    def test_ineligible_and_invalid_inputs_keep_old_footer(self):
        cases = [dict(workflow_idx=0), dict(workflow_idx=2),
                 dict(issue='')]
        cases += [dict(issue=value) for value in
                  ('abc', '#123', '123x', '123\n', '１２３',
                   'https://example.com/o/r/issues/123',
                   'https://github.com/o/r/issues/nope')]
        for fields in cases:
            with self.subTest(fields=fields):
                text = self.draw(self.ui(**fields)).writes[0][2]
                self.assertEqual(text, self.old_parts().ljust(160)[:159])
        ui = self.ui(state='menu')
        text = self.draw(ui).writes[0][2]
        self.assertEqual(text, (' runner: codex   model: —   effort: — '
                                '  mode: — ').ljust(160)[:159])

    def launch(self, ui):
        with patch.object(ui, 'maybe_reload'), patch.object(ui, 'start_workflow') as start:
            ui._run()
            start.assert_called_once_with()

    def test_direct_cancellation_restart_and_relaunch(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as install:
            origin = Path(project, '.uncle/workflow/origin')
            origin.parent.mkdir(parents=True)
            Path(project, 'CHANGE_REQUEST.md').touch()
            Path(project, '.uncle/workflow/state').write_text('888:ANALYZE\n')
            sentinel = Path(install, '.uncle/workflow/origin')
            sentinel.parent.mkdir(parents=True)
            sentinel.write_text('other/repo\t777\n')
            with patch.dict(os.environ, UNCLE_PROJECT_ROOT=project,
                            STAGEGATE_ORIGIN_ISSUE='666'), patch('uncle_tui.ROOT', install), \
                    patch('uncle_tui.os.getcwd', return_value=install):
                ui = self.ui(state='issue', input_buf='999')
                ui._confirm_text()
                self.assertEqual(ui.state, 'issue_mode')
                ui._go_back()
                ui._go_back()
                self.assertEqual(ui.state, 'menu')
                ui.sel = 2
                with patch.object(ui, 'maybe_reload'), patch.object(ui, 'start_workflow') as start:
                    ui._confirm()
                    start.assert_called_once_with()
                self.assertEqual(ui.issue, '999')
                self.assertNotIn('change request', self.draw(ui).writes[0][2])
                for retained in ('', '999'):
                    origin.write_text('owner/repo\t123\tgh\nignored\t456\n')
                    ui = self.ui(workflow_idx=2, issue=retained)
                    command = ui.cmd_for()
                    self.launch(ui)
                    self.assertTrue(self.draw(ui).writes[0][2].endswith('change request 123'))
                    origin.write_text('owner/repo\t456\n')
                    with patch('builtins.open', side_effect=AssertionError('redraw I/O')):
                        self.assertTrue(self.draw(ui).writes[0][2].endswith('change request 123'))
                    self.launch(ui)
                    self.assertTrue(self.draw(ui).writes[0][2].endswith('change request 456'))
                    origin.unlink()
                    self.launch(ui)
                    self.assertNotIn('change request', self.draw(ui).writes[0][2])
                    self.assertEqual(ui.cmd_for(), command)
                    self.assertEqual(ui.issue, retained)
                self.assertEqual(sentinel.read_text(), 'other/repo\t777\n')

    def test_direct_invalid_and_unavailable_origin(self):
        with tempfile.TemporaryDirectory() as project, patch('uncle_tui._project_root') as root:
            root.return_value = project
            origin = Path(project, '.uncle/workflow/origin')
            origin.parent.mkdir(parents=True)
            ui = self.ui(workflow_idx=2, issue='999')
            for data in (b'', b'owner/repo', b'\t123\n', b'owner/repo\t\n',
                         b'owner/repo\t123x\n', b'owner/repo\t 123\n',
                         'owner/repo\t１２３\n'.encode(), b'owner/repo\t\xff\n'):
                with self.subTest(data=data):
                    origin.write_bytes(data)
                    self.launch(ui)
                    self.assertNotIn('change request', self.draw(ui).writes[0][2])
            for error in (PermissionError, OSError, UnicodeError):
                with patch('builtins.open', side_effect=error):
                    self.launch(ui)
                self.assertNotIn('change request', self.draw(ui).writes[0][2])
            origin.write_text('owner/repo\t123\n')
            self.launch(ui)
            ui.workflow_idx = 0
            self.launch(ui)
            ui.workflow_idx = 2
            self.assertNotIn('change request', self.draw(ui).writes[0][2])

    def identities(self):
        for mode in ('', '--change', '--new'):
            yield dict(issue_mode=mode)
        yield dict(workflow_idx=2, direct_issue='123', issue='999')

    def test_fit_colors_and_resize(self):
        for identity in self.identities():
            self.check_fit_colors_and_resize(identity)

    def check_fit_colors_and_resize(self, identity):
        for status_mode, prompt, mode, attr in (
                ('act', '', 'Act', 12), ('plan', '', 'Plan', 13),
                ('review', '', 'Review', 13), ('', '', '—', 0),
                ('act', 'approval', 'Waiting for you', 11)):
            ui = self.ui(status_mode=status_mode, prompt_kind=prompt, **identity)
            parts = self.old_parts(mode)
            label = 'change request 123'
            fit = len(parts) + len(label) + 2
            for width in (fit - 1, fit, fit + 1, 40, 160):
                with self.subTest(mode=mode, width=width):
                    screen = self.draw(ui, width)
                    text = screen.writes[0][2]
                    if width >= fit:
                        self.assertEqual(text, parts + ' ' * (width - 1 - len(parts) - len(label)) + label)
                    else:
                        self.assertEqual(text, parts.ljust(width)[:width - 1])
                    self.assertEqual(len(text), width - 1)
                    self.assertEqual(screen.attrs, [attr | curses.A_REVERSE, 0])

    def test_viewer_and_curses_error(self):
        for identity in self.identities():
            ui = self.ui(state='viewer', **identity)
            screen = self.draw(ui)
            self.assertEqual(screen.writes, [])
            self.assertEqual(screen.attrs, [])
            ui.state = 'running'
            self.assertTrue(self.draw(ui).writes[0][2].endswith('change request 123'))
            screen = self.draw(ui, fail=True)
            self.assertEqual(screen.attrs, [12 | curses.A_REVERSE, 0])

unittest.main()
PY

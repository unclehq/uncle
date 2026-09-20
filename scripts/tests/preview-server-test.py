#!/usr/bin/env python3
"""The early preview shows a live page and never claims the run is over.

Two failures drove this, both seen on a real calculator build. The page went up
at 01:49:15 and implementation kept rewriting it until 01:54:25, so a one-shot
open showed a first draft whose stylesheet did not exist yet. And the preview
was launched through CompletionPreview, which announces `done` -- raising the
finished/star dialog in the middle of a build that was still running.
"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
from preview_server import PreviewServer, VERSION_PATH, development_preview, tree_version


def get(url):
    return urllib.request.urlopen(url, timeout=5).read().decode('utf-8')


def project(**files):
    root = Path(tempfile.mkdtemp())
    for name, text in files.items():
        path = root / name.replace('__', '/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


class Server(unittest.TestCase):
    def setUp(self):
        self.root = project(**{'index.html': '<h1>draft</h1>', 'style.css': 'h1{color:red}'})
        self.server = PreviewServer(self.root)
        self.addCleanup(self.server.close)
        self.base = self.server.url.rsplit('/', 1)[0]

    def test_serves_on_loopback_only(self):
        self.assertTrue(self.server.url.startswith('http://127.0.0.1:'))

    def test_page_is_served_with_a_reload_script(self):
        body = get(self.server.url)
        self.assertIn('<h1>draft</h1>', body)
        self.assertIn(VERSION_PATH, body)
        self.assertIn('location.reload', body)

    def test_injection_never_touches_the_file(self):
        get(self.server.url)
        self.assertEqual((self.root / 'index.html').read_text(), '<h1>draft</h1>')

    def test_assets_are_served_untouched(self):
        self.assertEqual(get(self.base + '/style.css'), 'h1{color:red}')

    def test_version_moves_only_when_a_served_file_does(self):
        first = get(self.base + VERSION_PATH)
        self.assertEqual(get(self.base + VERSION_PATH), first)
        os.utime(self.root / 'style.css', (0, 0))
        self.assertNotEqual(get(self.base + VERSION_PATH), first)

    def test_noise_directories_do_not_churn_the_version(self):
        first = get(self.base + VERSION_PATH)
        for noise in ('.git', 'node_modules', '__pycache__'):
            (self.root / noise).mkdir()
            (self.root / noise / 'x').write_text('x')
        self.assertEqual(get(self.base + VERSION_PATH), first)

    def test_rewrites_reach_the_browser(self):
        (self.root / 'index.html').write_text('<h1>final</h1>')
        self.assertIn('<h1>final</h1>', get(self.server.url))

    def test_close_stops_listening(self):
        self.server.close()
        with self.assertRaises(Exception):
            get(self.base + VERSION_PATH)

    def test_a_root_that_cannot_be_served_does_not_raise(self):
        PreviewServer('/nonexistent/nope').close()

    def test_tree_version_survives_a_vanishing_file(self):
        tree_version(self.root)                     # must not raise on churn

    def test_react_and_svelte_use_vite_only_after_dependencies_exist(self):
        for framework in ('react', 'svelte'):
            with self.subTest(framework=framework):
                root = project(**{'package.json': '{"scripts":{"dev":"vite"},"dependencies":{"%s":"x","vite":"x"}}' % framework})
                self.assertIsNone(development_preview(root))
                vite = root / 'node_modules' / '.bin' / 'vite'
                vite.parent.mkdir(parents=True)
                vite.write_text('')
                spec = development_preview(root)
                self.assertEqual(spec['command'][:4], ['npm', 'run', 'dev', '--'])
                self.assertTrue(spec['url'].startswith('http://127.0.0.1:'))


class EarlyPreview(unittest.TestCase):
    """The TUI side: one tab, live, and no end-of-run dialog."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location('uncle_tui', ROOT / 'uncle_tui.py')
        self.tui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tui)
        self.opened, self.dialogs = [], []
        self.tui.webbrowser = type('W', (), {
            'open': staticmethod(lambda url: self.opened.append(url) or True)})()

    def make(self, root, stage='implementation'):
        self.tui._project_root = lambda: str(root)
        names = ('_poll_early_preview', '_previewable_page', '_show_early_preview',
                 '_close_early_preview', '_preview_after_implementation',
                 '_poll_completion_preview')
        body = {name: getattr(self.tui.UncleTUI, name) for name in names}
        body['_PREVIEW_POLL_SECONDS'] = 0
        # Which stages are watched; the preview build is one of them.
        body['_PREVIEW_STAGES'] = self.tui.UncleTUI._PREVIEW_STAGES
        body['_PREVIEW_UPGRADE_STAGES'] = self.tui.UncleTUI._PREVIEW_UPGRADE_STAGES
        body['_completion_dialog'] = lambda _self, value: self.dialogs.append(value)
        screen = type('Screen', (), body)()
        screen.status_stage, screen.completion_preview = stage, None
        screen.early_preview_shown, screen._early_preview_stamp = False, None
        screen._early_preview_next, screen._preview_page = 0.0, 'index.html'
        screen.preview_server = None
        self.addCleanup(screen._close_early_preview)
        return screen

    @staticmethod
    def settle(screen):
        for _ in range(2):
            screen._early_preview_next = 0.0
            screen._poll_early_preview()

    def test_no_page_opens_nothing(self):
        self.settle(self.make(project()))
        self.assertEqual(self.opened, [])

    def test_one_tab_serving_the_live_page(self):
        screen = self.make(project(**{'index.html': '<h1>calc</h1>'}))
        self.settle(screen)
        self.assertEqual(len(self.opened), 1)
        self.assertTrue(self.opened[0].startswith('http://127.0.0.1:'))
        self.assertIn('<h1>calc</h1>', get(self.opened[0]))

    def test_no_finished_dialog_during_a_running_build(self):
        screen = self.make(project(**{'index.html': '<h1>calc</h1>'}))
        self.settle(screen)
        self.assertIsNone(screen.completion_preview)
        self.assertFalse(screen._poll_completion_preview())
        self.assertEqual(self.dialogs, [])

    def test_later_rewrites_do_not_open_another_tab(self):
        root = project(**{'index.html': '<h1>v1</h1>'})
        screen = self.make(root)
        self.settle(screen)
        (root / 'index.html').write_text('<h1>v2</h1>')
        (root / 'style.css').write_text('body{background:linear-gradient(red,blue)}')
        self.settle(screen)
        self.assertEqual(len(self.opened), 1)
        self.assertIn('<h1>v2</h1>', get(self.opened[0]))
        self.assertIn('linear-gradient', get(self.opened[0].rsplit('/', 1)[0] + '/style.css'))

    def test_declared_nested_page_is_honoured(self):
        root = project(**{'public__app.html': '<h1>nested</h1>',
                          '.uncle__launch.json': '{"kind":"webpage","path":"public/app.html"}'})
        self.settle(self.make(root))
        self.assertTrue(self.opened[0].endswith('public/app.html'))
        self.assertIn('<h1>nested</h1>', get(self.opened[0]))

    def test_planning_stages_open_the_early_page(self):
        # The preview build runs beside planning and writes the page at the root.
        for stage in ('requirements', 'project-plan', 'adversarial-review'):
            self.opened.clear()
            screen = self.make(project(**{'index.html': '<h1>early</h1>'}), stage)
            self.settle(screen)
            self.assertEqual(len(self.opened), 1, stage)
            self.assertIn('<h1>early</h1>', get(self.opened[0]))
            screen._close_early_preview()

    def test_only_implementation_stages_preview(self):
        for stage in ('change-plan', 'final-audit', 'test-review', 'execute-checklist'):
            self.opened.clear()
            self.settle(self.make(project(**{'index.html': '<h1>x</h1>'}), stage))
            self.assertEqual(self.opened, [], stage)

    def test_command_projects_are_never_launched(self):
        root = project(**{'.uncle__launch.json': '{"kind":"command","command":["./run.sh"]}'})
        self.settle(self.make(root))
        self.assertEqual(self.opened, [])

    def test_static_preview_upgrades_to_development_once_dependencies_exist(self):
        """A React/Svelte project has no vite binary at the moment the page
        first goes up, so the first preview is a static server -- which can
        never run source modules and shows a blank page for the life of the
        tab. Once `npm install` finishes mid-build, the next check must
        replace it with a real dev server instead of leaving the dead tab
        latched in forever."""
        root = project(**{'index.html': '<script type="module" src="/src/main.jsx"></script>'})
        screen = self.make(root)
        self.settle(screen)
        self.assertEqual(len(self.opened), 1, 'the static fallback opened first')
        static_server = screen.preview_server
        self.assertFalse(getattr(static_server, 'closed', False))
        original_close = static_server.close
        static_server.close = lambda: (setattr(static_server, 'closed', True), original_close())

        (root / 'package.json').write_text('{"scripts":{"dev":"vite"},"dependencies":{"react":"x"}}')
        vite = root / 'node_modules' / '.bin' / 'vite'
        vite.parent.mkdir(parents=True)
        vite.write_text('')

        opened_dev = []
        class StubDevelopmentPreview:
            def __init__(self, root, spec):
                opened_dev.append(spec)
                self.url = spec['url']
            def close(self):
                pass
        self.tui.DevelopmentPreview = StubDevelopmentPreview

        self.settle(screen)
        self.assertTrue(static_server.closed, 'the dead static server is closed')
        self.assertEqual(len(opened_dev), 1, 'a development preview replaces it')
        self.assertIsInstance(screen.preview_server, StubDevelopmentPreview)
        self.assertEqual(len(self.opened), 1, 'no second webbrowser.open for the same-tab upgrade')

        # A second settle with nothing new must not upgrade again.
        self.settle(screen)
        self.assertEqual(len(opened_dev), 1)

    def test_opens_on_first_sighting_and_corrects_itself(self):
        """A half-written page is opened, not waited out.

        The earlier behaviour held the page back until two readings agreed,
        because a `file://` page could not correct itself. The page is now
        served with a reload script, so opening early costs one refresh and
        saves the wait -- and an empty file is still skipped, which is the only
        case worth holding for.
        """
        root = project()
        screen = self.make(root)
        screen._early_preview_next = 0.0
        screen._poll_early_preview()
        self.assertEqual(self.opened, [], 'nothing on disk yet')

        (root / 'index.html').write_text('<h1>partial')
        screen._early_preview_next = 0.0
        screen._poll_early_preview()
        self.assertEqual(len(self.opened), 1, 'opens as soon as a page exists')

        (root / 'index.html').write_text('<h1>partial</h1><p>rest</p>')
        screen._early_preview_next = 0.0
        screen._poll_early_preview()
        self.assertEqual(len(self.opened), 1, 'the same tab, refreshed by the page itself')
        self.assertIn('rest', get(self.opened[0]))

if __name__ == '__main__':
    unittest.main(verbosity=0)

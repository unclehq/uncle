#!/usr/bin/env python3
"""Tests for scripts/lib/home_agent_session.py (argv safety, grants, env, denials)."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'scripts', 'lib'))
sys.path.insert(0, ROOT)

import home_agent_session as has  # noqa: E402

BYPASS = ('--dangerously-skip-permissions', 'bypassPermissions', '--permission-mode',
          '--allow-dangerously-skip-permissions')


def fake_claude():
    d = tempfile.mkdtemp()
    path = os.path.join(d, 'claude')
    with open(path, 'w') as fh:
        fh.write('#!/bin/sh\nexit 0\n')
    os.chmod(path, 0o755)
    return path


def opt(argv, flag):
    return argv[argv.index(flag) + 1]


class BuildCommand(unittest.TestCase):
    def setUp(self):
        self.env = {'PATH': os.environ.get('PATH', ''), 'WORKFLOW_CLAUDE_CMD': fake_claude(), 'HOME': '/h',
                    'ANTHROPIC_API_KEY': 'k', 'UNCLE_MODEL_REFRESH_KEY': 'r', 'GH_TOKEN': 't', 'LC_ALL': 'C'}

    def build(self, grants=()):
        return has.build_command(ROOT, 'sonnet', 'low', grants, self.env)

    def test_no_bypass_flag(self):
        argv, _ = self.build()
        joined = ' '.join(argv)
        for bad in BYPASS:
            self.assertNotIn(bad, joined)

    def test_no_bare_bash_or_wildcard_by_default(self):
        argv, _ = self.build()
        allowed = opt(argv, '--allowedTools').split(',')
        self.assertNotIn('Bash', allowed)
        self.assertFalse([a for a in allowed if '*' in a])

    def test_env_strips_secrets(self):
        _, env = self.build()
        for name in has.STRIP_ENV:
            self.assertNotIn(name, env)
        self.assertNotIn('GH_TOKEN', env)
        self.assertEqual(env['HOME'], '/h')
        self.assertEqual(env['LC_ALL'], 'C')

    def test_missing_claude_unavailable(self):
        with self.assertRaises(ValueError) as ctx:
            has.build_command(ROOT, 'sonnet', 'low', (), {'PATH': '', 'WORKFLOW_CLAUDE_CMD': 'nope-xyz'})
        self.assertIn('unavailable', str(ctx.exception))

    def test_grant_is_exact_and_deny_list_intact(self):
        grant = has.grant_for_denial({'tool_name': 'Bash', 'tool_input': {'command': 'gh issue list'}})
        self.assertEqual(grant, 'Bash(gh issue list)')
        base, _ = self.build()
        argv, _ = self.build([grant])
        allowed = opt(argv, '--allowedTools').split(',')
        self.assertIn('Bash(gh issue list)', allowed)
        self.assertNotIn('Bash', allowed)
        self.assertEqual(opt(argv, '--disallowedTools'), opt(base, '--disallowedTools'))
        for p in has.DENY_PATTERNS:
            self.assertIn('Bash(%s:*)' % p, opt(argv, '--disallowedTools').split(','))

    def test_grants_absent_after_close(self):
        argv, env = self.build()
        s = has.HomeAgentSession(argv, env, ROOT, ['Bash(x)'])
        self.assertEqual(s.grants, ('Bash(x)',))
        s.close()
        self.assertEqual(s.grants, ())

    def test_broad_grants_refused(self):
        for bad in ('Bash', 'Bash(git:*)', 'Bash(*)', 'Write'):
            with self.assertRaises(ValueError):
                self.build([bad])

    def test_system_prompt_lists_deny_patterns(self):
        text = has.system_prompt(ROOT)
        self.assertIn('uncle_action', text)
        for p in has.DENY_PATTERNS:
            self.assertIn('`%s`' % p, text)


class Grants(unittest.TestCase):
    def grant(self, cmd):
        return has.grant_for_denial({'tool_name': 'Bash', 'tool_input': {'command': cmd}})

    def test_pattern_characters_escaped(self):
        self.assertEqual(self.grant('rm *.tmp'), 'Bash(rm \\*.tmp)')
        self.assertEqual(self.grant('echo (x)'), 'Bash(echo \\(x\\))')
        self.assertEqual(self.grant('echo a\\b'), 'Bash(echo a\\\\b)')

    def test_no_trailing_wildcard_ever(self):
        self.assertNotIn(':*', self.grant('git status'))
        self.assertFalse(self.grant('git status:*').endswith(':*)'))

    def test_deny_pattern_refused(self):
        for cmd in ('git push --force origin main', 'git push -f', 'FOO=1 git push --force',
                    'ls && rm -rf /', "bash -c 'git push -f'"):
            with self.assertRaises(ValueError, msg=cmd):
                self.grant(cmd)

    def test_unreadable_command_refused(self):
        with self.assertRaises(ValueError):
            self.grant("echo 'unterminated")

    def test_unsupported_values_refused(self):
        for denial in ({'tool_name': 'WebFetch', 'tool_input': {'url': 'x'}},
                       {'tool_name': 'Bash', 'tool_input': {}},
                       {'tool_name': 'Bash', 'tool_input': {'command': 'a,b'}},
                       {'tool_name': 'Bash', 'tool_input': {'command': 'a\nb'}}):
            with self.assertRaises(ValueError):
                has.grant_for_denial(denial)

    def test_file_tool_grant_is_the_path(self):
        self.assertEqual(has.grant_for_denial({'tool_name': 'Write', 'tool_input': {'file_path': '/a/b.txt'}}),
                         'Write(/a/b.txt)')


class Denials(unittest.TestCase):
    def test_denials_surfaced_verbatim(self):
        denial = {'tool_name': 'Bash', 'tool_input': {'command': 'git clone https://x/y.git', 'description': 'd'}}
        lines = [json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'hi'}]}}),
                 json.dumps({'type': 'result', 'is_error': False, 'result': 'hi', 'permission_denials': [denial]})]
        self.assertEqual(has.permission_denials(lines), [denial])

    def test_no_denials(self):
        self.assertEqual(has.permission_denials([json.dumps({'type': 'result', 'result': 'x'}), 'garbage']), [])


if __name__ == '__main__':
    unittest.main()

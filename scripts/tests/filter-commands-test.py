#!/usr/bin/env python3
"""filter_commands.py: ordinary commands and the defect-injection command are separated, and group positions follow."""
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib', 'filter_commands.py')
COMMANDS = ['npm ls --depth=0 >/dev/null 2>&1 || npm install', 'npx vite build', 'npx vitest run',
            'npx playwright test', 'node tests/mutations/run.mjs']


def run(commands, groups, kind):
    d = tempfile.mkdtemp()
    c, g = os.path.join(d, 'c'), os.path.join(d, 'g')
    open(c, 'w').write('\n'.join(commands) + '\n')
    open(g, 'w').write(groups)
    out = subprocess.run([sys.executable, '-B', SCRIPT, c, g, kind], capture_output=True, text=True, check=True).stdout.strip()
    return out, open(c).read().splitlines(), open(g).read().splitlines()


class Filter(unittest.TestCase):
    def test_main_drops_the_mutation_runner_and_keeps_order(self):
        n, cmds, _ = run(COMMANDS, '', 'main')
        self.assertEqual(n, '4')
        self.assertEqual(cmds, COMMANDS[:4])

    def test_mutation_keeps_only_the_runner(self):
        n, cmds, groups = run(COMMANDS, '2 3\n', 'mutation')
        self.assertEqual((n, cmds, groups), ('1', [COMMANDS[4]], []))

    def test_groups_are_renumbered_and_a_group_reduced_to_one_command_is_dropped(self):
        # browser tests (4) grouped with the runner (5): once the runner is split off, that group has one member left
        _, _, groups = run(COMMANDS, '2 3\n4 5\n', 'main')
        self.assertEqual(groups, ['2 3'])

    def test_a_plan_without_a_mutation_command_is_unchanged(self):
        n, cmds, groups = run(COMMANDS[:4], '2 3\n', 'main')
        self.assertEqual((n, cmds, groups), ('4', COMMANDS[:4], ['2 3']))
        n, cmds, _ = run(COMMANDS[:4], '', 'mutation')
        self.assertEqual((n, cmds), ('0', []))

    def test_other_runner_names_are_recognized(self):
        for cmd in ('node scripts/inject.mjs', 'npm run test:defects', 'node tools/run-mutations.js'):
            _, main_cmds, _ = run(['npx vitest run', cmd], '', 'main')
            self.assertEqual(main_cmds, ['npx vitest run'], cmd)


if __name__ == '__main__':
    unittest.main()

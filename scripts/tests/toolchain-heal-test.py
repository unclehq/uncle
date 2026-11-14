import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import toolchain_heal as th  # noqa: E402

SUDO = '#!/bin/sh\n[ "$1" = -n ] || exit 9\nshift\nexec "$@"\n'


class SignatureTest(unittest.TestCase):
    def test_finds_programs_from_common_failure_messages(self):
        text = ('Program zzocamlc not found in the tree or in PATH\nsh: 1: zzbison: not found\nbash: zzflex: command not found\n'
                'exec: "zzgcc": executable file not found in $PATH\nError: spawn zzconvert ENOENT\nenv: \'zzpython9\': No such file or directory\n')
        self.assertEqual(sorted(th.missing_programs(text)), sorted(['zzocamlc', 'zzbison', 'zzflex', 'zzgcc', 'zzconvert', 'zzpython9']))

    def test_ignores_programs_that_exist_and_odd_names(self):
        self.assertEqual(th.missing_programs('sh: 1: sh: not found\n$(rm -rf x): command not found\n; evil: not found'), ['evil'])


class HealTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        self.record = self.tmp / 'state' / 'heal.json'
        self.log = self.tmp / 'green.log'
        env = {'PATH': '%s:/usr/bin:/bin' % self.bin, 'UNCLE_HOSTED': '1'}
        p = mock.patch.dict(os.environ, env, clear=False)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop('WORKFLOW_TOOLCHAIN_INSTALL', None)
        self.script('sudo', SUDO)

    def script(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def apt_file(self, mapping):
        rows = ''.join('%s) echo "%s: /usr/bin/%s";; ' % (prog, pkg, prog) for prog, pkg in mapping.items())
        self.script('apt-file', '#!/bin/sh\n[ "$1" = search ] || exit 0\ncase "$3" in\n*/sh$) echo "dash: /usr/bin/sh";;\n%s\nesac\n' % ''.join(
            '*/%s$) echo "%s: /usr/bin/%s"; echo "%s-doc: /usr/bin/%s";;\n' % (prog, pkg, prog, pkg, prog) for prog, pkg in mapping.items()))

    def test_installs_the_package_that_ships_the_missing_program(self):
        argv = self.tmp / 'argv.log'
        self.script('apt-get', '#!/bin/sh\necho "$@" >> %s\ntouch %s/zzcc\nchmod +x %s/zzcc\n' % (argv, self.bin, self.bin))
        self.apt_file({'zzcc': 'pkg-cc'})
        self.log.write_text('Program zzcc not found in the tree or in PATH\n')
        with mock.patch('sys.stdout'):
            self.assertEqual(th.main([str(self.log), str(self.record)]), 0)
        self.assertIn('install -y --no-install-recommends pkg-cc', argv.read_text())
        self.assertNotIn('pkg-cc-doc', argv.read_text())
        self.assertEqual(json.loads(self.record.read_text())['tried'], ['zzcc'])

    def test_a_program_is_tried_once(self):
        self.script('apt-get', '#!/bin/sh\nexit 0\n')
        self.apt_file({'zzcc': 'pkg-cc'})
        self.log.write_text('Program zzcc not found\n')
        with mock.patch('sys.stdout'):
            self.assertEqual(th.main([str(self.log), str(self.record)]), 1)     # installed nothing that satisfies it
            self.assertEqual(th.main([str(self.log), str(self.record)]), 1)     # and it is not tried again
        self.assertEqual(len(json.loads(self.record.read_text())['rounds']), 1)

    def test_not_hosted_does_nothing(self):
        os.environ['UNCLE_HOSTED'] = '0'
        marker = self.tmp / 'ran'
        self.script('apt-get', '#!/bin/sh\ntouch %s\n' % marker)
        self.log.write_text('Program zzcc not found\n')
        self.assertEqual(th.main([str(self.log), str(self.record)]), 1)
        self.assertFalse(marker.exists())

    def test_no_package_for_the_program_is_reported(self):
        self.script('apt-get', '#!/bin/sh\nexit 0\n')
        self.apt_file({'zzother': 'pkg-other'})
        self.log.write_text('bash: zzcc: command not found\n')
        with mock.patch('sys.stdout') as out:
            self.assertEqual(th.main([str(self.log), str(self.record)]), 1)
        self.assertIn('no package ships it', ''.join(c.args[0] for c in out.write.call_args_list))

    def test_usage_error_is_two(self):
        with mock.patch('sys.stderr'):
            self.assertEqual(th.main([]), 2)


if __name__ == '__main__':
    unittest.main()

import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import toolchain_install as ti  # noqa: E402

SUDO = '#!/bin/sh\n[ "$1" = -n ] || exit 9\nshift\nexec "$@"\n'


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie still answers signal 0; check state.
    try:
        state = Path('/proc/%d/stat' % pid).read_text().split(')')[-1].split()[0]
        return state != 'Z'
    except OSError:
        return True


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        self.record = self.tmp / 'state' / 'toolchain-install.json'
        self.cmds = self.tmp / 'commands.txt'
        env = {'PATH': '%s:/usr/bin:/bin' % self.bin, 'UNCLE_HOSTED': '1'}
        patcher = mock.patch.dict(os.environ, env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop('WORKFLOW_TOOLCHAIN_INSTALL', None)
        pk = mock.patch.dict(ti.PACKAGES, {'zzfake1': 'pkg-one', 'zzfake2': 'pkg-two'})
        pk.start()
        self.addCleanup(pk.stop)
        self.script('sudo', SUDO)

    def script(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def run_installer(self, commands):
        self.cmds.write_text(commands)
        with mock.patch('sys.stdout'):
            ti.install(self.cmds, self.record)
        return json.loads(self.record.read_text())

    def test_installs_missing_tools_in_one_apt_call(self):
        log = self.tmp / 'argv.log'
        self.script('apt-get', '#!/bin/sh\necho "$@" >> %s\ntouch %s/zzfake1 %s/zzfake2\n'
                    'chmod +x %s/zzfake1 %s/zzfake2\n' % ((log,) + (self.bin,) * 4))
        rec = self.run_installer('zzfake1 --go\nzzfake2 && zzfake1\n')
        lines = log.read_text().splitlines()
        self.assertEqual(lines, ['install -y --no-install-recommends pkg-one pkg-two'])
        self.assertEqual(rec['install']['status'], 'ok')
        self.assertEqual(rec['still_missing'], [])

    def test_unmapped_tool_skipped_with_reason(self):
        self.script('apt-get', '#!/bin/sh\nexit 0\n')
        rec = self.run_installer('zznomap run\n')
        self.assertEqual(rec['skipped'][0]['tool'], 'zznomap')
        self.assertIn('no package mapping', rec['skipped'][0]['reason'])
        self.assertIsNone(rec['install'])

    def test_not_hosted_never_installs(self):
        os.environ['UNCLE_HOSTED'] = '0'
        marker = self.tmp / 'ran'
        self.script('apt-get', '#!/bin/sh\ntouch %s\n' % marker)
        rec = self.run_installer('zzfake1\n')
        self.assertFalse(marker.exists())
        self.assertIsNone(rec['install'])
        self.assertEqual(rec['still_missing'], ['zzfake1'])

    def test_kill_switch_never_installs(self):
        os.environ['WORKFLOW_TOOLCHAIN_INSTALL'] = '0'
        marker = self.tmp / 'ran'
        self.script('apt-get', '#!/bin/sh\ntouch %s\n' % marker)
        self.run_installer('zzfake1\n')
        self.assertFalse(marker.exists())

    def test_missing_sudo_recorded_and_not_fatal(self):
        (self.bin / 'sudo').unlink()
        with mock.patch('shutil.which', side_effect=lambda n: None if n in ('sudo', 'zzfake1') else '/x/' + n):
            rec = self.run_installer('zzfake1\n')
        self.assertEqual(rec['install']['status'], 'unavailable')

    def test_partial_success_reports_only_remaining_tool(self):
        self.script('apt-get', '#!/bin/sh\ntouch %s/zzfake1\nchmod +x %s/zzfake1\nexit 100\n' % (self.bin, self.bin))
        rec = self.run_installer('zzfake1\nzzfake2\n')
        self.assertEqual(rec['install']['status'], 'failed')
        self.assertEqual(rec['installed'], ['zzfake1'])
        self.assertEqual(rec['still_missing'], ['zzfake2'])

    def test_mixed_valid_and_malformed_lines(self):
        self.script('apt-get', '#!/bin/sh\ntouch %s/zzfake1 %s/zzfake2\nchmod +x %s/zzfake1 %s/zzfake2\n'
                    % ((self.bin,) * 4))
        rec = self.run_installer('zzfake1 a\necho $(whoami)\nzzfake2 b\nfoo && (\n')
        self.assertEqual({m['line'] for m in rec['malformed']}, {2, 4})
        self.assertTrue(all(m['reason'] for m in rec['malformed']))
        self.assertEqual(rec['missing'], ['zzfake1', 'zzfake2'])
        self.assertEqual(rec['installed'], ['zzfake1', 'zzfake2'])

    def test_timeout_kills_whole_process_tree(self):
        pidfile = self.tmp / 'child.pid'
        self.script('apt-get', '#!/bin/sh\nsleep 300 &\necho $! > %s\nwait\n' % pidfile)
        os.environ['WORKFLOW_TOOLCHAIN_DEADLINE'] = '1'
        os.environ['WORKFLOW_TOOLCHAIN_GRACE'] = '1'
        rec = self.run_installer('zzfake1\n')
        self.assertEqual(rec['install']['status'], 'timeout')
        self.assertTrue(rec['install']['cleanup'])
        pid = int(pidfile.read_text())
        deadline = time.monotonic() + 3
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(alive(pid), 'descendant survived timeout cleanup')
        self.assertEqual([s['tool'] for s in rec['skipped']], ['zzfake1'] * 0 + ['pkg-one'] * 0 + [s['tool'] for s in rec['skipped']])
        self.assertIn('pkg-one', [s['tool'] for s in rec['skipped']])

    def apt_cache(self, available):
        self.script('apt-cache', '#!/bin/sh\n[ "$1" = policy ] || exit 0\ncase "$2" in %s) echo "  Candidate: 1.0";; *) echo "  Candidate: (none)";; esac\n'
                    % '|'.join(available))

    def test_renamed_package_uses_second_candidate(self):
        log = self.tmp / 'argv.log'
        self.script('apt-get', '#!/bin/sh\necho "$@" >> %s\ntouch %s/zzfake1\nchmod +x %s/zzfake1\n' % (log, self.bin, self.bin))
        self.apt_cache(['pkg-new'])
        with mock.patch.dict(ti.PACKAGES, {'zzfake1': ('pkg-old', 'pkg-new')}):
            rec = self.run_installer('zzfake1\n')
        self.assertIn('install -y --no-install-recommends pkg-new', log.read_text())
        self.assertEqual(rec['still_missing'], [])

    def test_unavailable_package_does_not_block_the_others(self):
        log = self.tmp / 'argv.log'
        self.script('apt-get', '#!/bin/sh\necho "$@" >> %s\ntouch %s/zzfake2\nchmod +x %s/zzfake2\n' % (log, self.bin, self.bin))
        self.apt_cache(['pkg-two'])
        rec = self.run_installer('zzfake1\nzzfake2\n')
        self.assertNotIn('pkg-one', ' '.join(l for l in log.read_text().splitlines() if l.startswith('install')))
        self.assertEqual(rec['installed'], ['zzfake2'])
        self.assertEqual(rec['still_missing'], ['zzfake1'])
        self.assertIn('no installable package', [s for s in rec['skipped'] if s['tool'] == 'zzfake1'][0]['reason'])

    def test_dune_also_brings_the_ocaml_compiler(self):
        log = self.tmp / 'argv.log'
        self.script('apt-get', '#!/bin/sh\necho "$@" >> %s\n' % log)
        with mock.patch.dict(ti.PACKAGES, {'zzdune': 'pkg-dune', 'zzocaml': 'pkg-ocaml'}), \
                mock.patch.dict(ti.NEEDS, {'zzdune': ('zzocaml',)}):
            rec = self.run_installer('zzdune build\n')
        self.assertIn('pkg-dune', log.read_text())
        self.assertIn('pkg-ocaml', log.read_text())
        self.assertIn('zzocaml', rec['missing'])

    def test_cli_usage_error_is_two(self):
        with mock.patch('sys.stderr'):
            self.assertEqual(ti.main([]), 2)

    def test_cli_unreadable_commands_file_exits_zero(self):
        with mock.patch('sys.stderr'):
            self.assertEqual(ti.main([str(self.tmp / 'nope'), str(self.record)]), 0)


if __name__ == '__main__':
    unittest.main()

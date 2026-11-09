#!/usr/bin/env python3
"""reviewer-prompt-file: --prompt-file parsing (AC-1), guard (AC-5) and launch-failure (AC-6) helpers."""
import importlib.util, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts' / 'lib' / 'reviewer-prompt.sh'


def load_self_hosted():
    spec = importlib.util.spec_from_file_location('self_hosted_under_test', ROOT / 'scripts' / 'lib' / 'self_hosted.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bash(script, *args):
    return subprocess.run(['bash', '-c', script, 'bash', *args], capture_output=True, text=True)


class ParseArgumentsPromptFile(unittest.TestCase):
    def setUp(self):
        self.sh = load_self_hosted()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name).resolve()
        self.old = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def parse(self, *args):
        return self.sh.parse_arguments('reviewer', list(args))

    def test_bytes_round_trip(self):
        for raw in (b'  hello\r\nworld\r\n', b'x\n', b'\n lead and trail \n\n', 'café ☃\n'.encode()):
            p = self.dir / 'prompt.txt'
            p.write_bytes(raw)
            prompt = self.parse('--prompt-file', str(p))[1]
            self.assertEqual(prompt.encode('utf-8'), raw)

    def test_large_prompt_intact(self):
        raw = (b'abcdefghij' * 20000)
        p = self.dir / 'big.txt'
        p.write_bytes(raw)
        self.assertEqual(self.parse('--prompt-file', str(p))[1].encode(), raw)

    def test_errors_raise_value_error_naming_path(self):
        ok = self.dir / 'ok.txt'
        ok.write_text('hi')
        blank = self.dir / 'blank.txt'
        blank.write_text(' \n\t\n')
        empty = self.dir / 'empty.txt'
        empty.write_bytes(b'')
        bad = self.dir / 'bad.txt'
        bad.write_bytes(b'\xff\xfe\x00bad')
        (self.dir / 'sub').mkdir()
        outside = Path(tempfile.mkdtemp())
        out_file = outside / 'o.txt'
        out_file.write_text('outside')
        link = self.dir / 'link.txt'
        link.symlink_to(out_file)
        cases = {
            'blank': [str(blank)], 'empty': [str(empty)], 'missing': [str(self.dir / 'nope.txt')],
            'directory': [str(self.dir / 'sub')], 'badutf8': [str(bad)],
            'outside': [str(out_file)], 'symlink': [str(link)],
        }
        for name, (path,) in ((k, v) for k, v in cases.items()):
            with self.subTest(name):
                with self.assertRaises(ValueError) as cm:
                    self.parse('--prompt-file', path)
                self.assertIn(path, str(cm.exception))
        with self.subTest('file plus positional'):
            self.assertEqual(self.parse('--prompt-file', str(ok), 'positional prompt')[1], 'hi')
        with self.subTest('repeated option'):
            with self.assertRaises(ValueError):
                self.parse('--prompt-file', str(ok), '--prompt-file', str(ok))

    def test_positional_still_supported(self):
        self.assertEqual(self.parse('a positional prompt')[1], 'a positional prompt')


class Guard(unittest.TestCase):
    def guard(self, size, kind, prefix=0, multibyte=False):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'p.txt'
            f.write_bytes(('é' * (size // 2) + 'a' * (size % 2)).encode() if multibyte else b'a' * size)
            return bash('source "$1"; reviewer_prompt_guard "$2" "$3" "$4"', str(HELPER), 'Rev', kind, str(f))

    def test_boundaries_argv(self):
        self.assertEqual(self.guard(1024, 'argv').returncode, 0)
        self.assertEqual(self.guard(120000, 'argv').returncode, 0)
        for size in (120001, 200 * 1024):
            r = self.guard(size, 'argv')
            self.assertNotEqual(r.returncode, 0, size)
            out = r.stdout + r.stderr
            self.assertIn('Reviewer Rev', out)
            self.assertIn(str(size), out)
            self.assertIn('131,072', out)

    def test_multibyte_counts_bytes(self):
        r = self.guard(130000, 'argv', multibyte=True)  # ~65000 characters, 130000 bytes
        self.assertNotEqual(r.returncode, 0)

    def test_assembled_element_over_limit_fails(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'assembled.txt'
            f.write_bytes(b'wrapper-prefix\n' + b'a' * 119990 + b'\nsuffix')  # assembled element > 120000
            r = bash('source "$1"; reviewer_prompt_guard Rev argv "$2"', str(HELPER), str(f))
            self.assertNotEqual(r.returncode, 0)

    def test_file_capable_never_guarded(self):
        self.assertEqual(self.guard(200 * 1024, 'file').returncode, 0)


class LaunchFailure(unittest.TestCase):
    def report(self, status, log_text):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / 'log.txt'
            log.write_text(log_text)
            r = bash('source "$1"; reviewer_report_launch_failure Rev "$2" "$3"', str(HELPER), str(status), str(log))
            return r, r.stdout + r.stderr

    def test_exit_126_127_reported(self):
        for status in (126, 127):
            r, out = self.report(status, '')
            self.assertIn('Reviewer Rev: launch failed (exit %d)' % status, out)
            self.assertEqual(r.returncode, 0)

    def test_e2big_with_exit_zero_not_reported(self):
        _, out = self.report(0, 'bash: x: Argument list too long\n')
        self.assertNotIn('launch failed', out)

    def test_ordinary_failure_not_reported(self):
        _, out = self.report(1, 'validation problem\n')
        self.assertNotIn('launch failed', out)


FAKE_RUNNER = '''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
rec = {'argv_sizes': [len(a.encode()) for a in args], 'prompt_len': -1, 'prompt_sha': None}
if '--prompt-file' in args:
    import hashlib
    data = open(args[args.index('--prompt-file') + 1], 'rb').read()
    rec['prompt_len'] = len(data)
    rec['prompt_sha'] = hashlib.sha256(data).hexdigest()
elif args:
    import hashlib
    data = args[-1].encode()
    rec['prompt_len'] = len(data)
    rec['prompt_sha'] = hashlib.sha256(data).hexdigest()
open(os.environ['RECORD_FILE'], 'a').write(json.dumps(rec) + '\\n')
'''

PROMPT = b'0123456789abcdef' * (200 * 1024 // 16)


def extract(path, start, end):
    text = (ROOT / path).read_text()
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


class CallSites(unittest.TestCase):
    """Behavioral: real launch-site code is executed against a recording fake runner."""

    def setUp(self):
        import hashlib, json
        self.json, self.sha = json, hashlib.sha256(PROMPT).hexdigest()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name).resolve()
        self.runner = self.dir / 'self_hosted.py'
        self.runner.write_text(FAKE_RUNNER)
        self.prompt = self.dir / 'prompt.md'
        self.prompt.write_bytes(PROMPT)
        self.record = self.dir / 'record.jsonl'

    def tearDown(self):
        self.tmp.cleanup()

    def check_record(self):
        lines = self.record.read_text().splitlines()
        self.assertTrue(lines, 'runner was never invoked')
        for line in lines:
            rec = self.json.loads(line)
            self.assertLess(max(rec['argv_sizes']), 120000)
            self.assertEqual(rec['prompt_len'], len(PROMPT))
            self.assertEqual(rec['prompt_sha'], self.sha)

    def run_bash(self, script):
        env = dict(os.environ, RECORD_FILE=str(self.record))
        r = subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_stagegate_single_launch(self):
        body = extract('scripts/stagegate.sh', 'local prompt_kind=argv', '        fi\n        # race_self')
        script = f'''
perf_stream() {{ cat; }}
. "{HELPER}"
f() {{
  local client_cmd=(python3 "{self.runner}") log_name=t prompt_file="{self.prompt}" delivery_file="" review_schema="" reviewer_sandbox=read-only output_file="{self.dir}/out" LOG_DIR="{self.dir}"
  local -a model_args=()
  local status=0
  {body}
}}
f
'''
        self.run_bash(script)
        self.check_record()

    def test_stagegate_candidate_launch_script(self):
        body = extract('scripts/stagegate.sh', 'local part\n        for part in "${client_cmd[@]}"; do printf \'%q \' "$part"; done\n        printf -- \'exec --ephemeral', '    } > "$launch_script"')
        cand = self.dir / 'cand'
        cand.mkdir()
        script = f'''
f() {{
  local client_cmd=(python3 "{self.runner}") reviewer_sandbox=read-only delivery_mode=0 launch_script="{self.dir}/launch.sh"
  local -a model_args=()
  {{
    printf '#!/usr/bin/env bash\\n'
    {body}
  }} > "{self.dir}/launch.sh"
}}
f
cp "{self.prompt}" "{cand}/prompt.md"
CANDIDATE_DIR="{cand}" bash "{self.dir}/launch.sh"
'''
        self.run_bash(script)
        self.check_record()

    def test_change_workflow_launch(self):
        body = extract('scripts/change-workflow.sh', '. "$ROOT/scripts/lib/reviewer-prompt.sh"', '        wait "$!"')
        script = f'''
ROOT="{ROOT}"
perf_stream() {{ cat; }}
f() {{
  local client_cmd=(python3 "{self.runner}") cmd=python3 log_name=t prompt_file="{self.prompt}" delivery_file="" review_schema="" LOG_DIR="{self.dir}"
  local -a flags=()
  {body}
  wait "$!"
}}
f
'''
        self.run_bash(script)
        self.check_record()


class NativeStagePromptFile(unittest.TestCase):
    def test_read_prompt_file_200kb(self):
        sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
        spec = importlib.util.spec_from_file_location('native_stage_under_test', ROOT / 'scripts' / 'lib' / 'native_stage.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            raw = b'a\r\nb' * 40000
            (d / 'p.md').write_bytes(raw)
            old = os.getcwd()
            os.chdir(d)
            try:
                rest, text = mod.read_prompt_file(['--x', '--prompt-file', str(d / 'p.md')])
                self.assertEqual(rest, ['--x'])
                self.assertEqual(text.encode(), raw)
                (d / 'e.md').write_bytes(b'')
                with self.assertRaises(ValueError):
                    mod.read_prompt_file(['--prompt-file', str(d / 'e.md')])
            finally:
                os.chdir(old)


if __name__ == '__main__':
    unittest.main()

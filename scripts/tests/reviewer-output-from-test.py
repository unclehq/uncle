"""reviewer_output.py --from FILE must behave exactly like the same document on stdin: same stdout, same stderr, same exit status, in every
mode (plain, --packet, --artifact PATH), for documents it accepts and ones it rejects. The driver passes --from so the call needs no stdin
and the Python host can serve it (scripts/lib/pyhost.py)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'lib' / 'reviewer_output.py'
DOCUMENTS = {
    'heading': '# Review\n\nAll good.\n',
    'table': '| id | status |\n|---|---|\n| MC-1 | PASS |\n',
    'summary-only': 'I will now write the artifact for you.',
    'empty': '',
    'no-trailing-newline': '## Findings\n\nnone',
    'crlf': '# Review\r\n\r\ntext\r\n',
    'unicode': '# Résumé\n\ncafé ✓\n',
    'packet-json': '{"schema":"uncle.artifact/v1","kind":"adversarial-review-worker-packet","findings":[]}\n',
    'fenced-json': '```json\n{"schema":"uncle.artifact/v1","kind":"x","findings":[]}\n```\n',
}


def run(args, stdin_text=None):
    result = subprocess.run([sys.executable, '-B', str(SCRIPT), *args], input=stdin_text, capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout, result.stderr


class FromMatchesStdin(unittest.TestCase):
    def test_every_mode_and_document(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, text in DOCUMENTS.items():
                path = Path(directory, name + '.md')
                path.write_bytes(text.encode('utf-8'))
                artifact = str(Path(directory, 'ARTIFACT.md'))
                for label, flags in (('plain', []), ('packet', ['--packet']), ('artifact', ['--artifact', artifact])):
                    with self.subTest(document=name, mode=label):
                        via_stdin = run([*flags, 'claude'], text)
                        via_file = run([*flags, '--from', str(path), 'claude'])
                        self.assertEqual(via_file, via_stdin)

    def test_flag_order_is_free(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'd.md')
            path.write_text('# Review\n\nOk.\n')
            self.assertEqual(run(['--from', str(path), '--packet', 'kimi']), run(['--packet', 'kimi'], '# Review\n\nOk.\n'))

    def test_from_needs_a_path(self):
        code, _, err = run(['claude', '--from'])
        self.assertEqual(code, 2)
        self.assertIn('--from requires a path', err)

    def test_a_missing_file_fails_like_an_unreadable_input(self):
        code, out, _ = run(['--from', '/nonexistent/input.md', 'claude'])
        self.assertNotEqual(code, 0)
        self.assertEqual(out, '')


if __name__ == '__main__':
    unittest.main()

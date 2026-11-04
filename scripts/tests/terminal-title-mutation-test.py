#!/usr/bin/env python3
"""AC-8 defect injection: mutants of terminal_title.py must fail the title assertions."""
import os
import pathlib
import pty
import re
import select
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "scripts" / "lib" / "terminal_title.py"
TITLE_RE = re.compile(rb"\x1b\]2;(.*?)(?:\x07|\x1b\\)", re.S)
POP = b"\x1b[23;2t"

MUTANT_A_OLD = "_title_seq(None) + POP"
MUTANT_A_NEW = "osc('uncle') + POP"


def mutate_a(src):
    if MUTANT_A_OLD not in src:
        raise AssertionError("cannot apply mutant (a): end() title write not found")
    return src.replace(MUTANT_A_OLD, MUTANT_A_NEW)


def mutate_b(src):
    m = re.search(r"^def sanitize\(\s*(\w+)[^)]*\)[^:]*:\s*\n", src, re.M)
    if not m:
        raise AssertionError("cannot apply mutant (b): sanitize not found")
    return src[:m.end()] + "    return %s\n" % m.group(1) + src[m.end():]


def run_cli(script, args, root):
    env = {"PATH": os.environ["PATH"], "TERM": "xterm", "UNCLE_PROJECT_ROOT": root}
    master, slave = pty.openpty()
    p = subprocess.Popen([sys.executable, "-B", str(script)] + args, env=env,
                         stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    out = b""
    while True:
        r, _, _ = select.select([master], [], [], 15)
        if not r:
            p.kill()
            break
        try:
            c = os.read(master, 4096)
        except OSError:
            break
        if not c:
            break
        out += c
    p.wait()
    os.close(master)
    return out


def title_assertions(script):
    """Return list of failed assertion descriptions for the helper at `script`."""
    failed = []
    out = run_cli(script, ["end"], "/tmp/mutproj")
    ts = [t.decode() for t in TITLE_RE.findall(out)]
    if not ts or ts[-1] != "mutproj · uncle":
        failed.append("end writes project-only title")
    out = run_cli(script, ["begin"], "/tmp/evil\x1b]2;pwn\x07name")
    if out.count(b"\x07") > 1 or b"pwn\x07" in out:
        failed.append("sanitize strips controls")
    ts = [t.decode() for t in TITLE_RE.findall(out)]
    if not ts or ts[0] != "evil]2;pwnname · uncle":
        failed.append("sanitized title text")
    return failed


class MutationTest(unittest.TestCase):
    def _copy(self, d, mutate=None):
        dst = pathlib.Path(d) / "terminal_title.py"
        src = SRC.read_text()
        dst.write_text(mutate(src) if mutate else src)
        return dst

    def test_unmutated_copy_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(title_assertions(self._copy(d)), [])

    def test_mutant_a_end_bare_uncle_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            failed = title_assertions(self._copy(d, mutate_a))
            self.assertIn("end writes project-only title", failed)

    def test_mutant_b_sanitize_disabled_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            failed = title_assertions(self._copy(d, mutate_b))
            self.assertTrue(failed, "sanitize-disabled mutant survived")


if __name__ == "__main__":
    unittest.main()

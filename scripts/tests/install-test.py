#!/usr/bin/env python3
"""Hermetic bootstrap and payload checks; no package-manager mutations."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/install/build-package.py"
spec = importlib.util.spec_from_file_location("package", BUILDER)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.log = self.work / "calls"
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", CALLS=str(self.log))

    def stub(self, name, text):
        path = self.bin / name
        path.write_text("#!/bin/bash\nset -eu\n" + text)
        path.chmod(0o755)

    def run_installer(self, *args):
        return subprocess.run(["bash", str(ROOT / "install.sh"), *args], env=self.env,
                              capture_output=True, text=True)

    def test_os_detection_and_dry_run_do_not_install(self):
        self.stub("apt-get", 'echo MUTATION >> "$CALLS"\n')
        self.stub("brew", 'echo MUTATION >> "$CALLS"\n')
        for kernel, expected in [("Darwin", "homebrew"), ("Linux", "apt"),
                                 ("MINGW64_NT-10.0", "scoop"), ("MSYS_NT-10.0", "scoop")]:
            self.stub("uname", f"echo {kernel}\n")
            result = self.run_installer("--dry-run", "--ref", "feature/install")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"Installer: {expected}", result.stdout)
        self.assertFalse(self.log.exists())
        self.stub("uname", "echo FreeBSD\n")
        self.assertNotEqual(self.run_installer("--dry-run").returncode, 0)

    def test_invalid_arguments_do_not_reach_package_manager(self):
        for args in [("--repo", "x/y;echo"), ("--ref", "--upload-pack=bad"),
                     ("--ref", "../main"), ("--ref",), ("--unknown",)]:
            self.assertEqual(self.run_installer(*args).returncode, 2, args)
        self.assertFalse(self.log.exists())

    def test_linux_installs_built_deb_and_propagates_errors(self):
        self.stub("uname", "echo Linux\n")
        self.stub("id", "echo 0\n")
        self.stub("apt-get", 'printf "%s\\n" "$*" >> "$CALLS"\nexit "${APT_STATUS:-0}"\n')
        self.stub("python3", '''printf 'build %s\\n' "$*" >> "$CALLS"
while [[ $# -gt 0 ]]; do
  if [[ "$1" == --output ]]; then mkdir -p "$2"; touch "$2/uncle_0.1.0_all.deb"; break; fi
  shift
done
''')
        result = self.run_installer("--source-dir", str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text()
        self.assertIn("update\n", calls)
        self.assertIn("--reinstall", calls)
        self.assertIn("uncle_0.1.0_all.deb", calls)
        self.log.unlink()
        self.env["APT_STATUS"] = "37"
        self.assertEqual(self.run_installer("--source-dir", str(ROOT)).returncode, 37)
        self.assertNotIn("build ", self.log.read_text())

    def test_windows_dispatch_preserves_paths_and_ref(self):
        self.stub("uname", "echo MINGW64_NT-10.0\n")
        self.stub("cygpath", 'printf "%s\\n" "$2"\n')
        self.stub("powershell.exe", 'printf "%s\\n" "$@" "${MSYS2_ARG_CONV_EXCL:-}" > "$CALLS"\nexit 19\n')
        result = self.run_installer("--source-dir", str(ROOT), "--ref", "v1.2.3")
        self.assertEqual(result.returncode, 19)
        calls = self.log.read_text().splitlines()
        self.assertIn(str(ROOT / "install.ps1"), calls)
        self.assertIn("v1.2.3", calls)
        self.assertIn("-SourceDir", calls)
        self.assertEqual(calls[-1], "*")

    def test_archive_excludes_state_and_runs_from_path_with_spaces(self):
        source = self.work / "source"
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", ".uncle", "__pycache__"))
        (source / ".uncle/workflow").mkdir(parents=True)
        (source / ".uncle/workflow/secret").write_text("do not ship")
        (source / "UNRELATED_PRIVATE_FILE").write_text("do not ship")
        output = self.work / "packages"
        output.mkdir()
        package.build_archive(source, output)
        with tarfile.open(output / "uncle.tar.gz") as archive:
            names = archive.getnames()
            self.assertFalse(any(".uncle" in name or "PRIVATE" in name or "__pycache__" in name for name in names))
            extracted = self.work / "installed with spaces"
            # Archive was just created from the explicit local allowlist above.
            archive.extractall(extracted)
        result = subprocess.run(["bash", str(extracted / "uncle/uncle"), "--help"],
                                cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: uncle", result.stdout)
        self.assertTrue(os.access(extracted / "uncle/scripts/stagegate.sh", os.X_OK))

    def test_linux_fetches_requested_github_ref(self):
        self.stub("uname", "echo Linux\n")
        self.stub("id", "echo 0\n")
        self.stub("apt-get", 'printf "%s\\n" "$*" >> "$CALLS"\n')
        self.stub("git", '''printf 'git %s\\n' "$*" >> "$CALLS"
if [[ "$1" == init ]]; then mkdir -p "$3"; fi
if [[ "$1" == -C ]]; then
    mkdir -p "$2/scripts/install"
    touch "$2/scripts/install/build-package.py"
    if [[ "$3" == rev-parse ]]; then echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; fi
fi
''')
        self.stub("python3", '''while [[ $# -gt 0 ]]; do
if [[ "$1" == --output ]]; then mkdir -p "$2"; touch "$2/uncle_0.1.0_all.deb"; break; fi
shift
done
''')
        result = self.run_installer("--repo", "example/uncle", "--ref", "v1.2.3")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text()
        self.assertIn("remote add origin https://github.com/example/uncle.git", calls)
        self.assertIn("fetch --depth 1 origin v1.2.3", calls)
        self.assertIn("checkout -q --detach FETCH_HEAD", calls)

    def test_homebrew_packages_local_checkout_and_preserves_archive(self):
        self.stub("uname", "echo Darwin\n")
        self.stub("id", "echo 1000\n")
        self.env["BREW_ROOT"] = str(self.work / "brew with spaces")
        self.stub("brew", '''printf 'brew %s\\n' "$*" >> "$CALLS"
case "$1" in
  --repository)
    if [[ $# == 1 ]]; then echo "$BREW_ROOT"; else echo "$BREW_ROOT/Library/Taps/unclehq/homebrew-github-install"; fi ;;
  --prefix) echo "$BREW_ROOT/python" ;;
  tap-new) mkdir -p "$BREW_ROOT/Library/Taps/unclehq/homebrew-github-install" ;;
  list) exit 1 ;;
esac
''')
        result = self.run_installer("--source-dir", str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)
        tap = Path(self.env["BREW_ROOT"]) / "Library/Taps/unclehq/homebrew-github-install"
        formula = (tap / "Formula/uncle.rb").read_text()
        archive = tap / "archives/uncle.tar.gz"
        self.assertTrue(archive.is_file())
        self.assertIn(hashlib.sha256(archive.read_bytes()).hexdigest(), formula)
        self.assertIn("brew install unclehq/github-install/uncle", self.log.read_text())
        self.assertIn("brew test unclehq/github-install/uncle", self.log.read_text())

    def test_formula_is_hash_pinned_and_rejects_interpolation(self):
        output = self.work / "formula"
        output.mkdir()
        archive = self.work / "archive"
        archive.write_bytes(b"actual downloaded bytes")
        url = "https://github.com/unclehq/uncle/archive/" + "a" * 40 + ".tar.gz"
        package.build_formula(ROOT, output, archive, url, "0.1.0")
        formula = (output / "uncle.rb").read_text()
        self.assertIn(hashlib.sha256(archive.read_bytes()).hexdigest(), formula)
        self.assertIn(url, formula)
        self.assertNotIn('  head ', formula)
        with self.assertRaises(ValueError):
            package.build_formula(ROOT, output, archive, url + '#{system("bad")}', "0.1.0")

    def test_symlink_payload_is_rejected(self):
        source = self.work / "source"
        source.mkdir()
        (source / "uncle").symlink_to(ROOT / "uncle")
        with self.assertRaises(ValueError):
            package.copy_payload(source, self.work / "target")

    @unittest.skipUnless(shutil.which("dpkg-deb"), "dpkg-deb runs in Linux CI")
    def test_real_debian_package(self):
        output = self.work / "packages"
        output.mkdir()
        package.build_deb(ROOT, output, "0.1.0")
        deb = output / "uncle_0.1.0_all.deb"
        metadata = subprocess.check_output(["dpkg-deb", "--field", str(deb)], text=True)
        self.assertIn("Architecture: all", metadata)
        self.assertIn("Depends: bash", metadata)
        target = self.work / "installed"
        subprocess.run(["dpkg-deb", "--extract", str(deb), str(target)], check=True)
        result = subprocess.run([str(target / "usr/bin/uncle"), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: uncle", result.stdout)


if __name__ == "__main__":
    unittest.main()

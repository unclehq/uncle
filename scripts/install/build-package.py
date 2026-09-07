#!/usr/bin/env python3
"""Build installable payloads from a checkout; never include project/agent state."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PAYLOAD = (
    "uncle", "uncle_tui.py", "scripts", "prompts", "lib", "OUTPUT_RULES.md",
    "README.md", "uncle.png", "LICENSE", "VERSION", "packaging", "install.sh", "install.ps1",
    "Formula",
)


def package_version(source):
    base = (source / "VERSION").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", base):
        raise ValueError("VERSION must contain MAJOR.MINOR.PATCH")
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "--short=12", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        timestamp = subprocess.check_output(
            ["git", "-C", str(source), "show", "-s", "--format=%ct", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        date = datetime.fromtimestamp(int(timestamp), timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"{base}+git{date}.{commit}"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return f"{base}+local{datetime.now(timezone.utc):%Y%m%d%H%M%S}"


def copy_payload(source, target):
    target.mkdir(parents=True)
    target.chmod(0o755)
    for name in PAYLOAD:
        src = source / name
        if not src.exists():
            raise ValueError(f"Missing payload: {name}")
        paths = [src, *src.rglob("*")] if src.is_dir() else [src]
        for path in paths:
            relative = path.relative_to(source)
            if "__pycache__" in relative.parts or path.suffix == ".pyc":
                continue
            if path.is_symlink():
                raise ValueError(f"Symlink in package input: {relative}")
            dest = target / relative
            if path.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                dest.chmod(0o755)
            elif path.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
                executable = path.suffix == ".sh" or path.name in ("uncle", "python3")
                dest.chmod(0o755 if executable else 0o644)
            else:
                raise ValueError(f"Unsupported package input: {relative}")


def build_deb(source, output, version):
    if not shutil.which("dpkg-deb"):
        raise ValueError("Install dpkg-dev to build Debian packages")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "package"
        copy_payload(source, root / "usr/lib/uncle")
        (root / "usr/bin").mkdir(parents=True)
        (root / "usr/bin/uncle").symlink_to("../lib/uncle/uncle")
        metadata = root / "DEBIAN"
        metadata.mkdir()
        control = (source / "packaging/debian/control").read_text().replace("@VERSION@", version)
        (metadata / "control").write_text(control)
        doc = root / "usr/share/doc/uncle"
        doc.mkdir(parents=True)
        shutil.copyfile(source / "LICENSE", doc / "copyright")
        # Package permissions must not inherit a developer's restrictive umask.
        for directory in (root, *root.rglob("*")):
            if directory.is_dir():
                directory.chmod(0o755)
        (metadata / "control").chmod(0o644)
        (doc / "copyright").chmod(0o644)
        subprocess.run([
            "dpkg-deb", "--root-owner-group", "--build", str(root),
            str(output / f"uncle_{version}_all.deb"),
        ], check=True)


def build_archive(source, output):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "uncle"
        copy_payload(source, root)
        with tarfile.open(output / "uncle.tar.gz", "w:gz") as archive:
            archive.add(root, arcname="uncle")


def build_formula(source, output, archive, url, version):
    if not archive or not url or not (url.startswith("https://github.com/") or url.startswith("file://")):
        raise ValueError("Formula requires an archive and a GitHub HTTPS or local file URL")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if url.startswith("file://"):
        url = archive.resolve().as_uri()
    # JSON quoting is also a valid Ruby string literal for these validated URLs.
    # Exclude Ruby interpolation rather than accepting executable URL contents.
    if any(char in url for char in ('#', '\n', '\r')):
        raise ValueError("Invalid archive URL")
    template = (source / "Formula/uncle.rb").read_text()
    head = '  head "https://github.com/unclehq/uncle.git", branch: "main"'
    if template.count(head) != 1:
        raise ValueError("Formula template must contain one source declaration")
    stable = f"  url {json.dumps(url)}\n  sha256 \"{digest}\"\n  version {json.dumps(version)}"
    (output / "uncle.rb").write_text(template.replace(head, stable))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("deb", "archive", "formula"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--url")
    parser.add_argument("--version")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output == source or source in output.parents:
        parser.error("Build output must be outside the source checkout")
    output.mkdir(parents=True, exist_ok=True)
    try:
        version = args.version or package_version(source)
        if not re.fullmatch(r"[0-9][A-Za-z0-9.+~-]*", version):
            raise ValueError("Invalid package version")
        if args.kind == "deb":
            build_deb(source, output, version)
        elif args.kind == "archive":
            build_archive(source, output)
        else:
            build_formula(source, output, args.archive, args.url, version)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Package build failed: {exc}\n")


if __name__ == "__main__":
    main()

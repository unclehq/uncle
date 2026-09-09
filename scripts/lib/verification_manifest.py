"""Produce the same complete SHA-256 inventory as the portable shell backend."""
import hashlib
import os
from pathlib import Path
import sys


def manifest(scopes_file):
    entries = set()
    for scope in Path(scopes_file).read_text(encoding="utf-8").splitlines():
        directory_only = scope.endswith("/")
        if directory_only:
            scope = scope[:-1]  # One optional directory suffix, not arbitrary cleanup.
        parts = scope.split("/")
        if (not scope or scope.startswith(("/", "-"))
                or any(p in ("", ".", "..") for p in parts)
                or any(c in scope for c in "\t\r\n")
                or parts[0] in (".git", ".uncle")):
            raise ValueError(f"Invalid protected verification path: {scope}")
        prefix = Path()
        for part in parts:
            prefix /= part
            if prefix.is_symlink():
                raise ValueError(f"Protected verification path uses a symlink: {prefix}")
        path = Path(scope)
        if path.is_dir():
            entries.add("DIRECTORY\t" + scope)

            def fail(error):
                raise error

            for parent, dirs, files in os.walk(scope, onerror=fail):
                for name in dirs + files:
                    child = Path(parent) / name
                    if child.is_symlink():
                        raise ValueError(f"Protected verification directory contains symlinks: {child}")
                    if any(c in str(child) for c in "\t\r\n"):
                        raise ValueError(f"Unsupported protected filename: {child!s}")
                for name in files:
                    child = Path(parent) / name
                    if child.is_file() and not name.endswith(".pyc") and "__pycache__" not in child.parts:
                        entries.add(child.as_posix())
        elif path.is_file() and not directory_only:
            entries.add(scope)
        else:
            raise ValueError(f"Missing protected verification path: {scope}")
    result = []
    for entry in sorted(entries, key=os.fsencode):
        if entry.startswith("DIRECTORY\t"):
            result.append(entry)
        else:
            digest = hashlib.sha256()
            with open(entry, "rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            result.append(digest.hexdigest() + "\t" + entry)
    return "\n".join(result) + ("\n" if result else "")


if __name__ == "__main__":
    try:
        sys.stdout.buffer.write(manifest(sys.argv[1]).encode("utf-8"))
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
"""Hand current driver evidence to reviewers without relying on hidden-file globbing."""

import hashlib
import re
import sys
from pathlib import Path


def focused_evidence(project, state):
    """Bounded navigation hints from authoritative files, never inferred PASSes."""
    lines = ['\n## Focused evidence index',
             'Snippets are navigation hints, not coverage conclusions. Inspect surrounding logic.',
             'At most 12 KB of indexed evidence; omitted content remains available at the cited path.']
    remaining = 12000

    def add(label, text):
        nonlocal remaining
        entry = label + ': ' + text[:400]
        if len(entry.encode('utf-8')) + 1 > remaining:
            return False
        lines.append(entry)
        remaining -= len(entry.encode('utf-8')) + 1
        return True

    def read(path):
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(project) or path.is_symlink():
                return ''
            with path.open('rb') as stream:
                raw = stream.read(262145)
            if len(raw) > 262144:
                add(str(path), '[Input excerpt limited to first 256 KB]')
            return raw[:262144].decode('utf-8', errors='replace')
        except OSError:
            add(str(path), '[Missing or unreadable; no evidence inferred]')
            return ''

    for name in ('REQUIREMENTS.md', 'UPDATED_PROJECT_PLAN.md'):
        for number, line in enumerate(read(project / name).splitlines(), 1):
            if re.search(r'\b(?:AC|REQ|FR|MC)-[0-9]+\b', line):
                if not add(f'{name}:{number}', line):
                    break
    # The driver's explicit inventory avoids recursive project discovery.
    seen = set()
    for row in read(state / 'verification.manifest').splitlines():
        digest, sep, rel = row.partition('\t')
        if not sep or not re.fullmatch(r'[a-f0-9]{64}', digest) or rel in seen:
            continue
        seen.add(rel)
        path = project / rel
        if path.suffix not in ('.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.sh', '.go', '.rs'):
            continue
        if not add(rel, 'protected SHA-256 ' + digest):
            break
        for number, line in enumerate(read(path).splitlines(), 1):
            if re.search(r'\b(?:assert\w*|expect|test|it|describe|fail|check_\w+)\s*\(', line):
                if not add(f'{rel}:{number}', line):
                    break
    for number, line in enumerate(read(state / 'logs/green-check.log').splitlines(), 1):
        if re.search(r'(?i)\b(?:fail(?:ed|ure)?|error|not ok|timeout)\b', line):
            if not add(f'{state}/logs/green-check.log:{number}', line):
                break
    if remaining < 500:
        lines.append('[Index budget reached; read remaining evidence directly.]')
    return '\n'.join(lines)


def render(project: Path, state: Path) -> str:
    project, state = project.resolve(), state.resolve()
    lines = [
        "\n## Driver-supplied test review evidence",
        f"Project root: {project}",
        "This inventory was read directly from disk for this review invocation.",
        "Read listed paths directly; Glob/search may omit hidden .uncle files.",
        "Compare current driver results with earlier reports before carrying a",
        "blocker forward. A passing command resolves only the failure it covers;",
        "it does not establish unrelated coverage, oracle integrity, or approval.",
        "An omitted/truncated excerpt is not evidence that the file is absent.",
    ]
    files = [
        (state / "green-check.md", True),
        (state / "green-check.tsv", True),
        (state / "logs/green-check.log", False),
        (state / "TEST_CHANGES.diff", False),
        (state / "previous-test-review.md", False),
        (state / "verification.paths", False),
        (state / "verification.manifest", False),
        (project / "VERIFICATION_REPORT.md", False),
        (project / "DEFECTS.md", False),
    ]
    for path, inline in files:
        lines.append(f"\n### {path}")
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            lines.append("MISSING at prompt preparation; do not infer a pass.")
            continue
        except OSError as exc:
            lines.append(f"UNREADABLE: {exc}; do not infer a pass.")
            continue
        lines.append(f"{len(data)} bytes; SHA-256 {hashlib.sha256(data).hexdigest()}")
        if not data:
            lines.append("EMPTY; does not establish verification.")
        elif inline:
            lines.append(data[:16384].decode("utf-8", errors="replace"))
            if len(data) > 16384:
                lines.append("[Excerpt truncated at 16384 bytes; read the remaining file directly.]")
        else:
            lines.append("Read relevant sections directly when needed; contents not preloaded.")
    lines.append(focused_evidence(project, state))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    print(render(Path(sys.argv[1]), Path(sys.argv[2])), end="")

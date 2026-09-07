#!/usr/bin/env python3
"""Hand current driver evidence to reviewers without relying on hidden-file globbing."""

import hashlib
import sys
from pathlib import Path


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
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(render(Path(sys.argv[1]), Path(sys.argv[2])), end="")

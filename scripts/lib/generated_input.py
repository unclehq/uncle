"""Where REQUIREMENTS.md / CHANGE_REQUEST.md actually live.

Both are operator inputs: a human may drop either at the project root by
hand, and that copy is authoritative. But uncle also generates them itself
(the TUI's chat-derived brief, from-issue seeding), and a generated file
belongs beside the rest of uncle's own output, under .uncle/docs, not at the
project's own root.

The rule: a root copy always wins if present; otherwise the generated copy
lives at .uncle/docs/<name>.
"""
from pathlib import Path


def generated_input_path(name, root='.'):
    root = Path(root)
    if (root / name).exists():
        return root / name
    return root / '.uncle' / 'docs' / name


def generated_input_write_path(name, root='.'):
    """Where a freshly-generated copy should be written -- always
    .uncle/docs, regardless of whether a root copy exists (a generator that
    finds one already there should not be writing at all)."""
    root = Path(root)
    directory = root / '.uncle' / 'docs'
    directory.mkdir(parents=True, exist_ok=True)
    return directory / name

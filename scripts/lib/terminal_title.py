#!/usr/bin/env python3
"""Single source of truth for the Uncle terminal tab title.

Pure builder (sanitize / project_name / build_title), a guard (enabled) and
writers (begin / retitle / end).  CLI: terminal_title.py begin|retitle|end [issue]
The CLI is stateless; the project root comes only from UNCLE_PROJECT_ROOT or cwd.
"""
import os
import re
import sys
import unicodedata

MAX_PROJECT = 60
PUSH = '\033[22;2t'
POP = '\033[23;2t'
_DROP = {'Cc', 'Cf', 'Zl', 'Zp'}
_pushed = False


def sanitize(text):
    """Drop Cc/Cf/Zl/Zp characters, then trim whitespace."""
    kept = ''.join(c for c in str(text) if unicodedata.category(c) not in _DROP)
    return kept.strip()


def project_name(root=None):
    """Basename of an absolute root (UNCLE_PROJECT_ROOT), else of cwd; sanitized."""
    if root is None:
        root = os.environ.get('UNCLE_PROJECT_ROOT', '')
    if not root or not os.path.isabs(root):
        try:
            root = os.getcwd()
        except OSError:
            root = ''
    stripped = root.rstrip('/')
    return sanitize(os.path.basename(stripped))


def build_title(project, issue=None):
    """`<project> · uncle` or `<project> · uncle issue #N`; bare `uncle` if no project."""
    name = sanitize(project or '')[:MAX_PROJECT]
    if not name:
        return 'uncle'
    issue = '' if issue is None else str(issue)
    if re.fullmatch(r'[0-9]+', issue):
        return '%s · uncle issue #%s' % (name, issue)
    return '%s · uncle' % name


def enabled():
    if os.environ.get('UNCLE_TERMINAL_TITLE') == '0':
        return False
    term = os.environ.get('TERM', '')
    if not term or term == 'dumb':
        return False
    try:
        return bool(sys.stdout.isatty() and sys.stderr.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def osc(title):
    return '\033]2;%s\007' % title


def _title_seq(issue):
    return '\033]2;%s\007' % build_title(project_name(), issue)


def _write(stream, data):
    try:
        stream.write(data)
        stream.flush()
        return True
    except Exception:
        return False


def begin(issue=None, stream=None):
    """Push the title stack (once per process) and set the title. True if pushed."""
    global _pushed
    if _pushed or not enabled():
        return False
    stream = stream or sys.stdout
    if _write(stream, PUSH + _title_seq(issue)):
        _pushed = True
    return _pushed


def retitle(issue=None, stream=None):
    if not enabled():
        return False
    return _write(stream or sys.stdout, _title_seq(issue))


def end(stream=None, force=False):
    """Write the project-only title then pop; only if this process pushed (or force)."""
    global _pushed
    if not (_pushed or force):
        return False
    _pushed = False
    if not enabled():
        return False
    return _write(stream or sys.stdout, _title_seq(None) + POP)


def main(argv):
    try:
        cmd = argv[1] if len(argv) > 1 else ''
        issue = argv[2] if len(argv) > 2 else None
        if cmd == 'begin':
            begin(issue)
        elif cmd == 'retitle':
            retitle(issue)
        elif cmd == 'end':
            end(force=True)
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

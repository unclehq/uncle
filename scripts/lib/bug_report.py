#!/usr/bin/env python3
"""Build, scrub, save and (on explicit confirmation) publish a bug report about a diagnosed Uncle tool bug.

    bug_report.py STATE_DIR PROJECT_ROOT UNCLE_ROOT [STAGE]    # builds and saves a draft, prints the preview

Only allow-listed fields are included. Nothing is published without confirm=True.
"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

REPO = 'unclehq/uncle'
UNAVAILABLE = 'unavailable'
TITLE_MAX = 80
EXCERPT_LINES = 20
EXCERPT_LINE_MAX = 300
GH_TIMEOUT = 30
FIELD = re.compile(r'[A-Za-z0-9._:/-]{1,64}')
DRAFT = re.compile(r'bug-report-(\d+)\.md$')

TOKENS = [
    (re.compile(r'github_pat_[A-Za-z0-9_]+'), '[REDACTED]'),
    (re.compile(r'ghp_[A-Za-z0-9]+'), '[REDACTED]'),
    (re.compile(r'sk-[A-Za-z0-9_-]+'), '[REDACTED]'),
    (re.compile(r'Bearer\s+[A-Za-z0-9._~+/=-]+'), '[REDACTED]'),
    (re.compile(r'AKIA[0-9A-Z]{16}'), '[REDACTED]'),
    (re.compile(r'([A-Za-z][A-Za-z0-9+.-]*://)[^\s/@:]+:[^\s/@]*@'), r'\1[REDACTED]@'),
    (re.compile(r'(?im)^((?:Set-)?Cookie:[ \t]*).*$'), r'\1[REDACTED]'),
]
_ABS = re.compile(r'(?<![\w.<>~\]-])/(?:[A-Za-z0-9._-]+/?)+')
_RESIDUAL_TOKENS = [re.compile(p.pattern) for p, _ in TOKENS[:5]]


def eligible(classification):
    return isinstance(classification, str) and classification.strip().lower() == 'tool bug'


def _roots(roots):
    found = [str(r) for r in roots if r]
    home = os.path.expanduser('~')
    if home and home != '~':
        found.append(home)
    return sorted({r.rstrip('/') for r in found if r.rstrip('/')}, key=len, reverse=True)


def _chat_sanitize(text):
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from chat import sanitize
        return sanitize(text)
    except Exception:
        return ''.join(c for c in text if c in '\n\t' or (ord(c) >= 32 and ord(c) != 127))
    finally:
        if sys.path and sys.path[0] == str(Path(__file__).parent):
            sys.path.pop(0)


def scrub(text, roots=()):
    text = str(text)
    names = {}
    for root in _roots(roots):
        names[root] = None
    uncle_like = [str(r).rstrip('/') for r in roots]
    for root in _roots(roots):
        label = '~' if root == os.path.expanduser('~').rstrip('/') and root not in uncle_like else None
        names[root] = label
    mapping = {}
    for index, r in enumerate(roots):
        if r:
            mapping[str(r).rstrip('/')] = ('<project>', '<uncle>')[index] if index < 2 else '~'
    home = os.path.expanduser('~').rstrip('/')
    if home:
        mapping.setdefault(home, '~')
    for root in sorted(mapping, key=len, reverse=True):
        if root:
            text = text.replace(root, mapping[root])
    for pattern, repl in TOKENS:
        text = pattern.sub(repl, text)
    return _chat_sanitize(text)


def residual_check(text, roots=()):
    """Matches that survive scrub: absolute paths and token patterns. Relative .uncle/workflow references are fine."""
    found = []
    for root in _roots(roots):
        if root in text:
            found.append(root)
    for match in _ABS.finditer(text):
        found.append(match.group(0))
    for pattern in _RESIDUAL_TOKENS:
        found.extend(m.group(0) for m in pattern.finditer(text))
    return found


def _valid(value):
    return value if isinstance(value, (str, int)) and not isinstance(value, bool) and FIELD.fullmatch(str(value)) else None


def _field(value):
    return str(_valid(value)) if _valid(value) is not None else UNAVAILABLE


def _role(kind):
    kind = str(kind or '').lower()
    if kind in ('review', 'verification', 'audit', 'reviewer'):
        return 'reviewer'
    if kind in ('agent', 'worker', 'implementation', 'implement', 'plan', 'planner'):
        return 'worker'
    return 'agent'


def _records(state_dir):
    try:
        saved = json.loads((Path(state_dir) / 'session-totals.json').read_text(encoding='utf-8'))
        rows = saved.get('records')
        return [r for r in rows if isinstance(r, dict) and not r.get('speculative')] if isinstance(rows, list) else []
    except (OSError, ValueError, AttributeError):
        return []


def _failed(row):
    return row.get('process_exit') not in (0, None) or row.get('reported_error') is True


def _excerpt(state_dir, row):
    try:
        log = Path(row.get('log') or '')
        if not log.is_absolute():
            log = Path(state_dir) / log
        if str(log) == '/dev/null' or not log.is_file():
            return None
        lines = log.read_text(encoding='utf-8', errors='replace').splitlines()
    except (OSError, ValueError):
        return None
    lines = [l for l in lines if l.strip()]
    return lines[-EXCERPT_LINES:] or None


def _install_type(uncle_root):
    root = str(uncle_root or '')
    if 'Cellar' in root or 'homebrew' in root.lower():
        return 'homebrew'
    if uncle_root and (Path(uncle_root) / '.git').exists():
        return 'git'
    return 'unknown'


def _version(uncle_root):
    try:
        return _field((Path(uncle_root) / 'VERSION').read_text(encoding='utf-8').strip().splitlines()[0])
    except (OSError, IndexError, TypeError):
        return UNAVAILABLE


def _title(text, roots):
    title = scrub(text, roots).replace('\n', ' ').replace('\r', ' ').replace("'", '').replace('"', '')
    return title[:TITLE_MAX].strip()


def build_report(state_dir, project_root, uncle_root, stage=None):
    roots = (project_root, uncle_root)
    if stage is not None and _valid(stage) is None:
        stage = None
    rows = _records(state_dir)
    failed = [r for r in rows if _failed(r)]
    if stage is not None:
        named = [r for r in failed if r.get('stage') == stage]
        failed = named or failed
    row = max(failed, key=lambda r: r.get('ended_at') or 0) if failed else None
    if row is None:
        stage_name = attempts = role = exit_status = runner = model = effort = UNAVAILABLE
    else:
        stage_name = _field(row.get('stage'))
        count = sum(1 for r in rows if r.get('stage') == row.get('stage'))
        attempts = str(count) if count else UNAVAILABLE
        role = _role(row.get('kind'))
        exit_status = _field(row.get('process_exit'))
        runner, model, effort = (_field(row.get(k)) for k in ('runner', 'model', 'effort'))
    lines = _excerpt(state_dir, row) if row else None
    if lines:
        excerpt = '\n'.join(scrub(l, roots)[:EXCERPT_LINE_MAX] for l in lines)
    else:
        excerpt = UNAVAILABLE
    validation = UNAVAILABLE
    if row and isinstance(row.get('validation_error'), str) and row['validation_error'].strip():
        validation = scrub(row['validation_error'], roots)[:EXCERPT_LINE_MAX]
    fields = {'stage': stage_name, 'attempt': attempts, 'role': role, 'exit status': exit_status, 'runner': runner,
              'model': model, 'effort': effort, 'artifact validation error': validation,
              'uncle version': _version(uncle_root), 'install type': _install_type(uncle_root)}
    title = _title(f'Uncle tool bug in stage {stage_name}', roots)
    body = ['## Uncle tool bug report', '']
    body += [f'- {k}: {v}' for k, v in fields.items()]
    body += ['', '## Error excerpt', '', '```', excerpt, '```', '']
    body = '\n'.join(body)
    residual = residual_check(title + '\n' + body, roots)
    return {'title': title, 'body': body, 'fields': fields, 'blocked': bool(residual),
            'reason': ('residual absolute path or token pattern after scrub: ' + ', '.join(sorted(set(residual))[:5]))
            if residual else ''}


def save_draft(state_dir, report):
    """Exclusive, no-follow create of the lowest unused bug-report-N.md; never overwrites."""
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True)
    used = set()
    for p in state.glob('bug-report-*.md'):
        m = DRAFT.fullmatch(p.name)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while True:
        while n in used:
            n += 1
        path = state / f'bug-report-{n}.md'
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o644)
        except FileExistsError:
            used.add(n)
            continue
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            out.write(report['body'])
        return path


def fallback_command(title, draft_relative):
    return (f'gh auth login, then: gh issue create --repo {REPO} --title {shlex.quote(title)} '
            f'--body-file {shlex.quote(str(draft_relative))}')


def publish(draft_path, title, confirm=False, runner=subprocess.run, relative=None):
    """Send the saved draft bytes. Returns {'ok', 'url', 'message', 'may_exist'}."""
    if confirm is not True:
        return {'ok': False, 'url': None, 'message': 'Not confirmed; nothing published.', 'may_exist': False}
    shown = relative or draft_path
    fail = {'ok': False, 'url': None, 'may_exist': False,
            'message': f'Saved {shown}. Run: ' + fallback_command(title, shown)}
    env = dict(os.environ, GH_PROMPT_DISABLED='1')
    common = dict(stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=GH_TIMEOUT, env=env)
    try:
        auth = runner(['gh', 'auth', 'status'], **common)
    except (OSError, subprocess.SubprocessError):
        return fail
    if auth.returncode != 0:
        return fail
    try:
        made = runner(['gh', 'issue', 'create', '--repo', REPO, '--title', title, '--body-file', str(draft_path)], **common)
    except (OSError, subprocess.SubprocessError):
        return dict(fail, may_exist=True, message=f'Saved {shown}. The issue may already exist; check '
                    f'github.com/{REPO}/issues before filing again.')
    url = None
    if made.returncode == 0:
        for line in (made.stdout or '').splitlines():
            if line.strip().startswith('https://'):
                url = line.strip()
    if url:
        return {'ok': True, 'url': url, 'may_exist': False, 'message': f'Issue created: {url} (draft kept at {shown})'}
    return dict(fail, may_exist=True, message=f'Saved {shown}. The issue may already exist; check '
                f'github.com/{REPO}/issues before filing again.')


def main(argv):
    if len(argv) < 4:
        print('usage: bug_report.py STATE_DIR PROJECT_ROOT UNCLE_ROOT [STAGE]', file=sys.stderr)
        return 2
    report = build_report(argv[1], argv[2], argv[3], argv[4] if len(argv) > 4 else None)
    path = save_draft(argv[1], report)
    print(report['title'] + '\n\n' + report['body'])
    if report['blocked']:
        print('Publish refused: ' + report['reason'])
    print(f'Draft saved: {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

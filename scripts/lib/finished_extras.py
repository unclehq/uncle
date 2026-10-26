#!/usr/bin/env python3
"""Total-time and PR lines printed after `Finished build:`. Never exits nonzero."""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

REASONS = {
    'handoff-disabled': 'none (handoff disabled)',
    'no-base-commit': 'none (no base commit)',
    'publication-pending': 'not created (publication pending)',
    'not-published': 'none (not published)',
    'not-applicable': 'none (not applicable to new-application builds)',
}
STAMP = 'run-started-at'
_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f\u2028\u2029]')


def clean(value):
    return _CONTROL.sub('', str(value)).strip()


def format_duration(seconds):
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f'{hours}h {minutes}m {secs}s'
    if minutes:
        return f'{minutes}m {secs}s'
    return f'{secs}s'


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def start(state):
    """Write the start stamp exclusively; an existing stamp is never overwritten."""
    try:
        Path(state).mkdir(parents=True, exist_ok=True)
        fd = os.open(str(Path(state) / STAMP), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except OSError:
        return
    with os.fdopen(fd, 'w') as handle:
        handle.write(now().strftime('%Y-%m-%dT%H:%M:%SZ') + '\n')


def reset(state):
    try:
        (Path(state) / STAMP).unlink()
    except OSError:
        pass


def read_start(state):
    try:
        text = (Path(state) / STAMP).read_text().strip()
        if not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|\+00:00)', text):
            return None
        return datetime.datetime.fromisoformat(text.replace('Z', '+00:00'))
    except (OSError, ValueError):
        return None


def parenthetical(state, total):
    try:
        saved = json.loads((Path(state) / 'session-totals.json').read_text(encoding='utf-8'))
        rows = [r for r in saved['records'] if isinstance(r, dict)]
        busy = sum(float(r['elapsed_seconds']) for r in rows
                   if isinstance(r.get('elapsed_seconds'), (int, float)))
    except (OSError, ValueError, KeyError, TypeError):
        return ''
    waiting = max(0, total - busy)
    return f' (stages {format_duration(busy)}, approx. waiting at gates {format_duration(waiting)})'


def total_line(state, unattended):
    began = read_start(state)
    if began is None:
        return 'Total time: unknown'
    total = max(0, (now() - began).total_seconds())
    extra = '' if unattended else parenthetical(state, total)
    return f'Total time: {format_duration(total)}{extra}'


def pr_line(state, kind, reason, stopped):
    if kind == 'new':
        return None if stopped else 'PR: none (not applicable to new-application builds)'
    path = Path(state) / 'pr' / 'journal.json'
    try:
        journal = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        journal = None
    except (OSError, ValueError):
        return 'PR: none (journal unreadable)'
    if isinstance(journal, dict) and journal.get('phase') == 'created' and journal.get('url'):
        number = clean(journal.get('number', ''))
        mark = ' [draft]' if journal.get('draft') is True else ''
        return f'PR: {clean(journal["url"])} (#{number}){mark}'
    if stopped:
        return None
    return 'PR: ' + REASONS.get(reason, REASONS['not-published'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('start', 'reset', 'print'))
    parser.add_argument('--state', default=os.environ.get('STATE_DIR') or '.uncle/workflow')
    parser.add_argument('--kind', choices=('new', 'change'), default='change')
    parser.add_argument('--reason', default='not-published')
    parser.add_argument('--unattended', action='store_true')
    parser.add_argument('--stopped', action='store_true')
    try:
        args = parser.parse_args()
        if args.command == 'start':
            start(args.state)
        elif args.command == 'reset':
            reset(args.state)
        else:
            print(total_line(args.state, args.unattended))
            line = pr_line(args.state, args.kind, args.reason, args.stopped)
            if line:
                print(line)
    except SystemExit:
        pass
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Recover a completed Markdown investigation returned in an agent event log.

Investigation prompts ask an agent to write a private handoff file.  Some
OpenCode models instead return that complete document in their final event.
This utility recovers only a fenced, structurally recognizable Markdown
document; it never manufactures prose from a partial status message.
"""
import argparse
import json
import re
import sys
from pathlib import Path

FENCE = re.compile(r'^\s*```(?:markdown|md)?\s*\n(.*?)\n```\s*$', re.S | re.I)


def texts(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ('text', 'result', 'content') and isinstance(child, str):
                yield child
            else:
                yield from texts(child)
    elif isinstance(value, list):
        for child in value:
            yield from texts(child)


def document(log, heading):
    candidates = []
    for line in Path(log).read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        # A result event is the runner's final answer, so it wins over
        # partial assistant/status messages from the same turn.
        priority = 1 if event.get('type') == 'result' else 0
        for text in texts(event):
            match = FENCE.match(text)
            if match:
                candidates.append((priority, match.group(1).strip()))
    for _, text in reversed(sorted(candidates, key=lambda item: item[0])):
        if heading in text:
            return text + '\n'
    raise ValueError('no complete fenced Markdown investigation with heading %r in final runner output' % heading)


def recover(log, target, heading):
    text = document(log, heading)
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('log')
    parser.add_argument('target')
    parser.add_argument('--heading', required=True)
    args = parser.parse_args(argv)
    try:
        recover(args.log, args.target, args.heading)
    except (OSError, ValueError) as error:
        print('investigation recovery: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

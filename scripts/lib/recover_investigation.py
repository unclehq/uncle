#!/usr/bin/env python3
"""Recover a completed Markdown investigation returned in an agent event log.

Investigation prompts ask an agent to write a private handoff file.  Some
OpenCode models instead return that complete document in their final event.
This utility recovers only a structurally recognizable Markdown document
(fenced, or a final answer that is itself the document, opening with a heading);
it never manufactures prose from a partial status message.
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    from runner_events import texts
except ModuleNotFoundError:
    # Direct-file importlib callers need not put scripts/lib on sys.path.
    import importlib.util as _importlib_util
    _spec = _importlib_util.spec_from_file_location('runner_events', Path(__file__).with_name('runner_events.py'))
    _runner_events = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_runner_events)
    texts = _runner_events.texts

FENCE = re.compile(r'^\s*```(?:markdown|md)?\s*\n(.*?)\n```\s*$', re.S | re.I)


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
            elif priority and text.lstrip().startswith('#'):
                # The model returned the document itself as its final answer,
                # unfenced (seen live: a complete requirements investigation
                # in one 13 s turn, no Write, no fence).  Failing it cost a
                # whole rerun of the stage for a formatting choice.  Only a
                # final answer that opens with a heading qualifies, so chat
                # such as "I wrote the document." still never does.
                candidates.append((0, text.strip()))
    for _, text in reversed(sorted(candidates, key=lambda item: item[0])):
        if heading in text:
            return text + '\n'
    raise ValueError('no complete Markdown investigation with heading %r in final runner output' % heading)


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

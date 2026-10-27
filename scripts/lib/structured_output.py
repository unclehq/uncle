#!/usr/bin/env python3
"""The schema-checked object a Claude stage returned, taken from its event log.

`claude -p --json-schema SCHEMA` makes the model deliver through a StructuredOutput tool whose input is
validated against SCHEMA, and reports the validated object as `structured_output` on the final result event.
Nothing is parsed out of chat text and nothing depends on the model calling Write.

    structured_output.py extract EVENT_LOG OUTPUT.json     exit 1 when the log holds no object
"""
import json
import sys
from pathlib import Path


def extract(log):
    """The last schema-validated object in the log, or None."""
    found = None
    try:
        lines = Path(log).read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'result' and isinstance(event.get('structured_output'), dict):
            found = event['structured_output']
        elif event.get('type') == 'assistant' and found is None:
            for part in (event.get('message') or {}).get('content') or []:
                if (isinstance(part, dict) and part.get('type') == 'tool_use' and part.get('name') == 'StructuredOutput'
                        and isinstance(part.get('input'), dict)):
                    found = part['input']
    return found


def main(argv):
    if len(argv) != 3 or argv[0] != 'extract':
        raise SystemExit(__doc__)
    value = extract(argv[1])
    if value is None:
        print('structured output: the stage returned no schema-checked object', file=sys.stderr)
        return 1
    Path(argv[2]).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

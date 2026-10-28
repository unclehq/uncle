#!/usr/bin/env python3
"""The schema-checked object a Claude stage returned, taken from its event log.

`claude -p --json-schema SCHEMA` makes the model deliver through a StructuredOutput tool whose input is
validated against SCHEMA, and reports the validated object as `structured_output` on the final result event.
Nothing is parsed out of chat text and nothing depends on the model calling Write.

    structured_output.py extract EVENT_LOG OUTPUT.json     exit 1 when the log holds no object
    structured_output.py recover EVENT_LOG OUTPUT.json     the packet a worker printed in chat instead of writing
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


def reply_texts(log):
    """What the worker said, newest first: the result event's text, then each assistant text."""
    result, texts = '', []
    try:
        lines = Path(log).read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'result' and isinstance(event.get('result'), str):
            result = event['result']
        elif event.get('type') == 'assistant':
            for part in (event.get('message') or {}).get('content') or []:
                if isinstance(part, dict) and part.get('type') == 'text' and part.get('text'):
                    texts.append(part['text'])
    return ([result] if result else []) + texts[::-1]


def recover(log):
    """The newest JSON object in the worker's replies that is an uncle artifact packet, or None.

    A local model often prints its packet instead of calling Write, and may follow it with a prose summary,
    so every reply is searched, newest first.  Only an object carrying the artifact schema and a kind is
    taken; the consumer still validates its content."""
    decoder = json.JSONDecoder()
    for text in reply_texts(log):
        found, index = None, text.find('{')
        while index != -1:
            try:
                value, end = decoder.raw_decode(text, index)
            except ValueError:
                index = text.find('{', index + 1)
                continue
            if isinstance(value, dict) and value.get('schema') == 'uncle.artifact/v1' and value.get('kind'):
                found = value
            index = text.find('{', end)
        if found is not None:
            return found
    return None


def main(argv):
    if len(argv) != 3 or argv[0] not in ('extract', 'recover'):
        raise SystemExit(__doc__)
    value = extract(argv[1]) if argv[0] == 'extract' else recover(argv[1])
    if value is None:
        print('structured output: the stage returned no %s object' % ('schema-checked' if argv[0] == 'extract' else 'packet in chat'), file=sys.stderr)
        return 1
    Path(argv[2]).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Read one field out of a canonical plan JSON. These were inline `python3 -c` and heredoc scripts in green-check.sh; as a file they can be
served by the driver's Python host (scripts/lib/pyhost.py) instead of starting an interpreter each time.

    json_field.py verification-commands FILE    the commands, right-trimmed, or exit 1 if the field is not text or the file is unreadable
    json_field.py narrative FILE                the narrative text with no trailing newline, or exit 1 if the file is unreadable
"""
import json
import sys


def main(argv):
    if len(argv) != 3 or argv[1] not in ('verification-commands', 'narrative'):
        return 2
    try:
        payload = json.load(open(argv[2], encoding='utf-8'))
        if argv[1] == 'narrative':
            sys.stdout.write(payload.get('narrative') or '')
            return 0
        commands = payload.get('verification_commands', '')
        if not isinstance(commands, str):
            raise ValueError('verification_commands is not a string')
        print(commands.rstrip())
        return 0
    except Exception:
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))

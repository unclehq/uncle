#!/usr/bin/env python3
"""Read-only prerequisite gate; never execute commands from requirements."""
import json
from pathlib import Path
import re
import shutil
import sys


def check(source, root):
    required_files = set()
    commands = []
    text = (root / source).read_text() if (root / source).is_file() else ''
    # Infer only an explicit instruction naming a local authoritative input.
    # Do not interpret arbitrary code spans (outputs, examples, URLs) as inputs.
    for line in text.splitlines():
        if re.search(r'^\s*(?:[-*]\s*)?Use\b.*\bas (?:the |an? )?(?:authoritative source|source of truth)', line, re.I):
            for name in re.findall(r'`([^`]+)`', line):
                if re.fullmatch(r'[\w ./-]+\.[\w]+', name):
                    required_files.add(name)
    manifest = root / '.uncle/prerequisites.json'
    if manifest.exists():
        data = json.loads(manifest.read_text())
        if not isinstance(data, dict) or set(data) - {'files', 'commands'}:
            raise ValueError('expected an object with files and/or commands')
        for key in ('files', 'commands'):
            values = data.get(key, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError(f'{key} must be a list of nonempty strings')
        required_files.update(data.get('files', []))
        commands = data.get('commands', [])
    missing = []
    for name in sorted(required_files):
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError(f'input must be repository-relative: {name}')
        path = root / path
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(f'missing or empty source file: {name}')
    for command in commands:
        if not re.fullmatch(r'[\w.+-]+', command):
            raise ValueError(f'command must be an executable name, without arguments: {command}')
        if shutil.which(command) is None:
            missing.append(f'missing executable on PATH: {command}')
    return missing


if __name__ == '__main__':
    try:
        missing = check(sys.argv[1], Path.cwd())
        if missing:
            print('Prerequisites blocked before planning:', file=sys.stderr)
            for item in missing:
                print(f'- {item}', file=sys.stderr)
            print('Resolve these prerequisites and rerun; no planning agent was launched.', file=sys.stderr)
            sys.exit(42)
    except (ValueError, OSError) as error:
        print(f'Invalid prerequisite input: {error}', file=sys.stderr)
        sys.exit(42)

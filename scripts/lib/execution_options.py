"""Execution settings: explicit environment overrides the project's config."""
import os
from pathlib import Path


def values():
    path = Path(os.environ.get('UNCLE_CONFIG') or '.uncle/config')
    result = {}
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            parts = line.split('#', 1)[0].split(None, 1)
            if len(parts) == 2:
                result.setdefault(parts[0], parts[1].strip())
    except FileNotFoundError:
        pass
    return result


def option(name, default):
    return os.environ.get('WORKFLOW_' + name.upper().replace('-', '_'),
                          values().get('execution.' + name, str(default))).strip()


def seconds(name, default, allow_zero=False):
    value = float(option(name, default))
    if not (0 <= value <= 86400 if allow_zero else 0 < value <= 86400):
        raise ValueError('execution.%s must be %s and at most 86400' %
                         (name, 'nonnegative' if allow_zero else 'positive'))
    return value

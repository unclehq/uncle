"""Shared evidence reads with the original empty-value and malformed-row fallbacks."""
import hashlib
import json
from pathlib import Path


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def sha256_file(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ''


def _records(state):
    try:
        saved = json.loads((Path(state) / 'session-totals.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    rows = saved.get('records') if isinstance(saved, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []

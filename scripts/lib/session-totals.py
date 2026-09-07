#!/usr/bin/env python3
"""Durable current-session metrics; historical attempt files stay untouched."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid


def update(workspace, source=None, origin=''):
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / 'session-totals.json'
    with (workspace / '.session-totals.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            saved = json.loads(path.read_text())
        except (OSError, ValueError):
            saved = None
        identity = None
        if source is not None:
            source = Path(source)
            if origin == '#':
                try:
                    origin = '#'.join((workspace / 'origin').read_text().splitlines()[0].split()[:2])
                except (OSError, IndexError):
                    origin = '#'
            identity = [source.name, hashlib.sha256(source.read_bytes()).hexdigest(), origin]
        metrics = workspace / 'metrics'
        names = sorted(p.name for p in metrics.glob('*.json'))
        if saved is None or (identity is not None and saved['identity'] != identity):
            # On first adoption include existing metrics. A new source starts at zero.
            saved = dict(schema=1, id=uuid.uuid4().hex, identity=identity,
                         baseline=names if saved else [], records=[], seen=[])
        baseline = set(saved['baseline'])
        records, seen = [], []
        for name in names:
            if name in baseline:
                continue
            try:
                row = json.loads((metrics / name).read_text())
            except (OSError, ValueError):
                continue
            seen.append(name)
            if row.get('kind') in ('agent', 'reviewer'):
                records.append(row)
        saved.update(records=records, seen=list(baseline) + seen)
        fd, temporary = tempfile.mkstemp(prefix='.session-totals-', dir=workspace)
        try:
            with os.fdopen(fd, 'w') as out:
                json.dump(saved, out)
                out.write('\n')
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return saved


if __name__ == '__main__':
    update(*sys.argv[1:])

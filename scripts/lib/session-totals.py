#!/usr/bin/env python3
"""Durable current-session metrics; historical attempt files stay untouched."""
try:
    import fcntl
except ImportError:
    fcntl = None
    import msvcrt
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid


def update(workflow, source=None, origin=''):
    workflow = Path(workflow)
    workflow.mkdir(parents=True, exist_ok=True)
    path = workflow / 'session-totals.json'
    with (workflow / '.session-totals.lock').open('a+b') as lock:
        if fcntl is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        else:
            # Windows byte-range locks need a byte and a stable file offset.
            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b'\0')
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = None
        identity = None
        if source is not None:
            source = Path(source)
            if origin == '#':
                try:
                    origin = '#'.join((workflow / 'origin').read_text(encoding="utf-8").splitlines()[0].split()[:2])
                except (OSError, IndexError):
                    origin = '#'
            identity = [source.name, hashlib.sha256(source.read_bytes()).hexdigest(), origin]
        metrics = workflow / 'metrics'
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
                row = json.loads((metrics / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            seen.append(name)
            if row.get('kind') in ('agent', 'reviewer'):
                records.append(row)
        saved.update(records=records, seen=list(baseline) + seen)
        fd, temporary = tempfile.mkstemp(prefix='.session-totals-', dir=workflow)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
                json.dump(saved, out)
                out.write('\n')
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return saved


if __name__ == '__main__':
    update(*sys.argv[1:])

"""Keep app and change state machines from resuming each other's state.

Called by the supervised driver, while its permanent driver.lock is held.
"""
from pathlib import Path
import os
import re
import sys
import uuid


def prepare(root, family, fresh=False):
    root = Path(root)
    state = root / '.uncle/workflow'
    state.mkdir(parents=True, exist_ok=True)
    marker = state / 'family'
    previous = marker.read_text().strip() if marker.exists() else ''
    token = (state / 'state').read_text().strip() if (state / 'state').exists() else ''
    token = re.sub(r'^\d+:', '', token)
    if not previous:
        if token in ('ANALYZE', 'WAIT_ANALYSIS_APPROVAL', 'PLAN'):
            previous = 'change'
        elif token in ('REQUIREMENTS', 'WAIT_REQUIREMENTS_APPROVAL', 'PROJECT_PLAN', 'PREFLIGHT'):
            previous = 'app'
    entries = [p for p in state.iterdir() if p.name not in ('driver.lock', 'driver.guard', 'lock')]
    archive = None
    if entries and (fresh or (previous and previous != family)):
        archive = root / '.uncle/workflow-history' / uuid.uuid4().hex
        archive.mkdir(parents=True)
        # Keep the locked inode and directory in place. Archive evidence and
        # approvals; never delete them or transfer their authority to a new run.
        active_timing = os.environ.get('UNCLE_TIMING_DIR')
        for path in sorted(entries, key=lambda p: p.name == 'state'):
            if path.name == 'performance' and active_timing:
                # The launcher starts profiling before the driver prepares its
                # state. Keep this launch's metadata and events together.
                active = Path(active_timing).resolve()
                for run in path.iterdir():
                    if run.resolve() != active:
                        target = archive / 'performance' / run.name
                        target.parent.mkdir(exist_ok=True)
                        run.rename(target)
            else:
                path.rename(archive / path.name)
        print('Previous workflow archived at ' + str(archive), flush=True)
    marker.write_text(family + '\n')
    return archive


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ('app', 'change'):
        raise SystemExit('Usage: workflow_family.py app|change')
    prepare(Path.cwd(), sys.argv[1], os.environ.get('UNCLE_NEW_WORKFLOW') == '1')

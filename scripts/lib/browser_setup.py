#!/usr/bin/env python3
"""Bound browser installation and retry a stalled local CLI with isolated Node 22."""
import os
from pathlib import Path
import subprocess
import sys
from process_tree import start_check, finish_check, wait_check


def run(command, timeout):
    child = start_check(command, env=os.environ.copy(), stdout=sys.stdout.buffer, stderr=subprocess.STDOUT)
    try:
        return wait_check(child, timeout, sys.stdout.buffer)
    finally:
        finish_check(child)


def install(args, root='.', runner=run):
    root = Path(root).resolve()
    cli = next((root / 'node_modules' / package / 'cli.js'
                for package in ('playwright', '@playwright/test')
                if (root / 'node_modules' / package / 'cli.js').is_file()), None)
    if cli is None:
        return runner(['npx', '--yes', 'playwright', 'install', *args], 180)
    status = runner(['node', str(cli), 'install', *args], 120)
    if status != 124:
        return status
    print('Browser installation stalled; retrying the same installed Playwright CLI with isolated Node 22.', flush=True)
    return runner(['npm', 'exec', '--yes', '--package=node@22', '--', 'node', str(cli), 'install', *args], 180)


if __name__ == '__main__':
    raise SystemExit(install(sys.argv[1:]))

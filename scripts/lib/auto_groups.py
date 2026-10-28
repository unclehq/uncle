#!/usr/bin/env python3
"""Verification groups for a plan that declares none: the pairs of commands that are plainly independent.

A plan may declare `## Parallel verification groups`; most do not, so a plan's six commands (install, browser download,
build, unit tests, browser tests, mutation runner) ran one after another (noinit: 31 s).  This finds only the pairs no plan
author would call risky, and leaves everything else in order:

  - a build and a unit-test command next to each other: the build writes its output directory, the unit tests read the sources;
  - browser tests next to the defect-injection runner: the runner works in copies of the project, each on its own port, so it does
    not touch the port or the output directory the browser tests use (noinit: the two ran one after the other, 40 s together);
  - unit tests next to browser tests: a unit suite reads source and writes no server of its own; a browser suite starts and
    tears down its own dev server on its own port. Neither touches what the other needs. This is the common shape for a
    project with no build step (a static page served directly) -- unit then e2e, back to back, with nothing between them
    that a build+unit or e2e+mutation pairing would have caught.

Setup commands (install, browser download) are not grouped: a command that runs `npx playwright` while `npm install` is still
writing node_modules can pick up a half-written binary.  Browser tests stay after the build they serve; anything the patterns
below do not recognise stays alone.

    auto_groups.py COMMANDS_FILE        prints one row of consecutive one-based positions per group (nothing when none)
"""
import re
import sys
from pathlib import Path

E2E = re.compile(r'\bplaywright\s+test\b|\bcypress\b|\be2e\b|\bwdio\b|\bselenium\b|\bpuppeteer\b|\bnightwatch\b', re.I)
SETUP = re.compile(r'\b(?:npm\s+(?:ci|install|i)|yarn(?:\s+install)?|pnpm\s+(?:install|i)|pip3?\s+install|poetry\s+install|'
                   r'bundle\s+install)\b|\bplaywright\s+install\b')
BUILD = re.compile(r'\b(?:npm|yarn|pnpm)\s+(?:run\s+)?build\b|\bvite\s+build\b|\btsc\b|\bwebpack\b|\brollup\b|\besbuild\b|'
                   r'\bcargo\s+build\b|\bgo\s+build\b|\bmake\s+build\b')
UNIT = re.compile(r'\b(?:vitest|jest|mocha|pytest)\b|\bgo\s+test\b|\bcargo\s+test\b|\bnode\s+--test\b|'
                   r'\b(?:npm|yarn|pnpm)\s+(?:run\s+)?test(?::unit)?\b')
MUTATION = re.compile(r'mutat|defect|inject', re.I)
COMPOUND = re.compile(r'&&|;|(?<!\|)\|(?!\|)|`|\$\(')       # a pipeline or a chain is more than one command; leave it alone


def kind(command):
    if COMPOUND.search(command.replace('>/dev/null', '').replace('2>&1', '')) or E2E.search(command):
        return 'e2e' if E2E.search(command) and not COMPOUND.search(command) else 'other'
    if MUTATION.search(command) and re.search(r'\b(?:node|python3?|tsx|bash|sh)\b', command):
        return 'mutation'
    if SETUP.search(command):
        return 'setup'
    if BUILD.search(command):
        return 'build'
    if UNIT.search(command):
        return 'unit'
    return 'other'


def groups(commands):
    """[[positions]] of consecutive, independent commands, one-based, in order."""
    kinds = [kind(c) for c in commands]
    rows, i = [], 0
    while i < len(kinds) - 1:
        if {kinds[i], kinds[i + 1]} in ({'build', 'unit'}, {'e2e', 'mutation'}, {'unit', 'e2e'}):
            rows.append([i + 1, i + 2])
            i += 2
        else:
            i += 1
    return rows


def main(argv):
    if len(argv) != 1:
        raise SystemExit(__doc__)
    try:
        lines = [l for l in Path(argv[0]).read_text(encoding='utf-8').splitlines() if l.strip()]
    except OSError:
        return 0
    for row in groups(lines):
        print(' '.join(str(n) for n in row))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Would a speculative implementation have survived the adversarial review?

A probe. It changes nothing and runs nothing: at the point the updated plan is
written, it compares the sections that decide whether already-written code is
still valid, and records what a speculative implementation started from
PROJECT_PLAN.md would have met.

The question is whether the review usually leaves the buildable parts of a plan
alone. If it does, starting implementation early is mostly free; if it does not,
the work is discarded every time and the only thing gained is an earlier look at
a running app. Two runs measured by hand said discard both times, which is too
small a sample to design on.

Cosmetic rewording counts as a change here, deliberately. A comparison loose
enough to ignore it would also ignore a behavior that kept its identifier and
changed its meaning, which is exactly the case that makes written code wrong.
The report separates the two so the rate can be read either way.
"""
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def sections(plan, lib):
    out = subprocess.run(
        ['bash', '-c', '. "%s/plan-scope.sh"; plan_material_sections "%s"' % (lib, plan)],
        capture_output=True, text=True)
    return out.stdout.splitlines()


def by_section(lines):
    current, out = None, {}
    for line in lines:
        if line.startswith('### '):
            current = line[4:]
            out[current] = []
        elif current:
            out[current].append(line)
    return out


def wording_only(before, after):
    """True when the two lines differ only in whitespace and word order."""
    norm = lambda s: sorted(re.findall(r'[A-Za-z0-9_./-]+', s.lower()))
    return norm(before) == norm(after)


def main():
    lib = str(Path(__file__).resolve().parent)
    before_path, after_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    before, after = sections(before_path, lib), sections(after_path, lib)
    digest = lambda rows: hashlib.sha256('\n'.join(rows).encode()).hexdigest()

    a, b = by_section(before), by_section(after)
    changed_sections = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))

    removed = [l for l in difflib.unified_diff(before, after, lineterm='', n=0) if l.startswith('-') and not l.startswith('---')]
    added = [l for l in difflib.unified_diff(before, after, lineterm='', n=0) if l.startswith('+') and not l.startswith('+++')]
    cosmetic = sum(1 for x, y in zip(removed, added) if wording_only(x[1:], y[1:]))

    report = {
        'would_adopt': digest(before) == digest(after),
        'material_lines': {'before': len(before), 'after': len(after)},
        'changed_material_lines': len(removed) + len(added),
        'changed_sections': changed_sections,
        'paired_changes_that_are_wording_only': cosmetic,
        'would_adopt_if_wording_ignored': (
            not changed_sections or (len(removed) == len(added) == cosmetic)),
        'sample': [l[:160] for l in (removed + added)[:6]],
    }
    Path(out_path).write_text(json.dumps(report, indent=2) + '\n')
    verdict = 'ADOPT' if report['would_adopt'] else 'DISCARD'
    print('Code written from %s would have been: %s'
          % (Path(before_path).name, verdict))
    if not report['would_adopt']:
        print('  material sections the review changed: %s'
              % (', '.join(changed_sections) or 'none'))
        if report['would_adopt_if_wording_ignored']:
            print('  ...but every change was wording only.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

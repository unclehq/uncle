#!/usr/bin/env python3
"""Is this project something a person could actually look at early?

The preview build runs before any code exists, so `launch_spec` cannot answer
this -- there is no index.html and no launch.json yet to inspect. The only
evidence available is what the plan says it is building.

Only two kinds are worth previewing. A web application shows a page; a command
line tool shows output. A library, a service, an API or a daemon has nothing to
put on screen, and building one early spends tokens to show the operator
nothing.

Deliberately conservative: it answers `none` unless the plan positively says
otherwise, because a preview that should not have run costs real money on every
build, while a missing one costs only the early look.
"""
import re
import sys
from pathlib import Path

WEB = (r'\bindex\.html\b', r'\bhtml\b', r'\bbrowser\b', r'\bweb ?app\b', r'\bwebpage\b',
       r'\bweb page\b', r'\bsingle[- ]page\b', r'\bfront ?end\b', r'\bdom\b', r'\bcss\b',
       r'\breact\b', r'\bvue\b', r'\bsvelte\b', r'\blocalstorage\b', r'\bvite\b')
CLI = (r'\bcli\b', r'\bcommand[- ]line\b', r'\bstdout\b', r'\bstdin\b', r'\bargv\b',
       r'\bterminal\b', r'\bconsole app\b', r'\bshell script\b', r'\bcommand script\b')
# Things that look like an application but have no early face to show.
HEADLESS = (r'\bREST API\b', r'\bmicroservice\b', r'\bdaemon\b', r'\bbackground (service|worker)\b')


def architecture(text):
    match = re.search(r'^#{2,3} +(?:[0-9]+\. +)?Architecture *$', text, re.M)
    if not match:
        return ''
    rest = text[match.end():]
    end = re.search(r'^#{2,3} ', rest, re.M)
    return rest[:end.start()] if end else rest


def hits(text, patterns):
    return sum(1 for p in patterns if re.search(p, text, re.I))


def classify(root='.'):
    root = Path(root)
    plan = ''
    for name in ('PROJECT_PLAN.md', 'UPDATED_PROJECT_PLAN.md'):
        if (root / name).is_file():
            plan = (root / name).read_text(errors='replace')
            break
    brief = ''
    for name in ('REQUIREMENTS.md', 'REQUIREMENTS_INTERPRETATION.md'):
        if (root / name).is_file():
            brief += (root / name).read_text(errors='replace')
    if not plan and not brief:
        return 'none'

    # The architecture section is the plan's own statement of what it builds, so
    # it decides; the brief only breaks a tie.
    arch = architecture(plan)
    for text in (arch, plan + brief):
        if not text.strip():
            continue
        web, cli = hits(text, WEB), hits(text, CLI)
        if web and web >= cli:
            return 'webpage'
        if cli:
            return 'none' if hits(text, HEADLESS) > cli else 'command'
    return 'none'


if __name__ == '__main__':
    print(classify(sys.argv[1] if len(sys.argv) > 1 else '.'))

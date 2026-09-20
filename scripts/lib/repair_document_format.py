#!/usr/bin/env python3
"""Repair a stage document's shape when the deviation is unambiguous.

A run has been lost more than once to a document that was correct in substance
and wrong in shape: an `**Overall assessment:**` written as a bold label inside
another section instead of as its own heading; a reviewer's think-aloud left
above the first heading; a verdict with a trailing sign-off line after it. In
each case the finding text, the evidence and the verdict were all intact and
the stage still failed.

This repairs exactly those cases and nothing else. Every rule here is a shape
change with one possible reading:

  - drop a preamble above the document's first heading (leaked reasoning)
  - promote a bold `**Overall assessment:**` label to a `## Overall assessment`
    heading, keeping its text
  - move a final-audit verdict back to the last line when prose follows it

It does not invent a section, reword a finding, change a status, add a row, or
decide anything. If a document is wrong in a way that needs judgment, it is
left alone and the stage fails as before -- a repair that guessed would be
worse than the failure, because the guess would be approved as the reviewer's
own words.

Usage: repair_document_format.py <file>
Exit 0 and print what changed, or exit 1 having changed nothing.
"""
from pathlib import Path
import re
import sys

# A heading that starts the document proper. Anything above the first one is
# not part of the artifact.
_FIRST_HEADING = re.compile(r'^#{1,6}[ \t]+\S', re.M)

# `**Overall assessment:** text` as a bold label rather than a heading. The
# validator wants `## Overall assessment` followed by body text.
# The colon may sit inside or outside the bold markers; both spellings are
# common and both are what the validator refuses.
_BOLD_ASSESSMENT = re.compile(
    r'^[ \t]*(?:[-*+][ \t]+)?(?:\*\*|__)Overall assessment[ \t]*:?[ \t]*(?:\*\*|__)'
    r'[ \t]*:?[ \t]*(?P<body>.*?)[ \t]*$',
    re.M | re.I)

_HAS_ASSESSMENT_HEADING = re.compile(
    r'^##[ \t]+(?:\d+[.)][ \t]+)?(?:\*\*)?Overall assessment', re.M | re.I)

_VERDICTS = ('READY WITH NON-BLOCKING ISSUES', 'NOT READY', 'READY')


def _strip_preamble(text):
    """Drop anything above the first heading. Reviewer think-aloud lands here."""
    match = _FIRST_HEADING.search(text)
    if not match or match.start() == 0:
        return text, None
    preamble = text[:match.start()].strip()
    if not preamble or preamble.startswith('|') or preamble.startswith('---'):
        return text, None          # a table or front matter, not a leak
    first = preamble.splitlines()[0][:60]
    return text[match.start():], 'dropped %d characters above the first heading (%r...)' % (
        len(preamble), first)


def _promote_assessment(text):
    """A bold Overall assessment label becomes its own section."""
    if _HAS_ASSESSMENT_HEADING.search(text):
        return text, None
    match = _BOLD_ASSESSMENT.search(text)
    if not match:
        return text, None
    body = match.group('body').strip()
    if not body:
        # The text may be on following lines; take until the next blank line.
        rest = text[match.end():].lstrip('\n')
        body = rest.split('\n\n', 1)[0].strip()
        if not body:
            return text, None
        end = match.end() + text[match.end():].index(body) + len(body)
    else:
        end = match.end()
    section = '\n## Overall assessment\n\n%s\n' % body
    return text[:match.start()].rstrip() + '\n' + section + text[end:], \
        'promoted a bold Overall assessment label to a heading'


def _verdict_last(text):
    """The final audit's verdict must be the last line."""
    lines = [l for l in text.rstrip().splitlines()]
    if not lines:
        return text, None
    def verdict_of(line):
        bare = re.sub(r'^Conclusion:[ \t]*', '', line.strip().strip('#*_ ')).strip('*_ ')
        return bare if bare.upper() in _VERDICTS else None
    if verdict_of(lines[-1]):
        return text, None
    for index in range(len(lines) - 1, -1, -1):
        found = verdict_of(lines[index])
        if not found:
            continue
        trailing = [l for l in lines[index + 1:] if l.strip()]
        if len(trailing) > 3:
            return text, None      # too much follows; not a stray sign-off
        kept = lines[:index] + lines[index + 1:]
        return '\n'.join(kept).rstrip() + '\n' + found + '\n', \
            'moved the verdict %r to the last line, past %d trailing line(s)' % (found, len(trailing))
    return text, None


# file -> the repairs that are safe for it.
_RULES = {
    'ADVERSARIAL_REVIEW.md': (_strip_preamble, _promote_assessment),
    'FINAL_AUDIT.md': (_strip_preamble, _verdict_last),
    'TEST_REVIEW.md': (_strip_preamble,),
    'MANUAL_CHECKLIST.md': (_strip_preamble,),
    'VERIFICATION_REPORT.md': (_strip_preamble,),
    'PREFLIGHT_REPORT.md': (_strip_preamble,),
}


def repair(path):
    path = Path(path)
    rules = _RULES.get(path.name)
    if not rules:
        return []
    text = original = path.read_text(encoding='utf-8')
    applied = []
    for rule in rules:
        text, note = rule(text)
        if note:
            applied.append(note)
    if not applied or text == original:
        return []
    path.write_text(text, encoding='utf-8')
    return applied


if __name__ == '__main__':
    try:
        changes = repair(sys.argv[1])
    except (OSError, IndexError, ValueError) as error:
        print('Format repair failed: %s' % error, file=sys.stderr)
        raise SystemExit(1)
    if not changes:
        raise SystemExit(1)
    for change in changes:
        print('Format repair: %s' % change)

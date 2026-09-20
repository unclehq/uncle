"""Reject progress messages and incomplete checklist artifacts before execution."""
from pathlib import Path
import re
import sys
from checklist_groups import parse

# A self-hosted reviewer twice wrote a checklist with real, complete content
# under prose-style bold labels ("**Checks:**", "**Pass condition:**")
# instead of the required bullet fields -- every check was fully specified,
# just spelled differently, and got rejected for it. checklist_groups.py's
# own FIELD regex already tolerates bold markup for "Exclusive resources"/
# "Depends on"; this extends the same tolerance to the two fields whose
# absence this file's sanity check treats as "not a checklist at all".
# Deliberately label-only: no action, expected result, or any other content
# is invented or altered.
def _label_pattern(words):
    # The colon lands either inside or outside the closing bold marker
    # ("**Checks:**" vs "**Checks**:") in the wild; match both explicitly
    # rather than guess, so no markup is ever left dangling in the output.
    return re.compile(
        r'^(\s*)(?:[-*+]\s*)?'
        r'(?:\*\*(?:%s):\*\*|\*\*(?:%s)\*\*:|__(?:%s):__|__(?:%s)__:|(?:%s):)'
        r'\s*' % ((words,) * 5), re.I | re.M)


LABEL_SYNONYMS = (
    (_label_pattern(r'Checks?|Steps?'), r'\g<1>- Exact action: '),
    (_label_pattern(r'Pass\s+condition'), r'\g<1>- Expected result: '),
)


def normalize_labels(text):
    for pattern, replacement in LABEL_SYNONYMS:
        text = pattern.sub(replacement, text)
    return text


def validate(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    try:
        return validate_text(text)
    except ValueError:
        normalized = normalize_labels(text)
        if normalized == text:
            raise
        checks = validate_text(normalized)
        path.write_text(normalized, encoding='utf-8')
        return checks


def validate_text(text):
    checks,_,warnings=parse(text)
    if not checks:
        raise ValueError('No checklist rows: return the complete checklist, not a filename or progress message')
    if len({c.id for c in checks}) != len(checks):
        raise ValueError('Duplicate checklist IDs')
    # Both supported layouts must describe actions and their observable results.
    # Resource/dependency errors continue to use the existing serial fallback.
    if not re.search(r'\b(?:exact action|action|steps)\b',text,re.I) or not re.search(r'\bexpected(?: result)?\b',text,re.I):
        raise ValueError('Checklist lacks actions or expected results')
    return checks

if __name__=='__main__':
    args = sys.argv[1:]
    if args and args[0] == '--validate':
        args = args[1:]
    try:validate(args[0])
    except (OSError,ValueError) as error:
        print(f'Checklist artifact invalid: {error}. Correct MANUAL_CHECKLIST.md and resume; resume only revalidates this saved file and does not regenerate it. Execution has not started.',file=sys.stderr)
        raise SystemExit(1)

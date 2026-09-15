"""Reject progress messages and incomplete checklist artifacts before execution."""
from pathlib import Path
import re
import sys
from checklist_groups import parse


def validate(path):
    text=Path(path).read_text(encoding='utf-8')
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
    try:validate(sys.argv[1])
    except (OSError,ValueError) as error:
        print(f'Checklist artifact invalid: {error}. Correct MANUAL_CHECKLIST.md and resume; execution has not started.',file=sys.stderr)
        raise SystemExit(1)

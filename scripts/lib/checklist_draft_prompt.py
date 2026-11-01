#!/usr/bin/env python3
"""Turn a manual-checklist lens prompt into a DRAFT prompt: written before implementation, from the approved requirements and plan only.

    checklist_draft_prompt.py PROMPT_FILE      rewrites it in place

The final panel's prompt tells the lens to read the test review and to cite the driver's verification record. Neither exists while the
code is still being written, so those sentences go and a note says what this draft is for.
"""
import re
import sys
from pathlib import Path

NOTE = '''

## Draft before implementation (binding)

This checklist is drafted while the code is still being written, from the approved requirements, plan and adversarial review only. You
are independent of the implementation on purpose: do not look for the application's source, and do not assume how it was built. After
implementation a reconciler compares your checks with the built application and the driver's results, so write each check against the
approved behavior (observable action, observable result), not against any file or selector you cannot find in the plan.
'''


def transform(text):
    # the driver's verification record and the test review both exist only after implementation
    text = re.sub(r',?\s*plus the completed driver record `\.uncle/workflow/green-check\.tsv`', '', text)
    text = re.sub(r',?\s*(?:and\s+)?`\.uncle/workflow/documents/TEST_REVIEW\.json`', '', text)
    text = re.sub(r'\n\nTreat the driver record as authoritative for dependency, build, unit, and automated-browser commands: '
                  r'cite it rather than proposing those commands again\.', '\n\nDo not propose commands for dependency, build, unit '
                  'or automated-browser checks: the driver runs the approved verification commands itself.', text)
    # the base lens prompt also leans on the completed green check for the same facts
    text = re.sub(r'through the completed green\s+check and its deterministic records', 'themselves', text)
    text = re.sub(r'The completed driver green-check is\s+authoritative for automated commands; cite it rather than re-running its\s+'
                  r'tests, install, build, or browser suite\.', 'The driver runs the automated commands itself; do not propose them.', text)
    return text.rstrip('\n') + NOTE


def main(argv):
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[0])
    path.write_text(transform(path.read_text(encoding='utf-8')), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

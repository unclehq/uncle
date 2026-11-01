#!/usr/bin/env python3
"""Find implementation steps that only run the test suites, which the driver runs itself afterwards.

A plan sometimes ends with a step like "Verification only: run `bash scripts/run-shell-tests.sh` and
`bash scripts/run-python-tests.sh`; failures are routed back to the owning step -- Owns: none". Run as an implementation step it
executes the whole regression block inside a model session (991 s of a 1,923 s implementation on issue 117), and then the driver
runs the same approved verification commands independently anyway, because the driver's own result is the evidence and a step's
claim is not. Skipping the step loses nothing and saves its whole wall-clock and token cost.

A step is verification-only only when ALL of these hold, so a step that does anything else is never skipped:
  * it declares no files (`Owns: none`, `n/a`, or a dash) -- a step that owns a file writes something;
  * what it says before the ownership marker begins with a verification or run-the-tests phrase;
  * that text contains no verb that changes things (create, add, write, edit, modify, implement, update, fix, ...).

    verification_steps.py skip-set [STEPS_FILE|-]     # 1-based indices of the steps to skip, space-separated
"""
import re
import sys

OWNS_NONE = re.compile(r'(?i)\bowns\s*:\s*[`*_ ]*(none|n/?a|nothing|no files|—|–|-)(?=[\s`*_.,;)—–-]|$)')
OWNS_ANY = re.compile(r'(?i)\bowns\s*:')
OWNS_SOMETHING = re.compile(r'(?i)\bowns\s*:\s*[`*_ ]*(?!none\b|n/?a\b|nothing\b|no files\b|—|–|-)\S')
OPENING = re.compile(r'(?i)^[\s\W]*(?:\d+[.)]\s*)?(verification(\s+only)?|verify\b|final verification|full (test|regression)|'
                     r'run\b[^.;:]*\b(tests?|suites?|verification|regression)\b|execute\b[^.;:]*\b(tests?|suites?|verification|regression)\b)')
CHANGES = re.compile(r'(?i)\b(create|creat(es|ing)|add(s|ing)?|write|writes|writing|edit|edits|modify|modifies|implement|implements|'
                     r'update|updates|fix|fixes|refactor|rename|delete|remove|document|generate|patch|install|migrate)\b')


def is_verification_only(step):
    text = step.strip()
    if not OWNS_NONE.search(text) or OWNS_SOMETHING.search(text):
        return False
    head = re.split(r'(?i)[—–-]{1,2}\s*owns\s*:', text, maxsplit=1)[0]
    head = re.split(r'(?i)\bowns\s*:', head, maxsplit=1)[0]
    if not OPENING.search(head):
        return False
    # "failures are routed back to the owning step" mentions fixing without doing it; judge only the instruction itself.
    instruction = re.split(r';|\. ', head, maxsplit=1)[0]
    return not CHANGES.search(instruction)


def skip_set(lines):
    return [number for number, line in enumerate((l for l in lines if l.strip()), 1) if is_verification_only(line)]


def main(argv):
    if len(argv) >= 2 and argv[1] == 'skip-set':
        source = argv[2] if len(argv) > 2 else '-'
        lines = (sys.stdin if source == '-' else open(source, encoding='utf-8')).read().splitlines()
        print(' '.join(str(n) for n in skip_set(lines)))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))

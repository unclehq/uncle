#!/usr/bin/env python3
"""Is a reviewer's reply the document it was asked for, or a note about it?

Every runner checked that the model replied: non-empty text, a result event,
`is_error` false, a clean finish reason. None checked that the reply was a
document. A model that ends its turn saying "I will now produce
ADVERSARIAL_REVIEW.md with concrete findings" satisfies all of those, and the
announcement gets written to the artifact as though it were the review.

That happened on unclehq/uncle#59: the reviewer's log ended with a to-do list
whose last item was "Produce ADVERSARIAL_REVIEW.md with concrete findings", the
runner reported success, and the artifact was a 31-line chat summary with no
findings. The stage then failed three checks later on a format error, which
described a symptom and hid what actually went wrong.

Weak models make this likely; nothing in any runner makes it impossible, so the
check belongs in one place that all four use.

The test is deliberately shallow: a reviewer artifact is structured markdown, so
it carries at least one heading or one table row. Judging content is the job of
the stage validators, which know what each document must contain. This only
separates "a document" from "a sentence about a document".
"""
import re
import sys

_HEADING = re.compile(r'^#{1,6}\s+\S', re.M)
_TABLE_ROW = re.compile(r'^\s*\|.*\|', re.M)


def looks_like_document(text):
    return bool(_HEADING.search(text) or _TABLE_ROW.search(text))


def check(text, runner='reviewer'):
    """Return the text, or raise ValueError naming the real failure."""
    if looks_like_document(text):
        return text
    preview = ' '.join(text.split())[:120]
    raise ValueError(
        '%s returned no document: the response has no heading or table row. '
        'It reads as a summary, a plan, or a promise to write the artifact '
        'rather than the artifact. First words: %s'
        % (runner, preview or '(empty)'))


if __name__ == '__main__':
    # Filter: document on stdin, same document on stdout, or exit 1 with the
    # reason on stderr so the shim can fail before writing the artifact.
    runner = sys.argv[1] if len(sys.argv) > 1 else 'reviewer'
    # Windows text mode would translate LF to CRLF on the way to the artifact.
    sys.stdout.reconfigure(newline='\n')
    body = sys.stdin.read()
    try:
        sys.stdout.write(check(body, runner))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)

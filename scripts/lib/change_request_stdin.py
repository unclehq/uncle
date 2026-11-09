#!/usr/bin/env python3
"""Validate a change request piped to `uncle --change-request`.

Usage: change_request_stdin.py PROJECT_ROOT PRIVATE_DIR

Reads raw stdin bytes, validates them, normalizes CRLF/CR to LF, writes the
text to a 0600 file inside PRIVATE_DIR and prints that path.  On any rejection
it prints `Error: ...` to stderr, exits 1 and writes nothing.
"""
import os
import re
import sys
import tempfile

CAP = 1048576
EXISTS = 'CHANGE_REQUEST.md already exists. Run it or choose a new project; it was not overwritten.'
REJECTED = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]')


def fail(message):
    sys.stderr.write(message + '\n')
    raise SystemExit(1)


def main(argv):
    root, private = argv[1], argv[2]
    data = sys.stdin.buffer.read(CAP + 1)
    if len(data) > CAP:
        fail('Error: --change-request input exceeds %d bytes' % CAP)
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        fail('Error: --change-request input is not valid UTF-8')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if REJECTED.search(text):
        fail('Error: --change-request input contains NUL or control characters')
    if not text.strip():
        fail('Error: --change-request text cannot be empty')
    # A finished run leaves its request behind. The text is valid, so the old one is archived (run_duties.archive_change_request;
    # UNCLE_KEEP_CHANGE_REQUEST=1 keeps the refusal) instead of making the operator delete it by hand.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import run_duties
        for archived in run_duties.archive_change_request(root):
            sys.stderr.write('Archived the previous change request to %s\n' % archived)
    except (OSError, ImportError):
        pass
    if any(os.path.lexists(os.path.join(root, *part, 'CHANGE_REQUEST.md'))
           for part in ((), ('.uncle', 'docs'))):
        fail(EXISTS)
    fd, path = tempfile.mkstemp(prefix='change-request-', dir=private)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(text.encode('utf-8'))
    print(path)


if __name__ == '__main__':
    main(sys.argv)

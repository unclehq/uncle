#!/usr/bin/env python3
"""Validate housekeeping request text for `uncle --housekeeping`.

Usage: housekeeping_input.py PRIVATE_DIR [--text TEXT]

Text comes from --text when given, otherwise from raw stdin bytes.  Limits
mirror change_request_stdin.py (size cap, UTF-8, CRLF/CR normalised to LF, no
NUL/control characters, non-empty) but there is no CHANGE_REQUEST.md check.
Writes the text to a 0600 file inside PRIVATE_DIR and prints that path.  On any
rejection it prints `Error: ...` to stderr, exits 1 and writes nothing.
"""
import os
import re
import sys
import tempfile

CAP = 1048576
REJECTED = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]')


def fail(message):
    sys.stderr.write(message + '\n')
    raise SystemExit(1)


def main(argv):
    if len(argv) < 2:
        fail('Error: usage: housekeeping_input.py PRIVATE_DIR [--text TEXT]')
    private = argv[1]
    if len(argv) >= 3:
        if argv[2] != '--text' or len(argv) != 4:
            fail('Error: usage: housekeeping_input.py PRIVATE_DIR [--text TEXT]')
        data = argv[3].encode('utf-8', 'surrogateescape')
    else:
        data = sys.stdin.buffer.read(CAP + 1)
    if len(data) > CAP:
        fail('Error: --housekeeping input exceeds %d bytes' % CAP)
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        fail('Error: --housekeeping input is not valid UTF-8')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if REJECTED.search(text):
        fail('Error: --housekeeping input contains NUL or control characters')
    if not text.strip():
        fail('Error: --housekeeping text cannot be empty')
    fd, path = tempfile.mkstemp(prefix='housekeeping-', dir=private)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(text.encode('utf-8'))
    print(path)


if __name__ == '__main__':
    main(sys.argv)

#!/usr/bin/env python3
"""Validate housekeeping request text for `uncle --housekeeping`.

Usage: housekeeping_input.py [--label OPT] PRIVATE_DIR [--text TEXT]

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
    usage = 'Error: usage: housekeeping_input.py [--label OPT] PRIVATE_DIR [--text TEXT]'
    args = argv[1:]
    label = '--housekeeping'
    if args[:1] == ['--label']:
        if len(args) < 2:
            fail(usage)
        label = '--' + args[1].lstrip('-')
        args = args[2:]
    if not args:
        fail(usage)
    private = args[0]
    stdin_path = len(args) == 1
    if not stdin_path:
        if args[1] != '--text' or len(args) != 3:
            fail(usage)
        data = args[2].encode('utf-8', 'surrogateescape')
    else:
        data = sys.stdin.buffer.read(CAP + 1)
    if len(data) > CAP:
        fail('Error: %s input exceeds %d bytes' % (label, CAP))
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        fail('Error: %s input is not valid UTF-8' % label)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if stdin_path and text.endswith('\n'):
        text = text[:-1]
    if REJECTED.search(text):
        fail('Error: %s input contains NUL or control characters' % label)
    if not text.strip():
        fail('Error: %s text cannot be empty' % label)
    fd, path = tempfile.mkstemp(prefix='housekeeping-', dir=private)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(text.encode('utf-8'))
    print(path)


if __name__ == '__main__':
    main(sys.argv)

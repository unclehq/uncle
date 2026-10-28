#!/usr/bin/env python3
"""Make a verification-command list one complete shell command per line.

The driver runs the approved commands one line at a time.  A plan that writes
a command across lines -- `sh -c '` ... `'`, a multi-line `if`, a `for` loop --
was therefore shredded into fragments, each run on its own: the opening line
failed with "unexpected EOF", the lines inside the quotes ran as if they were
top-level commands, and the closing quote failed too.  Two of a plan's
commands reported FAIL that never failed, and a run was stopped on them.

This reads the list on stdin and writes it back with every command that spans
lines folded into one line that runs the same text:

    eval "$(printf '%s\\n' 'sh -c '"'"'' '  set -e' ... )"

A command is complete when `bash -n` accepts it.  Lines that never complete
are written out unchanged, exactly as before, so nothing that worked changes.
"""
import shlex
import subprocess
import sys

LOOKAHEAD = 200


def complete(text, bash):
    result = subprocess.run([bash, '-n', '-c', text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def fold(lines, bash):
    out, index = [], 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith('#') or complete(line, bash):
            out.append(line)
            index += 1
            continue
        for end in range(index + 2, min(index + LOOKAHEAD, len(lines)) + 1):
            if complete('\n'.join(lines[index:end]), bash):
                quoted = ' '.join(shlex.quote(part) for part in lines[index:end])
                out.append('eval "$(printf \'%s\\n\' ' + quoted + ')"')
                index = end
                break
        else:
            out.append(line)           # never completes: leave it for the shell to report
            index += 1
    return out


def main():
    lines = sys.stdin.read().split('\n')
    trailing = lines and lines[-1] == ''
    if trailing:
        lines.pop()
    try:
        sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
        from process_tree import bash_executable
        folded = fold(lines, bash_executable())
    except (OSError, ImportError):
        folded = lines
    if not any(line.strip() for line in folded):
        # An input that was empty (or all blank lines, e.g. a single
        # trailing newline from printing an empty verification_commands
        # string) must fold to nothing -- not a bare newline, which
        # verify_commands' own "no command block" check reads as "there is
        # one command, and it is blank" instead of "there is none."
        return
    sys.stdout.write('\n'.join(folded) + ('\n' if trailing else ''))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Tell a verification command that could not run from one that failed.

A preflight row that is BLOCKED-SETUP names something only a person can arrange (a port another project holds, a missing tool).
A verification command whose own output shows that same obstacle did not find a defect in the code: it did not run. It is
re-labelled BLOCKED-SETUP, so it is never sent to repair (nothing the repair agent edits can free a port), and the report and the
final audit say it was not performed instead of counting it as a failure to fix or, worse, as a pass.

    blocked_prerequisites.py reclassify PREFLIGHT_REPORT.json GREEN_LOG [SIDE_TSV]   < classified.tsv > classified.tsv

`classified.tsv` is green_classify's `CLASS<TAB>command` rows. A REGRESSION, FAIL or MUTATION row whose command output an
outstanding BLOCKED-SETUP row explains becomes `BLOCKED-SETUP<TAB>command`; SIDE_TSV receives `command<TAB>row ids<TAB>action`.
Any trouble reading the report or the log passes every row through unchanged: an attribution is made only on evidence.

The one obstacle recognised is a port that is already in use: the row's evidence names the port, and the command's output has a
line saying a port is in use (Playwright "is already used", Node EADDRINUSE, "Address already in use") on or beside a line naming it."""
import json
import re
import sys

REASSIGNED = ('REGRESSION', 'FAIL', 'MUTATION')
IN_USE = re.compile(r'already (?:used|in use)|EADDRINUSE|address in use|port is (?:already )?in use', re.I)
PORT = re.compile(r'(?:127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1?\]|::1|\bports?\b)[:\s]*(\d{2,5})\b', re.I)
ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
WINDOW = 2


def blocked_rows(report_path):
    with open(report_path, encoding='utf-8') as stream:
        rows = json.load(stream).get('rows') or []
    return [row for row in rows if isinstance(row, dict) and row.get('status') == 'BLOCKED-SETUP' and isinstance(row.get('id'), str)]


def sections(log_path):
    """{first line of a command: its output}, from a log that marks each command with a `$ ` line."""
    with open(log_path, encoding='utf-8', errors='replace') as stream:
        lines = ANSI.sub('', stream.read()).splitlines()
    found, name = {}, None
    for line in lines:
        if line.startswith('$ '):
            name = line[2:].strip()
            found.setdefault(name, [])
        elif name is not None:
            found[name].append(line)
    return found


def ports_of(row):
    return set(PORT.findall(str(row.get('evidence') or '')))


def port_in_use(output_lines, ports):
    """True when a line saying a port is in use is on or beside a line naming one of `ports`."""
    for index, line in enumerate(output_lines):
        if not IN_USE.search(line):
            continue
        near = ' '.join(output_lines[max(0, index - WINDOW):index + WINDOW + 1])
        if any(re.search(r'(?<!\d)%s(?!\d)' % re.escape(port), near) for port in ports):
            return True
    return False


def action_of(row):
    evidence = ' '.join(str(row.get('evidence') or '').split())
    found = re.search(r'Action:\s*(.+)$', evidence)
    return (found.group(1) if found else evidence)[:240]


def explaining(rows, output_lines):
    return [row for row in rows if (ports := ports_of(row)) and port_in_use(output_lines, ports)]


def reclassify(report_path, log_path, side_path, source, sink):
    text = source.read()
    try:
        rows = blocked_rows(report_path)
        by_command = sections(log_path) if rows else {}
    except (OSError, ValueError, AttributeError):
        sink.write(text)
        return
    side = []
    for line in text.splitlines():
        kind, tab, command = line.partition('\t')
        if tab and kind in REASSIGNED:
            why = explaining(rows, by_command.get(command.splitlines()[0].strip() if command else '', []))
            if why:
                side.append('%s\t%s\t%s' % (command, ','.join(row['id'] for row in why), action_of(why[0])))
                line = 'BLOCKED-SETUP\t' + command
        sink.write(line + '\n')
    if side_path:
        try:
            with open(side_path, 'w', encoding='utf-8') as stream:
                stream.write('\n'.join(side) + ('\n' if side else ''))
        except OSError:
            pass


def main(argv):
    if len(argv) in (3, 4) and argv[0] == 'reclassify':
        reclassify(argv[1], argv[2], argv[3] if len(argv) == 4 else None, sys.stdin, sys.stdout)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

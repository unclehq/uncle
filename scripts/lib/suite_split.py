"""Split one long suite into pieces that run side by side as separate pool entries.

A suite whose wall time is one long chain of independent cases keeps a core busy for minutes while the rest sit idle. The pieces
here are the same suite file, each running a share of its cases; every case runs in exactly one piece.

  Python (unittest) suites: a piece runs its share of the `Class.test_name` ids.
  Shell suites: cases are the top-level `new_case` / `new_stagegate_case` calls, or a top-level for/while/if block that contains
  them. A piece runs the whole file with the other pieces' cases removed. Everything outside a case (setup, helper functions,
  the closing summary after a `# split:end` line) stays in every piece. UNCLE_SPLIT_PART=i/k is exported so a suite with its own
  non-`new_case` sections (close-flow's PR handoff cases) can take its share too.

    suite_split.py shell I K FILE [ARGS...]     run piece I of K (0-based)
    suite_split.py python I K FILE              run piece I of K
    suite_split.py count shell|python FILE      how many cases the suite has (for checking the pieces add up)
"""
import os
from pathlib import Path
import re
import subprocess
import sys

UNIT = re.compile(r'(new_case|new_stagegate_case)\b(?!\s*\()')   # a call, not the function definition
COMPOUND = re.compile(r'(for|while|until|if)\b')
CLOSER = re.compile(r'(done|fi)\b')
FUNCTION = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\(\) *\{')
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def shell_pieces(text, index, parts):
    """The suite text with only piece `index` of `parts` of its cases kept. Returns (text, total_cases_seen_per_scope)."""
    lines = text.split('\n')
    n = len(lines)
    # Where each col-0 compound block ends, and whether it contains a case.
    compound_end = {}
    for j, line in enumerate(lines):
        if COMPOUND.match(line):
            for e in range(j + 1, n):
                if CLOSER.match(lines[e]):
                    if any(re.match(r'\s+(new_case|new_stagegate_case)\b(?!\s*\()', lines[x]) for x in range(j + 1, e)):
                        compound_end[j] = e
                    break
    out, state, keep, counter, scopes = [], 'common', True, 0, []
    heredoc, skip_until = None, -1
    for j, line in enumerate(lines):
        if heredoc:
            if line.strip() == heredoc or line.rstrip() == heredoc:
                heredoc = None
            if state == 'common' or keep:
                out.append(line)
            continue
        boundary = (line.startswith('}') or line.startswith('# split:end') or FUNCTION.match(line))
        starts = j > skip_until and (UNIT.match(line) or j in compound_end)
        if state == 'unit' and (boundary or starts):
            state = 'common'
        loop_line = None
        if state == 'common' and starts:
            skip_until = compound_end.get(j, j)
            if j in compound_end and line.startswith('for ') and line.rstrip().endswith('; do'):
                # Every piece keeps the loop and takes its share of the iterations; the loop counts as one unit for the
                # static numbering, and its number staggers which piece gets the first iteration.
                keep = True
                loop_line = counter
            else:
                keep = counter % parts == index
            counter += 1
            state = 'unit'
        if loop_line is not None:
            out.append('__split_it=0')
            out.append(line)
            out.append(f'__split_it=$((__split_it + 1)); (( (__split_it + {loop_line}) % {parts} == {index} )) || continue')
            heredoc_found = HEREDOC.findall(line.replace('<<<', ''))
            continue
        if FUNCTION.match(line):
            scopes.append(counter)
            counter = 0
        if state == 'common' or keep:
            out.append(line)
            if FUNCTION.match(line) and line.rstrip().endswith('{'):
                out.append(':')     # a body whose cases all went to other pieces must not be empty
        found = HEREDOC.findall(line.replace('<<<', ''))
        if found:
            heredoc = found[-1][1]
    scopes.append(counter)
    return '\n'.join(out), scopes


def python_ids(path):
    ids, cls = [], None
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        m = re.match(r'class (\w+)\(', line)
        if m:
            cls = m.group(1)
            continue
        m = re.match(r'    def (test\w*)\(self', line)
        if m and cls:
            ids.append(f'{cls}.{m.group(1)}')
    return ids


def case_count(kind, path):
    if kind == 'python':
        return len(python_ids(path))
    return sum(shell_pieces(Path(path).read_text(encoding='utf-8'), 0, 1)[1])


def run_python(index, parts, path, extra):
    ids = python_ids(path)[index::parts]
    if not ids:
        return 0
    return subprocess.call([sys.executable, '-B', path, *ids, *extra])


def run_shell(index, parts, path, extra):
    source = Path(path)
    text, _ = shell_pieces(source.read_text(encoding='utf-8'), index, parts)
    piece = source.with_name(f'.part{index}of{parts}-{os.getpid()}-{source.name}')
    piece.write_text(text, encoding='utf-8')
    try:
        env = dict(os.environ, UNCLE_SPLIT_PART=f'{index}/{parts}')
        return subprocess.call(['bash', str(piece), *extra], env=env)
    finally:
        piece.unlink(missing_ok=True)


SPLITS = Path('scripts/tests/suite-splits.tsv')


def read_splits(path=SPLITS):
    """{suite or gate-group name: pieces}. A suite with no row is not split; a project without the file splits nothing."""
    splits = {}
    try:
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            name, _, pieces = line.partition('\t')
            if name and pieces.strip().isdigit() and int(pieces) > 1:
                splits[name] = int(pieces)
    except OSError:
        pass
    return splits


def expand(name, kind, path, command, extra=(), splits=None):
    """{entry name: command} for one suite: the suite's own command, or one command per piece when the table splits it.

    `command` is how the whole suite is launched; `extra` are the arguments after the file for a piece (gates' --group N).
    """
    pieces = (read_splits() if splits is None else splits).get(name, 1)
    if pieces <= 1:
        return {name: command}
    return {f'{name}#{i + 1}of{pieces}': [sys.executable, '-B', str(Path(__file__).resolve()), kind, str(i), str(pieces), path, *extra]
            for i in range(pieces)}


def main(argv):
    if len(argv) >= 4 and argv[1] == 'count':
        print(case_count(argv[2], argv[3]))
        return 0
    if len(argv) >= 5 and argv[1] in ('shell', 'python'):
        index, parts = int(argv[2]), int(argv[3])
        if not 0 <= index < parts:
            raise SystemExit('piece index out of range')
        return (run_shell if argv[1] == 'shell' else run_python)(index, parts, argv[4], argv[5:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))

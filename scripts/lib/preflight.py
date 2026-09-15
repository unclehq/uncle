"""Cheap runtime prerequisite probes; never execute the plan's commands."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

PROBES = {name: ['--version'] for name in
          ('node', 'npm', 'npx', 'python', 'python3', 'bash', 'git', 'ruby', 'go', 'cargo', 'rustc', 'pytest', 'ruff')}
PROBES['shasum'] = ['--version']
# POSIX sh has no portable --version; execute only our fixed no-op probe.
PROBES['sh'] = ['-c', ':']
# BSD tee has no --version. With EOF on stdin and no paths, this writes nothing.
PROBES['tee'] = []
BUILTINS = {'true', ':', 'echo', 'printf', 'mkdir', 'test', '['}


def prerequisites(commands):
    """Recognize simple shell lists; inspect tokens, never evaluate shell code."""
    names = set()
    separators = {'&&', '||', ';', '|'}
    redirects = {'>', '>>', '<', '>&', '<&'}

    def inspect(words):
        if not words:
            raise ValueError('Empty command needs model preflight')
        while words and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', words[0]):
            key = words.pop(0).split('=', 1)[0]
            if key in ('PATH', 'HOME', 'PYTHONHOME', 'NODE_OPTIONS', 'BASH_ENV', 'ENV'):
                raise ValueError('Runtime-changing assignment needs model preflight: ' + key)
        if not words:
            raise ValueError('Standalone assignment needs model preflight')
        name = words[0]
        if name in BUILTINS:
            return
        if name not in PROBES:
            raise ValueError('Unrecognized verification executable: ' + name)
        if name in ('bash', 'sh') and any(arg == '-c' or arg.startswith('-') and 'c' in arg for arg in words[1:]):
            raise ValueError('Embedded shell program needs model preflight')
        names.add(name)

    for line in commands.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        # Expansion and control structures may hide additional executables.
        # Even quoted substitution text falls back conservatively.
        if any(token in line for token in ('$(', '`', '${', '\\\n')):
            raise ValueError('Shell expansion needs model preflight')
        lexer = shlex.shlex(line, posix=True, punctuation_chars=';&|<>()')
        lexer.whitespace_split = True
        tokens = list(lexer)
        words = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in separators:
                inspect(words)
                words = []
            elif token in redirects:
                if words and words[-1].isdigit():
                    words.pop()  # Optional file descriptor, e.g. 2>&1.
                i += 1
                if i >= len(tokens) or tokens[i] in separators | redirects or re.fullmatch(r'[;&|<>()]+', tokens[i]):
                    raise ValueError('Missing redirection target')
                if token in ('>&', '<&') and not re.fullmatch(r'\d+|-', tokens[i]):
                    raise ValueError('Unsupported descriptor redirection')
            elif re.fullmatch(r'[;&|<>()]+', token):
                raise ValueError('Unsupported shell syntax: ' + token)
            else:
                words.append(token)
            i += 1
        if words:
            inspect(words)
        elif tokens and tokens[-1] != ';':
            raise ValueError('Incomplete shell command')
    return sorted(names)


def probe(name):
    executable = shutil.which(name)
    if not executable:
        raise ValueError('Missing runtime: ' + name)
    from process_tree import start_check, wait_check, finish_check
    import tempfile
    with tempfile.TemporaryFile() as output:
        child = start_check([executable, *PROBES[name]], stdout=output, stderr=subprocess.STDOUT)
        try:
            status = wait_check(child, 10, output)
        finally:
            finish_check(child)
        if status:
            raise ValueError('%s runtime probe exited %s' % (name, status))
    return name + (' fixed startup probe exited 0' if name in ('sh', 'tee') else ' --version exited 0')


def run(commands, report):
    names = prerequisites(Path(commands).read_text())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(probe, names))
    body = '''# Preflight report

## Summary
Deterministic runtime probes completed. Approved commands were not executed.

## Findings
'''
    body += '\n'.join('- ' + result for result in results) or '- No external runtime required by the command list.'
    body += '''

## Assumptions
Dependency installation and application-specific browser, service, credential,
and human checks remain subject to implementation and checklist verification.
Runtime availability does not establish that those capabilities work.

## Open questions
None about runtime startup. This report makes no application acceptance claims.

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| PF-RUNTIME | YES | PASS | Recognized verification runtimes started successfully; shell command structure was inspected |
'''
    Path(report).write_text(body, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('commands')
    parser.add_argument('report')
    args = parser.parse_args()
    try:
        run(args.commands, args.report)
    except (OSError, ValueError) as exc:
        print('Deterministic preflight needs diagnosis: ' + str(exc), file=sys.stderr)
        raise SystemExit(2)

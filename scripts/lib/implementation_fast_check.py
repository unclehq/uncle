"""Run bounded unit checks after each landed implementation step or group."""
import json
import os
from pathlib import Path
import re
import sys

from execution_options import option, seconds
from process_tree import bash_executable


def command(root):
    explicit = option('step-test-command', '')
    if explicit:
        return explicit
    try:
        scripts = json.loads((root / 'package.json').read_text()).get('scripts', {})
    except (OSError, ValueError):
        return ''
    tests = False
    for directory, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '.uncle', 'dist', 'test-results', 'e2e')]
        if any(re.search(r'\.(?:test|spec)\.[cm]?[jt]sx?$', f) for f in files):
            tests = True
            break
    if not tests:
        return ''
    for name in ('test:unit', 'test'):
        body = scripts.get(name, '')
        if re.fullmatch(r'(?:vitest run|node --test)(?: [\w./*=-]+)*', body):
            return 'npm run ' + name
    return ''


def main(label, runner):
    # Off by default for every runner: plans that land failing tests first (the change
    # workflow's regression-first steps) would otherwise stop at a correct step.
    enabled = option('step-tests', '0').lower()
    if enabled not in ('1', 'true'):
        return 0
    selected = command(Path('.'))
    if not selected:
        print('Step fast checks: NOT RUN (no ready unit target; configure execution.step-test-command).')
        return 0
    state = Path('.uncle/workflow/logs')
    state.mkdir(parents=True, exist_ok=True)
    label = re.sub(r'[^\w-]', '-', label)
    log = state / ('step-fast-' + label + '.log')
    # run_check owns the tree, idle limit, and environment preflight.
    os.environ['WORKFLOW_CHECK_TIMEOUT_SECONDS'] = str(seconds('step-test-seconds', 120))
    with log.open('wb') as output:
        from process_tree import start_check, wait_check, kill_tree, finish_check, python3_executable
        child = start_check([python3_executable(), '-B', str(Path(__file__).with_name('run_check.py')),
                             '--shell-command', selected, '--', bash_executable(), '-o', 'pipefail', '-c', selected],
                            stdout=output, stderr=output)
        try:
            status = wait_check(child, float(os.environ['WORKFLOW_CHECK_TIMEOUT_SECONDS']) + 10, output, idle=0)
        finally:
            kill_tree(child)
            child.wait()
            finish_check(child)
    print('Step fast checks: %s; %s; output: %s' % ('PASS' if status == 0 else 'FAIL(%s)' % status, selected, log))
    return status


if __name__ == '__main__':
    raise SystemExit(main(*sys.argv[1:]))

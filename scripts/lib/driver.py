#!/usr/bin/env python3
"""Entry point for the Python driver, and the seam through which states move from bash to Python.

    driver.py plan [PROJECT_ROOT]    what a project has, what could start now, what is left on the critical path
    driver.py run [DRIVER ARGS...]   run the build; stagegate.sh executes every state not yet ported
    driver.py run-state STATE        run one ported state (stagegate.sh calls this for states in UNCLE_PY_STATES)

A state is ported by adding a handler to HANDLERS and listing it in UNCLE_PY_STATES; the loop in stagegate.sh then calls
`run-state` for it instead of running its bash arm. Bash keeps the loop itself for now because speculative stages are
background jobs it holds in shell variables, which a process launched per state would lose.

Two rules keep a port from changing behaviour:

* Python never writes the state file. A handler returns the next state, `run-state` writes it to UNCLE_PY_NEXT_FILE, and
  stagegate.sh calls its own `set_state`, which also starts the next stage's idle CLI in unattended runs.
* A handler does the path it fully reproduces and raises Declined for anything else; `run-state` then exits DECLINED and the
  loop runs the bash arm. The states ported this way are idempotent up to that point, so declining costs a repeat, not a fault.

The state file, the artifacts and the approval records are the interfaces other tools read, and stay as bash writes them.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from driver_stages import ARTIFACT_FILES, MEASURED_SECONDS, STATES, new_application  # noqa: E402

TERMINAL = ('COMPLETE',)
DECLINED = 4


class Declined(Exception):
    """A handler met something it does not reproduce; the bash arm runs instead."""


@dataclass(frozen=True)
class Context:
    root: Path             # where uncle itself lives
    project_root: Path     # the project being built

    @property
    def state_dir(self):
        return self.project_root / '.uncle' / 'workflow'

    @property
    def state_file(self):
        return self.state_dir / 'state'


def context(project_root=None):
    root = Path(os.environ.get('UNCLE_RUNTIME_ROOT') or Path(__file__).resolve().parents[2])
    project = Path(project_root or os.environ.get('UNCLE_PROJECT_ROOT') or root)
    return Context(root=root, project_root=project.resolve())


def read_state(ctx, default='DERIVE_BRIEF'):
    """First line of the state file, without the `<issue>:` prefix the issue driver writes."""
    try:
        first = ctx.state_file.read_text(encoding='utf-8').split('\n', 1)[0].strip()
    except FileNotFoundError:
        return default
    return re.sub(r'^[0-9]+:', '', first) or default


def artifacts_present(ctx):
    return {name for name, rel in ARTIFACT_FILES.items() if (ctx.project_root / rel).exists()}


def approvals_granted(ctx):
    folder = ctx.state_dir / 'approvals'
    if not folder.is_dir():
        return set()
    return {p.name[:-len('.approved-by')] for p in folder.glob('*.approved-by')}


def plan(ctx):
    graph = new_application()
    have = artifacts_present(ctx)
    granted = approvals_granted(ctx)
    done = {name for name, node in graph.nodes.items() if set(node.outputs) <= have}
    remaining = {name: (0.0 if name in done else MEASURED_SECONDS.get(name, 0.0)) for name in graph.nodes}
    total, path = graph.critical_path(remaining)
    started = done
    return {
        'state': read_state(ctx),
        'artifacts': sorted(have),
        'approvals': sorted(granted),
        'done': sorted(done),
        'ready': graph.ready(have, granted, started),
        'remaining_seconds': round(total, 1),
        'remaining_path': [n for n in path if n not in done],
    }


def _python(ctx, script, *args, cwd=None):
    return subprocess.run([sys.executable, str(ctx.root / 'scripts' / 'lib' / script), *args], cwd=str(cwd or ctx.project_root),
                          capture_output=True, text=True)


def _replay(*results):
    """Show what the scripts printed, once the whole path succeeded: on a decline the bash arm repeats them."""
    for result in results:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)


def validate_manual_checklist(ctx):
    """VALIDATE_MANUAL_CHECKLIST on its happy path: scope the checklist, validate it, render it, go to EXECUTE_CHECKLIST.

    A failed validation, which the bash arm answers with one retry of MANUAL_CHECKLIST or a stop, is declined, as is a failure
    of either other script."""
    documents = ctx.state_dir / 'documents'
    manual = str(documents / 'MANUAL_CHECKLIST.json')
    scoped = _python(ctx, 'checklist_driver_scope.py', manual, '--scope', str(documents / 'MANUAL_CHECKLIST_DRIVER_SCOPE.json'))
    if scoped.returncode != 0:
        raise Declined('driver scope failed')
    if _python(ctx, 'checklist_document.py', '--validate-json', manual).returncode != 0:
        raise Declined('checklist invalid')
    rendered = _python(ctx, 'checklist_document.py', '--render-json', manual, '.uncle/docs/MANUAL_CHECKLIST.md')
    if rendered.returncode != 0:
        raise Declined('render failed')
    _replay(scoped, rendered)
    return 'EXECUTE_CHECKLIST'


# state name -> callable(Context) -> next state name.
HANDLERS = {'VALIDATE_MANUAL_CHECKLIST': validate_manual_checklist}


def run_state(ctx, state):
    handler = HANDLERS.get(state)
    if handler is None:
        sys.stderr.write('state %s is not ported to Python\n' % state)
        return 3
    try:
        following = handler(ctx)
    except Declined as why:
        sys.stderr.write('python driver declined %s: %s\n' % (state, why))
        return DECLINED
    if following not in STATES:
        raise ValueError('state %s produced unknown state %r' % (state, following))
    target = os.environ.get('UNCLE_PY_NEXT_FILE')
    if not target:
        sys.stderr.write('UNCLE_PY_NEXT_FILE is not set; nowhere to hand the next state\n')
        return 2
    Path(target).write_text(following + '\n', encoding='utf-8')
    print('python driver handled %s -> %s' % (state, following))
    return 0


def run(ctx, args):
    """Replace this process with the bash driver. Exec, not a child, so signals, the terminal and the exit code
    are exactly what they are when the driver is started directly."""
    env = dict(os.environ, UNCLE_PY_DRIVER='1')
    env.setdefault('UNCLE_PROJECT_ROOT', str(ctx.project_root))
    script = str(ctx.root / 'scripts' / 'stagegate.sh')
    os.execvpe('bash', ['bash', script, *args], env)


def main(argv):
    command = argv[1] if len(argv) > 1 else 'plan'
    rest = argv[2:]
    if command == 'plan':
        ctx = context(rest[0] if rest else None)
        for key, value in plan(ctx).items():
            print('%-18s %s' % (key, value if not isinstance(value, list) else ', '.join(value) or '-'))
        return 0
    if command == 'run':
        return run(context(), rest)
    if command == 'run-state':
        if len(rest) != 1:
            sys.stderr.write('usage: driver.py run-state STATE\n')
            return 2
        return run_state(context(), rest[0])
    sys.stderr.write('usage: driver.py plan [PROJECT_ROOT] | run [ARGS...] | run-state STATE\n')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))

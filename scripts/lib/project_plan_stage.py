#!/usr/bin/env python3
"""Once-per-sectioned-stage duties; no plan schemas or acceptance checks change.

prepare DIRECTORY PLAN PROMPT creates the dedicated step's prompt.
verify DIRECTORY PLAN [--record] checks the reply and actual ignore behavior.
A receipt binds successful work to this invocation's section directory and files.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from project_plan_sections import final_text, prompt_contexts

COMPLETE = 'PROJECT_PLAN_STAGE_COMPLETE'


def required_paths(plan):
    """Probe common outputs for the selected ecosystems, plus universal local files.

    The agent still owes *every* ecosystem/default/custom entry, per the original
    prompt. These deterministic probes are an additional floor, not a replacement.
    """
    paths = ['.env', '.env.local', '.DS_Store']
    groups = [
        (r'node|npm|pnpm|yarn|javascript|typescript|vite|react|svelte|next[. /-]|package\.json',
         ['node_modules/probe', 'dist/probe', 'build/probe']),
        (r'svelte', ['.svelte-kit/probe']),
        (r'next[. /-]', ['.next/probe', 'out/probe']),
        (r'python|pytest|pip\b|pyproject', ['.venv/probe', '__pycache__/probe.pyc', '.pytest_cache/probe', 'probe.pyc']),
        (r'cargo|rust', ['target/probe']),
        (r'composer|php', ['vendor/probe']),
        (r'playwright', ['test-results/probe', 'playwright-report/probe', 'blob-report/probe', '.pw-browsers/probe']),
    ]
    for pattern, probes in groups:
        if re.search(pattern, plan, re.I):
            paths.extend(probes)
    return paths


def fingerprints(plan):
    paths = [Path(plan), Path('.gitignore')]
    if any(p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError('plan and .gitignore must be regular files')
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def verify(directory, plan, record=False):
    directory = Path(directory)
    receipt = directory / 'stage-duties.json'
    hashes = fingerprints(plan)
    if receipt.exists() and json.loads(receipt.read_text()) != hashes:
        raise ValueError('stage inputs or .gitignore changed after completion; start a new planning stage')
    paths = required_paths(Path(plan).read_text())
    # Test this file, not a user's global excludes or .git/info/exclude. No
    # commits, hooks, network, or signing are involved in the disposable index.
    with tempfile.TemporaryDirectory(prefix='uncle-ignore-check-') as scratch:
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        git = ['git', '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', '-c', 'core.excludesFile=' + os.devnull]
        subprocess.run(git + ['init', '-q', scratch], env=env, check=True, capture_output=True)
        Path(scratch, '.gitignore').write_bytes(Path('.gitignore').read_bytes())
        result = subprocess.run(git + ['check-ignore', '--no-index', '-z', '--stdin'], cwd=scratch, env=env,
                                input='\0'.join(paths) + '\0', text=True, capture_output=True)
    ignored = set(result.stdout.rstrip('\0').split('\0'))
    missing = [p for p in paths if p not in ignored]
    if result.returncode not in (0, 1) or missing:
        raise ValueError('ignore verification failed: ' + (', '.join(missing) or result.stderr.strip()))
    if record:
        if final_text(directory / 'stage-duties.jsonl').strip() != COMPLETE:
            raise ValueError('stage step did not confirm consistency and file duties')
        receipt.write_text(json.dumps(hashes, sort_keys=True) + '\n')
    elif not receipt.exists():
        raise ValueError('stage duties have no successful receipt')


def prepare(directory, plan, output):
    base = Path(__file__).resolve().parents[2] / 'prompts' / 'project-plan-investigate.md'
    contexts = prompt_contexts(base.read_text())
    duties = ''.join(text for owners, text in contexts if 'stage-ignore' in owners)
    consistency = next(text for owners, text in contexts if 'stage-consistency' in owners)
    text = ('Finish the sectioned project-plan stage once. The workers have finished; the driver assembled their plan.\n'
            'Read the assembled plan at `%s` and the authoritative requirements at '
            '`.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json`.\n'
            'Check consistency before updating .gitignore. If a contradiction remains, report it and stop; '
            'do not claim completion. Do not rewrite the plan or its packets.\n\n' % Path(plan).resolve())
    text += consistency + '\n' + duties
    text += ('\nPreserve existing project ignore rules. You own the stage file update; workers do not. '
             'When both duties are complete, reply with exactly %s and nothing else.\n' % COMPLETE)
    Path(output).write_text(text)


def main(argv):
    try:
        if len(argv) == 4 and argv[0] == 'prepare':
            prepare(*argv[1:])
        elif len(argv) in (3, 4) and argv[0] == 'verify' and argv[3:] in ([], ['--record']):
            verify(*argv[1:3], record=bool(argv[3:]))
        else:
            raise ValueError(__doc__)
    except (ValueError, OSError) as error:
        print('project plan stage: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

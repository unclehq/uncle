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


def stack_evidence(plan):
    """What the plan *does* rather than says: its verification commands and the files its steps own.

    Prose is full of ordinary words that are also ecosystem names (a linked-list "node", "react to errors", "no JavaScript"),
    and matching them demanded another stack's ignores and threw away the whole sectioned plan.  Commands and owned file
    names are language-neutral evidence of the stack the plan really builds.  Empty when the plan has neither."""
    lines = plan.splitlines()
    found = [line for line in lines if re.match(r'\s*Owns:', line)]
    inside = False
    for line in lines:
        if re.match(r'##\s+Verification commands\b', line):
            inside = True
        elif inside and re.match(r'##\s', line):
            inside = False
        elif inside:
            found.append(line)
    return '\n'.join(found)


def required_paths(plan):
    """Probe common outputs for the selected ecosystems, plus universal local files.

    The agent still owes *every* ecosystem/default/custom entry, per the original
    prompt. These deterministic probes are an additional floor, not a replacement.
    A stack with no entry here (Haskell, Zig, OCaml, anything) is never demanded anything beyond the universal files:
    the floor only ever names stacks it knows, so an unknown language cannot fail it.
    """
    paths = ['.env', '.env.local', '.DS_Store']
    evidence = stack_evidence(plan)
    text = evidence or plan
    # With commands and owned files to read, file extensions and tool names are reliable; read from whole prose,
    # only whole-word stack names count.
    loose = bool(evidence)
    groups = [
        (r'\b(?:npm|pnpm|typescript|vite|svelte|next\.?js|node\.?js|package\.json)\b'
         + (r'|\b(?:yarn|react|node|npx|vitest|jest|tsc)\b|\.(?:[cm]?[jt]sx?|svelte)\b' if loose else ''),
         ['node_modules/probe', 'dist/probe', 'build/probe']),
        (r'\bsvelte(?:kit)?\b', ['.svelte-kit/probe']),
        (r'\bnext\.?js\b|"next"\s*:', ['.next/probe', 'out/probe']),
        (r'\b(?:python|pytest|pip|pyproject)\b' + (r'|\.py\b' if loose else ''),
         ['.venv/probe', '__pycache__/probe.pyc', '.pytest_cache/probe', 'probe.pyc']),
        (r'\b(?:cargo|rust)\b' + (r'|\.rs\b' if loose else ''), ['target/probe']),
        (r'\b(?:composer|php)\b' + (r'|\.php\b' if loose else ''), ['vendor/probe']),
        (r'\bplaywright\b', ['test-results/probe', 'playwright-report/probe', 'blob-report/probe', '.pw-browsers/probe']),
    ]
    for pattern, probes in groups:
        if re.search(pattern, text, re.I):
            paths.extend(probes)
    return paths


def fingerprints(plan):
    paths = [Path(plan), Path('.gitignore')]
    if any(p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError('plan and .gitignore must be regular files')
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def ignore_gaps(plan):
    """(probe paths the current .gitignore does not ignore, git's error text or '').

    Test this file, not a user's global excludes or .git/info/exclude. No commits, hooks, network, or signing are involved in the
    disposable index."""
    paths = required_paths(Path(plan).read_text())
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
    failure = result.stderr.strip() if result.returncode not in (0, 1) else ''
    return missing, failure


def ignore_entries(missing):
    """The .gitignore lines that cover the probe paths the check found uncovered (`build/probe` -> `build/`)."""
    entries = []
    for path in missing:
        if path == 'probe.pyc':
            line = '*.pyc'
        elif path.endswith('/probe') or path.endswith('/probe.pyc'):
            line = path.rsplit('/', 1)[0] + '/'
        else:
            line = path
        if line not in entries:
            entries.append(line)
    return entries


def ignore_instruction(plan):
    """Tell the model exactly which lines to add, or '' when `.gitignore` already satisfies the driver's check.

    The driver demands these for the stack the plan names, whether or not this project's tooling writes there (a Vite project
    builds into `dist`, yet the Node floor also wants `build/`). A model that judges the existing file sufficient for the tooling
    then fails the check, twice; naming the lines removes the judgement."""
    try:
        missing, failure = ignore_gaps(plan)
    except (OSError, subprocess.SubprocessError):
        return ''
    entries = ignore_entries(missing) if not failure else []
    if not entries:
        return ''
    return ('The driver checks that `.gitignore` ignores a fixed set of paths for this stack, whether or not this project writes '
            'there, and it currently does not ignore: %s. Add exactly these lines to `.gitignore` (keep every existing rule):\n%s\n'
            "Do not decide they are unnecessary: the check is the driver's, not a judgement about this project's tooling.\n"
            % (', '.join(missing), ''.join('    %s\n' % entry for entry in entries)))


def verify(directory, plan, record=False):
    directory = Path(directory)
    receipt = directory / 'stage-duties.json'
    hashes = fingerprints(plan)
    if receipt.exists() and json.loads(receipt.read_text()) != hashes:
        raise ValueError('stage inputs or .gitignore changed after completion; start a new planning stage')
    missing, failure = ignore_gaps(plan)
    if failure or missing:
        raise ValueError('ignore verification failed: ' + (', '.join(missing) or failure))
    if record:
        if final_text(directory / 'stage-duties.jsonl').strip() != COMPLETE:
            raise ValueError('stage step did not confirm consistency and file duties')
        receipt.write_text(json.dumps(hashes, sort_keys=True) + '\n')
    elif not receipt.exists():
        raise ValueError('stage duties have no successful receipt')


def known_inconsistencies(plan):
    """Cross-section file-name conflicts found without a model (plan_consistency.py)."""
    try:
        from plan_consistency import findings
        return findings(Path(plan).read_text(encoding='utf-8'))
    except (ImportError, OSError, ValueError):
        return []


FIX_RULES = ('Fix a contradiction yourself with Edit on the assembled plan only, using a unique text anchor, and change the '
             'fewest places: keep the choice the requirements, the outline and most of the plan already use. Do not rewrite '
             'the plan, and do not touch its packets or any other file except `.gitignore`. Report and stop only if a '
             'contradiction needs a decision the requirements do not make.')


def prepare(directory, plan, output):
    base = Path(__file__).resolve().parents[2] / 'prompts' / 'project-plan-investigate.md'
    contexts = prompt_contexts(base.read_text())
    duties = ''.join(text for owners, text in contexts if 'stage-ignore' in owners)
    consistency = next(text for owners, text in contexts if 'stage-consistency' in owners)
    text = ('Finish the sectioned project-plan stage once. The workers have finished; the driver assembled their plan.\n'
            'Read the assembled plan at `%s` and the authoritative requirements at '
            '`.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json`.\n'
            'Check consistency before updating .gitignore. %s\n\n' % (Path(plan).resolve(), FIX_RULES))
    known = known_inconsistencies(plan)
    if known:
        text += ('The driver already found these, by comparing every file the plan mentions with the files its steps own. '
                 'Resolve each one:\n' + ''.join('- %s\n' % line for line in known) + '\n')
    text += consistency + '\n' + duties
    instruction = ignore_instruction(plan)
    if instruction:
        text += '\n' + instruction
    text += ('\nPreserve existing project ignore rules. You own the stage file update; workers do not. '
             'When both duties are complete, reply with exactly %s and nothing else.\n' % COMPLETE)
    Path(output).write_text(text)


def prepare_repair(directory, plan, output, reason=''):
    """The one second attempt: what the first attempt said, what the driver still finds, and the fix rules."""
    directory = Path(directory)
    previous = final_text(directory / 'stage-duties.jsonl').strip()
    text = ('The first pass over the assembled project plan did not finish. Do not start over and do not give up on the '
            'plan: repair it now, once.\n'
            'The assembled plan is `%s`; the requirements are `.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json`.\n\n'
            '%s\n\n' % (Path(plan).resolve(), FIX_RULES))
    if reason:
        text += 'The driver rejected the result because: %s\n\n' % reason
    if previous:
        text += 'The first pass said:\n\n%s\n\n' % previous[:6000]
    known = known_inconsistencies(plan)
    if known:
        text += 'The driver still finds:\n' + ''.join('- %s\n' % line for line in known) + '\n'
    instruction = ignore_instruction(plan)
    if instruction:
        text += instruction + '\n'
    text += ('Fix every contradiction listed, choosing for each the option that fits the requirements and most of the plan, '
             'then complete the `.gitignore` duties. When the plan is consistent and `.gitignore` is updated, reply with '
             'exactly %s and nothing else.\n' % COMPLETE)
    Path(output).write_text(text)


def main(argv):
    try:
        if len(argv) == 4 and argv[0] == 'prepare':
            prepare(*argv[1:])
        elif argv[0] == 'prepare-repair' and len(argv) in (4, 5):
            prepare_repair(*argv[1:])
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

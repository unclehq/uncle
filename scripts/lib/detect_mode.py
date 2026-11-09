#!/usr/bin/env python3
"""Decide whether a request is a NEW APPLICATION or a CHANGE to existing code, from the repository and the prompt.

Two independent kinds of evidence are scored, and the answer is only as confident as they agree:

  repository  how much real, non-scaffolding source is already here (empty / scaffold / existing / prior-uncle-build),
              plus run state: an in-progress CHANGE_PLAN or PROJECT_PLAN, a non-empty CHANGE_REQUEST.md
  prompt      change cues ("restyle", "fix", "the existing app"), new-build cues ("build me a", "from scratch"),
              and references to files or names that actually exist in the repository

The result is a mode (`new`, `change` or `ask`), a confidence, a `fallback` to use when nobody can be asked (the safer reading:
`change` whenever there is code that a new build could overwrite), and the reasons, so a person can see why.

Explicit flags always win over this; callers only use it for "auto".

usage:
  detect_mode.py [--project DIR] [--prompt TEXT | --prompt-file FILE] [--json | --field NAME | --summary]
"""
import argparse
import json
import os
import re
import subprocess
import sys

SKIP_DIRS = {'.git', '.uncle', '.claude', '.github', 'node_modules', 'dist', 'build', 'out', 'target', '__pycache__', '.venv',
             'venv', '.vite', '.next', '.cache', 'coverage', 'test-results', 'playwright-report', '.test-out', 'vendor'}
SOURCE_EXT = {'.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.py', '.go', '.rs', '.java', '.kt', '.c', '.cc', '.cpp', '.h', '.hpp',
              '.cs', '.rb', '.php', '.swift', '.sh', '.html', '.css', '.scss', '.vue', '.svelte', '.sql', '.lua', '.ex', '.exs',
              '.dart', '.scala', '.clj', '.hs', '.ml'}
# Present in a freshly created project and not evidence that anything has been built.
SCAFFOLD_NAMES = {'readme.md', 'requirements.md', 'claude.md', 'agents.md', 'change_request.md', 'license', 'license.md',
                  '.gitignore', '.gitattributes', '.editorconfig', 'package.json', 'package-lock.json', 'pnpm-lock.yaml',
                  'yarn.lock', 'pyproject.toml', 'requirements.txt', 'cargo.toml', 'cargo.lock', 'go.mod', 'go.sum',
                  'tsconfig.json', 'index.html', 'vite.config.js', 'vite.config.ts', 'playwright.config.js',
                  'playwright.config.ts', 'makefile'}
# A source file this small is boilerplate from a template, not an application.
SUBSTANTIAL_BYTES = 1500
MIN_REAL_FILES = 3

STRONG_CHANGE = re.compile(
    r"\b(fix|fixes|bug|bugs|regression|restyle|re-?style|refactor|rename|redesign|revamp|rework|existing|current(ly)?|"
    r"(this|the|our|my) (app|application|project|repo|repository|codebase|code|site|website|page|ui|component|module))\b", re.I)
WEAK_CHANGE = re.compile(
    r"\b(add|adds|update|updates|change|changes|improve|tweak|modify|remove|delete|migrate|upgrade|extend|support for|"
    r"instead of|rather than|currently|no longer|should (now|also))\b", re.I)
NEW_BUILD = re.compile(
    r"\b(build (me|a|an)|create (a|an|me)|make (a|an|me)|write (a|an|me)|develop (a|an)|implement (a|an) new|from scratch|brand new|"
    r"greenfield|scaffold|bootstrap|start (a|an) new|new (app|application|project|program|tool|website|game|service|cli|api))\b",
    re.I)
PATH_TOKEN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9]{1,5}\b|\b[A-Za-z0-9_-]+/[A-Za-z0-9_./-]+")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,}")
STOP_STEMS = {'index', 'main', 'readme', 'config', 'test', 'tests', 'style', 'styles', 'app', 'utils', 'helpers', 'module',
              'package', 'script', 'scripts', 'source', 'sources', 'build', 'public', 'assets', 'static', 'components'}


def _git(project, *args):
    try:
        out = subprocess.run(['git', '-C', project, *args], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def list_files(project):
    """Relative paths of the project's files: tracked and untracked-unignored when it is a git repository, else a walk."""
    out = _git(project, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')
    if out is not None:
        names = [n.decode('utf-8', 'replace') for n in out.split(b'\0') if n]
    else:
        names = []
        for base, dirs, files in os.walk(project):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                names.append(os.path.relpath(os.path.join(base, name), project))
    return [n for n in names if not (set(n.split('/')[:-1]) & SKIP_DIRS) and os.path.isfile(os.path.join(project, n))]


def _read(project, rel, limit=200000):
    try:
        with open(os.path.join(project, rel), encoding='utf-8', errors='replace') as fh:
            return fh.read(limit)
    except OSError:
        return ''


def repository_facts(project):
    files = list_files(project)
    source, real, test_files = [], [], []
    # A project created from uncle's own template carries uncle's scripts/ and prompts/; those are tooling, not the application.
    uncle_template = 'scripts/stagegate.sh' in files
    for rel in files:
        base = os.path.basename(rel).lower()
        ext = os.path.splitext(base)[1]
        if base in SCAFFOLD_NAMES or (uncle_template and rel.startswith(('scripts/', 'prompts/'))):
            continue
        if ext not in SOURCE_EXT:
            continue
        source.append(rel)
        try:
            size = os.path.getsize(os.path.join(project, rel))
        except OSError:
            size = 0
        if size >= SUBSTANTIAL_BYTES:
            real.append(rel)
        if re.search(r'(^|/)(tests?|__tests__|spec)(/|$)|\.(test|spec)\.[a-z]+$|_test\.[a-z]+$', rel):
            test_files.append(rel)
    commits = _git(project, 'rev-list', '--count', 'HEAD')
    commits = int(commits.decode().strip() or 0) if commits is not None and commits.strip().isdigit() else 0
    docs = os.path.join(project, '.uncle', 'docs')
    state = _read(project, '.uncle/workflow/state', 64).strip()

    def doc(name):
        return os.path.isfile(os.path.join(docs, name)) and bool(_read(project, '.uncle/docs/' + name, 64).strip())

    facts = {
        'files': len(files), 'source_files': len(source), 'substantial_source_files': len(real), 'test_files': len(test_files),
        'commits': commits, 'workflow_state': state,
        'attested_build': os.path.isfile(os.path.join(project, '.uncle', 'attestation.json'))
                          or (doc('UPDATED_PROJECT_PLAN.md') and state == 'COMPLETE'),
        'change_plan': doc('CHANGE_PLAN.md') or doc('CHANGE_SPEC.md'),
        'project_plan': doc('PROJECT_PLAN.md') or doc('UPDATED_PROJECT_PLAN.md'),
        'change_request': bool(_read(project, '.uncle/docs/CHANGE_REQUEST.md', 64).strip()
                               or _read(project, 'CHANGE_REQUEST.md', 64).strip()),
        'requirements_brief': bool(_read(project, '.uncle/docs/REQUIREMENTS.md', 64).strip()
                                   or _read(project, 'REQUIREMENTS.md', 64).strip()),
        'source_names': sorted(source),
        'all_files': files,
    }
    if facts['source_files'] == 0:
        facts['kind'] = 'empty'
    elif facts['substantial_source_files'] < MIN_REAL_FILES and facts['source_files'] <= 4:
        facts['kind'] = 'scaffold'
    else:
        facts['kind'] = 'prior-uncle-build' if facts['attested_build'] else 'existing'
    return facts


def prompt_facts(prompt, repo):
    text = prompt or ''
    strong = sorted({m.group(0).lower() for m in STRONG_CHANGE.finditer(text)})
    weak = sorted({m.group(0).lower() for m in WEAK_CHANGE.finditer(text)})
    new = sorted({m.group(0).lower() for m in NEW_BUILD.finditer(text)})
    names = {n.lower() for n in repo['all_files']}
    stems = {os.path.splitext(os.path.basename(n))[0].lower() for n in repo['source_names']} - STOP_STEMS
    refs = set()
    for token in PATH_TOKEN.findall(text) if text else []:
        token = token.strip('./').lower()
        if token and (token in names or any(n.endswith('/' + token) for n in names)):
            refs.add(token)
    for word in WORD.findall(text):
        if word.lower() in stems:
            refs.add(word.lower())
    return {'strong_change': strong, 'weak_change': weak, 'new_build': new, 'repo_references': sorted(refs), 'has_prompt': bool(text.strip())}


def classify(project, prompt=''):
    repo = repository_facts(project)
    pf = prompt_facts(prompt, repo)
    new_score = change_score = 0.0
    reasons = []

    kind = repo['kind']
    if kind == 'empty':
        new_score += 3
        reasons.append('the directory has no source code, so there is nothing to change')
    elif kind == 'scaffold':
        new_score += 2
        reasons.append('only template-sized source is present (%d file(s), %d substantial): a fresh scaffold' % (
            repo['source_files'], repo['substantial_source_files']))
    elif kind == 'existing':
        change_score += 3
        reasons.append('the repository holds %d source file(s) (%d substantial)%s' % (
            repo['source_files'], repo['substantial_source_files'],
            ', %d commit(s)' % repo['commits'] if repo['commits'] else ''))
    else:
        change_score += 3.5
        reasons.append('the repository is a finished uncle build (attested), so a new request is a change to it')
    if repo['commits'] >= 5 and kind in ('scaffold', 'existing', 'prior-uncle-build'):
        change_score += 0.5
    # Run state is stronger than inference: it is what the user already started.
    if repo['change_plan'] or repo['change_request']:
        change_score += 4
        reasons.append('a change request or change plan is already in progress here')
    if repo['project_plan'] and not repo['attested_build'] and repo['workflow_state'] not in ('', 'COMPLETE'):
        new_score += 4
        reasons.append('a new-application project plan is in progress (state %s)' % repo['workflow_state'])

    if pf['has_prompt']:
        c = min(3.0, 1.5 * len(pf['strong_change']) + 0.5 * len(pf['weak_change']))
        if pf['repo_references']:
            c += 3.0     # the request points at code that is really here: the strongest prompt evidence there is
            reasons.append('the request names things that exist in the repository: ' + ', '.join(pf['repo_references'][:5]))
        if c and (pf['strong_change'] or pf['weak_change']):
            reasons.append('the request reads like a change (%s)' % ', '.join((pf['strong_change'] + pf['weak_change'])[:5]))
        change_score += c
        if pf['new_build']:
            n = min(3.0, 1.5 * len(pf['new_build']))
            new_score += n
            reasons.append('the request reads like a new build (%s)' % ', '.join(pf['new_build'][:3]))

    diff = new_score - change_score
    mode = 'new' if diff >= 2 else 'change' if diff <= -2 else 'ask'
    confidence = 'high' if abs(diff) >= 4 else 'medium' if abs(diff) >= 2 else 'low'
    # A change cue in an empty directory, or a new-build cue over substantial code, is a contradiction, not a close call.
    conflict = ''
    if kind == 'empty' and (pf['strong_change'] or pf['repo_references']) and mode == 'new':
        conflict = 'the request sounds like a change, but this directory is empty: is the code somewhere else?'
    elif kind in ('existing', 'prior-uncle-build') and pf['new_build'] and not pf['repo_references'] and mode == 'change':
        conflict = 'the request sounds like a new build, but this directory already holds an application a new build would overwrite'
    if conflict:
        mode, confidence = 'ask', 'low'
        reasons.append(conflict)
    # Nobody to ask: the reading that cannot destroy existing work. A new build over code is the costly mistake.
    fallback = 'change' if kind in ('existing', 'prior-uncle-build') or repo['change_plan'] or repo['change_request'] else 'new'
    if mode != 'ask':
        fallback = mode
    for key in ('source_names', 'all_files'):
        repo.pop(key, None)
    return {'mode': mode, 'confidence': confidence, 'fallback': fallback, 'repository': kind, 'scores': {'new': new_score, 'change': change_score},
            'reasons': reasons, 'repo': repo, 'prompt': pf}


def summary(result):
    lines = ['Detected: %s (%s confidence); repository looks like %s.' % (result['mode'], result['confidence'], result['repository'])]
    lines += ['  - ' + r for r in result['reasons']]
    if result['mode'] == 'ask':
        lines.append('  Not decisive: if no one can be asked, use "%s".' % result['fallback'])
    return '\n'.join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--project', default='.')
    ap.add_argument('--prompt', default='')
    ap.add_argument('--prompt-file')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--field')
    ap.add_argument('--summary', action='store_true')
    args = ap.parse_args(argv[1:])
    prompt = args.prompt
    if args.prompt_file:
        try:
            prompt = open(args.prompt_file, encoding='utf-8', errors='replace').read()
        except OSError:
            pass
    result = classify(os.path.abspath(args.project), prompt)
    if args.field:
        value = result.get(args.field, '')
        print(value if isinstance(value, str) else json.dumps(value))
    elif args.summary:
        print(summary(result))
    else:
        print(json.dumps(result, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

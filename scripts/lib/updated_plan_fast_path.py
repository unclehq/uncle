#!/usr/bin/env python3
"""Produce an updated plan locally only when there is nothing to resolve."""
import argparse
import json
import re
from pathlib import Path


def read(path, kind):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema') != 'uncle.artifact/v1' or data.get('kind') != kind:
        raise ValueError('%s is not %s JSON' % (path, kind))
    return data


def protected_paths(plan):
    """Keep the updated-plan execution contract without another model call.

    Initial plans predate the dedicated field but carry the exact same list in
    the driver-owned frozen-path comment at the top of their command block.
    A clean review must preserve that contract deterministically.
    """
    paths = plan.get('protected_verification_paths')
    if isinstance(paths, str) and paths.strip():
        return paths
    commands = plan.get('verification_commands', '')
    for line in commands.splitlines():
        marker = '# Frozen verification paths:'
        if line.strip().lower().startswith(marker.lower()):
            paths = line.split(':', 1)[1].strip()
            if paths:
                return paths
    paths = _section_paths(plan.get('narrative', ''))
    if paths:
        return paths
    raise ValueError('project plan has no protected verification paths to preserve')


_PATHS_HEADING = re.compile(r'^#{1,6}\s+.*\bprotected\b.*\bpaths?\b', re.I)
_ANY_HEADING = re.compile(r'^#{1,6}\s')


def _section_paths(narrative):
    """Paths listed under the plan's own "Protected verification paths" heading, as bullets or one fenced block.

    The project-plan prompt asks for that section but not for the dedicated field, so a plan that followed it exactly
    still carried the list only here; ignoring it sent every clean review through a model call to copy the plan."""
    found, inside, fenced = [], False, False
    for line in (narrative or '').splitlines():
        stripped = line.strip()
        if not inside:
            inside = bool(_PATHS_HEADING.match(stripped))
            continue
        if stripped.startswith('```'):
            fenced = not fenced
            continue
        if not fenced and _ANY_HEADING.match(stripped):
            break
        text = re.sub(r'^[-*+]\s+', '', stripped).strip('`').strip()
        if text and not text.startswith('#') and ' ' not in text:
            found.append(text)
    return '\n'.join(dict.fromkeys(found))


# Older approved plans predate the dedicated protected-paths field.  These are
# still deterministic plan facts: test files and runner configs named by the
# plan or its verification commands.  Keep this small parser here rather than
# asking an updated-plan compiler to reproduce an unchanged list.
# Any language: a path-like token in the plan is a test file or runner config by its *name*, not by a list of languages.
PATH_TOKEN = re.compile(r'(?<![\w./-])((?:[\w.+-]+/)*[\w.+-]+\.[A-Za-z0-9]{1,8})(?![\w])')
TEST_DIRS = {'test', 'tests', 'spec', 'specs', '__tests__', 'e2e', 'integration', 'testing'}
# Docs, data and manifests are never the test itself, whatever directory they sit in.
NOT_CODE = {'md', 'markdown', 'txt', 'rst', 'json', 'lock', 'yml', 'yaml', 'toml', 'xml', 'csv', 'log', 'svg', 'png', 'jpg',
            'jpeg', 'gif', 'snap', 'html', 'css', 'ini', 'cfg'}
RUNNER_CONFIG = re.compile(r'^(?:(?:vitest|jest|playwright|cypress|karma)\.config\.[cm]?[jt]s|conftest\.py|pytest\.ini|tox\.ini'
                           r'|phpunit\.xml(?:\.dist)?|\.rspec)$')
# test_x.py, x_test.go, x.test.js, x.spec.ts, x-tests.rb, FooTest.java, ParserSpec.hs, FooTests.cs ...
TEST_NAME = re.compile(r'^(?:test[_-].+|.+[_-]tests?|.+[_-]spec|.+\.(?:test|spec)|.*[a-z0-9](?:Tests?|Specs?)|Tests?|Specs?)$')


def is_test_path(path):
    name = Path(path).name
    if RUNNER_CONFIG.match(name):
        return True
    stem, _, ext = name.rpartition('.')
    if not stem or ext.lower() in NOT_CODE:
        return False
    if TEST_NAME.match(stem):
        return True
    return any(part.lower() in TEST_DIRS for part in Path(path).parts[:-1])


def derive_protected_paths(text, commands=''):
    """Return named test/config paths, one per line, excluding generated files.  Recognized by name in any language."""
    found = []
    for match in PATH_TOKEN.finditer((text or '') + '\n' + (commands or '')):
        path = match.group(1)
        if (path.startswith(('.', '/', 'node_modules', 'dist/', 'build/', 'out/', 'coverage/', 'target/', 'vendor/',
                             'dist-newstyle/', 'bin/', 'obj/', '__pycache__/'))
                or '..' in path or path in found or path.endswith(('.json', '.lock')) or not is_test_path(path)):
            continue
        found.append(path)
    # A plan often mentions both `tests/e2e/keyboard.spec.js` and the shorter
    # `keyboard.spec.js` in prose. The latter cannot be matched against an
    # implementation step's repository-relative `Owns:` path. Prefer the
    # qualified spelling when both occur; retain a genuinely root-level test.
    qualified_names = {Path(path).name for path in found if '/' in path}
    found = [path for path in found if '/' in path or Path(path).name not in qualified_names]
    return '\n'.join(found[:40])


def render_view(payload, view, change=False):
    """Render the non-authoritative approval view from the JSON we just wrote."""
    import importlib.util
    artifact = Path(__file__).with_name('artifact_json.py')
    spec = importlib.util.spec_from_file_location('artifact_json', artifact)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rendered = (module.render_change_plan(payload, require_dispositions=True)
                if change else module.render_plan(payload, protected=True))
    Path(view).write_text(rendered + '\n', encoding='utf-8')


def build(project_plan, review, output, view=None):
    plan = read(project_plan, 'plan')
    assessment = read(review, 'adversarial-review')
    if assessment.get('findings'):
        return False
    result = dict(plan, dispositions=[], protected_verification_paths=protected_paths(plan))
    narrative = result.get('narrative', '')
    if narrative.startswith('# Project plan'):
        result['narrative'] = '# Updated project plan' + narrative[len('# Project plan'):]
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if view:
        render_view(result, view)
    return True


def build_change(change_plan, review, output, view=None):
    """Carry a clean change plan through its post-review revision locally.

    CHANGE_PLAN.md is rendered from this JSON by the normal ingest step.  The
    explicit empty dispositions list is meaningful: it records that the
    adversarial review had nothing to disposition, rather than omitting the
    post-review contract altogether.
    """
    plan = read(change_plan, 'change-plan')
    assessment = read(review, 'adversarial-review')
    if assessment.get('findings'):
        return False
    result = dict(plan, dispositions=[])
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if view:
        render_view(result, view, change=True)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--change', action='store_true',
                        help='copy a change-plan instead of an application plan')
    parser.add_argument('--render', metavar='MARKDOWN',
                        help='render this human approval view from the canonical JSON')
    parser.add_argument('project_plan'); parser.add_argument('review'); parser.add_argument('output')
    args = parser.parse_args()
    try:
        handler = build_change if args.change else build
        raise SystemExit(0 if handler(args.project_plan, args.review, args.output, args.render) else 1)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print('updated-plan fast path: ' + str(error))
        raise SystemExit(1)

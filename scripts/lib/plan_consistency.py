#!/usr/bin/env python3
"""Cross-section file-name check for an assembled project plan, without a model.

The section workers write in parallel from the same requirements and decide some things
independently. The commonest result is two names for one file: the components say
`src/styles.css` while another section says `src/theme.css`. Nothing declares the second, so
no step owns it and no validator notices; a model asked to "check consistency" found it, and
when it reported rather than fixed, the driver threw the assembled plan away.

This reads the plan's own model (steps' `owns`, components' `files`) and every backticked path
the prose mentions, and reports a mentioned source file that no step owns when an owned file
sits beside it with the same extension, or it lives under a directory the plan owns files in.

    plan_consistency.py check PLAN.md     one finding per line on stdout; exit 0 either way
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_model

SOURCE = {'js', 'jsx', 'ts', 'tsx', 'mjs', 'cjs', 'css', 'scss', 'html', 'json', 'py', 'md', 'vue', 'svelte'}
# Output of a build or a test run, driver state, or a file a package manager owns: mentioned, never owned.
GENERATED = re.compile(r'(^|/)(node_modules|dist|build|coverage|test-results|playwright-report|blob-report|\.mutants|'
                       r'\.uncle|\.git|\.vite|\.next|out)(/|$)|(^|/)package-lock\.json$|(^|/)\.build-')
TICKS = re.compile(r'`([^`\n]+)`')
PATH = re.compile(r'^(?:\./)?[A-Za-z0-9_.@-][A-Za-z0-9_./@-]*\.([A-Za-z0-9]+)$')
# A directory-qualified path in plain text, as table cells write them: `src/styles.css;` has no ticks.
BARE = re.compile(r'(?<![\w/.@-])((?:[A-Za-z0-9_.@-]+/)+[A-Za-z0-9_@-][A-Za-z0-9_.@-]*\.(?:%s))(?![\w/-])' % '|'.join(sorted(SOURCE)))


def clean(path):
    path = path.strip().removeprefix('./')
    return path


def collect(node, owned):
    if isinstance(node, dict):
        for key in ('owns', 'files'):
            values = node.get(key)
            if isinstance(values, list):
                owned.update(clean(v) for v in values if isinstance(v, str) and v.strip())
        for child in node.values():
            collect(child, owned)
    elif isinstance(node, list):
        for child in node:
            collect(child, owned)


def owned_files(text):
    owned = set()
    collect(plan_model.import_markdown(text), owned)
    return owned


def mentioned_files(text):
    found = {}
    for token in TICKS.findall(text):
        token = token.strip()
        # A command, a glob, a placeholder, a URL or a sentence is not a file name.
        if re.search(r'[\s*<>{}()$:=|;,]', token) or token.startswith(('http', '/')) or '..' in token:
            continue
        match = PATH.match(token)
        if not match or match.group(1).lower() not in SOURCE:
            continue
        path = clean(token)
        if not GENERATED.search(path):
            found[path] = found.get(path, 0) + 1
    for token in BARE.findall(text):
        path = clean(token)
        if not GENERATED.search(path) and 'http' not in path:
            found.setdefault(path, 0)
            found[path] += 1
    return found


def findings(text):
    owned = owned_files(text)
    if not owned:
        return []
    directories = {str(Path(p).parent) for p in owned}
    out = []
    for path in sorted(mentioned_files(text)):
        if path in owned:
            continue
        parent, suffix = str(Path(path).parent), Path(path).suffix
        beside = sorted(o for o in owned if str(Path(o).parent) == parent and Path(o).suffix == suffix)
        if beside:
            out.append('`%s` is mentioned but no step owns it, and `%s` is owned beside it: one file with two names?'
                       % (path, '`, `'.join(beside)))
        elif parent in directories and parent != '.':
            out.append('`%s` is mentioned but no step owns it (the plan owns other files in `%s/`).' % (path, parent))
    return out


def main(argv):
    if len(argv) != 2 or argv[0] != 'check':
        raise SystemExit(__doc__)
    try:
        text = Path(argv[1]).read_text(encoding='utf-8')
        for line in findings(text):
            print(line)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print('plan consistency check could not run: %s' % error, file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

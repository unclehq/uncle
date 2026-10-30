#!/usr/bin/env python3
"""Mechanical fixes for a scaffold that disagrees with the code it scaffolds.

The implementation is written by isolated parallel workers; the scaffold
(vitest.config.js, package.json, test file extensions) is written by one of
them too, in the same isolated pass, and routinely ends up pointing at the
wrong place: an include glob that does not match where the tests actually
landed, or a CommonJS require() in a file package.json declares an ES
module. Both failures are purely mechanical -- fixing them changes *where*
a check looks or *how* a file is parsed, never *what* it asserts or whether
it passes -- so they are fixed here deterministically, with no model in the
loop, rather than spending a bounded repair attempt an implementation agent
cannot usefully use against a file it may not even be allowed to touch.

Every fix returns a description of exactly what changed, for the caller to
record as an explicit, auditable deviation before touching a protected file
-- an unattributed protected-file change is exactly what the driver's own
verification-integrity check exists to catch, and rightly refuses.

usage: scaffold_reconcile.py PROJECT_ROOT
  Prints one JSON object per line to stdout, one per file actually changed:
  {"file": ..., "reason": ..., "before": ..., "after": ...}
  Exit status is 0 whether or not anything changed; a change is reported on
  stdout, not through exit status.
"""
import json
import os
import re
import sys
from pathlib import Path

# vitest's own convention is *.test.*; a *.spec.* file is Playwright's.
# Mixing the two into one vitest include glob would make vitest try to run
# Playwright specs (a different test() global, a different runtime) -- real
# new breakage, not a fix. The CJS/ESM rewrite is not vitest-specific, so it
# applies to both.
UNIT_TEST_FILE_RE = re.compile(r'\.test\.(jsx?|tsx?)$')
ANY_TEST_FILE_RE = re.compile(r'\.(?:test|spec)\.(jsx?|tsx?)$')
REQUIRE_NAMED = re.compile(r"^(\s*)const\s*\{([^}]*)\}\s*=\s*require\((['\"])([^'\"]+)\3\)\s*;?\s*$")
REQUIRE_DEFAULT = re.compile(r"^(\s*)const\s+(\w+)\s*=\s*require\((['\"])([^'\"]+)\3\)\s*;?\s*$")


def find_test_files(root, pattern=ANY_TEST_FILE_RE):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('node_modules', 'dist', '.git', '.uncle')]
        for name in filenames:
            if pattern.search(name):
                found.append(os.path.relpath(os.path.join(dirpath, name), root))
    return found


def glob_matches(pattern, relpath):
    # vitest/minimatch-equivalent subset actually used by these configs:
    # '**' (any depth), '*' (one segment, any chars), literal segments, and a
    # brace list like {js,jsx}. Sufficient for the include lists this fixes;
    # never claims to be a general glob engine.
    brace = re.match(r'^(.*)\{([^}]+)\}(.*)$', pattern)
    if brace:
        prefix, options, suffix = brace.groups()
        return any(glob_matches(prefix + option + suffix, relpath) for option in options.split(','))
    regex = re.escape(pattern).replace(r'\*\*/', '(?:.*/)?').replace(r'\*\*', '.*').replace(r'\*', '[^/]*')
    return re.fullmatch(regex, relpath.replace(os.sep, '/')) is not None


def fix_vitest_discovery(root):
    """Widen vitest.config.js's include list if it matches none of the
    project's actual *.test.* files. Only ever adds a pattern; an existing
    pattern, and therefore whatever it already covered, is never removed or
    narrowed."""
    config_path = Path(root) / 'vitest.config.js'
    try:
        text = config_path.read_text(encoding='utf-8')
    except OSError:
        return None
    match = re.search(r'include\s*:\s*\[([^\]]*)\]', text, re.S)
    if not match:
        return None
    existing = re.findall(r"""['"]([^'"]+)['"]""", match.group(1))
    test_files = find_test_files(root, UNIT_TEST_FILE_RE)
    if not test_files:
        return None
    if any(glob_matches(pattern, f) for pattern in existing for f in test_files):
        return None  # at least one real test file is already discoverable
    # Group uncovered files by directory depth and propose the narrowest glob
    # that would have covered all of them, preferring directories actually
    # used by more than one file.
    by_dir = {}
    for f in test_files:
        by_dir.setdefault(os.path.dirname(f).replace(os.sep, '/'), []).append(f)
    new_patterns = []
    for directory in sorted(by_dir):
        exts = sorted({f.rsplit('.', 1)[-1] for f in by_dir[directory]})
        ext_group = exts[0] if len(exts) == 1 else '{%s}' % ','.join(exts)
        pattern = ('%s/*.test.%s' % (directory, ext_group)) if directory else ('*.test.%s' % ext_group)
        if pattern not in existing:
            new_patterns.append(pattern)
    if not new_patterns:
        return None
    new_include = match.group(1).rstrip()
    separator = ',\n    ' if new_include.rstrip().endswith(',') or not new_include.strip() else ',\n    '
    new_include_block = new_include + (separator if new_include.strip() else '') \
        + ', '.join("'%s'" % p for p in new_patterns)
    new_text = text[:match.start(1)] + new_include_block + text[match.end(1):]
    config_path.write_text(new_text, encoding='utf-8')
    return {
        'file': 'vitest.config.js',
        'reason': "include matched none of the project's *.test.* files (%s); "
                   'widened it to also cover %s. Nothing already covered was removed.'
                   % (', '.join(existing) or '(none)', ', '.join(new_patterns)),
        'before': match.group(0),
        'after': 'include: [%s]' % new_include_block,
    }


def fix_cjs_requires_in_esm(root):
    """package.json says "type": "module", so Node parses every plain .js
    file as an ES module; a file still using top-of-file CommonJS require()
    throws ReferenceError before a single test in it can run. Rewrite only
    recognizable, simple require() assignment lines to the equivalent
    import; anything else in the file -- including every assertion -- is
    untouched."""
    package_path = Path(root) / 'package.json'
    try:
        package = json.loads(package_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    if package.get('type') != 'module':
        return []
    changes = []
    for relpath in find_test_files(root):
        if not relpath.endswith('.js'):
            continue  # .mjs/.cjs are unambiguous either way; nothing to fix
        full = Path(root) / relpath
        try:
            lines = full.read_text(encoding='utf-8').splitlines()
        except OSError:
            continue
        before_lines, after_lines, new_lines = [], [], []
        for line in lines:
            named = REQUIRE_NAMED.match(line)
            default = REQUIRE_DEFAULT.match(line)
            if named:
                indent, names, _quote, module = named.groups()
                new_line = "%simport {%s} from '%s';" % (indent, names, module)
            elif default:
                indent, name, _quote, module = default.groups()
                new_line = "%simport %s from '%s';" % (indent, name, module)
            else:
                new_line = None
            if new_line is not None:
                before_lines.append(line)
                after_lines.append(new_line)
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        if not before_lines:
            continue
        full.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
        changes.append({
            'file': relpath,
            'reason': 'package.json declares "type": "module", so this plain .js file is parsed as an ES '
                      'module and its top-of-file CommonJS require() throws before any test in it can run. '
                      'Rewrote only the require() assignment lines to the equivalent import; no other line, '
                      'including every assertion in the file, was changed.',
            'before': '\n'.join(before_lines),
            'after': '\n'.join(after_lines),
        })
    return changes


def main(argv):
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    root = argv[0]
    changes = []
    vitest_change = fix_vitest_discovery(root)
    if vitest_change:
        changes.append(vitest_change)
    changes.extend(fix_cjs_requires_in_esm(root))
    for change in changes:
        print(json.dumps(change))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

"""Read-only compatibility checks before dependency setup and verification."""
import json
from pathlib import Path
import re
import subprocess

from execution_options import option


def version(value):
    match = re.fullmatch(r'v?(\d+)(?:\.(\d+))?(?:\.(\d+))?', value.strip())
    if not match:
        raise ValueError('Unsupported version: ' + value)
    return tuple(int(part or 0) for part in match.groups())


def accepts_node(expression, installed):
    """Evaluate the release ranges used by engines.node, without loading project JS."""
    def bounds(value):
        parts = value.lstrip('v').split('.')
        if len(parts) > 3 or any(not re.fullmatch(r'\d+|[xX*]', p) for p in parts):
            raise ValueError('Unsupported engines.node range: ' + expression)
        fixed = []
        for part in parts:
            if part in ('x', 'X', '*'):
                break
            fixed.append(int(part))
        low = tuple(fixed + [0] * (3 - len(fixed)))
        high = None
        if len(fixed) < 3 and fixed:
            high = tuple(fixed[:-1] + [fixed[-1] + 1] + [0] * (3 - len(fixed)))
        return low, high, len(fixed)

    def comparator(op, text):
        low, high, count = bounds(text)
        if not count:
            return op not in ('<', '>')
        if op == '^':
            index = next((i for i, n in enumerate(low) if n), count - 1)
            upper = low[:index] + (low[index] + 1,) + (0,) * (2 - index)
            return low <= installed < upper
        if op == '~':
            index = min(count - 1, 1)
            upper = low[:index] + (low[index] + 1,) + (0,) * (2 - index)
            return low <= installed < upper
        if op == '>=':
            return installed >= low
        if op == '>':
            return installed >= high if high else installed > low
        if op == '<':
            return installed < low
        if op == '<=':
            return installed < high if high else installed <= low
        return low <= installed < high if high else installed == low

    matched = False
    for branch in expression.split('||'):
        branch = branch.strip()
        hyphen = re.fullmatch(r'(\S+)\s+-\s+(\S+)', branch)
        if hyphen:
            lower, upper = hyphen.groups()
            result = comparator('>=', lower) and comparator('<=', upper)
        else:
            branch = re.sub(r'([<>]=?|[~^=])\s+', r'\1', branch)
            tokens = branch.split()
            result = True
            for token in tokens:
                match = re.fullmatch(r'(>=|<=|>|<|~|\^|=)?([v\d*xX][\d.xX*]*)', token)
                if not match:
                    raise ValueError('Unsupported engines.node range: ' + expression)
                result = comparator(match[1] or '=', match[2]) and result
        matched |= result
    return matched


def read_package(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Expected a JSON object in ' + str(path))
    return data


def playwright_version(root, package, installing=False, prefer_lock=False):
    if not installing:
        installed = root / 'node_modules/@playwright/test/package.json'
        if installed.is_file() and not prefer_lock:
            return read_package(installed).get('version'), str(installed)
        for name in ('npm-shrinkwrap.json', 'package-lock.json'):
            lock = root / name
            if lock.is_file():
                data = read_package(lock)
                entry = data.get('packages', {}).get('node_modules/@playwright/test', {})
                entry = entry or data.get('dependencies', {}).get('@playwright/test', {})
                if entry.get('version'):
                    return entry['version'], str(lock)
        if installed.is_file():
            return read_package(installed).get('version'), str(installed)
    for section in ('devDependencies', 'dependencies', 'optionalDependencies'):
        declared = package.get(section, {}).get('@playwright/test', '')
        if re.fullmatch(r'v?\d+\.\d+\.\d+', declared):
            return declared, str(root / 'package.json')
    return None, ''


def check(root='.', installing=False, prefer_lock=False):
    if option('dependency-version-check', '1').lower() not in ('1', 'true'):
        return
    root = Path(root)
    manifest = root / 'package.json'
    if not manifest.is_file():
        return
    package = read_package(manifest)
    floor_text = option('playwright-min-version', '1.50')
    floor = version(floor_text)[:2]
    resolved, source = playwright_version(root, package, installing, prefer_lock)
    if resolved and version(resolved.split('-', 1)[0].split('+', 1)[0])[:2] < floor:
        raise ValueError('DEPENDENCY_VERSION: %s resolves @playwright/test %s, below %s; '
                         'use a current stable range (for example latest) and refresh the lockfile/install '
                         'through the existing repair or plan-review path; keep the installed Node.' %
                         (source, resolved, floor_text))
    engine = package.get('engines', {}).get('node')
    if engine:
        try:
            result = subprocess.run(['node', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode:
                raise ValueError('node --version failed')
            installed = version(result.stdout.strip())
            accepted = accepts_node(engine, installed)
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            raise ValueError('DEPENDENCY_VERSION: cannot check %s engines.node %r: %s; '
                             'verify compatibility with the installed Node without switching runtimes.' %
                             (manifest, engine, error)) from error
        if not accepted:
            raise ValueError('DEPENDENCY_VERSION: %s engines.node %r excludes installed Node %s; '
                             'use compatible dependencies and an engines.node range accepting Node major %s '
                             'through the existing repair or plan-review path; do not install or switch Node.' %
                             (manifest, engine, '.'.join(map(str, installed)), installed[0]))

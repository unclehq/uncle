#!/usr/bin/env python3
"""Reuse a completed plan review only for an identical local input snapshot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def key(output, prompt, runner, model, effort):
    root = Path.cwd().resolve()
    excluded = output.resolve()
    # Budget changes can make a preserved review acceptable without new analysis.
    text = prompt.read_text()
    text = re.sub(r'(?ms)^# Compact output budgets \(binding\).*?(?=^# Reviewer output|\Z)', '', text)
    settings = {name: os.environ.get(name) for name in (
        'WORKFLOW_KIMI_CMD', 'WORKFLOW_KIMI_MODEL', 'WORKFLOW_CLINE_CMD',
        'UNCLE_CLINE_MODEL', 'UNCLE_CLINE_EFFORT', 'WORKFLOW_CLAUDE_CMD',
        'WORKFLOW_CODEX_CMD')}
    result = hashlib.sha256(json.dumps([str(root), str(excluded), text, runner, model, effort, settings]).encode())
    executable = shutil.which(runner)
    if executable:
        result.update(Path(executable).read_bytes())
    if shutil.which('git'):
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, timeout=5)
        if head.returncode == 0:
            result.update(head.stdout)
    total = 0
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {'.git', '.uncle', '__pycache__'})
        for name in sorted(dirs + files):
            path = Path(current) / name
            if path.resolve() == excluded or name.endswith('.pyc'):
                continue
            if path.is_symlink():
                raise ValueError('symlink input: cache disabled')
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError('non-file input: cache disabled')
            total += path.stat().st_size
            if total > 100_000_000:
                raise ValueError('input snapshot exceeds 100 MB: cache disabled')
            result.update(json.dumps(str(path.relative_to(root))).encode())
            result.update(hashlib.sha256(path.read_bytes()).digest())
    # Runtime state/logs are excluded, but project configuration is an input.
    config = root / '.uncle/config'
    if config.exists():
        result.update(config.read_bytes())
    return result.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['key', 'save', 'restore'])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prompt', type=Path)
    p.add_argument('--runner', default='')
    p.add_argument('--model', default='')
    p.add_argument('--effort', default='')
    p.add_argument('--key', default='')
    p.add_argument('--cache-dir', type=Path)
    args = p.parse_args()
    try:
        if args.action == 'key':
            print(key(args.output, args.prompt, args.runner, args.model, args.effort))
            return 0
        if not re.fullmatch(r'[a-f0-9]{64}', args.key):
            return 1
        cache = args.cache_dir / (args.key + '.json')
        if args.action == 'save':
            content = args.output.read_text()
            record = {'key': args.key, 'content': content, 'sha256': digest(content.encode())}
            args.cache_dir.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=args.cache_dir)
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
                json.dump(record, out)
            os.replace(name, cache)
        else:
            record = json.loads(cache.read_text())
            if record['key'] != args.key or digest(record['content'].encode()) != record['sha256']:
                return 1
            if args.output.exists() and digest(args.output.read_bytes()) != record['sha256']:
                return 1
            if not args.output.exists():
                fd, name = tempfile.mkstemp(dir=args.output.parent)
                with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
                    out.write(record['content'])
                os.replace(name, args.output)
        return 0
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return 1


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    raise SystemExit(main())

"""Validate a compacted candidate before atomically replacing its original."""
import argparse
from collections import Counter
import hashlib
import os
from pathlib import Path
import re
import tempfile
import time
from build_timing import event


def protected(text):
    # Conservative: compact surrounding prose, not executable or tabular contracts.
    fences = re.findall(r'^```[^\n]*\n.*?^```[ \t]*$', text, re.M | re.S)
    fences += re.findall(r'^~~~[^\n]*\n.*?^~~~[ \t]*$', text, re.M | re.S)
    tables = [line.strip() for line in text.splitlines() if line.strip().startswith('|')]
    ids = set(re.findall(r'\b(?:AC|REQ|FR|AR|FA|MC|DD|I|S|D)-[A-Za-z0-9_.-]+\b', text))
    refs = set(re.findall(r'`[^`\n]+`|https?://[^\s)]+|[\w./-]+\.(?:md|jsonl?|log|tsv|py|sh)(?::\d+(?:-\d+)?)?', text))
    headings = [line.strip() for line in text.splitlines() if re.match(r'^#{1,6}\s',line)]
    return Counter(fences + tables + headings), ids, refs


def replace(original, candidate):
    original, candidate = Path(original), Path(candidate)
    if original.is_symlink() or candidate.is_symlink() or original.resolve() == candidate.resolve():
        raise ValueError('Use distinct regular original and candidate files')
    before, after = original.read_bytes(), candidate.read_bytes()
    if not after or len(after) >= len(before):
        raise ValueError('Candidate must be nonempty and smaller')
    old, new = protected(before.decode('utf-8')), protected(after.decode('utf-8'))
    if old[0] - new[0] or not old[1] <= new[1] or not old[2] <= new[2]:
        raise ValueError('Candidate removes or changes protected headings, tables, commands, IDs, or references')
    verdict = re.compile(r'^(?:READY|NOT READY|READY WITH NON-BLOCKING ISSUES)$', re.M)
    if verdict.findall(before.decode()) != verdict.findall(after.decode()):
        raise ValueError('Candidate changes verdict')
    # Preserve a recoverable source even after successful replacement.
    backup_dir = original.parent / '.uncle' / 'workflow' / 'compaction-backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (original.name + '-' + hashlib.sha256(before).hexdigest())
    if not backup.exists():
        backup.write_bytes(before)
    fd, temp = tempfile.mkstemp(dir=original.parent,prefix='.compact-')
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(after)
        if original.read_bytes() != before:
            raise ValueError('Original changed while validating; candidate not applied')
        os.chmod(temp, original.stat().st_mode & 0o777)
        os.replace(temp,original)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return len(before),len(after)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original');parser.add_argument('candidate')
    args=parser.parse_args()
    started,tick=time.time(),time.monotonic()
    try:
        before,after=replace(args.original,args.candidate)
    except (OSError,ValueError) as error:
        event('document_compaction',Path(args.original).name,started,time.monotonic()-tick,1,validation='rejected')
        parser.exit(1,f'Compaction rejected; original retained: {error}\n')
    event('document_compaction',Path(args.original).name,started,time.monotonic()-tick,0,before_bytes=before,after_bytes=after,saved_bytes=before-after)
    print(f'Compaction accepted: {before} -> {after} bytes; saved {before-after}.')

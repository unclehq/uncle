#!/usr/bin/env python3
"""Write a finished, audited change as a hand-off for a host that publishes it (issue 205).

For workspaces that can run git but cannot push or call `gh`: instead of pushing a branch and opening a PR, Uncle
writes `.uncle/handoff/handoff.json` and the host creates the branch, writes the files and opens the PR through the
hosting API. Nothing here touches a remote, `gh` or the user's index. The change is exactly the tree the audit bound
(`commit_tree` in the PR journal) against the base commit it was bound to (`original_head`).

    handoff_export.py [OUT_DIR]        prints the hand-off path; exit 0 (a hand-off is a success)
"""
import base64
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

STATE = Path('.uncle/workflow')
JOURNAL = STATE / 'pr' / 'journal.json'
ZERO = '0' * 40
SCHEMA = 'uncle.handoff/v1'


def git(*args, raw=False):
    out = subprocess.run(['git', *args], check=True, stdout=subprocess.PIPE).stdout
    return out if raw else out.decode().strip()


def read(path):
    try:
        return Path(path).read_text()
    except OSError:
        return ''


def verdict():
    for name in ('audit-verdict.original', 'audit-verdict'):
        row = read(STATE / name).strip().split('\t')
        if len(row) == 3:
            return row[1]
    return 'UNKNOWN'


def load_attestation(lib):
    spec = importlib.util.spec_from_file_location('attestation', Path(lib) / 'attestation.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def title(journal):
    text = read('.uncle/docs/CHANGE_REQUEST.md')
    match = re.search(r'^##\s+(?:\d+\.\s+)?Summary\s*\n(.*?)(?=^##\s|\Z)', text, re.M | re.S | re.I)
    line = ' '.join((match.group(1) if match else '').split())[:72].strip()
    return line or 'Completed change'


def changes(base, tree):
    """Every changed path between the base commit and the audited tree: action, mode and full new content."""
    old = base if base else '4b825dc642cb6eb9a060e54bf8d69288fbd2f15'      # the empty tree when there is no base
    fields = git('diff-tree', '-r', '-z', '--raw', '--no-renames', '--no-abbrev', old, tree, raw=True).split(b'\0')
    rows, i = [], 0
    while i + 1 < len(fields) and fields[i]:
        meta = fields[i].decode().lstrip(':').split()
        path = fields[i + 1].decode('utf-8', 'surrogateescape')
        old_mode, new_mode, old_oid, new_oid, status = meta[0], meta[1], meta[2], meta[3], meta[4][0]
        i += 2
        if '160000' in (old_mode, new_mode):
            raise ValueError('a submodule change (%s) cannot be handed off' % path)
        row = {'path': path, 'action': {'A': 'add', 'M': 'modify', 'D': 'delete', 'T': 'modify'}[status]}
        if status == 'D':
            rows.append(row)
            continue
        data = git('cat-file', 'blob', new_oid, raw=True)
        row.update(mode=new_mode, oid=new_oid, size=len(data), encoding='base64',
                   content=base64.b64encode(data).decode())
        rows.append(row)
    return rows


def main():
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else '.uncle/handoff')
    try:
        journal = json.loads(JOURNAL.read_text())
    except (OSError, ValueError):
        raise ValueError('No audited change to hand off: the PR binding is missing; rerun the final audit.')
    tree, base = journal.get('commit_tree') or '', journal.get('original_head') or ''
    if not re.fullmatch(r'[0-9a-f]{40}', tree):
        raise ValueError('No audited tree is bound; rerun the final audit.')
    lib = os.environ.get('UNCLE_LIB_DIR') or str(Path(__file__).resolve().parent)
    attest = load_attestation(lib)
    sealed = dict(journal.get('attestation') or {})
    if not sealed:
        # Only this no-attestation fallback is stamped here; a journal attestation is used as attest-handoff sealed it.
        sealed = attest.seal(journal, STATE, root='.', version=os.environ.get('UNCLE_VERSION', ''), lib=lib)
        sealed['gate_publication'] = 'handoff (published by the host)'
    result = verdict()
    draft = not result.startswith('READY')
    summary = ('Built by an unattended Uncle run; no human reviewed this change or the generated text. '
               'Final audit verdict: %s. Findings are in .uncle/docs/FINAL_AUDIT.md.' % result.lower())
    body = '## Work summary\n\n' + summary + '\n'
    if draft:
        body = ('> [!WARNING]\n> **Final audit verdict: %s.** The PR reviewer decides whether this merges.\n\n'
                % result + body)
    body = attest.attach_body(body, sealed)
    body = (journal.get('body_banners') or '') + body      # computed by attest-handoff, not recomputed here
    origin = (journal.get('origin') or '').strip().split('\t')
    if len(origin) == 3 and origin[1].isdigit():
        body += '\nRefs %s#%s\n' % (origin[0], origin[1])
    name = title(journal)
    branch = journal.get('head_branch') or 'uncle/change'
    rows = changes(base, tree)
    handoff = {'schema': SCHEMA, 'base_commit': base, 'head_branch': branch,
               'base_repo': journal.get('base_repo') or (origin[0] if len(origin) == 3 else ''),
               'commit_message': name + '\n\n' + body, 'pr_title': name, 'pr_body': body, 'draft': draft,
               'audit_verdict': result, 'tree': tree, 'audited_tree': journal.get('audited_tree') or tree, 'attestation': sealed, 'changes': rows}
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / 'handoff.json'
    path.write_text(json.dumps(handoff, indent=1, sort_keys=True) + '\n')
    print('Hand-off written: %s (%d changed paths, base %s, tree %s, %s).' %
          (path, len(rows), base[:12] or 'none', tree[:12], 'draft' if draft else 'ready'))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, subprocess.CalledProcessError) as error:
        print('Hand-off failed: %s' % error, file=sys.stderr)
        sys.exit(1)

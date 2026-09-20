#!/usr/bin/env python3
"""Isolation and write guard around every triage master turn.

The master never runs in the live tree. Each turn gets a sandbox mirror of the
project; when the turn ends the sandbox is diffed against what it started
with, and only during an execute turn, and only for allowed paths, is the
difference copied into the live tree. Everything else is refused: the sandbox
is dropped, so nothing the model wrote survives.

Two things are outside the sandbox and are checked by hash rather than by
diff: the forbidden set on the live tree (approvals, reviewer artifacts,
waivers, driver state, this guard's own evidence), whose pre-turn bytes are
restored if the model reached them anyway, and the installed uncle tree, whose
modification taints the run so resume is refused.

Usage:
  triage_guard.py begin --state-dir D --project P --root R --turn N --mode M
      prints JSON {"sandbox": path, "digest": hex}
  triage_guard.py end --state-dir D --project P --root R --turn N --mode M
      --digest hex [--proposal TEXT]
      prints JSON {"applied": [...], "refused": [...], "failed": [...],
                   "no_edit": bool, "tainted": bool, "messages": [...]}
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FORBIDDEN_FILES = (
    'ADVERSARIAL_REVIEW.md', 'MANUAL_CHECKLIST.md', 'TEST_REVIEW.md', 'FINAL_AUDIT.md',
)
FORBIDDEN_WORKFLOW_FILES = (
    'unattended-gates', 'repair-limit', 'repair-count', 'state', 'stop-reason',
    'green-check-override', 'verification.manifest', 'verification.paths',
    'verification.snapshot', 'VERIFICATION_INTEGRITY.md', 'TEST_CHANGES.diff',
    'triage-actions.tsv', 'TRIAGE.md',
)
FORBIDDEN_WORKFLOW_DIRS = ('approvals', 'waivers', 'triage')
FORBIDDEN_WORKFLOW_PREFIXES = ('green-check.',)
# Sandboxes live below .uncle/workflow/parallel.  Excluding that directory is
# essential for copy-mode projects (including unborn Git repositories): without
# it copytree descends into the sandbox it is creating and never reaches a
# worker launch.
SANDBOX_EXCLUDES = ('.git', '.pw-browsers', 'node_modules', '.venv',
                    '.uncle/workflow-history', '.uncle/workflow/logs',
                    '.uncle/workflow/triage', '.uncle/workflow/parallel')
INSTALL_PINS = ('uncle_tui.py', 'scripts')
TSV_HEADER = 'ts\tturn\tproposal\toutcome\tpath\tbefore\tafter\n'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def is_forbidden(rel):
    """Whether a project-relative path may never be written by the master."""
    parts = rel.split('/')
    if rel == '.uncle/workflow/triage-actions.tsv' or rel.startswith('.uncle/workflow/triage/'):
        return True
    if parts[0] == '.uncle':
        return False
    if rel.lower().endswith('.md') and '.git' not in parts:
        return False
    if rel in FORBIDDEN_FILES:
        return True
    if parts[:2] == ['.uncle', 'workflow'] and len(parts) > 2:
        name = parts[2]
        if name in FORBIDDEN_WORKFLOW_DIRS or name in FORBIDDEN_WORKFLOW_FILES:
            return True
        if any(name.startswith(prefix) for prefix in FORBIDDEN_WORKFLOW_PREFIXES):
            return True
    return False


def install_pinned(rel, project, root):
    """Whether a project-relative path is part of the installed uncle tree.

    The install is immutable whether or not it is the project being worked
    on: when developing uncle itself the launch paths of the TUI and scripts
    are pinned by name.
    """
    root = os.path.realpath(root)
    project = os.path.realpath(project)
    if root == project or root.startswith(project + os.sep):
        inner = os.path.relpath(root, project)
        base = '' if inner == '.' else inner + '/'
        return any(rel == base + pin or rel.startswith(base + pin + '/') for pin in INSTALL_PINS)
    live = os.path.realpath(os.path.join(project, rel))
    return live == root or live.startswith(root + os.sep)


def walk(base, excludes=()):
    """{relpath: [sha256, mode]} for every regular file and symlink under base."""
    base = Path(base)
    out = {}
    for dirpath, dirnames, filenames in os.walk(base):
        rel_dir = os.path.relpath(dirpath, base)
        rel_dir = '' if rel_dir == '.' else rel_dir
        keep = []
        for d in dirnames:
            rel = os.path.join(rel_dir, d) if rel_dir else d
            if rel in excludes or rel.startswith('.uncle/workflow/parallel') or d == '__pycache__':
                continue
            keep.append(d)
        dirnames[:] = keep
        for name in filenames:
            rel = os.path.join(rel_dir, name) if rel_dir else name
            if rel in excludes or rel.startswith('.uncle/workflow/parallel'):
                continue
            full = base / rel
            try:
                st = os.lstat(full)
            except OSError:
                continue
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ['link:' + hashlib.sha256(os.readlink(full).encode()).hexdigest(), st.st_mode & 0o7777]
            elif stat.S_ISREG(st.st_mode):
                out[rel] = [sha256(full), st.st_mode & 0o7777]
    return out


def install_inventory(project, root):
    """{root-relative path: [sha256, mode]} of the installed tree: the whole
    install, or the pinned launch paths when the install is the project."""
    root = os.path.realpath(root)
    project = os.path.realpath(project)
    if root == project or root.startswith(project + os.sep):
        inv = {}
        for pin in INSTALL_PINS:
            target = os.path.join(root, pin)
            if os.path.isdir(target):
                inv.update({pin + '/' + k: v for k, v in walk(target).items()})
            elif os.path.isfile(target):
                inv[pin] = [sha256(target), os.stat(target).st_mode & 0o7777]
        return inv
    return walk(root, excludes=('.git',))


def forbidden_live_paths(project):
    """Every existing live path in the forbidden set."""
    project = Path(project)
    found = []
    for name in FORBIDDEN_FILES:
        if (project / name).is_file():
            found.append(name)
    wf = project / '.uncle' / 'workflow'
    if wf.is_dir():
        for entry in sorted(os.listdir(wf)):
            rel = '.uncle/workflow/' + entry
            if entry == 'triage':
                continue  # the guard's own directory; checked by digest
            if is_forbidden(rel):
                full = wf / entry
                if full.is_dir():
                    found.extend(rel + '/' + k for k in walk(full))
                elif full.is_file():
                    found.append(rel)
    return found


def git_ok(project):
    try:
        subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=project, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def copy_entry(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    if src.is_symlink():
        os.symlink(os.readlink(src), dst)
    else:
        shutil.copy2(src, dst)


def make_sandbox(project, sandbox):
    """A mirror of the working tree: git worktree plus the dirty overlay, or a copy."""
    project = Path(project)
    sandbox = Path(sandbox)
    drop_sandbox(project, sandbox)
    sandbox.parent.mkdir(parents=True, exist_ok=True)
    if git_ok(project):
        result = subprocess.run(['git', 'worktree', 'add', '--detach', str(sandbox), 'HEAD'], cwd=project,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode:
            raise ValueError('Cannot create recovery worktree: ' + result.stderr.strip())
        status = subprocess.run(['git', 'status', '--porcelain', '-z', '--untracked-files=all'],
                                cwd=project, check=True, stdout=subprocess.PIPE).stdout.decode('utf-8', 'replace')
        entries = status.split('\0')
        i = 0
        while i < len(entries):
            entry = entries[i]
            i += 1
            if len(entry) < 4:
                continue
            code, rel = entry[:2], entry[3:]
            if 'R' in code or 'C' in code:
                # rename: the next entry is the source path
                i += 1
            if any(rel == ex or rel.startswith(ex + '/') for ex in SANDBOX_EXCLUDES):
                continue
            src = project / rel
            dst = sandbox / rel
            if src.is_symlink() or src.exists():
                if src.is_dir() and not src.is_symlink():
                    continue
                copy_entry(src, dst)
            elif dst.exists() or dst.is_symlink():
                dst.unlink()
        # Ignored/untracked Markdown is still editable project content.
        # Overlay it before snapshotting so apply-back compares the actual bytes.
        for rel in walk(project, excludes=SANDBOX_EXCLUDES):
            src = project / rel
            if (rel.lower().endswith('.md') or rel.startswith('.uncle/')) and not src.is_symlink():
                copy_entry(src, sandbox / rel)
        return 'worktree'
    def ignore(directory, names):
        rel_dir = os.path.relpath(directory, project)
        rel_dir = '' if rel_dir == '.' else rel_dir
        skipped = []
        for name in names:
            rel = os.path.join(rel_dir, name) if rel_dir else name
            if rel in SANDBOX_EXCLUDES or rel.startswith('.uncle/workflow/parallel') or name == '__pycache__':
                skipped.append(name)
        return set(skipped)
    shutil.copytree(project, sandbox, symlinks=True, ignore=ignore)
    return 'copy'


def drop_sandbox(project, sandbox):
    sandbox = Path(sandbox)
    # Git retains registration after a sandbox directory is deleted externally.
    # Remove only this worktree, including its stale registration.
    subprocess.run(['git', 'worktree', 'remove', '--force', str(sandbox)], cwd=project,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sandbox.exists():
        shutil.rmtree(sandbox, ignore_errors=True)


def snapshot_paths(state_dir, turn):
    snap = Path(state_dir) / 'triage' / 'snapshot'
    return snap, snap / ('turn-%d.json' % turn), snap / ('turn-%d-files' % turn)


def digest_of(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


def begin(args):
    project = os.path.realpath(args.project)
    sandbox = Path(args.state_dir) / 'triage' / 'sandbox'
    snap_dir, record_path, files_dir = snapshot_paths(args.state_dir, args.turn)
    snap_dir.mkdir(parents=True, exist_ok=True)
    if files_dir.exists():
        shutil.rmtree(files_dir)
    files_dir.mkdir()
    forbidden = {}
    for rel in forbidden_live_paths(project):
        if not is_forbidden(rel):
            continue
        full = Path(project) / rel
        forbidden[rel] = [sha256(full), os.stat(full).st_mode & 0o7777]
        copy_entry(full, files_dir / rel)
    # The install's bytes are kept too: a model that reaches it gets its
    # edit reverted, and the run is still tainted, because a module already
    # loaded in this TUI is not something a file copy can un-load.
    install = install_inventory(project, args.root)
    root = os.path.realpath(args.root)
    for rel in install:
        copy_entry(Path(root) / rel, files_dir / '__install__' / rel)
    kind = make_sandbox(project, sandbox)
    record = {
        'turn': args.turn, 'mode': args.mode, 'project': project,
        'root': root, 'sandbox_kind': kind,
        'forbidden': forbidden,
        'install': install,
        'sandbox': walk(sandbox, excludes=('.git',)),
        'started': time.time(),
    }
    record_path.write_text(json.dumps(record, sort_keys=True))
    print(json.dumps({'sandbox': str(sandbox), 'digest': digest_of(record), 'kind': kind}))
    return 0


def tsv_row(state_dir, turn, proposal, outcome, path='-', before='-', after='-'):
    tsv = Path(state_dir) / 'triage-actions.tsv'
    new = not tsv.exists() or tsv.stat().st_size == 0
    clean = lambda s: str(s).replace('\t', ' ').replace('\n', ' ')
    with tsv.open('a', encoding='utf-8') as fh:
        if new:
            fh.write(TSV_HEADER)
        fh.write('\t'.join([datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), str(turn),
                            clean(proposal or '-'), outcome, clean(path), before, after]) + '\n')
    with tsv.open('r', encoding='utf-8') as fh:
        return sum(1 for _ in fh) - 1


def note_deviation(project, rel, turn, row):
    notes = Path(project) / 'IMPLEMENTATION_NOTES.md'
    if not notes.is_file():
        return
    with notes.open('a', encoding='utf-8') as fh:
        fh.write('\n- Deviation (triage): `%s` edited by triage proposal in turn %d; '
                 'see .uncle/workflow/triage-actions.tsv row %d.\n' % (rel, turn, row))


def end(args):
    project = os.path.realpath(args.project)
    sandbox = Path(args.state_dir) / 'triage' / 'sandbox'
    snap_dir, record_path, files_dir = snapshot_paths(args.state_dir, args.turn)
    result = {'applied': [], 'refused': [], 'failed': [], 'no_edit': False,
              'tainted': False, 'messages': []}
    taint = lambda msg: (result['messages'].append(msg), result.__setitem__('tainted', True))
    proposal = args.proposal or ('diagnosis' if args.mode == 'diagnosis' else '-')
    try:
        record = json.loads(record_path.read_text())
    except (OSError, ValueError):
        taint('Triage evidence for turn %d is missing; the pre-turn state cannot be verified.' % args.turn)
        drop_sandbox(project, sandbox)
        print(json.dumps(result))
        return 0
    if args.digest and digest_of(record) != args.digest:
        taint('Triage evidence for turn %d was modified during the turn; the run is tainted.' % args.turn)
        drop_sandbox(project, sandbox)
        tsv_row(args.state_dir, args.turn, proposal, 'REFUSED', '.uncle/workflow/triage/snapshot', '-', '-')
        print(json.dumps(result))
        return 0

    # 1. Forbidden live paths: restore any that moved. The ledger is checked
    # first, before anything is appended to it, because it is one of them.
    ledger = '.uncle/workflow/triage-actions.tsv'
    ordered = sorted(record['forbidden'].items(), key=lambda item: (item[0] != ledger, item[0]))
    if is_forbidden(ledger) and ledger not in record['forbidden'] and (Path(project) / ledger).is_file():
        after = sha256(Path(project) / ledger)
        (Path(project) / ledger).unlink()
        result['refused'].append(ledger)
        tsv_row(args.state_dir, args.turn, proposal, 'REFUSED', ledger, '-', after)
    for rel, (before, mode) in ordered:
        live = Path(project) / rel
        now = sha256(live) if live.is_file() else None
        if now == before:
            continue
        try:
            copy_entry(files_dir / rel, live)
            os.chmod(live, mode)
            restored = sha256(live) == before
        except OSError as exc:
            restored = False
            result['messages'].append('Could not restore %s: %s' % (rel, exc))
        result['refused'].append(rel)
        tsv_row(args.state_dir, args.turn, proposal, 'REFUSED', rel, before, now or '-')
        if not restored:
            taint('Forbidden path %s could not be restored to its pre-turn bytes.' % rel)
    for rel in forbidden_live_paths(project):
        if not is_forbidden(rel):
            continue
        if rel not in record['forbidden'] and rel != ledger:
            live = Path(project) / rel
            after = sha256(live)
            try:
                live.unlink()
            except OSError as exc:
                taint('Forbidden path %s was created and could not be removed: %s' % (rel, exc))
            result['refused'].append(rel)
            tsv_row(args.state_dir, args.turn, proposal, 'REFUSED', rel, '-', after)

    # 2. Installed tree: restore what moved; any change taints the run.
    install_now = install_inventory(project, args.root)
    root = record['root']
    for rel in sorted(set(install_now) | set(record['install'])):
        pre = record['install'].get(rel)
        post = install_now.get(rel)
        if pre == post:
            continue
        live = Path(root) / rel
        try:
            if pre is None:
                live.unlink()
            else:
                copy_entry(files_dir / '__install__' / rel, live)
                os.chmod(live, pre[1])
        except OSError as exc:
            result['messages'].append('Could not restore %s: %s' % (live, exc))
        result['refused'].append(str(live))
        tsv_row(args.state_dir, args.turn, proposal, 'REFUSED', str(live), pre[0] if pre else '-', post[0] if post else '-')
        taint('The installed uncle tree changed during the turn (%s). Reinstall uncle and restart the TUI before resuming.' % live)

    # 3. Sandbox diff.
    before = record['sandbox']
    after = walk(sandbox, excludes=('.git',)) if sandbox.exists() else {}
    changed = sorted(set(k for k in set(before) | set(after) if before.get(k) != after.get(k)))
    if not changed and not result['refused']:
        result['no_edit'] = True
        tsv_row(args.state_dir, args.turn, proposal, 'NO_EDIT')
    for rel in changed:
        pre = before.get(rel)
        post = after.get(rel)
        pre_hash = pre[0] if pre else '-'
        post_hash = post[0] if post else '-'
        markdown_edit = rel.lower().endswith('.md') or rel.startswith('.uncle/')
        proposal_report_edit = args.mode == 'execute' and rel in FORBIDDEN_FILES
        if ((is_forbidden(rel) and not proposal_report_edit) or rel in result['refused']
                or (install_pinned(rel, project, args.root) and not markdown_edit)
                or (args.mode != 'execute' and not markdown_edit)):
            result['refused'].append(rel)
            tsv_row(args.state_dir, args.turn, proposal, 'REFUSED', rel, pre_hash, post_hash)
            if install_pinned(rel, project, args.root) and args.mode == 'execute':
                taint('Proposal touched the installed uncle tree at %s; refused.' % rel)
            continue
        live = Path(project) / rel
        live_now = sha256(live) if live.is_file() else None
        if live_now != (pre[0] if pre else None):
            result['failed'].append(rel)
            result['messages'].append('%s changed in the live tree during the turn; not applied.' % rel)
            tsv_row(args.state_dir, args.turn, proposal, 'FAILED', rel, pre_hash, post_hash)
            continue
        try:
            if post is None:
                live.unlink()
            else:
                copy_entry(sandbox / rel, live)
                os.chmod(live, post[1])
        except OSError as exc:
            result['failed'].append(rel)
            result['messages'].append('Could not apply %s: %s' % (rel, exc))
            tsv_row(args.state_dir, args.turn, proposal, 'FAILED', rel, pre_hash, post_hash)
            continue
        result['applied'].append(rel)
        row = tsv_row(args.state_dir, args.turn, proposal, 'APPLIED', rel, pre_hash, post_hash)
        note_deviation(project, rel, args.turn, row)

    drop_sandbox(project, sandbox)
    if sandbox.exists():
        taint('The sandbox could not be removed: %s' % sandbox)
    print(json.dumps(result))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('action', choices=['begin', 'end'])
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--turn', type=int, required=True)
    parser.add_argument('--mode', choices=['diagnosis', 'execute'], required=True)
    parser.add_argument('--digest', default='')
    parser.add_argument('--proposal', default='')
    args = parser.parse_args(argv)
    return begin(args) if args.action == 'begin' else end(args)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)

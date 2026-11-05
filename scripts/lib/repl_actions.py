"""Validated action executor for the line-based REPL (no curses, no TUI).

The single gate (I-2): every action, whether typed by the user or proposed by the
model, is re-validated through home_actions.parse_reply and mapped onto the
allowlisted startup actions before uncle_headless.prepare_driver/run is reached.
Anything else is refused with exit 2 and no driver is started.
"""
import json
import os
import time
from pathlib import Path

import home_actions
import run_duties
import uncle_headless

REFUSED = 2
_BRIEFS = {'create_app': 'REQUIREMENTS.md', 'create_change': 'CHANGE_REQUEST.md'}
_YES = ('y', 'yes')


class Refusal(Exception):
    pass


def validate(action):
    """Return the parse_reply-validated action dict; raise Refusal."""
    if not isinstance(action, dict):
        raise Refusal('action must be an object')
    body = dict(action)
    body.setdefault('message', '')
    try:
        data = home_actions.parse_reply(json.dumps(body))
    except (ValueError, TypeError) as exc:
        raise Refusal(str(exc))
    if not isinstance(data, dict) or data.get('uncle_action') not in home_actions.ACTIONS:
        raise Refusal('not a valid action')
    return data


def _brief_path(root, name):
    docs = Path(root) / '.uncle' / 'docs' / name
    return docs if docs.exists() else Path(root) / name


def _existing(root, name):
    return _brief_path(root, name)


def execute(action, ctx):
    """Validate and run one action; returns an exit code (2 = refused)."""
    err, root = ctx.err, ctx.root
    try:
        data = validate(action)
    except Refusal as exc:
        err.write('uncle --noui: refused: %s\n' % exc)
        return REFUSED
    name = data['uncle_action']
    if name == 'stop_build':
        ctx.out.write('no build running\n')
        return 0
    if name in ('resume_build', 'clear_build'):
        ctx.out.write('%s is available in the full-screen UI only; run `uncle` without --noui.\n' % name)
        return 0
    env = dict(ctx.env)
    for key in ('UNCLE_STARTUP_ACTION', 'UNCLE_STARTUP_TEXT', 'UNCLE_STARTUP_TEXT_FILE',
                'UNCLE_STARTUP_ISSUE_MODE'):
        env.pop(key, None)
    if name == 'github_issue':
        if data.get('start') is False:
            ctx.out.write('issue %s noted; say "build issue %s" to start it.\n' % (data['issue'], data['issue']))
            return 0
        env['UNCLE_STARTUP_ACTION'] = 'github_issue'
        env['UNCLE_STARTUP_TEXT'] = str(data['issue'])
        env['UNCLE_STARTUP_ISSUE_MODE'] = '--change' if getattr(ctx, 'issue_change', False) else ''
    elif name in _BRIEFS:
        if not data.get('start'):
            ctx.out.write('brief not started (start was false); nothing written.\n')
            return 0
        target = _existing(root, _BRIEFS[name])
        if target.exists():
            if not ctx.confirm('Replace the existing %s?' % _BRIEFS[name]):
                err.write('uncle --noui: refused: replacement declined; existing brief kept\n')
                return REFUSED
            history = Path(root) / '.uncle' / 'brief-history'
            history.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime('%Y%m%dT%H%M%S')
            dest = history / ('%s.%s' % (stamp, target.name))
            n = 0
            while dest.exists():
                n += 1
                dest = history / ('%s-%d.%s' % (stamp, n, target.name))
            os.replace(target, str(dest))
        env['UNCLE_STARTUP_ACTION'] = 'create_app' if name == 'create_app' else 'change_request'
        env['UNCLE_STARTUP_TEXT'] = data['document']
    else:  # run_app / run_change run the brief already on disk
        target = _existing(root, 'REQUIREMENTS.md' if name == 'run_app' else 'CHANGE_REQUEST.md')
        try:
            text = target.read_text(encoding='utf-8')
        except OSError:
            err.write('uncle --noui: refused: %s does not exist\n' % target.name)
            return REFUSED
        runtime = env.get('UNCLE_RUNTIME_ROOT') or str(Path(uncle_headless.__file__).resolve().parents[2])
        try:
            cmd = run_duties.build_driver_command('create_app' if name == 'run_app' else 'change_request',
                                                  text, False, runtime, '')
        except ValueError as exc:
            err.write('uncle --noui: refused: %s\n' % exc)
            return REFUSED
        return _run(cmd, ctx, env)
    cmd = uncle_headless.prepare_driver(root, err, env)
    if cmd is None:
        return REFUSED
    return _run(cmd, ctx, env)


def _run(cmd, ctx, env):
    return uncle_headless.run(cmd, ctx.root, attended=bool(ctx.attended), env=env, out=ctx.out,
                              err=ctx.err, stdin_fd=ctx.stdin_fd, install_signals=True)

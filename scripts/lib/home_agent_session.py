"""The persistent tool-enabled home agent behind the idle homepage chat.

One long-lived `claude -p` stream-json conversation running in the project
checkout, in Claude's default permission mode. `-p` cannot prompt, so a tool
that needs approval is denied by Claude and reported in the result event's
`permission_denials`; the TUI shows each one to the operator and, on approval,
restarts the session with that single exact tool+input added to the grants.

Safety rules enforced here (see CHANGE_PLAN D-1, D-4):
  * no bypass flag, no wildcard grant, no bare `Bash` grant;
  * a grant is the verbatim denied string, escaped so it cannot act as a pattern;
  * `--disallowedTools` is always emitted in full and a grant matching a deny
    pattern is refused;
  * grants live only on the session object (its argv), never on disk;
  * the spawned environment is an allowlist with every STRIP_ENV name removed.
"""
import json
import os
import re
import shlex
import shutil
import tempfile

from supervisor_runner import SupervisorSession, parse_stream

# Granted without asking: read-only tools. Everything else needs an approval.
BASE_ALLOWED = ('Read', 'Glob', 'Grep', 'TodoWrite')
DENY_PATTERNS = ('git push --force', 'git push -f', 'git push --force-with-lease',
                 'rm -rf /', 'rm -rf ~', 'rm -fr /', 'rm -fr ~')
# Environment that must never reach the agent: the OAuth login has to be what
# authenticates (see scripts/lib/stage-config.sh).
STRIP_ENV = ('ANTHROPIC_API_KEY', 'UNCLE_MODEL_REFRESH_KEY')
ENV_ALLOW = ('PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'TERM', 'TMPDIR', 'LANG', 'LANGUAGE',
             'SSH_AUTH_SOCK', 'WORKFLOW_CLAUDE_CMD')
ENV_ALLOW_PREFIXES = ('LC_', 'CLAUDE_', 'XDG_')

_SEGMENT = re.compile(r'&&|\|\||[;|\n]')
_ENV_ASSIGN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')


def deny_patterns():
    return list(DENY_PATTERNS)


def agent_env(environ=None):
    """Allowlisted environment for the agent process (and its Bash)."""
    environ = os.environ if environ is None else environ
    env = {}
    for key, value in environ.items():
        if key in STRIP_ENV:
            continue
        if key in ENV_ALLOW or key.startswith(ENV_ALLOW_PREFIXES):
            env[key] = value
    return env


def command_denied(command, patterns):
    """True when any command in a shell line starts with a denied prefix (unreadable lines are refused)."""
    try:
        tokens = shlex.split(command.strip())
    except ValueError:
        return True
    if len(tokens) >= 3 and os.path.basename(tokens[0]) in ('sh', 'bash', 'zsh') and tokens[1] in ('-c', '-lc', '-ic'):
        command = tokens[2]
    for segment in _SEGMENT.split(command):
        try:
            words = shlex.split(segment)
        except ValueError:
            return True
        while words and _ENV_ASSIGN.match(words[0]):
            words.pop(0)
        for pattern in patterns:
            wanted = pattern.split()
            if words[:len(wanted)] == wanted:
                return True
    return False


def _escape(text):
    return re.sub(r'([\\*()])', r'\\\1', text)


def grant_for_denial(denial, patterns=None):
    """The exact-match allow rule for one permission denial, or ValueError.

    `denial` is a result-event entry: {'tool_name': ..., 'tool_input': {...}}.
    Bash grants are `Bash(<verbatim command>)` with `\\`, `*`, `(` and `)`
    escaped. Never a wildcard, never a bare tool name.
    """
    patterns = deny_patterns() if patterns is None else patterns
    tool = str((denial or {}).get('tool_name') or '')
    data = (denial or {}).get('tool_input') or {}
    if tool == 'Bash':
        subject = data.get('command')
    elif tool in ('Write', 'Edit', 'MultiEdit', 'NotebookEdit'):
        subject = data.get('file_path')
    else:
        raise ValueError('no exact grant for tool %s' % (tool or '?'))
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError('denial has no command or path to grant')
    if any(ch in subject for ch in ',\n\r\0'):
        raise ValueError('cannot grant a value containing a comma or newline')
    if tool == 'Bash' and command_denied(subject, patterns):
        raise ValueError('command matches a deny pattern')
    return '%s(%s)' % (tool, _escape(subject))


def permission_denials(lines):
    """The list of {tool_name, tool_input} denials in a stream-json result event."""
    found = []
    for raw in lines or []:
        try:
            event = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(event, dict) and event.get('type') == 'result':
            for item in event.get('permission_denials') or []:
                if isinstance(item, dict) and item.get('tool_name'):
                    found.append({'tool_name': item['tool_name'], 'tool_input': item.get('tool_input') or {}})
    return found


def system_prompt(root, patterns=None):
    patterns = deny_patterns() if patterns is None else patterns
    with open(os.path.join(root, 'prompts', 'home-agent.md'), encoding='utf-8') as fh:
        text = fh.read()
    text += '\n## Never run commands starting with\n\n'
    text += ''.join('- `%s`\n' % pattern for pattern in patterns)
    return text


def build_command(root, model, effort, grants=(), environ=None):
    """(argv, env) for the home agent, or ValueError('unavailable ...')."""
    environ = os.environ if environ is None else environ
    executable = environ.get('WORKFLOW_CLAUDE_CMD') or 'claude'
    resolved = shutil.which(executable)
    if not resolved:
        raise ValueError('unavailable: %s is not on PATH' % executable)
    patterns = deny_patterns()
    allowed = list(BASE_ALLOWED)
    for grant in grants:
        if grant in ('Bash', 'Write', 'Edit') or grant.endswith('*)') or ':*' in grant:
            raise ValueError('refused broad grant: %s' % grant)
        if grant not in allowed:
            allowed.append(grant)
    argv = [resolved, '-p', '--output-format', 'stream-json', '--verbose', '--include-partial-messages',
            '--strict-mcp-config', '--no-session-persistence',
            '--model', model, '--effort', effort,
            '--allowedTools', ','.join(allowed),
            '--disallowedTools', ','.join('Bash(%s:*)' % p for p in patterns),
            '--append-system-prompt', system_prompt(root, patterns)]
    return argv, agent_env(environ)


class HomeAgentSession(SupervisorSession):
    """A SupervisorSession in the project checkout, carrying its session-only grants."""

    def __init__(self, command, env, cwd, grants=()):
        self.cwd = cwd
        self.grants = tuple(grants)
        home = tempfile.mkdtemp(prefix='uncle-home-agent-')
        super().__init__(command, env, home, cwd=cwd)

    def close(self):
        super().close()
        self.grants = ()
        shutil.rmtree(self.home, ignore_errors=True)


def start_session(root, model, effort, cwd, grants=(), environ=None):
    """(session, argv) for a fresh home agent; ValueError('unavailable ...') when claude is missing."""
    argv, env = build_command(root, model, effort, grants, environ)
    return HomeAgentSession(argv, env, cwd, grants), argv


def persistent_session(root, model, effort, cwd, grants=(), environ=None):
    """Alias of start_session used by the TUI."""
    return start_session(root, model, effort, cwd, grants, environ)


def grant_rule(tool, tool_input):
    """The exact allow rule for one denied tool call, or ValueError."""
    return grant_for_denial({'tool_name': tool, 'tool_input': tool_input})


__all__ = ['persistent_session', 'grant_rule', 'BASE_ALLOWED', 'DENY_PATTERNS', 'STRIP_ENV', 'HomeAgentSession', 'agent_env', 'build_command',
           'command_denied', 'deny_patterns', 'grant_for_denial', 'parse_stream', 'permission_denials',
           'start_session', 'system_prompt']

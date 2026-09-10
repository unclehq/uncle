"""Aider-backed self-hosted runner and private endpoint configuration."""
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import shutil
from urllib.parse import urlsplit
import re
import time


def key_file(config):
    return Path(config).parent / 'self-hosted-keys.json'


def read_keys(config):
    path = key_file(config)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def save_keys(config, keys):
    path = key_file(config)
    if not keys and not path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ignore = path.parent / '.gitignore'
    existing = ignore.read_text(encoding='utf-8') if ignore.exists() else ''
    if '/self-hosted-keys.json' not in existing.splitlines():
        with ignore.open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(('\n' if existing and not existing.endswith('\n') else '') + '/self-hosted-keys.json\n')
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.self-hosted-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(keys, stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def discover_models(base_url, api_key):
    """Query the configured OpenAI-compatible endpoint without redirecting secrets."""
    from urllib.request import Request, build_opener, HTTPRedirectHandler
    from urllib.error import HTTPError, URLError
    url = urlsplit(base_url)
    if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password or url.query or url.fragment:
        raise ValueError('Enter an http(s) Base URL without credentials, query, or fragment')
    if not api_key or any(c in api_key for c in ('\r', '\n')):
        raise ValueError('Enter an API key; use local for an unauthenticated endpoint')
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    request = Request(base_url.rstrip('/') + '/models', headers={'Authorization': 'Bearer ' + api_key, 'Accept': 'application/json'})
    try:
        with build_opener(NoRedirect).open(request, timeout=10) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Model response is too large')
        data = json.loads(raw)
        entries = data['data']
        if not isinstance(entries, list):
            raise ValueError('Invalid models list')
        names = sorted({item['id'] for item in entries if isinstance(item, dict) and isinstance(item.get('id'), str)
                        and item['id'] and not any(c.isspace() for c in item['id']) and '#' not in item['id']})
        if not names:
            raise ValueError('The endpoint returned no usable models')
        return names
    except HTTPError as exc:
        raise ValueError(f'Model discovery failed (HTTP {exc.code}); check the Base URL and API key') from None
    except (URLError, OSError):
        raise ValueError('Could not reach the models endpoint; check the Base URL and server') from None
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeError):
        raise ValueError('Expected an OpenAI-compatible models response with data and model IDs') from None


def connection_settings(keys):
    return dict(keys.get('__aider_connection__') or next(iter(keys.get('__aider_models__', {}).values()), {}))


def refresh_models(keys, base_url, api_key):
    names = discover_models(base_url, api_key)
    connection = dict(base_url=base_url.rstrip('/'), api_key=api_key)
    # Commit only after a successful discovery; failures retain the old catalog.
    keys['__aider_connection__'] = connection
    keys['__aider_models__'] = {name: dict(connection) for name in names}
    return names


def settings(config, stage):
    if stage.startswith('implementation-step-'):
        stage = 'implementation'
    values = {}
    if Path(config).exists():
        for line in Path(config).read_text(encoding='utf-8').splitlines():
            parts = line.split('#', 1)[0].split(None, 1)
            if len(parts) == 2:
                values.setdefault(*parts)
    result = {}
    for field in ('base_url', 'model'):
        result[field] = os.environ.get('UNCLE_SELF_HOSTED_' + field.upper()) or values.get(stage + '.' + field) or values.get('self-hosted.' + field, '')
    result['api_key'] = os.environ.get('UNCLE_SELF_HOSTED_API_KEY') or read_keys(config).get(stage, '')
    profiles = read_keys(config).get('__aider_models__', {})
    selected = values.get(stage + '.model', '')
    if selected in profiles:
        profile = profiles[selected]
        result = dict(model=profile.get('model', selected), base_url=profile.get('base_url', ''), api_key=profile.get('api_key', ''))
    elif profiles and not values.get(stage + '.base_url'):
        raise ValueError('Select a configured Aider self-hosted model for stage ' + stage)
    for field in ('model', 'base_url', 'api_key'):
        result[field] = os.environ.get('UNCLE_SELF_HOSTED_' + field.upper()) or result[field]
    url = urlsplit(result['base_url'])
    if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password or url.query or url.fragment:
        raise ValueError('Self hosted requires an http(s) Base URL without credentials, query, or fragment')
    if not result['model']:
        raise ValueError('Self hosted requires a model name')
    if '\n' in result['api_key'] or '\r' in result['api_key']:
        raise ValueError('API key must be a single line')
    if not result['api_key']:
        raise ValueError('Self hosted requires an API key (use a placeholder for a server without authentication)')
    return result


def parse_arguments(side, args):
    output, prompt = '', ''
    turns = int(os.environ.get('UNCLE_STATUS_STAGE_TURNS') or 80)
    iterator = iter(args)
    valued = {'--model','-m','--effort','-c','--sandbox','--allowedTools','--output-format',
              '--max-budget-usd','--resume','--mcp-config'}
    for arg in iterator:
        if arg == '--output-last-message':
            output = next(iterator)
        elif arg == '--max-turns':
            turns = int(next(iterator))
        elif arg in valued:
            next(iterator)
        elif arg in ('exec','-p','--ephemeral','--json','--skip-git-repo-check','--verbose',
                     '--strict-mcp-config','--exclude-dynamic-system-prompt-sections','--fork-session'):
            pass
        elif arg.startswith('-'):
            raise ValueError('Unsupported self-hosted runner option: ' + arg)
        else:
            prompt = arg
    if side == 'agent':
        prompt = sys.stdin.read() or prompt
    if not prompt.strip() or turns < 1:
        raise ValueError('Self hosted requires a prompt and a positive turn limit')
    return output, prompt, turns



def response_from_history(path):
    """Aider prefixes each response line with ASSISTANT in its LLM journal."""
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    blocks = re.split(r'(?m)^LLM RESPONSE \d{4}-\d\d-\d\dT[^\n]*\n', text)
    if len(blocks) == 1:
        raise ValueError('Aider returned no model response')
    last = blocks[-1].split('\nTO LLM ', 1)[0]
    lines = []
    for line in last.splitlines():
        if line.startswith('ASSISTANT '):
            lines.append(line[len('ASSISTANT '):])
        elif line == 'ASSISTANT':
            lines.append('')
    response = '\n'.join(lines).strip()
    if not response:
        raise ValueError('Aider returned an empty final response')
    return response, len(blocks)-1


def aider_invocation(side, values, prompt, root, directory):
    work = Path(directory)
    message = work/'prompt.txt'
    message.write_bytes(prompt.encode('utf-8'))
    config = work/'aider.yml'
    config.write_bytes(b'{}\n')
    env_file = work/'empty.env'
    env_file.write_bytes(b'')
    ignore = work/'ignore'
    original_ignore = root/'.aiderignore'
    text = original_ignore.read_text(encoding='utf-8') if original_ignore.exists() else ''
    ignore.write_bytes((text + '\n.uncle/\n.git/\n').encode('utf-8'))
    model = values['model']
    if not model.startswith('openai/'):
        model = 'openai/' + model
    command = [os.environ.get('WORKFLOW_AIDER_CMD', 'aider'),
        '--model', model, '--weak-model', model, '--editor-model', model,
        '--openai-api-base', values['base_url'].rstrip('/'),
        '--config', str(config), '--env-file', str(env_file), '--aiderignore', str(ignore),
        '--message-file', str(message), '--llm-history-file', str(work/'llm.log'),
        '--chat-history-file', str(work/'chat.md'), '--input-history-file', str(work/'input.history'),
        '--no-restore-chat-history', '--no-auto-commits', '--no-dirty-commits', '--no-gitignore',
        '--no-check-update', '--no-show-model-warnings', '--no-analytics', '--no-stream', '--no-pretty', '--yes-always',
        '--no-auto-lint', '--no-auto-test', '--no-detect-urls', '--encoding', 'utf-8', '--line-endings', 'lf']
    if side == 'reviewer':
        command += ['--chat-mode','ask','--dry-run','--no-suggest-shell-commands']
    else:
        command += ['--edit-format','diff','--no-dry-run','--suggest-shell-commands']
    # Seed the chat with workflow documents; Aider's repo map and file mention
    # handling provide the remaining code context. Never seed local secrets.
    for path in sorted(root.glob('*.md')):
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 250_000:
            command += ['--read' if side == 'reviewer' else '--file', str(path)]
    # Ignore inherited Aider options (including AIDER_LOAD and model defaults).
    # Credentials stay in the child environment, never argv or the YAML file.
    env = {k:v for k,v in os.environ.items() if not k.startswith('AIDER_')}
    env.update(OPENAI_API_KEY=values['api_key'], OPENAI_API_BASE=values['base_url'].rstrip('/'),
               OPENAI_BASE_URL=values['base_url'].rstrip('/'), AIDER_OPENAI_API_KEY=values['api_key'],
               PYTHONIOENCODING='utf-8', PYTHONUTF8='1', LITELLM_LOCAL_MODEL_COST_MAP='True')
    return command, env


PLAN_ARTIFACTS = {
    'project-plan': 'PROJECT_PLAN.md',
    'updated-plan': 'UPDATED_PROJECT_PLAN.md',
}


def validate_plan(text, protected=True):
    """Reject incomplete machine-readable plans before publishing them."""
    blocks = {}
    heading, fence, body = '', None, []
    for line in text.splitlines():
        match = re.match(r'^\s*(`{3,}|~{3,})(.*)$', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                if fence.startswith('```'):
                    blocks.setdefault(heading, []).append(body)
                fence, body = None, []
            else:
                body.append(line)
        elif match:
            fence, body = match[1], []
        elif re.match(r'^#{1,6}\s+', line):
            heading = re.sub(r'^#{1,6}\s+(?:\d+[.)]\s*)?', '', line).strip().lower()
    if fence:
        raise ValueError('Plan has an unclosed Markdown code fence')
    required_blocks = ['verification commands'] + (['protected verification paths'] if protected else [])
    for required in required_blocks:
        candidates = blocks.get(required, [])
        if len(candidates) != 1 or not any(line.strip() and not line.lstrip().startswith('#') for line in candidates[0]):
            raise ValueError('Plan requires one complete, nonempty fenced block under ' + required)


def run_aider(side, values, prompt, root, stage=None):
    artifact = PLAN_ARTIFACTS.get(stage or os.environ.get('UNCLE_STATUS_STAGE', '')) if side == 'agent' else None
    if not artifact:
        return _run_aider(side, values, prompt, root)
    target = root / artifact
    if target.is_symlink():
        raise ValueError('Refusing to replace a symlinked plan')
    original = target.read_bytes() if target.exists() else None
    # Aider never edits the live project during planning. Publish only the
    # required document after validation; incidental model edits stay isolated.
    with tempfile.TemporaryDirectory(prefix='uncle-plan-') as directory:
        staged = Path(directory) / 'project'
        excluded = shutil.ignore_patterns('.git', '.uncle', '.aider*', 'node_modules', '.venv', 'venv', '__pycache__')
        def ignore(directory, names):
            return set(excluded(directory, names)) | {name for name in names if (Path(directory)/name).is_symlink()}
        shutil.copytree(root, staged, ignore=ignore)
        candidate = staged / artifact
        if candidate.exists():
            candidate.unlink()
        response, turns = _run_aider(side, values, prompt + '\nWrite the complete ' + artifact +
                                     ', including Verification commands and Protected verification paths fenced blocks.', staged, allow_shell=False)
        if not candidate.is_file() or candidate.is_symlink():
            raise ValueError('Aider did not produce a regular ' + artifact + '; original plan preserved')
        contents = candidate.read_bytes()
        validate_plan(contents.decode('utf-8'), protected=artifact == 'UPDATED_PROJECT_PLAN.md')
        if target.is_symlink() or (target.read_bytes() if target.exists() else None) != original:
            raise ValueError('Plan changed during generation; refusing to overwrite it')
        fd, pending = tempfile.mkstemp(prefix='.' + artifact + '.', dir=root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(contents)
            os.replace(pending, target)
        finally:
            if os.path.exists(pending): os.unlink(pending)
        return response, turns


def _run_aider(side, values, prompt, root, allow_shell=True):
    from process_tree import start_check, launch_command, kill_tree, finish_check
    seconds = int(os.environ.get('WORKFLOW_SELF_HOSTED_SECONDS', '900'))
    if seconds < 1:
        raise ValueError('WORKFLOW_SELF_HOSTED_SECONDS must be positive')
    with tempfile.TemporaryDirectory(prefix='uncle-aider-') as directory:
        command, env = aider_invocation(side, values, prompt, root, directory)
        if not allow_shell:
            command = [arg for arg in command if arg != "--suggest-shell-commands"] + ["--no-suggest-shell-commands"]
        with (Path(directory)/'output.log').open('wb') as log:
            child = start_check(launch_command(command), cwd=root, env=env,
                                stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + seconds
            try:
                while True:
                    try:
                        status = child.wait(timeout=.1)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= deadline:
                            raise ValueError(f'Aider exceeded its {seconds}-second time limit')
            finally:
                try:
                    if child.poll() is None:
                        kill_tree(child)
                        child.wait()
                finally:
                    finish_check(child)
        if status:
            # Do not expose CLI diagnostics that may contain inherited secrets.
            raise ValueError(f'Aider exited with status {status}; check its installation and endpoint configuration')
        response, turns = response_from_history(Path(directory)/'llm.log')
        return response, turns


def profile_menu(config, choose=False):
    import getpass
    keys = read_keys(config)
    profiles = keys.setdefault('__aider_models__', {})
    if choose:
        for name in sorted(profiles):
            print('  ' + name, file=sys.stderr)
        print('Aider model name: ', end='', file=sys.stderr, flush=True)
        name = input().strip()
        if name not in profiles:
            raise ValueError('Choose a configured Aider model; add models in Configure → Aider self-hosted models')
        print(name)
        return 0
    old = connection_settings(keys)
    url = input('Base URL [' + old.get('base_url', '') + ']: ').strip() or old.get('base_url', '')
    key = getpass.getpass('API key (hidden; blank keeps existing): ').strip() or old.get('api_key', '')
    print('Discovering Aider models…', flush=True)
    names = refresh_models(keys, url, key)
    save_keys(config, keys)
    print(f'Loaded {len(names)} Aider models: ' + ', '.join(names))
    return 0


def main(side, args):
    started = time.monotonic()
    if side in ('models', 'choose-model'):
        return profile_menu(args[0], side == 'choose-model')
    if side == 'set-key':
        keys = read_keys(args[0])
        key = sys.stdin.read().strip()
        if key:
            keys[args[1]] = key
        else:
            keys.pop(args[1], None)
        save_keys(args[0], keys)
        return 0
    if side not in ('agent','reviewer'):
        raise ValueError('Invalid runner side')
    output, prompt, _turns = parse_arguments(side, args)
    stage = os.environ.get('UNCLE_STATUS_STAGE', '')
    if not stage and side == 'reviewer' and output:
        stage = Path(output).stem.lower().replace('_','-')
    config = os.environ.get('UNCLE_CONFIG', str(Path.cwd()/'.uncle/config'))
    values = settings(config, stage)
    def interrupt(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, interrupt)
    status_file = os.environ.get('UNCLE_STATUS_FILE')
    if status_file:
        with open(status_file,'a',encoding='utf-8',newline='\n') as stream:
            stream.write(json.dumps({'event':'start','stage':stage,'model':values['model'],
                                     'mode':'act' if side=='agent' else 'review'})+'\n')
    text, turns = run_aider(side, values, prompt, Path.cwd().resolve(), stage=stage)
    if side == 'reviewer':
        if output:
            Path(output).write_bytes((text.rstrip()+'\n').encode('utf-8'))
        print(text)
    else:
        print(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':text}]}}))
        print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':text,
                          'model':values['model'],'num_turns':turns,'duration_ms':int((time.monotonic()-started)*1000),'usage':{},'total_cost_usd':None}))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', newline='\n')
    try:
        sys.exit(main(sys.argv[1], sys.argv[2:]))
    except KeyboardInterrupt:
        sys.exit(130)
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as error:
        print('Self hosted: ' + str(error), file=sys.stderr)
        if sys.argv[1:2] == ['agent']:
            print(json.dumps({'type':'result','subtype':'error','is_error':True}))
        sys.exit(2)

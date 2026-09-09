"""Aider-backed self-hosted runner and private endpoint configuration."""
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
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
        '--no-check-update', '--no-analytics', '--no-stream', '--no-pretty', '--yes-always',
        '--no-auto-lint', '--no-auto-test', '--no-detect-urls', '--encoding', 'utf-8', '--line-endings', 'lf']
    if side == 'reviewer':
        command += ['--chat-mode','ask','--dry-run','--no-suggest-shell-commands']
    else:
        command += ['--edit-format','whole','--no-dry-run','--suggest-shell-commands']
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


def run_aider(side, values, prompt, root):
    from process_tree import start_check, launch_command, kill_tree, finish_check
    seconds = int(os.environ.get('WORKFLOW_SELF_HOSTED_SECONDS', '900'))
    if seconds < 1:
        raise ValueError('WORKFLOW_SELF_HOSTED_SECONDS must be positive')
    with tempfile.TemporaryDirectory(prefix='uncle-aider-') as directory:
        command, env = aider_invocation(side, values, prompt, root, directory)
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
    print('Aider self-hosted models: ' + ', '.join(sorted(profiles)))
    name = input('Model name to add or edit (blank to return): ').strip()
    if not name:
        return 0
    if any(c.isspace() for c in name) or '#' in name:
        raise ValueError('Model names cannot contain spaces or #')
    old = profiles.get(name, {})
    url = input('Base URL [' + old.get('base_url', '') + ']: ').strip() or old.get('base_url', '')
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Enter an http(s) Base URL without credentials, query, or fragment')
    key = getpass.getpass('API key (hidden; blank keeps existing): ').strip() or old.get('api_key', '')
    if not key:
        raise ValueError('API key required; use local for an unauthenticated endpoint')
    profiles[name] = dict(base_url=url, api_key=key)
    save_keys(config, keys)
    return 0


def main(side, args):
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
    text, turns = run_aider(side, values, prompt, Path.cwd().resolve())
    if side == 'reviewer':
        if output:
            Path(output).write_bytes((text.rstrip()+'\n').encode('utf-8'))
        print(text)
    else:
        print(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':text}]}}))
        print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':text,
                          'model':values['model'],'num_turns':turns,'usage':{},'total_cost_usd':None}))
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

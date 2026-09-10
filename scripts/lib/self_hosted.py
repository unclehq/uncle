"""OpenCode-backed self-hosted runner and private endpoint configuration."""
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
    keys = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    # Read old credentials without rewriting them until the user saves config.
    if '__opencode_models__' not in keys and '__aider_models__' in keys:
        keys['__opencode_models__'] = {
            name.removeprefix('openai/'): dict(profile, model=profile.get('model', name).removeprefix('openai/'))
            for name, profile in keys.pop('__aider_models__').items()}
    if '__opencode_connection__' not in keys and '__aider_connection__' in keys:
        keys['__opencode_connection__'] = keys.pop('__aider_connection__')
    if '__opencode_models__' in keys:
        keys['__opencode_models__'] = {
            name.removeprefix('openai/'): dict(profile, model=profile.get('model', name).removeprefix('openai/'))
            for name, profile in keys['__opencode_models__'].items()}
    return keys


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
        return sorted({name.removeprefix('openai/') for name in names if name.removeprefix('openai/')})
    except HTTPError as exc:
        raise ValueError(f'Model discovery failed (HTTP {exc.code}); check the Base URL and API key') from None
    except (URLError, OSError):
        raise ValueError('Could not reach the models endpoint; check the Base URL and server') from None
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeError):
        raise ValueError('Expected an OpenAI-compatible models response with data and model IDs') from None


def connection_settings(keys):
    return dict(keys.get('__opencode_connection__') or next(iter(keys.get('__opencode_models__', {}).values()), {}))


def refresh_models(keys, base_url, api_key):
    names = discover_models(base_url, api_key)
    connection = dict(base_url=base_url.rstrip('/'), api_key=api_key)
    # Commit only after a successful discovery; failures retain the old catalog.
    keys['__opencode_connection__'] = connection
    keys['__opencode_models__'] = {name: dict(connection) for name in names}
    return names


def settings(config, stage):
    if stage in ('manual-checklist-base', 'manual-checklist-delta'):
        stage = 'manual-checklist'
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
    profiles = read_keys(config).get('__opencode_models__', {})
    selected = values.get(stage + '.model', '')
    if selected.startswith('openai/') and selected not in profiles:
        selected = selected[len('openai/'):]
    if selected in profiles:
        profile = profiles[selected]
        result = dict(model=profile.get('model', selected), base_url=profile.get('base_url', ''), api_key=profile.get('api_key', ''))
    elif profiles and not values.get(stage + '.base_url'):
        raise ValueError('Select a configured OpenCode self-hosted model for stage ' + stage)
    for field in ('model', 'base_url', 'api_key'):
        result[field] = os.environ.get('UNCLE_SELF_HOSTED_' + field.upper()) or result[field]
    result['model'] = result['model'].removeprefix('openai/')
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



def opencode_events(path):
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def response_from_events(path):
    events = opencode_events(path)
    if any(event.get('type') == 'error' for event in events):
        raise ValueError('OpenCode reported a model or session error')
    texts = [event.get('part', {}).get('text', '') for event in events if event.get('type') == 'text']
    finished = [event for event in events if event.get('type') == 'step_finish']
    if not texts or not texts[-1].strip() or not finished:
        raise ValueError('OpenCode returned no complete final response')
    if finished[-1].get('part', {}).get('reason') not in ('stop', 'end_turn'):
        raise ValueError('OpenCode stopped before completing the response')
    return texts[-1].strip(), len(finished)


def opencode_invocation(side, values, prompt, root, directory, allow_shell=True):
    work = Path(directory)
    (work/'prompt.txt').write_text(prompt, encoding='utf-8', newline='\n')
    model = values['model'].removeprefix('openai/')
    request_seconds = int(os.environ.get('WORKFLOW_SELF_HOSTED_REQUEST_SECONDS') or os.environ.get('WORKFLOW_SELF_HOSTED_SECONDS', '3600'))
    if request_seconds < 1:
        raise ValueError('WORKFLOW_SELF_HOSTED_REQUEST_SECONDS must be positive')
    context = int(os.environ.get('WORKFLOW_SELF_HOSTED_CONTEXT_TOKENS', '65536'))
    output = int(os.environ.get('WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS', '8192'))
    if not 0 < output < context:
        raise ValueError('Model limits require 0 < output tokens < context tokens')
    permission = {'*': 'deny', 'read': {'*': 'allow', '*.env': 'deny', '*.env.*': 'deny',
                  '*self-hosted-keys.json': 'deny'}, 'glob': 'allow', 'grep': 'allow',
                  'list': 'allow', 'edit': 'allow' if side == 'agent' else 'deny',
                  'bash': 'allow' if side == 'agent' and allow_shell else 'deny',
                  'external_directory': 'deny'}
    config = {
        '$schema': 'https://opencode.ai/config.json',
        'enabled_providers': ['uncle'], 'model': 'uncle/' + model,
        'small_model': 'uncle/' + model, 'share': 'disabled', 'autoupdate': False,
        'snapshot': False, 'permission': permission,
        'agent': {'uncle': {'mode': 'primary', 'description': 'Uncle workflow stage',
                            'steps': values.get('max_turns', 80),
                            'permission': permission}},
        'provider': {'uncle': {'npm': '@ai-sdk/openai-compatible', 'name': 'Uncle self hosted',
                     'options': {'baseURL': values['base_url'].rstrip('/'),
                                 'apiKey': '{env:UNCLE_OPENCODE_API_KEY}', 'timeout': request_seconds * 1000},
                     'models': {model: {'name': model, 'tool_call': True, 'limit': {
                         'context': context, 'output': output}}}}},
    }
    env = {k: v for k, v in os.environ.items() if not k.startswith(('OPENCODE_', 'AIDER_'))}
    env.update(OPENCODE_CONFIG_CONTENT=json.dumps(config), UNCLE_OPENCODE_API_KEY=values['api_key'],
               OPENCODE_DISABLE_PROJECT_CONFIG='true', OPENCODE_DISABLE_CLAUDE_CODE='true',
               OPENCODE_DISABLE_DEFAULT_PLUGINS='true', OPENCODE_DISABLE_MODELS_FETCH='true',
               PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    # Isolate session history and global providers/plugins from the user's CLI.
    for key, leaf in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_STATE_HOME', 'state')):
        folder = work/leaf
        folder.mkdir()
        env[key] = str(folder)
    command = [os.environ.get('WORKFLOW_OPENCODE_CMD', 'opencode'), 'run', '--format', 'json',
               '--dir', str(root), '--model', 'uncle/' + model, '--agent', 'uncle',
               '--file', str(work/'prompt.txt'), '--', 'Follow the attached workflow instructions.']
    return command, env


def opencode_usage(path):
    totals = dict(input_tokens=0, output_tokens=0, total_tokens=0)
    found = False
    for event in opencode_events(path):
        if event.get('type') != 'step_finish':
            continue
        tokens = event.get('part', {}).get('tokens', {})
        inp, out = tokens.get('input'), tokens.get('output')
        cache = tokens.get('cache') or {}
        counts = (inp, out, cache.get('read', 0), cache.get('write', 0), tokens.get('reasoning', 0))
        if any(type(n) not in (int, float) or n < 0 or int(n) != n for n in counts):
            return {}  # Never publish a partial or invalid total.
        # OpenCode reports cache and reasoning separately from input/output.
        inp += cache.get('read', 0) + cache.get('write', 0)
        out += tokens.get('reasoning', 0)
        totals['input_tokens'] += inp
        totals['output_tokens'] += out
        totals['total_tokens'] += inp + out
        found = True
    return totals if found else {}


PLAN_ARTIFACTS = {'requirements': 'REQUIREMENTS_INTERPRETATION.md', 'project-plan': 'PROJECT_PLAN.md', 'updated-plan': 'UPDATED_PROJECT_PLAN.md'}


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


def document_response(response, artifact):
    text = re.sub(r'<think>.*?</think>', '', response, flags=re.S).strip()
    if any(marker in text for marker in ('<<<<<<< SEARCH', '>>>>>>> REPLACE')):
        raise ValueError('Expected Markdown, received edit instructions; original preserved')
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r'^#{1,6}\s+\S', line)), None)
    if start is None:
        raise ValueError('Expected a complete Markdown document; original preserved')
    # Models may precede the document with a filename or a short explanation.
    wrappers = [re.match(r'^(`{3,}|~{3,})(?:markdown|md)?\s*$', line) for line in lines[:start]]
    wrappers = [match[1] for match in wrappers if match]
    end = len(lines)
    if wrappers:
        fence = wrappers[-1]
        closing = [i for i in range(start, len(lines)) if lines[i].strip() == fence]
        if not closing:
            raise ValueError('Incomplete document response; original preserved')
        end = closing[-1]
    text = '\n'.join(lines[start:end]).strip()
    if not text.startswith('# '):
        text = '# ' + artifact + '\n\n' + text
    return text + '\n'


def validate_requirements(text):
    if not re.search(r'^##\s+(?:10[.)]\s*)?(?:\*\*)?Definition of done(?:\*\*)?\s*#*\s*$', text, re.M | re.I):
        raise ValueError('Requirements interpretation lacks Definition of done; original preserved')



def run_opencode(side, values, prompt, root, stage=None, usage=None):
    artifact = PLAN_ARTIFACTS.get(stage or os.environ.get('UNCLE_STATUS_STAGE', '')) if side == 'agent' else None
    if not artifact:
        return _run_opencode(side, values, prompt, root, usage=usage)
    target = root / artifact
    if target.is_symlink():
        raise ValueError('Refusing to replace a symlinked plan')
    original = target.read_bytes() if target.exists() else None
    # OpenCode never edits the live project during planning. Publish only the
    # required document after validation; incidental model edits stay isolated.
    with tempfile.TemporaryDirectory(prefix='uncle-plan-') as directory:
        staged = Path(directory) / 'project'
        excluded = shutil.ignore_patterns('.git', '.uncle', '.opencode*', 'node_modules', '.venv', 'venv', '__pycache__')
        def ignore(directory, names):
            return set(excluded(directory, names)) | {name for name in names if (Path(directory)/name).is_symlink()}
        shutil.copytree(root, staged, ignore=ignore)
        candidate = staged / artifact
        if candidate.exists():
            candidate.unlink()
        if artifact == 'REQUIREMENTS_INTERPRETATION.md':
            request = prompt + '\nReturn the complete REQUIREMENTS_INTERPRETATION.md as Markdown, starting with its # heading and including ## 10. Definition of done. Uncle will save it. Do not emit SEARCH/REPLACE edits.'
            turns = 0
            for attempt in range(2):
                attempt_usage = {}
                try:
                    response, count = _run_opencode('reviewer', values, request, staged, allow_shell=False, usage=attempt_usage, diagnostic_root=root)
                    turns += count
                finally:
                    if usage is not None:
                        for key, value in attempt_usage.items():
                            usage[key] = usage.get(key, 0) + value
                try:
                    document = document_response(response, artifact)
                    validate_requirements(document)
                except ValueError as error:
                    logs = root/'.uncle/workflow/logs'
                    logs.mkdir(parents=True, exist_ok=True)
                    fd, rejected = tempfile.mkstemp(prefix='requirements-rejected-', suffix='.md', dir=logs)
                    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                        stream.write(response)
                    if attempt:
                        raise ValueError(str(error) + '; rejected response saved to ' + rejected) from None
                    print('Requirements response format rejected; retrying once. Response saved to ' + rejected, file=sys.stderr)
                    request += '\nThe previous response was rejected: ' + str(error) + '\nReturn only the full document, with no introductory text or edit instructions.'
                    continue
                candidate.write_text(document, encoding='utf-8', newline='\n')
                break
        else:
            request = prompt + '\nWrite the complete ' + artifact + ', including Verification commands and Protected verification paths fenced blocks.'
            turns = 0
            for attempt in range(2):
                attempt_usage = {}
                try:
                    response, count = _run_opencode(side, values, request, staged, allow_shell=False, usage=attempt_usage, diagnostic_root=root)
                    turns += count
                finally:
                    if usage is not None:
                        for key, value in attempt_usage.items():
                            usage[key] = usage.get(key, 0) + value
                if candidate.is_symlink():
                    raise ValueError('Refusing a symlinked plan; original preserved')
                try:
                    if not candidate.exists():
                        candidate.write_text(document_response(response, artifact), encoding='utf-8', newline='\n')
                    validate_plan(candidate.read_text(encoding='utf-8'), protected=artifact == 'UPDATED_PROJECT_PLAN.md')
                except ValueError as error:
                    logs = root/'.uncle/workflow/logs'
                    logs.mkdir(parents=True, exist_ok=True)
                    fd, rejected = tempfile.mkstemp(prefix=artifact.removesuffix('.md').lower() + '-rejected-', suffix='.md', dir=logs)
                    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                        stream.write(response)
                        if candidate.is_file():
                            stream.write('\n\n--- Candidate file ---\n' + candidate.read_text(encoding='utf-8'))
                    if attempt:
                        raise ValueError(str(error) + '; rejected response saved to ' + rejected) from None
                    if candidate.exists():
                        candidate.unlink()
                    print('Plan response format rejected; retrying once. Response saved to ' + rejected, file=sys.stderr)
                    request += '\nThe previous response was rejected: ' + str(error) + '\nWrite the complete document again. Close every Markdown fence, including any outer document wrapper. Include all required sections.'
                    continue
                break
        if not candidate.is_file() or candidate.is_symlink():
            raise ValueError('OpenCode did not produce a regular ' + artifact + '; original plan preserved')
        contents = candidate.read_bytes()
        if artifact != 'REQUIREMENTS_INTERPRETATION.md':
            validate_plan(contents.decode('utf-8'), protected=artifact == 'UPDATED_PROJECT_PLAN.md')
        else:
            validate_requirements(contents.decode('utf-8'))
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


def _run_opencode(side, values, prompt, root, allow_shell=True, usage=None, diagnostic_root=None):
    from process_tree import start_check, launch_command, kill_tree, finish_check
    seconds = int(os.environ.get('WORKFLOW_SELF_HOSTED_SECONDS', '3600'))
    if seconds < 1:
        raise ValueError('WORKFLOW_SELF_HOSTED_SECONDS must be positive')
    with tempfile.TemporaryDirectory(prefix='uncle-opencode-') as directory:
        command, env = opencode_invocation(side, values, prompt, root, directory, allow_shell=allow_shell)
        try:
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
                                raise ValueError(f'OpenCode exceeded its {seconds}-second time limit')
                finally:
                    try:
                        if child.poll() is None:
                            kill_tree(child)
                            child.wait()
                    finally:
                        finish_check(child)
                    if usage is not None:
                        usage.update(opencode_usage(Path(directory)/'output.log'))
            if status:
                # Do not expose CLI diagnostics that may contain inherited secrets.
                raise ValueError(f'OpenCode exited with status {status}; check its installation and endpoint configuration')
            try:
                response, turns = response_from_events(Path(directory)/'output.log')
            except ValueError:
                diagnostic = (Path(directory)/'output.log').read_text(encoding='utf-8', errors='replace')
                if re.search(r'APITimeoutError|litellm\.Timeout|provider timed out', diagnostic, re.I):
                    raise ValueError('Model API requests timed out without a response; check model-server logs, capacity, and proxy timeouts') from None
                raise
            return response, turns
        except (ValueError, OSError) as error:
            try:
                logs = (diagnostic_root or root)/'.uncle/workflow/logs'
                logs.mkdir(parents=True, exist_ok=True)
                output = Path(directory)/'output.log'
                detail = output.read_text(encoding='utf-8', errors='replace')[-262144:] if output.exists() else ''
                key = values.get('api_key', '')
                if key:
                    detail = detail.replace(key, '[REDACTED]')
                detail = re.sub(r'(?i)(bearer\s+)[^\s"\']+', r'\1[REDACTED]', detail)
                fd, saved = tempfile.mkstemp(prefix='opencode-failure-', suffix='.log', dir=logs)
                with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                    stream.write(str(error) + '\n\n' + (detail or 'OpenCode produced no console output.\n'))
            except OSError:
                raise error
            raise ValueError(str(error) + '; diagnostic log: ' + saved) from None


def profile_menu(config, choose=False):
    import getpass
    keys = read_keys(config)
    profiles = keys.setdefault('__opencode_models__', {})
    if choose:
        for name in sorted(profiles):
            print('  ' + name, file=sys.stderr)
        print('OpenCode model name: ', end='', file=sys.stderr, flush=True)
        name = input().strip()
        if name not in profiles:
            raise ValueError('Choose a configured OpenCode model; add models in Configure → OpenCode self-hosted models')
        print(name)
        return 0
    old = connection_settings(keys)
    url = input('Base URL [' + old.get('base_url', '') + ']: ').strip() or old.get('base_url', '')
    key = getpass.getpass('API key (hidden; blank keeps existing): ').strip() or old.get('api_key', '')
    print('Discovering OpenCode models…', flush=True)
    names = refresh_models(keys, url, key)
    save_keys(config, keys)
    print(f'Loaded {len(names)} OpenCode models: ' + ', '.join(names))
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
    values['max_turns'] = _turns
    def interrupt(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, interrupt)
    status_file = os.environ.get('UNCLE_STATUS_FILE')
    if status_file:
        with open(status_file,'a',encoding='utf-8',newline='\n') as stream:
            stream.write(json.dumps({'event':'start','stage':stage,'model':values['model'],
                                     'mode':'act' if side=='agent' else 'review'})+'\n')
    usage = {}
    try:
        text, turns = run_opencode(side, values, prompt, Path.cwd().resolve(), stage=stage, usage=usage)
    except (ValueError, OSError) as error:
        error.opencode_usage = usage
        raise
    if side == 'reviewer':
        if output:
            Path(output).write_bytes((text.rstrip()+'\n').encode('utf-8'))
        print(text)
        if usage:
            print(json.dumps({'type':'result', 'subtype':'success', 'is_error':False,
                              'model':values['model'], 'usage':usage, 'total_cost_usd':None,
                              'usage_source':'OpenCode step_finish events', 'usage_scope':'stage'}))
            print('tokens used\n' + str(usage['total_tokens']))
    else:
        print(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':text}]}}))
        print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':text,
                          'model':values['model'],'num_turns':turns,'duration_ms':int((time.monotonic()-started)*1000),'usage':usage,'total_cost_usd':None,
                          'usage_source':'OpenCode step_finish events','usage_scope':'stage'}))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', newline='\n')
    sys.stderr.reconfigure(encoding='utf-8', newline='\n')
    cli_started = time.monotonic()
    try:
        sys.exit(main(sys.argv[1], sys.argv[2:]))
    except KeyboardInterrupt:
        sys.exit(130)
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as error:
        print('Self hosted: ' + str(error), file=sys.stderr)
        if sys.argv[1:2] in (['agent'], ['reviewer']):
            print(json.dumps({'type':'result','subtype':'error','is_error':True,
                              'usage':getattr(error, 'opencode_usage', {}), 'total_cost_usd':None,
                              'error_detail':str(error), 'duration_ms':int((time.monotonic()-cli_started)*1000),
                              'usage_source':'OpenCode step_finish events','usage_scope':'stage'}))
        sys.exit(2)

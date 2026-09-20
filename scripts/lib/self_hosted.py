"""OpenCode-backed self-hosted runner and private endpoint configuration."""
import json
from contextlib import contextmanager
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



@contextmanager
def runner_directory(prefix):
    from process_tree import cleanup_directory
    directory = tempfile.TemporaryDirectory(prefix=prefix)
    try:
        yield directory.name
    finally:
        cleanup_directory(directory)


def key_file(config):
    return Path(config).parent / 'self-hosted-keys.json'


def local_model(name):
    name = name.removeprefix('openai/')
    return name if name.startswith('local/') else 'local/' + name


def read_keys(config):
    path = key_file(config)
    keys = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    # Read old credentials without rewriting them until the user saves config.
    if '__opencode_models__' not in keys and '__aider_models__' in keys:
        keys['__opencode_models__'] = {
            local_model(name): dict(profile, model=profile.get('model', name).removeprefix('openai/').removeprefix('local/'))
            for name, profile in keys.pop('__aider_models__').items()}
    if '__opencode_connection__' not in keys and '__aider_connection__' in keys:
        keys['__opencode_connection__'] = keys.pop('__aider_connection__')
    if '__opencode_models__' in keys:
        keys['__opencode_models__'] = {
            local_model(name): dict(profile, model=profile.get('model', name).removeprefix('openai/').removeprefix('local/'))
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
        return sorted({local_model(name) for name in names if name.removeprefix('openai/')})
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
    keys['__opencode_models__'] = {name: dict(connection, model=name.removeprefix('local/')) for name in names}
    return names


def config_stage(stage, values):
    """The stage whose config lines apply, mirroring uncle_config_stage in stage-config.sh.

    The preview build is not a Configure row; the shell resolver hands it the
    first configured model stage's runner and model. Reading its own key here
    instead found nothing and refused the very model the driver had chosen.
    """
    if stage in ('manual-checklist-base', 'manual-checklist-delta'):
        return 'manual-checklist'
    # Review-panel names contain both "-review-" and "-worker-".  Strip the
    # complete review-worker suffix before the generic worker case so, for
    # example, updated-plan-review-worker-scope inherits updated-plan rather
    # than looking for a nonexistent updated-plan-review config row.
    if '-review-worker-' in stage:
        return stage.split('-review-worker-', 1)[0]
    if '-worker-' in stage:
        return stage.split('-worker-', 1)[0]
    if stage.startswith('implementation-step-'):
        return 'implementation'
    if stage == 'preview-build' and not values.get('preview-build.model'):
        for key, value in values.items():
            if key.endswith('.model') and value and key != 'self-hosted.model':
                return key[:-len('.model')]
    return stage


def settings(config, stage):
    values = {}
    if Path(config).exists():
        for line in Path(config).read_text(encoding='utf-8').splitlines():
            parts = line.split('#', 1)[0].split(None, 1)
            if len(parts) == 2:
                values.setdefault(*parts)
    stage = config_stage(stage, values)
    result = {}
    for field in ('base_url', 'model'):
        result[field] = os.environ.get('UNCLE_SELF_HOSTED_' + field.upper()) or values.get(stage + '.' + field) or values.get('self-hosted.' + field, '')
    result['api_key'] = os.environ.get('UNCLE_SELF_HOSTED_API_KEY') or read_keys(config).get(stage, '')
    profiles = read_keys(config).get('__opencode_models__', {})
    selected = values.get(stage + '.model', '')
    if selected and selected not in profiles:
        selected = local_model(selected)
    if selected in profiles:
        profile = profiles[selected]
        result = dict(model=profile.get('model', selected), base_url=profile.get('base_url', ''), api_key=profile.get('api_key', ''))
    elif profiles and not values.get(stage + '.base_url'):
        raise ValueError('Select a configured OpenCode self-hosted model for stage ' + stage)
    for field in ('model', 'base_url', 'api_key'):
        result[field] = os.environ.get('UNCLE_SELF_HOSTED_' + field.upper()) or result[field]
    result['model'] = result['model'].removeprefix('openai/').removeprefix('local/')
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
    effort = ''
    turns = int(os.environ.get('UNCLE_STATUS_STAGE_TURNS') or 80)
    # Reviewer status uses zero to mean no explicit stage turn limit.
    # Explicit --max-turns values below still require a positive number.
    if turns == 0:
        turns = 80
    iterator = iter(args)
    valued = {'--model','-m','--sandbox','--allowedTools','--output-format',
              '--max-budget-usd','--resume','--mcp-config'}
    for arg in iterator:
        if arg == '--output-last-message':
            output = next(iterator)
        elif arg == '--max-turns':
            turns = int(next(iterator))
        elif arg == '--effort':
            effort = next(iterator)
        elif arg == '-c':
            override = next(iterator)
            if override.startswith('model_reasoning_effort='):
                effort = override.split('=', 1)[1]
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
    return output, prompt, turns, effort



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


OUTPUT_TOKENS_ENV = 'WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS'
CONTEXT_TOKENS_ENV = 'WORKFLOW_SELF_HOSTED_CONTEXT_TOKENS'


class OutputTruncated(ValueError):
    """The model reached the configured output limit: the response is a fragment."""


def output_token_limit(stage=''):
    """Configured output cap, with room for implementation reasoning.

    OpenCode counts reasoning inside its output limit. An implementation or
    checklist-execution agent can complete edits/tests and reports yet overflow
    an 8K/16K final stream, which incorrectly turns completed on-disk work into
    a failed stage. The same is true of manual-checklist synthesis: it reads
    every specialist packet from the review panel and writes the whole
    canonical checklist in one response. An updated plan is the same shape
    again: it must address or explicitly reject every adversarial finding
    (disposition rows for every F-/OW-/SCOPE-/V-/AR- id) while preserving the
    full plan, in one response, over a 16K retry cap once truncated once
    already. Keep review and short document defaults compact, but give
    long-running code, repair, checklist-writing/execution, and updated-plan
    synthesis stages a 32K first attempt; an explicit operator setting
    always wins.
    """
    # Dynamic workers inherit the parent stage's size class as well as its
    # configured model. This keeps every self-hosted worker consistent with
    # Claude, Cline, Codex, and Kimi through stage-config.sh.
    if '-review-worker-' in stage:
        stage = stage.split('-review-worker-', 1)[0]
    elif '-worker-' in stage:
        stage = stage.split('-worker-', 1)[0]
    configured = os.environ.get(OUTPUT_TOKENS_ENV)
    if configured:
        return int(configured)
    return 32768 if stage in ('implementation', 'repair', 'execute-checklist',
                               'manual-checklist', 'manual-checklist-base', 'manual-checklist-delta',
                               'updated-plan', 'updated-change-plan') \
        or stage.startswith('implementation-step-') else 8192


def context_token_limit():
    return int(os.environ.get(CONTEXT_TOKENS_ENV, '65536'))


def ensure_output_complete(usage, limit):
    """A response that used every output token it was allowed is cut off, not
    finished -- one review came back as three lines after 8,342 tokens of
    think-aloud, and was reported as success. output_tokens here includes
    reasoning tokens, which is what the limit governs."""
    produced = (usage or {}).get('output_tokens')
    if isinstance(produced, (int, float)) and not isinstance(produced, bool) and limit > 0 and produced >= limit:
        raise OutputTruncated('OpenCode output reached the configured limit of %d tokens (%d produced), '
                              'so the response is incomplete' % (limit, produced))


def response_from_events(path):
    events = opencode_events(path)
    if any(event.get('type') == 'error' for event in events):
        raise ValueError('OpenCode reported a model or session error')
    texts = [event.get('part', {}).get('text', '') for event in events if event.get('type') == 'text']
    finished = [event for event in events if event.get('type') == 'step_finish']
    if not texts or not texts[-1].strip() or not finished:
        raise ValueError('OpenCode returned no complete final response')
    reason = finished[-1].get('part', {}).get('reason')
    if reason in ('length', 'max_tokens', 'max_output_tokens'):
        raise OutputTruncated('OpenCode stopped at the output token limit (finish reason %s); the response is incomplete' % reason)
    if reason not in ('stop', 'end_turn'):
        raise ValueError('OpenCode stopped before completing the response')
    return texts[-1].strip(), len(finished)


def opencode_invocation(side, values, prompt, root, directory, allow_shell=True):
    work = Path(directory)
    (work/'prompt.txt').write_text(prompt, encoding='utf-8', newline='\n')
    model = values['model'].removeprefix('openai/').removeprefix('local/')
    request_seconds = int(os.environ.get('WORKFLOW_SELF_HOSTED_REQUEST_SECONDS') or os.environ.get('WORKFLOW_SELF_HOSTED_SECONDS', '3600'))
    if request_seconds < 1:
        raise ValueError('WORKFLOW_SELF_HOSTED_REQUEST_SECONDS must be positive')
    context = context_token_limit()
    output = output_token_limit(os.environ.get('UNCLE_STATUS_STAGE', ''))
    if not 0 < output < context:
        raise ValueError('Model limits require 0 < output tokens < context tokens')
    permission = {'*': 'deny', 'read': {'*': 'allow', '*.env': 'deny', '*.env.*': 'deny',
                  '*self-hosted-keys.json': 'deny'}, 'glob': 'allow', 'grep': 'allow',
                  'list': 'allow', 'edit': 'allow' if side == 'agent' else 'deny',
                  'bash': 'allow' if side == 'agent' and allow_shell else 'deny',
                  'external_directory': 'deny'}
    entry = {'name': model, 'tool_call': True, 'limit': {'context': context, 'output': output}}
    if values.get('effort'):
        # Passthrough per opencode's model options; the endpoint decides
        # whether a reasoning effort changes anything.
        entry['options'] = {'reasoningEffort': values['effort']}
    config = {
        '$schema': 'https://opencode.ai/config.json',
        'enabled_providers': ['local'], 'model': 'local/' + model,
        'small_model': 'local/' + model, 'share': 'disabled', 'autoupdate': False,
        'snapshot': False, 'permission': permission,
        'agent': {'uncle': {'mode': 'primary', 'description': 'Uncle workflow stage',
                            'steps': values.get('max_turns', 80),
                            'permission': permission}},
        'provider': {'local': {'npm': '@ai-sdk/openai-compatible', 'name': 'Uncle self hosted',
                     'options': {'baseURL': values['base_url'].rstrip('/'),
                                 'apiKey': '{env:UNCLE_OPENCODE_API_KEY}', 'timeout': request_seconds * 1000},
                     'models': {model: entry}}},
    }
    env = {k: v for k, v in os.environ.items() if not k.startswith(('OPENCODE_', 'AIDER_'))}
    # The adapter owns the live channel; tools/tests launched by the client
    # must not inherit the outer workflow's project or issue identity.
    for key in ('UNCLE_STATUS_FILE', 'UNCLE_PROJECT_ROOT', 'UNCLE_CONFIG',
                'STAGEGATE_RUN_ID', 'STAGEGATE_ORIGIN_REPO', 'STAGEGATE_ORIGIN_ISSUE',
                'DOCUMENT_BUDGET_SOURCE'):
        env.pop(key, None)
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
               '--dir', str(root), '--model', 'local/' + model, '--agent', 'uncle',
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


REVIEW_VALIDATORS = {
    'ADVERSARIAL_REVIEW.md': 'adversarial-context.py',
    'FINAL_AUDIT.md': 'final-audit-context.py',
    'MANUAL_CHECKLIST.md': 'checklist_document.py',
}


class InvalidReviewerDocument(ValueError):
    """The reviewer's final message is not the document the stage owns."""


# Text that can only come from the driver's own terminal/log narration, never
# from a reviewer's document, whatever its schema. A verbose self-hosted model
# has echoed a prior turn's tool-log/driver output back inside its own
# response before, and the fenced-document extraction in reviewer_document()
# does not defend against garbage placed outside any fence at all. Catching
# it here, generically, means every reviewer artifact gets this guard, not
# only the ones with a dedicated per-document format validator below.
DRIVER_NARRATION_MARKERS = (
    '{"type": "result"',
    'Current workflow state:',
    'System: Workflow stopped',
    'Recovery: ask about the failure',
)


def validate_reviewer_document(output, document):
    """Run the artifact's own format validator on the candidate text.

    A reviewer's artifact is its last message, and its last message is not
    always the review: after OpenCode compacts a full context the model
    answers the compaction prompt -- "what did we do so far" -- and that
    summary was written as ADVERSARIAL_REVIEW.md. The agent path already
    validates a plan before publishing it; the reviewer path published
    whatever came back.
    """
    marker = next((m for m in DRIVER_NARRATION_MARKERS if m in document), None)
    if marker:
        raise InvalidReviewerDocument(
            'Reviewer response is not a valid %s: contains driver narration (%r), not the document itself'
            % (Path(output).name, marker))
    validator = REVIEW_VALIDATORS.get(Path(output).name)
    if not validator:
        return
    with tempfile.NamedTemporaryFile('w', suffix='.md', prefix='reviewer-candidate-', delete=False, encoding='utf-8') as handle:
        handle.write(document)
        candidate = handle.name
    try:
        result = subprocess.run([sys.executable, '-B', str(Path(__file__).parent / validator), '--validate', candidate],
                                capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(candidate)
    if result.returncode:
        reason = (result.stderr or result.stdout).strip().splitlines()
        reason = reason[0] if reason else 'validator rejected the document'
        reason = reason.split('. Correct the saved')[0]
        raise InvalidReviewerDocument('Reviewer response is not a valid %s: %s' % (Path(output).name, reason))


def reviewer_document(response):
    """A reviewer's response with any leading think-aloud removed.

    No title synthesis, no rejection: the reviewer owns this artifact and the
    validators downstream judge its content. This only drops text that cannot
    be part of the document. A response with no heading at all is returned
    unchanged so the stage's own validator reports the real problem.

    A fenced block elsewhere in the response is stronger evidence of "the
    actual document" than an early line that merely matches the heading regex:
    a stray fragment of prior analysis ("### ~~MC-005~~ [DELETED: ...]") can
    look exactly like a heading while being nowhere near the real content,
    which the model then produced, correctly, inside its own fence further
    down. Once, a corrupted MANUAL_CHECKLIST.md was exactly this: 37 lines of
    leftover think-aloud starting with a heading-shaped fragment, then the
    real checklist fenced in full below it -- and the naive first-heading scan
    published the whole thing, fence markers included, as the document.
    """
    text = re.sub(r'<think>.*?</think>', '', response, flags=re.S).strip()
    lines = text.splitlines()

    def first_heading(candidate):
        return next((i for i, line in enumerate(candidate) if re.match(r'^#{1,6}\s+\S', line)), None)

    # Check every closed fence, not just the first: a verbose response can
    # wrap throwaway commentary, a stub outline, or tool-call narration in an
    # earlier bare fence before the real document's own fence further down.
    # Stopping at the first fence that doesn't qualify abandoned fence-scanning
    # entirely and fell through to the naive whole-response scan below, which
    # is exactly how a real MANUAL_CHECKLIST.md landed on disk as a stub
    # table of contents followed by narration and JSON tool-log blobs: the
    # real, complete, fenced checklist further down was never even looked at.
    fence_open = re.compile(r'^(`{3,}|~{3,})(?:markdown|md)?\s*$')
    for index, line in enumerate(lines):
        match = fence_open.match(line)
        if not match:
            continue
        fence = match[1]
        closing = next((j for j in range(index + 1, len(lines)) if lines[j].strip() == fence), None)
        if closing is None:
            continue
        inner = lines[index + 1:closing]
        inner_start = first_heading(inner)
        if inner_start is not None:
            return '\n'.join(inner[inner_start:]).strip() + '\n'

    start = first_heading(lines)
    if start is None:
        # No heading anywhere. One definition of "is this a document" for every
        # runner lives in reviewer_output; see it for why this check exists.
        from reviewer_output import check as _check_document
        _check_document(text, 'self-hosted reviewer')
        return text.rstrip() + '\n'
    if start == 0:
        return text.rstrip() + '\n'
    return '\n'.join(lines[start:]).strip() + '\n'


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
            request = prompt + '\nWrite the complete REQUIREMENTS_INTERPRETATION.md using your file tools, starting with its # heading and including ## 10. Definition of done. If returning the document instead, return complete Markdown, not tool-call markup.'
            turns = 0
            for attempt in range(2):
                attempt_usage = {}
                try:
                    response, count = _run_opencode('agent', values, request, staged, allow_shell=False, usage=attempt_usage, diagnostic_root=root, usage_baseline=usage)
                    turns += count
                finally:
                    if usage is not None:
                        for key, value in attempt_usage.items():
                            usage[key] = usage.get(key, 0) + value
                try:
                    if candidate.is_symlink():
                        raise ValueError('Refusing a symlinked requirements document')
                    document = candidate.read_text(encoding='utf-8') if candidate.is_file() else document_response(response, artifact)
                    validate_requirements(document)
                except ValueError as error:
                    logs = root/'.uncle/workflow/logs'
                    logs.mkdir(parents=True, exist_ok=True)
                    fd, rejected = tempfile.mkstemp(prefix='requirements-rejected-', suffix='.md', dir=logs)
                    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                        stream.write(response)
                        if candidate.is_file() and not candidate.is_symlink():
                            stream.write('\n\n--- Candidate file ---\n' + candidate.read_text(encoding='utf-8'))
                    if candidate.exists() or candidate.is_symlink():
                        candidate.unlink()
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
                    response, count = _run_opencode(side, values, request, staged, allow_shell=False, usage=attempt_usage, diagnostic_root=root, usage_baseline=usage)
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


def _run_opencode(side, values, prompt, root, allow_shell=True, usage=None, diagnostic_root=None, usage_baseline=None):
    from process_tree import start_check, launch_command, kill_tree, finish_check
    seconds = int(os.environ.get('WORKFLOW_SELF_HOSTED_SECONDS', '3600'))
    if seconds < 1:
        raise ValueError('WORKFLOW_SELF_HOSTED_SECONDS must be positive')
    # A reviewer has one authoritative output: its document.  In a live
    # steering session, a conversational question can arrive after the review
    # request and its answer becomes the adapter's final message, replacing
    # the requested checklist/audit/plan artifact.  Keep live steering for
    # agents, where conversation is part of their work, but run reviewers as
    # one isolated document request.
    if os.environ.get('UNCLE_STEERING') == '1' and side != 'reviewer':
        from native_stage import Stage
        from native_opencode import run as native_run
        adapter = Stage('self-hosted', side, os.environ.get('UNCLE_STATUS_STAGE', ''), [], prompt=prompt)
        adapter.model = values['model']
        adapter.usage_baseline = dict(usage_baseline or {})
        with runner_directory(prefix='uncle-opencode-live-') as directory:
            try:
                adapter.watch_parent()
                native_run(adapter, directory, values=values, root=root, allow_shell=allow_shell)
                if not adapter.answer.strip():
                    raise ValueError('OpenCode returned no response')
                ensure_output_complete({'output_tokens': adapter.usage.get('output_tokens')},
                                       output_token_limit(os.environ.get('UNCLE_STATUS_STAGE', '')))
                return adapter.final_answer or adapter.answer, 1
            finally:
                adapter.parent_watch_stop.set()
                if adapter.channel:
                    adapter.status('steering_closed', channel=str(adapter.channel))
                if usage is not None:
                    usage['input_tokens'] = adapter.usage['input_tokens'] + adapter.usage['cache_read_input_tokens'] + adapter.usage['cache_creation_input_tokens']
                    usage['output_tokens'] = adapter.usage['output_tokens']
                    if adapter.cost is not None:
                        usage['_total_cost_usd'] = adapter.cost
                    usage['total_tokens'] = usage['input_tokens'] + usage['output_tokens']
                if adapter.child is not None:
                    if adapter.child.poll() is None:
                        kill_tree(adapter.child)
                        adapter.child.wait()
                    finish_check(adapter.child)
    with runner_directory(prefix='uncle-opencode-') as directory:
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
            ensure_output_complete(opencode_usage(Path(directory)/'output.log'), output_token_limit())
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
            # Keep the type: a truncation must still read as one to the retry in
            # main(), and an OSError as an OSError to its callers.
            wrapped = type(error)(str(error) + '; diagnostic log: ' + saved) if isinstance(error, ValueError) \
                else ValueError(str(error) + '; diagnostic log: ' + saved)
            raise wrapped from None


def profile_menu(config, choose=False):
    import getpass
    keys = read_keys(config)
    profiles = keys.setdefault('__opencode_models__', {})
    if choose:
        for name in sorted(profiles):
            print('  ' + name, file=sys.stderr)
        print('OpenCode model name: ', end='', file=sys.stderr, flush=True)
        name = local_model(input().strip())
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
    output, prompt, _turns, effort = parse_arguments(side, args)
    stage = os.environ.get('UNCLE_STATUS_STAGE', '')
    if not stage and side == 'reviewer' and output:
        stage = Path(output).stem.lower().replace('_','-')
    config = os.environ.get('UNCLE_CONFIG', str(Path.cwd()/'.uncle/config'))
    values = settings(config, stage)
    values['max_turns'] = _turns
    if effort:
        values['effort'] = effort
    def interrupt(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, interrupt)
    status_file = os.environ.get('UNCLE_STATUS_FILE')
    if status_file:
        with open(status_file,'a',encoding='utf-8',newline='\n') as stream:
            stream.write(json.dumps({'event':'start','stage':stage,'model':local_model(values['model']),
                                     'mode':'act' if side=='agent' else 'review'})+'\n')
    usage = {}
    def add_usage(attempt_usage):
        for key, value in attempt_usage.items():
            if isinstance(value, (int, float)) and isinstance(usage.get(key, 0), (int, float)):
                usage[key] = usage.get(key, 0) + value
            else:
                usage[key] = value
    truncation_retried = format_retried = False
    document = None
    while True:
        attempt_usage = {}
        try:
            text, turns = run_opencode(side, values, prompt, Path.cwd().resolve(), stage=stage, usage=attempt_usage)
            add_usage(attempt_usage)
            if side == 'reviewer' and output:
                document = reviewer_document(text)
                validate_reviewer_document(output, document)
        except OutputTruncated as error:
            add_usage(attempt_usage)
            # A fragment reported as success is what the whole stage then
            # adopts. Once, the cap is doubled and the stage rerun; a second
            # fragment is the failure it always was.
            limit = output_token_limit(stage)
            larger = min(limit * 2, context_token_limit() - 1024)
            if truncation_retried or larger <= limit:
                error.opencode_usage = usage
                raise
            truncation_retried = True
            print('Self hosted: %s. Retrying once with an output limit of %d tokens.' % (error, larger), file=sys.stderr)
            os.environ[OUTPUT_TOKENS_ENV] = str(larger)
            continue
        except InvalidReviewerDocument as error:
            # Not the document: a compaction summary, a findings table with a
            # "next step" of writing the review, a fragment. Keep it in the
            # logs as evidence, and ask once more in a fresh session; never
            # publish it as the reviewer-owned artifact.
            logs = Path.cwd() / '.uncle/workflow/logs'
            logs.mkdir(parents=True, exist_ok=True)
            fd, rejected = tempfile.mkstemp(prefix=Path(output).stem.lower() + '-rejected-', suffix='.md', dir=logs)
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(text)
            if format_retried:
                error.opencode_usage = usage
                raise InvalidReviewerDocument(str(error) + '; rejected response saved to ' + rejected) from None
            format_retried = True
            print('Self hosted: %s. Rejected response saved to %s; retrying once.' % (error, rejected), file=sys.stderr)
            # Generic on purpose: this path serves every reviewer document
            # (adversarial review, test review, manual checklist, final audit,
            # ...), each with its own heading/table schema from the original
            # prompt. Hardcoding one document's shape here previously sent a
            # checklist or audit retry the adversarial-review finding format,
            # steering an already-struggling model further off course.
            prompt += ('\n\nThe previous response was rejected: ' + str(error) +
                       '\nReturn only the complete ' + Path(output).name + ' as your final message, in the '
                       'exact layout already specified above. Do not summarize your work, describe a plan to '
                       'write it, or promise to produce it later. You have no write or shell tools in this role; '
                       'the document text you return is the only artifact.')
            continue
        except (ValueError, OSError) as error:
            error.opencode_usage = attempt_usage
            raise
        break
    if side == 'reviewer':
        if output:
            # A reviewer's document is its final message, so any think-aloud the
            # model emitted before the document lands in the artifact. The agent
            # path already strips that; reviewers reached the file untouched,
            # and a reviewer-owned artifact is the one thing no later stage may
            # edit. Strip here, and only when a document is actually present --
            # a response with no heading is a real failure, not a preamble.
            Path(output).write_bytes((document if document is not None else reviewer_document(text)).encode('utf-8'))
        print(text)
        if usage:
            print(json.dumps({'type':'result', 'subtype':'success', 'is_error':False,
                              'model':local_model(values['model']), 'usage':usage, 'total_cost_usd':usage.get('_total_cost_usd'),
                              'usage_source':'OpenCode step_finish events', 'usage_scope':'stage'}))
            print('tokens used\n' + str(usage['total_tokens']))
    else:
        print(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':text}]}}))
        print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':text,
                          'model':local_model(values['model']),'num_turns':turns,'duration_ms':int((time.monotonic()-started)*1000),'usage':usage,'total_cost_usd':usage.get('_total_cost_usd'),
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
                              'usage':getattr(error, 'opencode_usage', {}), 'total_cost_usd':getattr(error, 'opencode_usage', {}).get('_total_cost_usd'),
                              'error_detail':str(error), 'duration_ms':int((time.monotonic()-cli_started)*1000),
                              'usage_source':'OpenCode step_finish events','usage_scope':'stage'}))
        sys.exit(2)

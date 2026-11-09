"""Transport for direct-HTTP self-hosted stages.

OpenCode cannot force a model server to honour a JSON schema, so self-hosted
stages talk to the OpenAI-compatible endpoint themselves (see http_agent).  This
module owns the wire: server detection, the strongest schema-constraint mode the
server accepts with clean fallback, temperature, usage and schema conformance.

Connections are persistent: one is kept per server and reused for every request
of a stage, so the many small tool-loop turns pay for TCP/TLS setup once.  HTTP/2
is used where it can be negotiated (https, via ALPN) when httpx and h2 are
installed; plain http servers speak HTTP/1.1 keep-alive.
"""
import contextlib
import contextvars
import errno
import http.client
import io
import json
import os
import re
import socket
import sys
import threading
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from self_hosted_stream import StreamStopped, assemble as assemble_stream

REJECTED = (400, 404, 405, 415, 422, 501)
_capabilities = {}
_request_features = {}          # optional fields learned per Base URL, like schema modes

# Includes the native Ollama schema and token-budget containers. Keep this in
# step with _final_call/chat: request options cannot weaken their contracts.
PROTECTED_REQUEST_KEYS = frozenset({
    'model', 'messages', 'tools', 'tool_choice', 'stream', 'stream_options',
    'response_format', 'structured_outputs', 'guided_json', 'format', 'options',
    'max_tokens', 'max_completion_tokens', 'max_output_tokens', 'num_predict',
})


def _parse_request_options(text, source):
    if '\n' in text or '\r' in text:
        raise ValueError('%s must be a single-line JSON object' % source)
    if len(text.encode('utf-8')) > 4096:
        raise ValueError('%s must be at most 4096 bytes (4 KB)' % source)
    try:
        result = json.loads(text)
        # Python accepts NaN/Infinity (including overflowing exponents); JSON
        # does not. Never let these produce a malformed request body.
        json.dumps(result, allow_nan=False)
    except (ValueError, RecursionError):
        raise ValueError('%s must be a valid JSON object' % source) from None
    if not isinstance(result, dict):
        raise ValueError('%s must be a JSON object' % source)
    for key in result:
        if key in PROTECTED_REQUEST_KEYS:
            raise ValueError('%s contains protected request key %s' % (source, key))
    return result


def _lookup_request_options(stage=None, config=None):
    """(whether anything was configured for this stage, the options). `{}` configured explicitly is "found": it opts out."""
    from self_hosted import config_stage
    stage = os.environ.get('UNCLE_STATUS_STAGE', '') if stage is None else stage
    config = _config_values() if config is None else config
    names = list(dict.fromkeys([stage, config_stage(stage, config)]))
    for name in names + ['']:
        var = 'WORKFLOW_SELF_HOSTED_REQUEST_OPTIONS'
        if name:
            var += '_' + re.sub(r'[^A-Z0-9]', '_', name.upper())
        if var in os.environ:
            return True, _parse_request_options(os.environ[var], var)
    for name in names + ['self-hosted']:
        key = name + '.request-options'
        if key in config:
            return True, _parse_request_options(config[key], key)
    return False, {}


def request_options(stage=None, config=None):
    """Resolve one whole object; {} explicitly opts out of inherited options."""
    return _lookup_request_options(stage, config)[1]


# The stages that run without thinking are the same on every runner (scripts/lib/thinking-off.sh, uncle_stage_thinking_off: claude
# gets MAX_THINKING_TOKENS=0, codex and kimi their no-thinking effort). Self-hosted gets the equivalent here: unless the operator
# configured request options for the stage (an explicit {} included), those stages' requests turn thinking off, the setting the
# updated-plan retry path already sends. WORKFLOW_THINKING=on restores thinking everywhere, and WORKFLOW_THINKING_OFF_EXTRA adds
# stage globs, exactly as for the other runners. Keep THINKING_OFF_STAGES in step with thinking-off.sh (a test compares them).
THINKING_OFF_STAGES = (
    'requirements', 'requirements-investigate', 'project-plan', 'project-plan-investigate', 'project-plan-section-*',
    'updated-plan', 'updated-plan-*', 'updated-change-plan', 'updated-change-plan-*',
    'preflight', 'preflight-*', 'preview-build', 'preview-build-*', 'module-interfaces', 'classify-change',
    'execute-checklist', 'execute-checklist-*', 'test-review', 'test-review-*', 'final-audit', 'final-audit-*')


def thinking_off_stage(stage):
    import fnmatch
    if os.environ.get('WORKFLOW_THINKING', 'auto') == 'on' or os.environ.get('WORKFLOW_WORKER_THINKING', '').lower() in ('on', '1', 'true'):
        return False
    patterns = THINKING_OFF_STAGES + tuple(os.environ.get('WORKFLOW_THINKING_OFF_EXTRA', '').split())
    return any(fnmatch.fnmatchcase(stage, pattern) for pattern in patterns)


def worker_default_options(stage, found):
    if found or not thinking_off_stage(stage or ''):
        return None
    return {'chat_template_kwargs': {'enable_thinking': False}}


def configure_request_options(values, stage=None, config=None):
    """Snapshot and validate at stage start, before tools or server discovery."""
    if os.environ.get('UNCLE_UPDATED_PLAN_CHEAP_RETRY') == '1':
        options = dict(values.get('_request_options', request_options(stage, config)))
        options['chat_template_kwargs'] = dict(options.get('chat_template_kwargs') or {}, enable_thinking=False)
        return dict(values, _request_options=options,
                    _request_options_stage=stage or os.environ.get('UNCLE_STATUS_STAGE', ''))
    if '_request_options' in values:
        return values
    stage = os.environ.get('UNCLE_STATUS_STAGE', '') if stage is None else stage
    found, options = _lookup_request_options(stage, config)
    options = worker_default_options(stage, found) or options
    return dict(values, _request_options=options, _request_options_stage=stage)


def merge_request_options(body, options):
    """One-level object merge; Uncle owns existing non-object top-level keys."""
    result, applied = dict(body), {}
    for key, value in options.items():
        if key in PROTECTED_REQUEST_KEYS:
            raise ValueError('request-options contains protected request key %s' % key)
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = dict(result[key], **value)
            applied[key] = value
        elif key not in result:
            result[key] = value
            applied[key] = value
    return result, applied


def _error_detail(error):
    if not hasattr(error, '_uncle_detail'):
        error._uncle_detail = error.read().decode('utf-8', errors='replace').lower()
    return error._uncle_detail


def _names_option(detail, options):
    for key, value in options.items():
        if key and re.search(r'(?<![\w])' + re.escape(key.lower()) + r'(?![\w])', detail):
            return True
        if isinstance(value, dict) and _names_option(detail, value):
            return True
    return False


def _server_reason(error, limit=300):
    """The server's own words for a refusal, on one line, for error messages."""
    try:
        detail = ' '.join(_error_detail(error).split())
    except Exception:
        return ''
    return (': ' + detail[:limit]) if detail else ''


# The reason the last tool-capable turn was refused, so "no tool calling" can say what the server said.
last_rejection = ''


def _has_temperature(body):
    return 'temperature' in body or 'temperature' in (body.get('options') or {})


def _without_temperature(body):
    clean = {key: value for key, value in body.items() if key != 'temperature'}
    if isinstance(clean.get('options'), dict):
        clean['options'] = {key: value for key, value in clean['options'].items() if key != 'temperature'}
    return clean


def compatible_post(values, body, timeout, url=None):
    """Reserve reasoning separately from the deliverable cap on every transport."""
    from self_hosted_stream import ANSWER_CAP, answer_signal, output_accounting
    if isinstance(values, dict) and values.get('_profile') == 'aws-bedrock':
        return _bedrock_converse_post(values, _strip_temperature(body), timeout)  # Self Hosted bodies stay untouched
    answer_cap = body.get('max_tokens', body.get('options', {}).get('num_predict'))
    if answer_cap is None:
        return _compatible_output_post(values, body, timeout, url)
    # OpenAI max_tokens and Ollama num_predict include reasoning. Even servers
    # that omit/reject reasoning_effort may still think, so always reserve room.
    reserve = output_cap(2 ** 31 - 1, 'reasoning-output-tokens')
    body = dict(body)
    if 'max_tokens' in body:
        body['max_tokens'] = answer_cap + reserve
    else:
        body['options'] = dict(body['options'], num_predict=answer_cap + reserve)
    token = ANSWER_CAP.set(answer_cap)
    try:
        data = _compatible_output_post(values, body, timeout, url)
        # Non-streaming fallback cannot interrupt generation, but still checks
        # the answer before capture or tool execution. Native Ollama reports
        # thinking separately and eval_count as the combined completion total.
        native = 'message' in data and 'choices' not in data
        message = data['message'] if native else (data.get('choices') or [{}])[0].get('message', {})
        if native:
            message = dict(message, reasoning_content=message.get('thinking', ''))
        usage = data.get('usage') or ({'completion_tokens': data.get('eval_count')} if native else {})
        accounting = output_accounting(message, usage)
        if answer_signal(accounting) > answer_cap:
            raise StreamStopped('answer_cap', usage=dict(usage, **accounting))
        data['usage'] = dict(usage, **accounting)
        return data
    finally:
        ANSWER_CAP.reset(token)


def _profile_prefix(region):
    head = (region or '').split('-', 1)[0]
    return {'eu': 'eu', 'ap': 'apac', 'us': 'us'}.get(head, 'global')


_CONVERSE_REASONS = {'end_turn': 'stop', 'max_tokens': 'length', 'tool_use': 'tool_calls'}


def _bedrock_converse_post(values, body, timeout):
    """Converse transport: translate the OpenAI-style body, POST via the `_request` seam (never redirected,
    so the token stays on the region's runtime host), return an OpenAI-shaped response so callers are unchanged."""
    import bedrock_protocols as bp
    token, model = values['api_key'], values['model']
    schema, name = None, 'result'
    rf = body.get('response_format') or {}
    if rf.get('type') == 'json_schema':
        schema, name = rf['json_schema']['schema'], rf['json_schema'].get('name', 'result')
    native = _strip_temperature(bp.build_body(body['messages'], body.get('max_tokens', 4096), body.get('tools'), schema, name))
    region = values.get('region') or bp.region_from_url(values.get('base_url')) or ''
    url = bp.build_url(region, model)
    def attempt(payload):
        # Parallel workers share one account quota: throttling (429) and overload (503, 529) are retried with
        # backoff instead of failing the stage.
        import random, time
        for tries in range(8):
            try:
                return attempt_once(payload)
            except HTTPError as error:
                if error.code not in (429, 503, 529) or tries == 7:
                    raise
                delay = min(60.0, 2.0 * (2 ** tries)) * (0.5 + random.random() / 2)
                print('Self hosted: AWS Bedrock HTTP %d; retrying in %.0fs.' % (error.code, delay), file=sys.stderr, flush=True)
                time.sleep(delay)

    def attempt_once(payload):
        nonlocal url, model
        try:
            return _request(url, token, payload, timeout, headers=bp.build_headers(token))
        except HTTPError as error:
            # Newer models only accept an inference-profile ID (geo prefix) for on-demand use.
            prefix = _profile_prefix(region)
            if error.code != 400 or model.split('.', 1)[0] in ('us', 'eu', 'apac', 'global', 'jp', 'au', 'ca', 'us-gov'):
                raise
            try:
                raw_body = error.read() or b'{}'
                error.fp = __import__('io').BytesIO(raw_body)  # keep the body for detail()
                note = json.loads(raw_body).get('message', '')
            except (ValueError, AttributeError, OSError):
                note = ''
            if 'inference profile' not in str(note).lower():
                raise
            model = prefix + '.' + model
            url = bp.build_url(region, model)
            return _request(url, token, payload, timeout, headers=bp.build_headers(token))

    def detail(error):
        # AWS's own explanation (never the token: _request already redacted it), bounded.
        try:
            message = json.loads(error.read() or b'{}').get('message', '')
        except (ValueError, AttributeError, OSError):
            return ''
        return ': ' + message[:300].replace('\n', ' ') if isinstance(message, str) and message else ''

    try:
        try:
            raw = attempt(native)
        except HTTPError as error:
            # Models differ in their output ceiling; retry once at the smallest common one.
            limit = native['inferenceConfig']['maxTokens']
            note = detail(error)
            if error.code == 400 and 'toolConfig' in native and any(w in note.lower() for w in ('tool', 'schema')):
                # The model rejects forced tool schemas: ask for the JSON in plain text instead
                # (the callers already request it in the prompt and validate it).
                native.pop('toolConfig')
                try:
                    return _converse_result(attempt(native), None, model)
                except HTTPError as again:
                    again.detail = detail(again)
                    raise
            if error.code != 400 or limit <= 4096 or 'token' not in note.lower():
                error.detail = note
                raise
            native['inferenceConfig']['maxTokens'] = 4096
            try:
                raw = attempt(native)
            except HTTPError as again:
                again.detail = detail(again)
                raise
    except HTTPError as error:
        if 300 <= error.code < 400:
            raise ValueError('AWS Bedrock request for model %s was redirected (HTTP %d); not followed' % (model, error.code)) from None
        raise ValueError('AWS Bedrock request failed (HTTP %d); check the Region, token and model %s%s'
                         % (error.code, model, getattr(error, 'detail', ''))) from None
    return _converse_result(raw, name if schema else None, model)


def _converse_result(raw, schema_name, model):
    import bedrock_protocols as bp
    try:
        parsed = bp.parse_response(raw, schema_name)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError('AWS Bedrock Converse response for model %s has no output.message.content' % model) from None
    message = {'role': 'assistant', 'content': parsed['text']}
    if parsed['tool_calls']:
        message['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {'name': c['name'], 'arguments': json.dumps(c['arguments'])}}
                                 for c in parsed['tool_calls']]
    u, reason = parsed['usage'], parsed['reason']
    return {'choices': [{'message': message, 'finish_reason': _CONVERSE_REASONS.get(reason, reason)}],
            'usage': {'prompt_tokens': u['input'], 'completion_tokens': u['output'], 'total_tokens': u['input'] + u['output']}}


def _compatible_output_post(values, body, timeout, url=None):
    """Apply extras to every turn, with fallback separate from effort/schema."""
    values = configure_request_options(values)
    base = values['base_url'].rstrip('/')
    url = url or base + '/chat/completions'
    features = _request_features.setdefault(base, {})
    options = values['_request_options'] if features.get('request_options') is not False else {}
    request, applied = merge_request_options(body, options)
    stage = values['_request_options_stage'] or 'self-hosted'
    keys = ', '.join(json.dumps(key) for key in sorted(applied))
    if applied:
        logged = features.setdefault('request_options_logged', set())
        identity = (stage, tuple(sorted(applied)))
        if identity not in logged:
            print('Self hosted [%s]: request options applied: %s.' % (stage, keys), file=sys.stderr)
            logged.add(identity)

    def disabled():
        if features.get('request_options') is not False:
            print('Self hosted [%s]: server rejected request options %s; using a retry without options '
                  'and omitting them for this Base URL for this process.' % (stage, keys), file=sys.stderr)
        features['request_options'] = False

    def without_options(candidate):
        clean = dict(candidate)
        for key in applied:
            if key in body:
                clean[key] = body[key]
            else:
                clean.pop(key, None)
        return clean

    no_temperature = features.setdefault('no_temperature_models', set())

    def post_body(candidate):
        """Hosted OpenAI-compatible gateways refuse `temperature` on some models (newer Claude and GPT
        models on Bedrock-backed gateways). Retry without it once and omit it for that model from then on."""
        model = candidate.get('model')
        if model in no_temperature:
            candidate = _without_temperature(candidate)
        try:
            return post(url, values['api_key'], candidate, timeout)
        except HTTPError as error:
            if not (400 <= error.code < 500 and _has_temperature(candidate) and
                    _names_option(_error_detail(error), {'temperature': None})):
                raise
            print('Self hosted [%s]: server rejected temperature for model %s; retrying without it and '
                  'omitting it for this model on this Base URL for this process.' % (stage, model), file=sys.stderr)
            no_temperature.add(model)
            return post(url, values['api_key'], _without_temperature(candidate), timeout)

    def send(candidate):
        clean = without_options(candidate)
        if not applied or features.get('request_options') is False:
            return post_body(clean)
        try:
            return post_body(candidate)
        except HTTPError as error:
            detail = _error_detail(error)
            if not 400 <= error.code < 500:
                raise
            if _names_option(detail, applied):
                disabled()
                return post_body(clean)
            # Explicit errors about a different protocol feature belong to
            # its own fallback. A generic 400 warrants an otherwise-identical
            # A/B probe, without changing effort or schema during that probe.
            if error.code != 400 or _names_option(detail, dict.fromkeys((
                    'reasoning_effort', 'reasoning_content', 'reasoning', 'response_format', 'json_schema',
                    'structured_outputs', 'guided_json', 'tools', 'tool_choice', 'format', 'stream', 'stream_options'))):
                raise
            try:
                result = post_body(clean)
            except HTTPError:
                raise error from None  # no evidence against options; retain support
            disabled()
            return result

    return _compatible_post(values, request, lambda candidate: streaming_post(
        url, values['api_key'], candidate, timeout, features, send=send))


def option(name, default):
    """Self-hosted-only option: WORKFLOW_SELF_HOSTED_* overrides .uncle/config."""
    return os.environ.get('WORKFLOW_SELF_HOSTED_' + name.upper().replace('-', '_'),
                          _config_values().get('self-hosted.' + name, default)).strip().lower()


def positive_option(name, default, minimum=1):
    value = int(option(name, str(default)))
    if value < minimum:
        raise ValueError('self-hosted.%s must be at least %d' % (name, minimum))
    return value


def streaming_post(url, key, body, timeout, features, send=None):
    """Negotiate SSE and usage independently; never confuse schema rejection with streaming.

    Generic 400s use otherwise-identical probes, and only a successful probe
    teaches a fallback. Memory is per Base URL for the life of this process.
    Native Ollama /api/chat keeps its native non-streaming wire format.
    """
    send = send or (lambda candidate: post(url, key, candidate, timeout))
    if not url.endswith('/chat/completions') or features.get('stream') is False:
        return send(body)
    candidate = dict(body, stream=True)
    if features.get('stream_usage') is not False:
        candidate['stream_options'] = {'include_usage': True}
    try:
        return send(candidate)
    except HTTPError as original:
        detail = _error_detail(original)
        if original.code not in REJECTED:
            raise
        named = _names_option(detail, {'stream': None, 'stream_options': None, 'include_usage': None})
        if not named and (original.code != 400 or _names_option(detail, dict.fromkeys((
                'response_format', 'json_schema', 'structured_outputs', 'guided_json', 'reasoning_effort',
                'reasoning_content', 'reasoning', 'tools', 'tool_choice', 'format')))):
            raise
        if 'stream_options' in candidate:
            candidate.pop('stream_options')
            try:
                result = send(candidate)
            except StreamStopped:
                # HTTP/SSE was accepted even though generation itself failed.
                features['stream_usage'] = False
                raise
            except HTTPError as probe:
                if probe.code not in REJECTED:
                    raise
            else:
                features['stream_usage'] = False
                return result
        try:
            result = send(dict(body, stream=False))
        except HTTPError:
            raise original from None
        features['stream'] = False
        return result


def reasoning_effort(values=None, effort=None):
    """Resolve Uncle effort to portable OpenAI low/medium/high; off omits the field."""
    # Off by default: on DeepSeek V4 any reasoning_effort value switches thinking
    # back on even when a stage's request options turn it off, and the hint showed
    # no measurable benefit on tool-using requests. Opt in per project.
    if os.environ.get('UNCLE_UPDATED_PLAN_CHEAP_RETRY') == '1':
        return None
    enabled = option('reasoning-effort', 'off')
    if enabled in ('off', '0', 'false'):
        return None
    if enabled not in ('on', '1', 'true'):
        raise ValueError('self-hosted.reasoning-effort must be on or off')
    config = _config_values()
    from self_hosted import config_stage
    stage = os.environ.get('UNCLE_STATUS_STAGE', '')
    parent = config_stage(stage, config)
    for name in dict.fromkeys([stage, parent]):
        override = os.environ.get('WORKFLOW_EFFORT_' + re.sub(r'[^A-Z0-9]', '_', name.upper()))
        if override:
            effort = override
            break
    else:
        effort = (effort or (values or {}).get('effort') or config.get(stage + '.effort') or
                  config.get(parent + '.effort') or config.get('effort') or 'low')
    mapping = {'none': 'low', 'minimal': 'low', 'low': 'low', 'medium': 'medium',
               'high': 'high', 'xhigh': 'high', 'max': 'high'}
    try:
        return mapping[effort.strip().lower()]
    except KeyError:
        raise ValueError('Unsupported self-hosted effort: %s' % effort) from None


def strip_reasoning(text):
    """Remove only leading thinking, including servers that omit the opening tag."""
    text = text or ''
    while text.lstrip().startswith('<think>'):
        end = text.find('</think>')
        if end < 0:
            return ''         # unfinished thinking is never an answer
        text = text[end + len('</think>'):].lstrip()
    # Some chat templates already supply <think> to the decoder. Do not strip
    # a literal tag embedded in an answer (JSON, code or ordinary prose).
    if re.search(r'(?m)(?:^[ \t]*|\S)</think>', text) and not text.lstrip().startswith(('{', '[', '```')):
        text = text.split('</think>', 1)[1].lstrip()
    return text


def clean_message(message):
    result = dict(message)
    result['content'] = strip_reasoning(result.get('content'))
    if result.get('tool_calls'):
        result['tool_calls'] = [dict(call, function=dict(call['function'], arguments=strip_reasoning(
            call['function'].get('arguments')))) for call in result['tool_calls']]
    return result


def _compatible_post(values, body, send):
    """Retry optional effort independently of schemas/tools, remembering proven support.

    Reasoning fields stay local unless a server explicitly requires one on tool
    continuations. Generic errors never opt a server into reasoning replay.
    """
    base = values['base_url'].rstrip('/')
    features = _request_features.setdefault(base, {})
    original = body

    def prepared():
        request = dict(original)
        if features.get('effort') is False:
            request.pop('reasoning_effort', None)
        request['messages'] = [{k: v for k, v in message.items()
                                if k not in ('reasoning', 'reasoning_content') or features.get(k)}
                               for message in original['messages']]
        return request

    while True:
        request = prepared()
        try:
            return send(request)
        except HTTPError as error:
            if error.code not in REJECTED:
                raise
            detail = _error_detail(error)
            required = next((field for field in ('reasoning_content', 'reasoning')
                             if re.search(r'\b' + field + r'\b', detail) and
                             re.search(r'missing|required|must (?:include|provide)', detail) and
                             not features.get(field) and
                             any(field in m for m in original['messages'])), None)
            if required:
                features[required] = True
                continue
            if ('reasoning_effort' not in detail and any(field in detail for field in
                    ('response_format', 'json_schema', 'structured_outputs', 'guided_json', 'tools'))):
                raise
            if 'reasoning_effort' not in request:
                raise
            # A successful otherwise-identical retry proves that effort caused
            # the rejection. If it also fails, keep the original capability.
            request.pop('reasoning_effort')
            result = send(request)
            features['effort'] = False
            return result


class OutputTruncated(ValueError):
    """The model reached the output limit: the response is a fragment."""


def _no_answer(timeout, limit):
    return ValueError('The model server did not answer within %d seconds (max_tokens %d). It is probably stuck in a '
                      'runaway generation or overloaded; check its load. Limits: WORKFLOW_SELF_HOSTED_REQUEST_SECONDS, '
                      'WORKFLOW_SELF_HOSTED_TURN_OUTPUT_TOKENS.' % (timeout, limit))


def request_seconds(stage_seconds=3600):
    """Seconds one model request may take (WORKFLOW_SELF_HOSTED_REQUEST_SECONDS, default 1200).

    The timeout also covers native/non-streaming fallback and pauses between
    streamed chunks. Twenty minutes allows a large prompt and a long answer.
    """
    configured = os.environ.get('WORKFLOW_SELF_HOSTED_REQUEST_SECONDS', '').strip()
    return int(configured) if configured else min(int(stage_seconds), 1200)


def turn_output_tokens(limit, name=''):
    """Output cap for one tool-loop turn (WORKFLOW_SELF_HOSTED_TURN_OUTPUT_TOKENS, default 32768).

    A turn is a tool call or a short note.  Using the whole-stage ceiling (64k) let
    one degenerate turn run for the better part of an hour before the server
    returned anything.  A synthesis stage writes its whole JSON delivery as one tool
    call, so the cap must hold a full plan: 16k cut one off mid-document
    (calculator-local, updated-plan); 32k matches the closing-answer cap.
    """
    return output_cap(limit, 'turn-output-tokens', name)


def output_cap(limit, option_name, artifact=''):
    """Environment (stage, parent, global), config in the same order, then defaults."""
    stage = os.environ.get('UNCLE_STATUS_STAGE', '')
    config = _config_values()
    from self_hosted import config_stage
    names = list(dict.fromkeys(stage_names(stage) + [config_stage(stage, config)]))
    prefix = 'WORKFLOW_SELF_HOSTED_' + option_name.upper().replace('-', '_')
    value = None
    for name in names + ['']:
        key = prefix + ('_' + re.sub(r'[^A-Z0-9]', '_', name.upper()) if name else '')
        if os.environ.get(key, '').strip():
            value = os.environ[key]
            break
    if value is None:
        for name in names + ['self-hosted']:
            if config.get(name + '.' + option_name):
                value = config[name + '.' + option_name]
                break
    # Only known mechanical deliveries are small. A generic worker packet may
    # contain judgment (preflight/checklist/custom lenses included).
    small = (option_name != 'reasoning-output-tokens' and
             (artifact.replace('_', '-').endswith(('ops-packet', 'outline-packet',
                                                   'section-worker-packet', 'section-model-packet')) or
              bool(re.search(r'-worker-(?:edits|resolution|resolve|section)-', stage))))
    default = 4096 if small else 32768
    if os.environ.get('UNCLE_ADVERSARIAL_SLICE') == '1':
        default = 8192 if option_name == 'reasoning-output-tokens' else 4096
    if small and option_name != 'reasoning-output-tokens' and os.environ.get('UNCLE_UPDATED_PLAN_ANSWER_TOKENS'):
        default = int(os.environ['UNCLE_UPDATED_PLAN_ANSWER_TOKENS'])
    cap = int(value) if value is not None else default
    if cap <= 0:
        raise ValueError(option_name + ' must be a positive integer')
    return min(int(limit), cap)


# Stages that run hotter than the default.  Requirements interpretation is
# open-ended reading of a thin brief; greedy decoding there repeats and
# under-explores, so it samples at 1 unless the operator says otherwise.
STAGE_TEMPERATURES = {'requirements': 1.0}


def stage_names(stage):
    """The stage's own name, then the names it inherits from, most specific first."""
    names = [stage] if stage else []
    for marker in ('-review-worker-', '-worker-'):
        if marker in stage:
            names.append(stage.split(marker, 1)[0])
    if stage.endswith('-investigate'):
        names.append(stage[:-len('-investigate')])
    return list(dict.fromkeys(names))


def _config_values(path=None):
    path = path or os.environ.get('UNCLE_CONFIG') or os.path.join(os.getcwd(), '.uncle', 'config')
    values = {}
    try:
        with open(path, encoding='utf-8') as stream:
            for line in stream:
                # JSON strings may contain # and significant whitespace. Only
                # these new keys use quote-aware comments; other keys retain
                # their historical parser behavior.
                parts = line.split(None, 1)
                if parts and parts[0].endswith('.request-options'):
                    value = parts[1].rstrip('\r\n') if len(parts) == 2 else ''
                    quoted = escaped = False
                    for index, char in enumerate(value):
                        if escaped:
                            escaped = False
                        elif char == '\\' and quoted:
                            escaped = True
                        elif char == '"':
                            quoted = not quoted
                        elif char == '#' and not quoted:
                            value = value[:index]
                            break
                    values.setdefault(parts[0], value)
                    continue
                parts = line.split('#', 1)[0].split(None, 1)
                if len(parts) == 2:
                    values.setdefault(parts[0], parts[1].strip())
    except OSError:
        pass
    return values


def _parse_temperature(text, source):
    if text.strip().lower() in ('none', 'omit', 'off'):
        return None  # send no temperature at all, for servers that refuse the field
    try:
        value = float(text)
    except ValueError:
        raise ValueError('%s must be a number' % source) from None
    if not 0 <= value <= 2:
        raise ValueError('%s must be between 0 and 2' % source)
    return value


def temperature_enabled():
    """Whether Self Hosted requests carry a temperature at all: `self-hosted.use-temperature` on|off, off by default."""
    value = option('use-temperature', 'off')
    if value in ('off', '0', 'false', 'no'):
        return False
    if value in ('on', '1', 'true', 'yes'):
        return True
    raise ValueError('self-hosted.use-temperature must be on or off')


def temperature(stage=None):
    """Sampling temperature for a request, or None when none is sent.

    None unless `self-hosted.use-temperature` (env WORKFLOW_SELF_HOSTED_USE_TEMPERATURE) is on; the model server then
    chooses its own default. When it is on, the value is, first match wins: WORKFLOW_SELF_HOSTED_TEMPERATURE_<STAGE>, then
    WORKFLOW_SELF_HOSTED_TEMPERATURE, then `<stage>.temperature` and
    `self-hosted.temperature` in .uncle/config, then the built-in per-stage
    defaults (requirements runs at 1), then 0.  A stage inherits from its parent:
    a worker from its stage, `requirements-investigate` from `requirements`.
    `none` (or `omit`/`off`) returns None: the request carries no temperature.
    """
    if not temperature_enabled():
        return None
    stage = os.environ.get('UNCLE_STATUS_STAGE', '') if stage is None else stage
    names = stage_names(stage)
    for name in names:
        var = 'WORKFLOW_SELF_HOSTED_TEMPERATURE_' + re.sub(r'[^A-Z0-9]', '_', name.upper())
        if os.environ.get(var, '').strip():
            return _parse_temperature(os.environ[var].strip(), var)
    if os.environ.get('WORKFLOW_SELF_HOSTED_TEMPERATURE', '').strip():
        return _parse_temperature(os.environ['WORKFLOW_SELF_HOSTED_TEMPERATURE'].strip(), 'WORKFLOW_SELF_HOSTED_TEMPERATURE')
    config = _config_values()
    for name in names + ['self-hosted']:
        if config.get(name + '.temperature'):
            return _parse_temperature(config[name + '.temperature'], name + '.temperature')
    for name in names:
        if name in STAGE_TEMPERATURES:
            return STAGE_TEMPERATURES[name]
    return 0.0


def _origin(base_url):
    """Server root: the Base URL without its OpenAI /v1 suffix."""
    url = urlsplit(base_url.rstrip('/'))
    path = url.path[:-3] if url.path.endswith('/v1') else url.path
    return urlunsplit((url.scheme, url.netloc, path, '', ''))


# --- persistent connections ------------------------------------------------

PROTOCOLS = set()               # protocols actually used: 'HTTP/1.1', 'HTTP/2'
STALE = (http.client.RemoteDisconnected, http.client.CannotSendRequest, BrokenPipeError, ConnectionResetError,
         ConnectionAbortedError)


class Connections:
    """The connections of one stage run (or one subagent): never shared with another."""

    def __init__(self):
        self.http1 = {}         # (scheme, netloc) -> http.client connection
        self.http2 = {}         # (scheme, netloc) -> httpx.Client
        self.lock = threading.Lock()
        self.aborting = threading.Event()   # set while a request is being dropped on purpose
        self.reconnect_seconds = None
        self.connect_seconds = None

    def abort(self):
        """Wake a request blocked on one of these connections, from another thread.

        Shutting the socket down makes the blocked read return at once; closing it
        alone does not reliably do so.  The request fails and the caller moves on.
        """
        self.aborting.set()
        for connection in list(self.http1.values()):
            sock = connection.sock
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def close(self):
        with self.lock:
            for connection in self.http1.values():
                connection.close()
            for client in self.http2.values():
                client.close()
            self.http1.clear()
            self.http2.clear()


_scope = contextvars.ContextVar('uncle_http_connections', default=None)
_thread = threading.local()     # connections for code running outside any scope


@contextlib.contextmanager
def connection_scope(connections=None):
    """Give the enclosed requests their own connections, closed on exit.

    Every stage run opens one, and a subagent run inside it opens another, so
    parallel stages and their subagents never share a socket.  A new thread
    starts with no scope and therefore with connections of its own as well.
    Pass `connections` to run inside a longer-lived set (the supervisor's) that
    the caller owns: it is entered and left, never closed here.
    """
    owned = connections is None
    connections = Connections() if owned else connections
    token = _scope.set(connections)
    try:
        yield connections
    finally:
        _scope.reset(token)
        if owned:
            connections.close()


def in_scope():
    return _scope.get() is not None


def _connections():
    scoped = _scope.get()
    if scoped is not None:
        return scoped
    if not hasattr(_thread, 'connections'):
        _thread.connections = Connections()
    return _thread.connections


def http2_available():
    try:
        import h2  # noqa: F401
        import httpx  # noqa: F401
    except ImportError:
        return False
    return True


def wants_http2(scheme):
    """HTTP/2 policy: WORKFLOW_SELF_HOSTED_HTTP2 = auto (default, https only) | off | h2c (also plain http)."""
    mode = os.environ.get('WORKFLOW_SELF_HOSTED_HTTP2', 'auto').strip().lower()
    if mode not in ('auto', 'off', 'h2c'):
        raise ValueError('WORKFLOW_SELF_HOSTED_HTTP2 must be auto, off or h2c')
    if mode == 'off' or not http2_available():
        return False
    return scheme == 'https' or mode == 'h2c'


def close_connections():
    """Close the connections used outside any scope on this thread."""
    if hasattr(_thread, 'connections'):
        _thread.connections.close()


class ServerUnreachable(OSError):
    """The model server could not be reached at all; the message says where and why."""


class NetworkLost(OSError):
    """An established connection died mid-request (reset, or no acknowledgement for too long)."""


NETWORK_ERRNOS = {errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE, errno.EHOSTUNREACH, errno.ENETUNREACH,
                  errno.ENETDOWN, errno.ETIMEDOUT, errno.ENOTCONN}


def tune_socket(sock):
    """Make a dead path show up in about a minute, not at the end of a 20-minute read.

    A connection can be silent for many minutes during prompt processing or
    non-streaming fallback. If the network under it dies (a dropped VPN), nothing says so: the
    kernel retransmits into the void and the stage looks hung (three preflight workers sat
    with 100 KB unsent in their sockets).  Keepalive probes and a bound on how long sent
    data may go unacknowledged turn that into a connection error the caller can act on.
    A live server that is merely busy still answers both.
    """
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for name, value in (('TCP_KEEPIDLE', 30), ('TCP_KEEPALIVE', 30), ('TCP_KEEPINTVL', 10), ('TCP_KEEPCNT', 3)):
            if hasattr(socket, name):
                sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, name), value)
        if hasattr(socket, 'TCP_USER_TIMEOUT'):                      # Linux, milliseconds
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_USER_TIMEOUT, 90_000)
        elif sys.platform == 'darwin':                                # TCP_RXT_CONNDROPTIME, seconds
            sock.setsockopt(socket.IPPROTO_TCP, 0x80, 90)
    except OSError:
        pass  # tuning is best-effort


def reconnect_seconds():
    """How long a request keeps trying to get through a lost network (WORKFLOW_SELF_HOSTED_RECONNECT_SECONDS, 300)."""
    configured = os.environ.get('WORKFLOW_SELF_HOSTED_RECONNECT_SECONDS', '').strip()
    try:
        return float(configured) if configured else 300.0
    except ValueError:
        raise ValueError('WORKFLOW_SELF_HOSTED_RECONNECT_SECONDS must be a number') from None


RETRYABLE_STATUS = (408, 409, 425, 429, 500, 502, 503, 504, 529)
RETRY_LIMIT = 6


def retry_delay(error, attempt):
    """Seconds to wait after a transient HTTP error: Retry-After when sent (capped at 120), else jittered exponential backoff."""
    import random
    try:
        header = error.headers.get('Retry-After') if error.headers else None
        if header is not None:
            return min(120.0, max(0.0, float(header)))
    except (TypeError, ValueError):
        pass
    return min(60.0, 2.0 * (2 ** (attempt - 1))) * (0.5 + random.random() / 2)


def post(url, api_key, body, timeout, what='model request'):
    """`_request` that rides out a lost network instead of failing the stage.

    A connection that cannot be made, or one that died mid-request, is tried again every
    few seconds for up to reconnect_seconds() (a VPN usually comes back within a minute).
    A server that answered with a transient error (RETRYABLE_STATUS) is tried again with backoff,
    up to RETRY_LIMIT tries, honoring Retry-After. Other answers, and a read timeout, are not retried.
    """
    started = time.monotonic()
    answers = 0
    budget = _connections().reconnect_seconds
    if budget is None:
        budget = reconnect_seconds()
    noted = -30.0
    while True:
        try:
            result = _request(url, api_key, body, timeout)
            _outage_mark(url, clear=True)
            return result
        except HTTPError as error:
            answers += 1
            if error.code not in RETRYABLE_STATUS or answers >= RETRY_LIMIT or _connections().aborting.is_set():
                raise
            delay = retry_delay(error, answers)
            print('Self hosted: %s HTTP %d%s; retry %d of %d in %.0fs.' %
                  (what, error.code, _server_reason(error), answers, RETRY_LIMIT - 1, delay), file=sys.stderr, flush=True)
            time.sleep(delay)
        except (ServerUnreachable, NetworkLost) as error:
            if _connections().aborting.is_set():
                raise  # the caller dropped this request on purpose; do not resend it
            waited = time.monotonic() - started
            # A server another call has already waited out is not waited for again (calculator-local: eleven writers waited five
            # minutes each, then the one-call fallback waited five more for the same dead host).
            if waited >= budget or _outage_recent(url):
                _outage_mark(url)
                raise type(error)('%s (the network stayed down for %d seconds; %s)' % (error, waited, what)) from None
            if waited - noted >= 30:
                noted = waited
                print('Self hosted: lost the model server (%s); retrying for up to %d more seconds.' %
                      (str(error).split(' (')[0][:120], budget - waited), file=sys.stderr, flush=True)
            time.sleep(min(10.0, max(1.0, budget - waited)) if budget >= 10 else 0.2)


OUTAGE_SECONDS = 180.0


def _outage_file(url):
    parts = urlsplit(url)
    return os.path.join(os.environ.get('UNCLE_OUTAGE_DIR') or tempfile.gettempdir(), 'uncle-server-down-%s-%s' % (parts.hostname, parts.port or 0))


def _outage_mark(url, clear=False):
    """Remember that this server stayed down for a whole reconnect budget (or forget it: it answered)."""
    try:
        if clear:
            os.unlink(_outage_file(url))
        else:
            with open(_outage_file(url), 'w') as handle:
                handle.write(str(time.time()))
    except OSError:
        pass


def _outage_recent(url):
    try:
        return time.time() - os.path.getmtime(_outage_file(url)) < OUTAGE_SECONDS
    except OSError:
        return False


def connect_timeout():
    """Seconds allowed to open a connection (WORKFLOW_SELF_HOSTED_CONNECT_SECONDS, default 15).

    Separate from the request timeout, which is an hour: a server that is simply
    not there (a dropped VPN, a stopped host) must fail in seconds, not wait out
    the operating system's connect timeout, once per attempt and per stage.
    """
    configured = os.environ.get('WORKFLOW_SELF_HOSTED_CONNECT_SECONDS', '').strip()
    try:
        value = float(configured) if configured else 15.0
    except ValueError:
        value = 0
    if value <= 0:
        raise ValueError('WORKFLOW_SELF_HOSTED_CONNECT_SECONDS must be a positive number')
    scoped = _connections().connect_seconds
    return min(value, scoped) if scoped is not None else value


def _failure(url, error, connecting=False):
    if connecting and isinstance(error, OSError):
        parts = urlsplit(url)
        if isinstance(error, TimeoutError) or getattr(error, 'errno', None) in (60, 110, 10060):
            reason = 'timed out'
        elif isinstance(error, ConnectionRefusedError):
            reason = 'connection refused'
        else:
            reason = str(error) or type(error).__name__
        return ServerUnreachable('Cannot reach the model server at %s://%s (%s). Check that it is running and that '
                                 'the network or VPN that leads to it is up.' % (parts.scheme, parts.netloc, reason))
    if isinstance(error, OSError) and getattr(error, 'errno', None) in NETWORK_ERRNOS:
        return NetworkLost('The connection to the model server was lost (%s).' % (str(error) or type(error).__name__))
    if isinstance(error, (http.client.RemoteDisconnected, BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
        return NetworkLost('The connection to the model server was lost (%s).' % (str(error) or type(error).__name__))
    if isinstance(error, TimeoutError):
        return error
    return URLError(error)


def _via_http1(method, url, data, headers, timeout):
    parts = urlsplit(url)
    key = (parts.scheme, parts.netloc)
    pool = _connections()
    connections = pool.http1
    target = parts.path + ('?' + parts.query if parts.query else '')
    for attempt in (0, 1):
        connection = connections.get(key)
        reused = connection is not None
        if connection is None:
            factory = http.client.HTTPSConnection if parts.scheme == 'https' else http.client.HTTPConnection
            connection = connections[key] = factory(parts.netloc, timeout=connect_timeout())
        try:
            if connection.sock is None:
                connection.timeout = connect_timeout()
                try:
                    connection.connect()
                except OSError as error:
                    connection.close()
                    connections.pop(key, None)
                    raise _failure(url, error, connecting=True) from None
            connection.timeout = timeout
            connection.sock.settimeout(timeout)
            tune_socket(connection.sock)
            connection.request(method, target, body=data, headers=dict(headers, Connection='keep-alive'))
            response = connection.getresponse()
            if 200 <= response.status < 300 and response.headers.get_content_type() == 'text/event-stream':
                try:
                    raw = assemble_stream(iter(response.readline, b''))
                finally:
                    # [DONE] need not consume the HTTP body terminator. Closing
                    # also cancels generation immediately on an early stop.
                    response.close()
                    connection.close()
                    connections.pop(key, None)
            else:
                raw = response.read()
        except ServerUnreachable:
            raise
        except STALE as error:
            # A kept-alive connection the server closed while idle: reconnect once.
            connection.close()
            connections.pop(key, None)
            if reused and attempt == 0:
                continue
            raise _failure(url, error) from None
        except (OSError, http.client.HTTPException) as error:
            connection.close()
            connections.pop(key, None)
            raise _failure(url, error) from None
        PROTOCOLS.add('HTTP/1.1')
        if response.will_close:
            connection.close()
            connections.pop(key, None)
        return response.status, response.reason, response.headers, raw


def _via_http2(method, url, data, headers, timeout):
    import httpx
    parts = urlsplit(url)
    key = (parts.scheme, parts.netloc)
    for attempt in (0, 1):
        pool = _connections()
        with pool.lock:
            client = pool.http2.get(key)
            reused = client is not None
            if client is None:
                # h2c ("prior knowledge") speaks HTTP/2 without TLS; with TLS the
                # protocol is negotiated, falling back to HTTP/1.1 on its own.
                client = pool.http2[key] = httpx.Client(
                    http1=parts.scheme == 'https', http2=True, follow_redirects=False)
        try:
            with client.stream(method, url, content=data, headers=headers,
                               timeout=httpx.Timeout(timeout, connect=connect_timeout())) as response:
                if response.is_success and response.headers.get('content-type', '').split(';')[0] == 'text/event-stream':
                    raw = assemble_stream(response.iter_lines())
                else:
                    raw = response.read()
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError) as error:
            with pool.lock:
                pool.http2.pop(key, None)
            client.close()
            if reused and attempt == 0:
                continue
            raise _failure(url, OSError(str(error))) from None
        except (httpx.ConnectTimeout, httpx.ConnectError) as error:
            raise _failure(url, TimeoutError(str(error)) if isinstance(error, httpx.ConnectTimeout)
                           else ConnectionRefusedError(str(error)), connecting=True) from None
        except httpx.TimeoutException as error:
            raise TimeoutError(str(error)) from None
        except httpx.TransportError as error:
            raise _failure(url, OSError(str(error))) from None
        PROTOCOLS.add(response.http_version)
        return response.status_code, response.reason_phrase, response.headers, raw


def _request(url, api_key, body=None, timeout=30, headers=None):
    """GET, or POST when `body` is given; returns parsed JSON.

    Redirects are never followed (the key must not leave the configured host).
    A non-2xx answer raises urllib's HTTPError so callers can read its code.
    """
    data = json.dumps(body).encode('utf-8') if body is not None else None
    headers = dict(headers or {'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}, Accept='application/json')
    method = 'POST' if data is not None else 'GET'
    transport = _via_http2 if wants_http2(urlsplit(url).scheme) else _via_http1
    status, reason, response_headers, raw = transport(method, url, data, headers, timeout)
    if not 200 <= status < 300:
        if api_key and not isinstance(raw, dict):
            # An upstream body or reason may echo the Authorization value; scrub it and bound what is kept.
            import self_hosted
            raw = self_hosted.redact_token((raw or b'')[:4000], api_key)
            reason = self_hosted.redact_token(reason, api_key)
        raise HTTPError(url, status, reason, response_headers, io.BytesIO(raw))
    return raw if isinstance(raw, dict) else json.loads(raw or b'null')


FLAVORS = ('generic', 'ollama', 'vllm')
FLAVOR_CACHE_SECONDS = 6 * 3600.0


def _flavor_file(origin):
    parts = urlsplit(origin)
    name = re.sub(r'[^A-Za-z0-9._-]', '_', '%s-%s%s' % (parts.hostname, parts.port or 0, parts.path))
    return os.path.join(os.environ.get('UNCLE_OUTAGE_DIR') or tempfile.gettempdir(), 'uncle-flavor-' + name)


def detect_flavor(base_url, api_key):
    """Name the server family when it identifies itself; 'generic' otherwise.

    UNCLE_SELF_HOSTED_FLAVOR (generic|ollama|vllm) skips detection. A Base URL below the server root
    (e.g. /publishers/<name>/v1) is a hosted service, not Ollama or vLLM, so it is generic without a check.
    Probed answers are remembered across stage processes for FLAVOR_CACHE_SECONDS.
    """
    forced = os.environ.get('UNCLE_SELF_HOSTED_FLAVOR', '').strip().lower()
    if forced:
        if forced not in FLAVORS:
            raise ValueError('UNCLE_SELF_HOSTED_FLAVOR must be one of: %s' % ', '.join(FLAVORS))
        return forced
    origin = _origin(base_url)
    if urlsplit(origin).path.strip('/'):
        return 'generic'
    cache = _flavor_file(origin)
    try:
        if time.time() - os.path.getmtime(cache) < FLAVOR_CACHE_SECONDS:
            with open(cache) as handle:
                cached = handle.read().strip()
            if cached in FLAVORS:
                return cached
    except OSError:
        pass
    flavor = 'generic'
    for name, path in (('ollama', '/api/version'), ('vllm', '/version')):
        try:
            data = _request(origin + path, api_key, timeout=5)
        except (HTTPError, URLError, OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get('version'), str):
            flavor = name
            break
    try:
        with open(cache, 'w') as handle:
            handle.write(flavor)
    except OSError:
        pass
    return flavor


# Strongest first.  A server that rejects a mode is skipped and the next one is
# tried; 'prompt' (no server-side constraint) is always last.
MODE_ORDER = {
    'ollama': ('ollama_format', 'json_schema', 'json_object', 'prompt'),
    'vllm': ('json_schema', 'vllm_structured', 'vllm_guided', 'json_object', 'prompt'),
    'generic': ('json_schema', 'json_object', 'prompt'),
}


def capabilities(base_url, api_key):
    key = base_url.rstrip('/')
    if key not in _capabilities:
        flavor = detect_flavor(base_url, api_key)
        _capabilities[key] = {'flavor': flavor, 'modes': list(MODE_ORDER[flavor]), 'rejected': set()}
    return _capabilities[key]


def _flatten(messages):
    parts = []
    for message in messages:
        role = message['role']
        if role == 'tool':
            parts.append('[tool result]\n' + str(message.get('content', '')))
        elif role == 'assistant' and message.get('tool_calls'):
            calls = '; '.join('%s(%s)' % (c['function']['name'], c['function']['arguments']) for c in message['tool_calls'])
            parts.append('[assistant called tools: %s]' % calls)
        else:
            parts.append('[%s]\n%s' % (role, message.get('content') or ''))
    return [{'role': 'user', 'content': '\n\n'.join(parts)}]


def _strip_temperature(node):
    if isinstance(node, dict):
        # Keys of a JSON-Schema `properties` map are user-chosen names, not sampling fields: keep them.
        return {k: (({n: _strip_temperature(sub) for n, sub in v.items()} if k == 'properties' and isinstance(v, dict) else _strip_temperature(v)))
                for k, v in node.items() if k != 'temperature' or k == 'properties'}
    if isinstance(node, list):
        return [_strip_temperature(v) for v in node]
    return node


def sampling(values):
    """Sampling fields for a request body. Fails closed for Bedrock: never a temperature."""
    profile = values.get('_profile') if isinstance(values, dict) else None
    if profile is None:
        config = _config_values()
        stage = os.environ.get('UNCLE_STATUS_STAGE', '')
        import self_hosted
        if self_hosted.resolve_profile(config, stage) == 'aws-bedrock':
            raise ValueError('AWS Bedrock request values lack _profile; refusing to send a request (never defaults to Self Hosted)')
    elif profile == 'aws-bedrock':
        return {}
    value = temperature()
    return {} if value is None else {'temperature': value}


def _final_call(values, messages, schema, name, mode, limit, effort, timeout):
    """One schema-constrained request in `mode`; returns (text, reason, usage)."""
    base_url, key = values['base_url'].rstrip('/'), values['api_key']
    if mode == 'ollama_format':
        body = {'model': values['model'], 'messages': _flatten(messages), 'stream': False, 'format': schema,
                'options': dict({'num_predict': limit}, **sampling(values))}
        if effort:
            body['reasoning_effort'] = effort
        data = compatible_post(values, body, timeout, url=_origin(base_url) + '/api/chat')
        usage = dict(data.get('usage') or {}, prompt_tokens=data.get('prompt_eval_count', 0),
                     completion_tokens=data.get('eval_count', 0))
        reason = 'length' if data.get('done_reason') == 'length' else 'stop'
        return strip_reasoning(data['message']['content']), reason, usage
    body = {'model': values['model'], 'messages': messages, 'max_tokens': limit, 'stream': False}
    body.update(sampling(values))
    if effort:
        body['reasoning_effort'] = effort
    if mode == 'json_schema':
        body['response_format'] = {'type': 'json_schema', 'json_schema': {'name': name, 'schema': schema}}
    elif mode == 'vllm_structured':
        body['structured_outputs'] = {'json': schema}
    elif mode == 'vllm_guided':
        body['guided_json'] = schema
    elif mode == 'json_object':
        body['response_format'] = {'type': 'json_object'}
    data = compatible_post(values, body, timeout)
    choice = data['choices'][0]
    return strip_reasoning(choice['message'].get('content')), choice.get('finish_reason'), data.get('usage') or {}


def constrained_completion(values, messages, schema, name, limit, effort=None, timeout=3600, skip=()):
    """Ask for `schema`-shaped output; returns (text, reason, usage, mode)."""
    values = configure_request_options(values)
    if values.get('_profile') == 'aws-bedrock':
        # Converse only: no capability probe, no mode fallback.
        effort = reasoning_effort(values, effort)
        try:
            text, reason, usage = _final_call(values, messages, schema, name, 'json_schema', limit, effort, timeout)
        except TimeoutError:
            raise _no_answer(timeout, limit) from None
        return text, reason, usage, 'json_schema'
    caps = capabilities(values['base_url'], values['api_key'])
    effort = reasoning_effort(values, effort)
    last = None
    for mode in caps['modes']:
        if mode in caps['rejected'] or mode in skip:
            continue
        try:
            text, reason, usage = _final_call(values, messages, schema, name, mode, limit, effort, timeout)
            return text, reason, usage, mode
        except HTTPError as error:
            if error.code not in REJECTED:
                raise ValueError('Model API request failed (HTTP %d%s); check the Base URL, API key and model'
                                 % (error.code, _server_reason(error))) from None
            caps['rejected'].add(mode)
            last = error
        except TimeoutError:
            raise _no_answer(timeout, limit) from None
    raise ValueError('Model API rejected every request form (HTTP %s%s); check the model name'
                     % (getattr(last, 'code', '?'), _server_reason(last) if last is not None else ''))


# Every mode that asks the server's grammar engine to shape the output.  The one
# left over, 'prompt', is plain generation checked locally afterwards.
GRAMMAR_MODES = ('ollama_format', 'json_schema', 'vllm_structured', 'vllm_guided', 'json_object')


def add_usage(total, usage):
    prompt, completion = usage.get('prompt_tokens') or 0, usage.get('completion_tokens') or 0
    total['input_tokens'] = total.get('input_tokens', 0) + prompt
    total['output_tokens'] = total.get('output_tokens', 0) + completion
    total['total_tokens'] = total.get('total_tokens', 0) + prompt + completion


# --- schema conformance ----------------------------------------------------

def conforms(value, schema, path='$'):
    """Check the JSON-Schema subset these artifacts use; raises ValueError."""
    if 'anyOf' in schema:
        problems = []
        for option in schema['anyOf']:
            try:
                conforms(value, option, path)
                return
            except ValueError as error:
                problems.append(str(error))
        raise ValueError('%s matches none of the allowed forms (%s)' % (path, '; '.join(problems)))
    kind = schema.get('type')
    if isinstance(kind, list):
        kinds = kind
        if value is None and 'null' in kinds:
            return
        remaining = [k for k in kinds if k != 'null']
        for option in remaining:
            try:
                conforms(value, dict(schema, type=option), path)
                return
            except ValueError:
                continue
        raise ValueError('%s must be %s' % (path, ' or '.join(kinds)))
    if kind == 'null':
        if value is not None:
            raise ValueError('%s must be null' % path)
        return
    checks = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool}
    if kind in checks and (not isinstance(value, checks[kind]) or (kind == 'integer' and isinstance(value, bool))):
        raise ValueError('%s must be %s' % (path, kind))
    if 'const' in schema and value != schema['const']:
        raise ValueError('%s must be %r' % (path, schema['const']))
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('%s must be one of %s' % (path, ', '.join(map(repr, schema['enum']))))
    if kind == 'string' and len(value.strip()) < schema.get('minLength', 0):
        raise ValueError('%s must not be empty' % path)
    if kind == 'string' and len(value) > schema.get('maxLength', len(value)):
        raise ValueError('%s is longer than %d characters' % (path, schema['maxLength']))
    if kind == 'array' and len(value) > schema.get('maxItems', len(value)):
        raise ValueError('%s has more than %d items' % (path, schema['maxItems']))
    if kind == 'object':
        for field in schema.get('required', ()):
            if field not in value:
                raise ValueError('%s is missing required field %s' % (path, field))
        properties = schema.get('properties', {})
        if schema.get('additionalProperties') is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise ValueError('%s has unexpected fields: %s' % (path, ', '.join(extra)))
        for field, sub in properties.items():
            if field in value:
                conforms(value[field], sub, path + '.' + field)
    if kind == 'array':
        for index, item in enumerate(value):
            conforms(item, schema.get('items', {}), '%s[%d]' % (path, index))


def chat(values, messages, tools, limit, effort=None, timeout=3600):
    """One tool-capable turn; None means the server rejected tool calling."""
    body = {'model': values['model'], 'messages': messages, 'max_tokens': limit, 'stream': False}
    body.update(sampling(values))
    if tools:
        body['tools'] = tools
    effort = reasoning_effort(values, effort)
    if effort:
        body['reasoning_effort'] = effort
    try:
        data = compatible_post(values, body, timeout)
        for choice in data.get('choices', []):
            choice['message'] = clean_message(choice['message'])
        return data
    except HTTPError as error:
        if error.code not in REJECTED:
            raise ValueError('Model API request failed (HTTP %d%s); check the Base URL, API key and model'
                             % (error.code, _server_reason(error))) from None
        global last_rejection
        last_rejection = 'HTTP %d%s' % (error.code, _server_reason(error))
    except TimeoutError:
        raise _no_answer(timeout, limit) from None
    return None

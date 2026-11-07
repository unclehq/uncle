"""Pure request/response adapters for the AWS Bedrock runner (OpenAI, Anthropic, Converse).

No I/O. Auth is bearer-token only: OpenAI and Converse send Authorization: Bearer;
Anthropic sends x-api-key plus anthropic-version and no Authorization header.
No adapter ever emits a temperature field.
"""
import json
from urllib.parse import quote

PROTOCOLS = ('openai', 'anthropic', 'converse')
ANTHROPIC_VERSION = '2023-06-01'
_ALIASES = {'openai': 'openai', 'openai compatible': 'openai', 'anthropic': 'anthropic',
            'anthropic compatible': 'anthropic', 'converse': 'converse', 'converse api compatible': 'converse'}


def normalize_protocol(value):
    key = (value or 'openai').strip().lower()
    if key not in _ALIASES:
        raise ValueError('Unknown AWS Bedrock API Compatibility %r; expected one of %s' % (value, ', '.join(PROTOCOLS)))
    return _ALIASES[key]


def build_headers(protocol, token):
    protocol = normalize_protocol(protocol)
    if protocol == 'anthropic':
        return {'Content-Type': 'application/json', 'x-api-key': token, 'anthropic-version': ANTHROPIC_VERSION}
    return {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}


def build_url(protocol, base_url, model):
    protocol = normalize_protocol(protocol)
    base = base_url.rstrip('/')
    if protocol == 'openai':
        return base + '/chat/completions'
    if protocol == 'anthropic':
        return base + '/v1/messages'
    return base + '/model/' + quote(model, safe='') + '/converse'


def _text(content):
    if isinstance(content, list):
        return ''.join(p.get('text', '') for p in content if isinstance(p, dict))
    return content or ''


def build_body(protocol, model, messages, max_tokens, tools=None, schema=None, schema_name='result'):
    """Request body. `messages` are OpenAI-style {role, content}; `tools` are OpenAI function tools."""
    protocol = normalize_protocol(protocol)
    system = '\n\n'.join(_text(m.get('content')) for m in messages if m.get('role') == 'system')
    turns = [m for m in messages if m.get('role') != 'system']
    if protocol == 'openai':
        body = {'model': model, 'messages': list(messages), 'max_tokens': max_tokens}
        if tools:
            body['tools'] = tools
        if schema is not None:
            body['response_format'] = {'type': 'json_schema', 'json_schema': {'name': schema_name, 'schema': schema, 'strict': True}}
        return body
    specs = [(t['function']['name'], t['function'].get('description', ''), t['function'].get('parameters', {'type': 'object'}))
             for t in (tools or [])]
    forced = None
    if schema is not None:
        forced = schema_name
        specs.append((schema_name, 'Return the final answer.', schema))
    if protocol == 'anthropic':
        body = {'model': model, 'max_tokens': max_tokens,
                'messages': [{'role': m['role'], 'content': _text(m.get('content'))} for m in turns]}
        if system:
            body['system'] = system
        if specs:
            body['tools'] = [{'name': n, 'description': d, 'input_schema': s} for n, d, s in specs]
        if forced:
            body['tool_choice'] = {'type': 'tool', 'name': forced}
        return body
    body = {'messages': [{'role': m['role'], 'content': [{'text': _text(m.get('content'))}]} for m in turns],
            'inferenceConfig': {'maxTokens': max_tokens}}
    if system:
        body['system'] = [{'text': system}]
    if specs:
        body['toolConfig'] = {'tools': [{'toolSpec': {'name': n, 'description': d, 'inputSchema': {'json': s}}} for n, d, s in specs]}
        if forced:
            body['toolConfig']['toolChoice'] = {'tool': {'name': forced}}
    return body


def parse_response(protocol, data, schema_name=None):
    """-> {'text', 'tool_calls': [{'id','name','arguments'(dict)}], 'usage': {'input','output'}, 'reason'}.

    A tool call named `schema_name` is the schema-constrained answer: its arguments become `text` (JSON)."""
    protocol = normalize_protocol(protocol)
    if not isinstance(data, dict):
        raise ValueError('AWS Bedrock response is not a JSON object')
    text, calls = '', []
    if protocol == 'openai':
        try:
            choice = data['choices'][0]
            message = choice['message']
        except (KeyError, IndexError, TypeError):
            raise ValueError('AWS Bedrock OpenAI response has no choices[0].message') from None
        text, reason = _text(message.get('content')), choice.get('finish_reason')
        for c in message.get('tool_calls') or []:
            raw = c['function'].get('arguments') or '{}'
            calls.append({'id': c.get('id'), 'name': c['function']['name'], 'arguments': json.loads(raw) if isinstance(raw, str) else raw})
        u = data.get('usage') or {}
        usage = {'input': u.get('prompt_tokens', 0), 'output': u.get('completion_tokens', 0)}
    elif protocol == 'anthropic':
        if 'content' not in data:
            raise ValueError('AWS Bedrock Anthropic response has no content')
        for b in data['content']:
            if b.get('type') == 'text':
                text += b.get('text', '')
            elif b.get('type') == 'tool_use':
                calls.append({'id': b.get('id'), 'name': b['name'], 'arguments': b.get('input') or {}})
        reason = data.get('stop_reason')
        u = data.get('usage') or {}
        usage = {'input': u.get('input_tokens', 0), 'output': u.get('output_tokens', 0)}
    else:
        try:
            parts = data['output']['message']['content']
        except (KeyError, TypeError):
            raise ValueError('AWS Bedrock Converse response has no output.message.content') from None
        for b in parts:
            if 'text' in b:
                text += b['text']
            elif 'toolUse' in b:
                t = b['toolUse']
                calls.append({'id': t.get('toolUseId'), 'name': t['name'], 'arguments': t.get('input') or {}})
        reason = data.get('stopReason')
        u = data.get('usage') or {}
        usage = {'input': u.get('inputTokens', 0), 'output': u.get('outputTokens', 0)}
    if schema_name:
        for c in calls:
            if c['name'] == schema_name:
                text = json.dumps(c['arguments'])
        calls = [c for c in calls if c['name'] != schema_name]
    return {'text': text, 'tool_calls': calls, 'usage': usage, 'reason': reason}

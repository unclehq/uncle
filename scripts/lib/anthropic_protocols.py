"""Pure request/response helpers for the Anthropic API runner (the Messages API only).

No I/O. The endpoint is fixed (https://api.anthropic.com): there is no Base URL to configure, so a key can only ever be
sent to Anthropic. Auth is the `x-api-key` header. No helper ever emits a temperature field.
"""
import json
import re

API_URL = 'https://api.anthropic.com'
API_VERSION = '2023-06-01'
MODEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]*$')


def messages_url():
    return API_URL + '/v1/messages'


def models_url(after_id=None, limit=1000):
    url = '%s/v1/models?limit=%d' % (API_URL, limit)
    return url + '&after_id=' + after_id if after_id else url


def build_headers(key):
    return {'Content-Type': 'application/json', 'x-api-key': key, 'anthropic-version': API_VERSION}


def validate_key(key):
    """Non-empty printable ASCII, no whitespace or control characters. Never echoes the key."""
    if not isinstance(key, str) or not key:
        raise ValueError('Anthropic API requires an API key (set it in Configure → Anthropic API Key)')
    if any(not 0x21 <= ord(c) <= 0x7E for c in key):
        raise ValueError('Anthropic API key must be a single line of printable ASCII without spaces')
    return key


def _text(content):
    if isinstance(content, list):
        return ''.join(p.get('text', '') for p in content if isinstance(p, dict))
    return content or ''


def _messages(turns):
    """OpenAI-style turns -> Messages API turns: tool calls become tool_use blocks, tool results become user
    tool_result blocks, and consecutive same-role turns merge (the API wants alternating user/assistant)."""
    out = []

    def add(role, blocks):
        if not blocks:
            return
        if out and out[-1]['role'] == role:
            out[-1]['content'].extend(blocks)
        else:
            out.append({'role': role, 'content': list(blocks)})

    for m in turns:
        role, text = m.get('role'), _text(m.get('content'))
        if role == 'tool':
            add('user', [{'type': 'tool_result', 'tool_use_id': m.get('tool_call_id') or '', 'content': text or '(no output)'}])
        elif role == 'assistant':
            blocks = [{'type': 'text', 'text': text}] if text else []
            for c in m.get('tool_calls') or []:
                fn = c.get('function') or {}
                args = fn.get('arguments')
                if isinstance(args, str):
                    try:
                        args = json.loads(args) if args.strip() else {}
                    except ValueError:
                        args = {}
                blocks.append({'type': 'tool_use', 'id': c.get('id') or '', 'name': fn.get('name', ''),
                               'input': args if isinstance(args, dict) else {}})
            add('assistant', blocks or [{'type': 'text', 'text': '(empty)'}])
        else:
            add('user', [{'type': 'text', 'text': text or '(empty)'}])
    return out


def build_body(model, messages, max_tokens, tools=None, schema=None, schema_name='result'):
    """Messages API body. `messages` are OpenAI-style {role, content}; `tools` are OpenAI function tools.

    A `schema` becomes one forced tool: the model must call it, and its arguments are the answer."""
    system = '\n\n'.join(_text(m.get('content')) for m in messages if m.get('role') == 'system')
    turns = [m for m in messages if m.get('role') != 'system']
    specs = [(t['function']['name'], t['function'].get('description', ''), t['function'].get('parameters', {'type': 'object'}))
             for t in (tools or [])]
    if schema is not None:
        specs.append((schema_name, 'Return the final answer.', schema))
    body = {'model': model, 'max_tokens': max_tokens, 'messages': _messages(turns)}
    if system:
        body['system'] = system
    if not specs:
        # The API rejects tool_use/tool_result history without a tools list, even when no tool may be called now.
        names = sorted({b['name'] for m in body['messages'] for b in m['content'] if b.get('type') == 'tool_use'})
        specs = [(n, 'Tool used earlier in this conversation.', {'type': 'object'}) for n in names]
    if specs:
        body['tools'] = [{'name': n, 'description': d, 'input_schema': s} for n, d, s in specs]
        if schema is not None:
            body['tool_choice'] = {'type': 'tool', 'name': schema_name}
    return body


def parse_response(data, schema_name=None):
    """-> {'text', 'tool_calls': [{'id','name','arguments'(dict)}], 'usage': {'input','output'}, 'reason'}.

    A tool call named `schema_name` is the schema-constrained answer: its arguments become `text` (JSON)."""
    if not isinstance(data, dict):
        raise ValueError('Anthropic API response is not a JSON object')
    parts = data.get('content')
    if not isinstance(parts, list):
        raise ValueError('Anthropic API response has no content')
    text, calls = '', []
    for b in parts:
        if not isinstance(b, dict):
            continue
        if b.get('type') == 'text':
            text += b.get('text', '')
        elif b.get('type') == 'tool_use':
            calls.append({'id': b.get('id'), 'name': b.get('name', ''), 'arguments': b.get('input') or {}})
    u = data.get('usage') or {}
    usage = {'input': u.get('input_tokens', 0), 'output': u.get('output_tokens', 0)}
    if schema_name:
        for c in calls:
            if c['name'] == schema_name:
                text = json.dumps(c['arguments'])
        calls = [c for c in calls if c['name'] != schema_name]
    return {'text': text, 'tool_calls': calls, 'usage': usage, 'reason': data.get('stop_reason')}


def parse_models(pages):
    """Sorted, de-duplicated model ids from /v1/models pages (a list of page dicts)."""
    names = set()
    for page in pages or []:
        if not isinstance(page, dict) or not isinstance(page.get('data'), list):
            raise ValueError('Anthropic API model list response is malformed')
        for item in page['data']:
            if isinstance(item, dict) and isinstance(item.get('id'), str) and MODEL_RE.match(item['id']):
                names.add(item['id'])
    return sorted(names)

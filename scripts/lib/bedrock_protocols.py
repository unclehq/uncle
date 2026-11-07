"""Pure request/response helpers for the AWS Bedrock runner (Converse only).

No I/O. Endpoints derive only from the region and are always https. Auth is a
bearer token. No helper ever emits a temperature field.
"""
import json
import re
from urllib.parse import quote, urlsplit

REGION_RE = re.compile(r'^[a-z]{2,}(-[a-z]+)+-\d+$')


def validate_region(value):
    """Return the trimmed region or raise ValueError. Never case-folds; empty counts as unset."""
    region = (value or '').strip() if isinstance(value, str) or value is None else ''
    if not region:
        raise ValueError('AWS Bedrock Region is not set; set Region in Configure → AWS Bedrock')
    if not REGION_RE.match(region):
        raise ValueError('Invalid AWS Bedrock Region %r; expected a lowercase region such as us-east-1' % region)
    return region


def control_url(region):
    return 'https://bedrock.%s.amazonaws.com' % validate_region(region)


def runtime_url(region):
    return 'https://bedrock-runtime.%s.amazonaws.com' % validate_region(region)


def region_from_url(url):
    """Legacy migration: region from an https Bedrock host, else None."""
    try:
        parts = urlsplit((url or '').strip())
        host, port = parts.hostname, parts.port
    except (ValueError, AttributeError):
        return None
    if parts.scheme != 'https' or not host or parts.username or parts.password or port or parts.query or parts.fragment:
        return None
    if parts.netloc != host:
        return None
    match = re.match(r'^bedrock(?:-runtime)?\.([^.]+)\.amazonaws\.com$', host)
    if not match:
        return None
    try:
        return validate_region(match.group(1))
    except ValueError:
        return None


def build_headers(token):
    return {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}


def build_url(region, model):
    return runtime_url(region) + '/model/' + quote(model, safe='') + '/converse'


def _text(content):
    if isinstance(content, list):
        return ''.join(p.get('text', '') for p in content if isinstance(p, dict))
    return content or ''


def build_body(messages, max_tokens, tools=None, schema=None, schema_name='result'):
    """Converse body. `messages` are OpenAI-style {role, content}; `tools` are OpenAI function tools."""
    system = '\n\n'.join(_text(m.get('content')) for m in messages if m.get('role') == 'system')
    turns = [m for m in messages if m.get('role') != 'system']
    specs = [(t['function']['name'], t['function'].get('description', ''), t['function'].get('parameters', {'type': 'object'}))
             for t in (tools or [])]
    if schema is not None:
        specs.append((schema_name, 'Return the final answer.', schema))
    body = {'messages': [{'role': m['role'], 'content': [{'text': _text(m.get('content'))}]} for m in turns],
            'inferenceConfig': {'maxTokens': max_tokens}}
    if system:
        body['system'] = [{'text': system}]
    if specs:
        body['toolConfig'] = {'tools': [{'toolSpec': {'name': n, 'description': d, 'inputSchema': {'json': s}}} for n, d, s in specs]}
        if schema is not None:
            body['toolConfig']['toolChoice'] = {'tool': {'name': schema_name}}
    return body


def parse_response(data, schema_name=None):
    """-> {'text', 'tool_calls': [{'id','name','arguments'(dict)}], 'usage': {'input','output'}, 'reason'}.

    A tool call named `schema_name` is the schema-constrained answer: its arguments become `text` (JSON)."""
    if not isinstance(data, dict):
        raise ValueError('AWS Bedrock response is not a JSON object')
    text, calls = '', []
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
    u = data.get('usage') or {}
    usage = {'input': u.get('inputTokens', 0), 'output': u.get('outputTokens', 0)}
    if schema_name:
        for c in calls:
            if c['name'] == schema_name:
                text = json.dumps(c['arguments'])
        calls = [c for c in calls if c['name'] != schema_name]
    return {'text': text, 'tool_calls': calls, 'usage': usage, 'reason': data.get('stopReason')}


def parse_models(foundation, profiles):
    """Sorted, de-duplicated modelId and inferenceProfileId values from discovery pages (lists of page dicts)."""
    names = set()
    for pages, summaries, field in ((foundation, 'modelSummaries', 'modelId'), (profiles, 'inferenceProfileSummaries', 'inferenceProfileId')):
        for page in pages or []:
            if not isinstance(page, dict) or not isinstance(page.get(summaries, []), list):
                raise ValueError('AWS Bedrock model list response is malformed')
            for item in page.get(summaries, []):
                if isinstance(item, dict) and isinstance(item.get(field), str) and item[field]:
                    names.add(item[field])
    return sorted(names)

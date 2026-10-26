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
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit

REJECTED = (400, 404, 405, 415, 422, 501)
_capabilities = {}


class OutputTruncated(ValueError):
    """The model reached the output limit: the response is a fragment."""


def _no_answer(timeout, limit):
    return ValueError('The model server did not answer within %d seconds (max_tokens %d). It is probably stuck in a '
                      'runaway generation or overloaded; check its load. Limits: WORKFLOW_SELF_HOSTED_REQUEST_SECONDS, '
                      'WORKFLOW_SELF_HOSTED_TURN_OUTPUT_TOKENS.' % (timeout, limit))


def request_seconds(stage_seconds=3600):
    """Seconds one model request may take (WORKFLOW_SELF_HOSTED_REQUEST_SECONDS, default 1200).

    Requests are not streamed, so the server says nothing until it has finished:
    a generation that never stops looked exactly like a hung stage for the whole of
    the stage timeout.  Twenty minutes covers a large prompt and a long answer.
    """
    configured = os.environ.get('WORKFLOW_SELF_HOSTED_REQUEST_SECONDS', '').strip()
    return int(configured) if configured else min(int(stage_seconds), 1200)


def turn_output_tokens(limit):
    """Output cap for one tool-loop turn (WORKFLOW_SELF_HOSTED_TURN_OUTPUT_TOKENS, default 32768).

    A turn is a tool call or a short note.  Using the whole-stage ceiling (64k) let
    one degenerate turn run for the better part of an hour before the server
    returned anything.  A synthesis stage writes its whole JSON delivery as one tool
    call, so the cap must hold a full plan: 16k cut one off mid-document
    (calculator-local, updated-plan); 32k matches the closing-answer cap.
    """
    configured = os.environ.get('WORKFLOW_SELF_HOSTED_TURN_OUTPUT_TOKENS', '').strip()
    return min(int(limit), int(configured) if configured else 32768)


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


def _config_values():
    path = os.environ.get('UNCLE_CONFIG') or os.path.join(os.getcwd(), '.uncle', 'config')
    values = {}
    try:
        with open(path, encoding='utf-8') as stream:
            for line in stream:
                parts = line.split('#', 1)[0].split(None, 1)
                if len(parts) == 2:
                    values.setdefault(parts[0], parts[1].strip())
    except OSError:
        pass
    return values


def _parse_temperature(text, source):
    try:
        value = float(text)
    except ValueError:
        raise ValueError('%s must be a number' % source) from None
    if not 0 <= value <= 2:
        raise ValueError('%s must be between 0 and 2' % source)
    return value


def temperature(stage=None):
    """Sampling temperature for a request, 0 unless configured.

    Order, first match wins: WORKFLOW_SELF_HOSTED_TEMPERATURE_<STAGE>, then
    WORKFLOW_SELF_HOSTED_TEMPERATURE, then `<stage>.temperature` and
    `self-hosted.temperature` in .uncle/config, then the built-in per-stage
    defaults (requirements runs at 1), then 0.  A stage inherits from its parent:
    a worker from its stage, `requirements-investigate` from `requirements`.
    """
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

    A request is not streamed, so a connection can be silent for many minutes while the
    server generates.  If the network under it dies (a dropped VPN), nothing says so: the
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


def post(url, api_key, body, timeout, what='model request'):
    """`_request` that rides out a lost network instead of failing the stage.

    A connection that cannot be made, or one that died mid-request, is tried again every
    few seconds for up to reconnect_seconds() (a VPN usually comes back within a minute).
    A server that answered, or one that simply never did (a read timeout), is not retried.
    """
    started = time.monotonic()
    budget = reconnect_seconds()
    noted = -30.0
    while True:
        try:
            return _request(url, api_key, body, timeout)
        except (ServerUnreachable, NetworkLost) as error:
            if _connections().aborting.is_set():
                raise  # the caller dropped this request on purpose; do not resend it
            waited = time.monotonic() - started
            if waited >= budget:
                raise type(error)('%s (the network stayed down for %d seconds; %s)' % (error, waited, what)) from None
            if waited - noted >= 30:
                noted = waited
                print('Self hosted: lost the model server (%s); retrying for up to %d more seconds.' %
                      (str(error).split(' (')[0][:120], budget - waited), file=sys.stderr, flush=True)
            time.sleep(min(10.0, max(1.0, budget - waited)) if budget >= 10 else 0.2)


def connect_timeout():
    """Seconds allowed to open a connection (WORKFLOW_SELF_HOSTED_CONNECT_SECONDS, default 15).

    Separate from the request timeout, which is an hour: a server that is simply
    not there (a dropped VPN, a stopped host) must fail in seconds, not wait out
    the operating system's connect timeout, once per attempt and per stage.
    """
    configured = os.environ.get('WORKFLOW_SELF_HOSTED_CONNECT_SECONDS', '').strip()
    if not configured:
        return 15.0
    try:
        value = float(configured)
    except ValueError:
        value = 0
    if value <= 0:
        raise ValueError('WORKFLOW_SELF_HOSTED_CONNECT_SECONDS must be a positive number')
    return value


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
            response = client.request(method, url, content=data, headers=headers,
                                      timeout=httpx.Timeout(timeout, connect=connect_timeout()))
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
        return response.status_code, response.reason_phrase, response.headers, response.content


def _request(url, api_key, body=None, timeout=30):
    """GET, or POST when `body` is given; returns parsed JSON.

    Redirects are never followed (the key must not leave the configured host).
    A non-2xx answer raises urllib's HTTPError so callers can read its code.
    """
    data = json.dumps(body).encode('utf-8') if body is not None else None
    headers = {'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json', 'Accept': 'application/json'}
    method = 'POST' if data is not None else 'GET'
    transport = _via_http2 if wants_http2(urlsplit(url).scheme) else _via_http1
    status, reason, response_headers, raw = transport(method, url, data, headers, timeout)
    if not 200 <= status < 300:
        raise HTTPError(url, status, reason, response_headers, io.BytesIO(raw))
    return json.loads(raw or b'null')


def detect_flavor(base_url, api_key):
    """Name the server family when it identifies itself; 'generic' otherwise."""
    origin = _origin(base_url)
    for flavor, path in (('ollama', '/api/version'), ('vllm', '/version')):
        try:
            data = _request(origin + path, api_key, timeout=5)
        except (HTTPError, URLError, OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get('version'), str):
            return flavor
    return 'generic'


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


def _final_call(values, messages, schema, name, mode, limit, effort, timeout):
    """One schema-constrained request in `mode`; returns (text, reason, usage)."""
    base_url, key = values['base_url'].rstrip('/'), values['api_key']
    if mode == 'ollama_format':
        body = {'model': values['model'], 'messages': _flatten(messages), 'stream': False, 'format': schema,
                'options': {'num_predict': limit, 'temperature': temperature()}}
        data = post(_origin(base_url) + '/api/chat', key, body, timeout)
        usage = {'prompt_tokens': data.get('prompt_eval_count', 0), 'completion_tokens': data.get('eval_count', 0)}
        reason = 'length' if data.get('done_reason') == 'length' else 'stop'
        return data['message']['content'], reason, usage
    body = {'model': values['model'], 'messages': messages, 'max_tokens': limit, 'stream': False,
            'temperature': temperature()}
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
    data = post(base_url + '/chat/completions', key, body, timeout)
    choice = data['choices'][0]
    return choice['message'].get('content') or '', choice.get('finish_reason'), data.get('usage') or {}


def constrained_completion(values, messages, schema, name, limit, effort='none', timeout=3600, skip=()):
    """Ask for `schema`-shaped output; returns (text, reason, usage, mode)."""
    caps = capabilities(values['base_url'], values['api_key'])
    last = None
    # The effort option is not universal either: if every mode refuses the
    # request with it, ask again without it before giving up.
    for with_effort in ([effort, ''] if effort else ['']):
        for mode in caps['modes']:
            if mode in caps['rejected'] or mode in skip:
                continue
            try:
                text, reason, usage = _final_call(values, messages, schema, name, mode, limit, with_effort, timeout)
                return text, reason, usage, mode
            except HTTPError as error:
                if error.code not in REJECTED:
                    raise ValueError('Model API request failed (HTTP %d); check the Base URL, API key and model' % error.code) from None
                caps['rejected'].add(mode)
                last = error
            except TimeoutError:
                raise _no_answer(timeout, limit) from None
        caps['rejected'].clear()
    raise ValueError('Model API rejected every request form (HTTP %s); check the model name' % getattr(last, 'code', '?'))


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


def chat(values, messages, tools, limit, effort='none', timeout=3600):
    """One tool-capable turn at the configured temperature.

    Returns the raw response, or None when the server refuses the request in
    every form (typically: no tool calling).  Other failures raise.
    """
    for with_effort in ([effort, ''] if effort else ['']):
        body = {'model': values['model'], 'messages': messages, 'max_tokens': limit, 'stream': False,
                'temperature': temperature()}
        if tools:
            body['tools'] = tools
        if with_effort:
            body['reasoning_effort'] = with_effort
        try:
            return post(values['base_url'].rstrip('/') + '/chat/completions', values['api_key'], body, timeout)
        except HTTPError as error:
            if error.code not in REJECTED:
                raise ValueError('Model API request failed (HTTP %d); check the Base URL, API key and model' % error.code) from None
        except TimeoutError:
            raise _no_answer(timeout, limit) from None
    return None

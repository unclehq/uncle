"""OpenAI SSE assembly and bounded, content-free runaway diagnostics."""
import json
import os


class StreamStopped(ValueError):
    """An incomplete generation; callers may retry, never publish its fragments."""
    retryable = True

    def __init__(self, reason, characters=0, byte_count=0, usage=None):
        self.reason, self.characters, self.byte_count = reason, characters, byte_count
        self.usage = usage or {}
        super().__init__('Stream stopped early: %s; retryable incomplete generation' % reason)


class Guard:
    def __init__(self):
        from self_hosted_http import positive_option
        self.whitespace_limit = positive_option('stream-whitespace-chars', 2000)
        self.repeats = positive_option('stream-repetition-count', 8, minimum=2)
        self.spaces = self.characters = self.byte_count = 0
        self.tail = self.line = self.previous_line = ''
        self.line_count = 0

    def feed(self, text):
        self.byte_count += len(text.encode('utf-8'))
        for char in text:
            self.characters += 1
            self.spaces = self.spaces + 1 if char.isspace() else 0
            if self.spaces >= self.whitespace_limit:
                raise StreamStopped('whitespace', self.characters, self.byte_count)
            self.tail = (self.tail + char)[-256 * self.repeats:]
            if char == '\n':
                line = self.line.strip()
                self.line_count = self.line_count + 1 if line == self.previous_line else 1
                self.previous_line, self.line = line, ''
                if len(line) >= 16 and self.line_count >= self.repeats:
                    raise StreamStopped('repetition', self.characters, self.byte_count)
            else:
                self.line = (self.line + char)[-4096:]
            # Chunk detection is independent of SSE/token boundaries. Short
            # JSON punctuation and indent sequences are not repetition evidence.
            if self.characters % 32 == 0:
                for size in range(16, min(256, len(self.tail) // self.repeats) + 1):
                    chunk = self.tail[-size:]
                    if len(chunk.strip()) >= 8 and self.tail.endswith(chunk * self.repeats):
                        raise StreamStopped('repetition', self.characters, self.byte_count)


def assemble(lines):
    """Consume SSE lines (bytes or str), returning the ordinary completion shape.

    Usage-only chunks and indexed/interleaved tool deltas are supported. A
    disconnect without a finish reason is a failure, never a successful answer.
    """
    message = {'role': 'assistant', 'content': ''}
    calls, guards, usage, fields = {}, {}, {}, []
    reason = None
    done = False

    def append(channel, fragment):
        if not isinstance(fragment, str):
            raise ValueError('Invalid streamed text delta')
        if channel not in guards:
            guards[channel] = Guard()
        guards[channel].feed(fragment)
        return fragment

    def event(data):
        nonlocal reason, usage, done
        if data == '[DONE]':
            done = True
            return
        part = json.loads(data)
        if part.get('error'):
            raise StreamStopped('server_error')
        if part.get('usage'):
            usage = part['usage']
        for choice in part.get('choices', []):
            if choice.get('index', 0) != 0:
                continue
            delta = choice.get('delta') or {}
            for key in ('content', 'reasoning', 'reasoning_content'):
                if delta.get(key) is not None:
                    message[key] = message.get(key, '') + append(key, delta[key])
            for item in delta.get('tool_calls') or []:
                index = item['index']
                call = calls.setdefault(index, {'id': '', 'type': 'function',
                                                'function': {'name': '', 'arguments': ''}})
                if item.get('id'):
                    call['id'] += item['id']
                if item.get('type'):
                    call['type'] = item['type']
                for key in ('name', 'arguments'):
                    fragment = (item.get('function') or {}).get(key)
                    if fragment is not None:
                        call['function'][key] += append(('tool', index, key), fragment)
            if choice.get('finish_reason') is not None:
                reason = choice['finish_reason']

    try:
        for raw in lines:
            line = raw.decode('utf-8') if isinstance(raw, bytes) else raw
            line = line.rstrip('\r\n')
            if not line:
                if fields:
                    event('\n'.join(fields))
                    fields = []
                    if done:
                        break
            elif line.startswith('data:'):
                fields.append(line[5:].removeprefix(' '))
        if fields and not done:
            event('\n'.join(fields))
        if reason is None:
            raise StreamStopped('incomplete_stream')
    except StreamStopped as error:
        error.usage = usage
        error.characters = sum(g.characters for g in guards.values())
        error.byte_count = sum(g.byte_count for g in guards.values())
        print(json.dumps({'type': 'self_hosted_stream_stop', 'stage': os.environ.get('UNCLE_STATUS_STAGE', ''),
                          'reason': error.reason, 'characters': error.characters, 'bytes': error.byte_count,
                          'output_tokens': usage.get('completion_tokens'), 'retryable': True}), flush=True)
        raise
    if calls:
        message['tool_calls'] = [calls[index] for index in sorted(calls)]
    return {'choices': [{'index': 0, 'message': message, 'finish_reason': reason}], 'usage': usage}

"""OpenAI SSE assembly and bounded, content-free runaway diagnostics."""
import json
import math
import os
import contextvars


ANSWER_CAP = contextvars.ContextVar('self_hosted_answer_cap', default=None)


def output_accounting(message, usage):
    """Keep measured channel tokens distinct from byte-based estimates.

    A total-only completion counter is not an answer counter when reasoning
    was observed. Unknown measured counts stay null, never become estimates.
    """
    def size(value):
        return len(value.encode('utf-8')) if isinstance(value, str) else 0
    from self_hosted_http import strip_reasoning
    content = message.get('content') or ''
    answer = strip_reasoning(content)
    answer_bytes = size(answer) + sum(
        size((call.get('function') or {}).get('arguments')) for call in message.get('tool_calls') or [])
    reasoning_bytes = size(message.get('reasoning')) + size(message.get('reasoning_content')) + size(content) - size(answer)
    return token_accounting(answer_bytes, reasoning_bytes, usage)


def token_accounting(answer_bytes, reasoning_bytes, usage):
    usage = usage or {}
    total = usage.get('completion_tokens')
    reasoning = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
    if isinstance(reasoning, int) and reasoning >= 0 and isinstance(total, int) and total >= reasoning:
        answer = total - reasoning
    else:
        reasoning = None
        answer = total if not reasoning_bytes else None
    return dict(answer_tokens=answer, reasoning_tokens=reasoning,
                estimated_answer_tokens=math.ceil(answer_bytes / 4),
                estimated_reasoning_tokens=math.ceil(reasoning_bytes / 4))


def answer_signal(accounting):
    return max(accounting['estimated_answer_tokens'], accounting.get('answer_tokens') or 0)


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
    from self_hosted_performance import ACTIVE
    budget = ACTIVE.get()

    def accounting():
        # Guards already count UTF-8 bytes incrementally. Do not rescan a long
        # reasoning buffer on every token; only inline thinking needs parsing.
        content = message['content']
        if content.lstrip().startswith('<think>'):
            return output_accounting(dict(message, tool_calls=list(calls.values())), usage)
        answer_bytes = sum(g.byte_count for channel, g in guards.items()
                           if channel == 'content' or isinstance(channel, tuple) and channel[2] == 'arguments')
        reasoning_bytes = sum(g.byte_count for channel, g in guards.items()
                              if channel in ('reasoning', 'reasoning_content'))
        return token_accounting(answer_bytes, reasoning_bytes, usage)

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
        estimate = answer_signal(accounting())
        # Only chat and tool arguments consume the deliverable allowance.
        # Reasoning retains its whitespace/repetition guards and server reserve.
        if budget is not None and budget.enabled and not budget.soft:
            if estimate > budget.threshold:
                budget.estimates.append(math.ceil(estimate))
                error = StreamStopped('learned_budget')
                error.message = dict(message, tool_calls=[calls[i] for i in sorted(calls)])
                raise error
        if ANSWER_CAP.get() is not None and estimate > ANSWER_CAP.get():
            raise StreamStopped('answer_cap')

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
                from writer_deadline import progress
                progress()
                fields.append(line[5:].removeprefix(' '))
        if fields and not done:
            event('\n'.join(fields))
        if reason is None:
            raise StreamStopped('incomplete_stream')
    except StreamStopped as error:
        error.usage = dict(usage, **accounting())
        error.characters = sum(g.characters for g in guards.values())
        error.byte_count = sum(g.byte_count for g in guards.values())
        print(json.dumps({'type': 'self_hosted_stream_stop', 'stage': os.environ.get('UNCLE_STATUS_STAGE', ''),
                          'reason': error.reason, 'characters': error.characters, 'bytes': error.byte_count,
                          'output_tokens': usage.get('completion_tokens'), 'retryable': True}), flush=True)
        raise
    if calls:
        message['tool_calls'] = [calls[index] for index in sorted(calls)]
    return {'choices': [{'index': 0, 'message': message, 'finish_reason': reason}],
            'usage': dict(usage, **output_accounting(message, usage))}

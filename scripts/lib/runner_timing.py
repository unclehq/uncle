"""Observe runner events without storing prompts, arguments or tool results."""
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
from build_timing import event, write_json


class RunnerTiming:
    def __init__(self, name):
        self.name = name
        self.attempt = uuid.uuid4().hex
        self.started, self.tick = time.time(), time.monotonic()
        self.last = self.tick
        self.count = 0
        self.responded = False
        self.native = False
        self.tools = {}
        self.completed = set()
        self.paired = 0
        self.unpaired = 0
        self.gaps = []
        self.usage_previous = {}
        self.cost_previous = 0.
        self.usage_tick = self.tick
        self.enabled = bool(os.environ.get('UNCLE_TIMING_DIR')) and os.environ.get('WORKFLOW_METRICS', '1') == '1'

    def emit(self, kind, name, start, end, **fields):
        event(kind, str(name)[:120], self.started + start - self.tick, max(0., end - start),
              workflow_state=self.name, attempt_id=self.attempt, **fields)

    def usage(self, usage, cost=None, inclusive=True, model=''):
        if not self.enabled:
            return
        try:
            from timing_usage import number, priced
            mapped = dict(input_tokens=usage.get('input_tokens'), output_tokens=usage.get('output_tokens'),
                          cache_read_tokens=usage.get('cache_read_input_tokens'),
                          cache_write_tokens=usage.get('cache_creation_input_tokens'))
            mapped = {k: v if number(v) else None for k, v in mapped.items()}
            now = time.monotonic()
            reset = any(number(v) and v < self.usage_previous.get(k, 0) for k, v in mapped.items())
            delta = {k: v - (0 if reset else self.usage_previous.get(k, 0)) if number(v) else None for k, v in mapped.items()}
            cost_delta = None
            if number(cost):
                cost_delta = cost - self.cost_previous if cost >= self.cost_previous and not reset else cost
                self.cost_previous = cost
            self.usage_previous.update({k: v for k, v in mapped.items() if number(v)})
            if any(delta.values()) or cost_delta:
                fields = priced(dict(delta, model=model, input_includes_cache=inclusive,
                                     reported_cost_usd=cost_delta))
                self.emit('model_usage', self.name, self.usage_tick, now, observed_at=time.time(),
                          counter_reset=reset, **fields)
                self.usage_tick = now
        except Exception:
            pass

    def response(self):
        if self.enabled and not self.responded:
            self.responded = True
            self.emit('runner_first_response', self.name, self.tick, time.monotonic())

    def context(self, tokens, source):
        if self.enabled and isinstance(tokens, (int, float)) and not isinstance(tokens, bool) and tokens >= 0:
            now = time.monotonic()
            self.emit('model_context', self.name, now, now, context_tokens=tokens,
                      context_source=source)

    def tool(self, identity, name, action, status=None):
        if not identity:
            return  # Never invent a pairing from a tool name alone.
        identity = str(identity)
        now = time.monotonic()
        if action == 'start' and identity not in self.completed:
            self.tools.setdefault(identity, (name, now))
        elif action == 'end' and identity not in self.completed:
            self.completed.add(identity)
            previous = self.tools.pop(identity, None)
            if previous:
                self.paired += 1
                self.emit('tool_call', previous[0], previous[1], now,
                          tool_status=str(status or 'completed')[:60])
            else:
                self.unpaired += 1
                self.emit('tool_unpaired', name, now, now, tool_status='start event unavailable')

    def observe(self, value):
        if not self.enabled:
            return
        try:
            self._observe(value)
        except Exception:
            pass  # Telemetry cannot interrupt the runner protocol.

    def _observe(self, e):
        if not isinstance(e, dict):
            return
        if e.get('uncle_timing_native'):
            self.native = True
            return
        now = time.monotonic()
        if not self.count:
            self.emit('runner_first_event', self.name, self.tick, now)
        else:
            self.gaps.append((now - self.last, self.last, now))
            self.gaps = sorted(self.gaps, reverse=True)[:20]
        self.last = now
        self.count += 1
        method, p = e.get('method'), e.get('params') or {}
        if method == 'thread/tokenUsage/updated':
            self.context((p.get('tokenUsage', {}).get('last') or {}).get('inputTokens'),
                         'Codex last request input (includes cached tokens)')
        if method == 'event' and p.get('type') == 'StatusUpdate':
            u = (p.get('payload') or {}).get('token_usage') or {}
            if isinstance(u.get('input_other'), (int, float)):
                self.context(u['input_other'] + (u.get('input_cache_read') or 0)
                             + (u.get('input_cache_creation') or 0), 'Kimi step input plus cache')
        message = e.get('message') or {}
        if e.get('type') == 'stream_event':
            message = (e.get('event') or {}).get('message') or {}
        if isinstance(message.get('usage'), dict):
            u = message['usage']
            if isinstance(u.get('input_tokens'), (int, float)):
                self.context(u['input_tokens'] + (u.get('cache_read_input_tokens') or 0)
                             + (u.get('cache_creation_input_tokens') or 0),
                             'Claude request input plus cache read/write')
        if e.get('type') == 'result' and isinstance(e.get('usage'), dict):
            self.usage(e['usage'], e.get('total_cost_usd'), e.get('input_includes_cache', False),
                       e.get('model') or os.environ.get('UNCLE_TIMING_MODEL', ''))

        if method in ('item/started', 'item/completed'):
            item = p.get('item') or {}
            kind = item.get('type')
            if kind in ('commandExecution', 'mcpToolCall', 'dynamicToolCall', 'fileChange', 'webSearch'):
                self.tool(item.get('id'), item.get('tool') or kind,
                          'start' if method.endswith('started') else 'end', item.get('status'))
        if method == 'item/agentMessage/delta' and p.get('delta'):
            self.response()
        if method == 'agent_event':
            if p.get('contentType') == 'tool':
                if p.get('type') == 'content_start': self.tool(p.get('toolCallId'), p.get('toolName', 'tool'), 'start')
                if p.get('type') == 'content_end': self.tool(p.get('toolCallId'), p.get('toolName', 'tool'), 'end', 'error' if p.get('error') else 'completed')
            if p.get('contentType') == 'text' and p.get('text'): self.response()
        # Kimi wire events retain invocation ids in tool_call_id/id.
        if method == 'event':
            wire = p; payload = wire.get('payload') or {}
            if wire.get('type') == 'ToolCall':
                self.tool(payload.get('id'), (payload.get('function') or {}).get('name', 'tool'), 'start')
            elif wire.get('type') == 'ToolResult':
                self.tool(payload.get('tool_call_id'), 'tool', 'end')
            elif wire.get('type') == 'ContentPart' and payload.get('type') == 'text' and payload.get('text'):
                self.response()
        # Claude stream messages: pair tool_use and tool_result by invocation id.
        content = (e.get('message') or {}).get('content', [])
        if isinstance(content, list):
            for part in content:
                if part.get('type') == 'tool_use':
                    self.tool(part.get('id'), part.get('name', 'tool'), 'start')
                elif part.get('type') == 'tool_result':
                    self.tool(part.get('tool_use_id'), 'tool', 'end', 'error' if part.get('is_error') else 'completed')
                elif e.get('type') == 'assistant' and part.get('type') == 'text' and part.get('text'):
                    self.response()
        # OpenCode canonical tool parts are polled; observations are deduplicated.
        if method == 'http/message':
            u = (p.get('info') or {}).get('tokens') or {}
            if isinstance(u.get('input'), (int, float)):
                cache = u.get('cache') or {}
                self.context(u['input'] + (cache.get('read') or 0) + (cache.get('write') or 0),
                             'OpenCode message input plus cache')
            for part in p.get('parts', []):
                if part.get('type') == 'tool':
                    state = part.get('state') or {}; status = state.get('status')
                    if status == 'running': self.tool(part.get('callID'), part.get('tool', 'tool'), 'start')
                    if status in ('completed', 'error'): self.tool(part.get('callID'), part.get('tool', 'tool'), 'end', status)
        if e.get('type') in ('item.started', 'item.completed'):
            item = e.get('item') or {}
            if item.get('type') in ('command_execution', 'mcp_tool_call', 'web_search', 'file_change'):
                self.tool(item.get('id'), item.get('type'), 'start' if e['type'].endswith('started') else 'end', item.get('status'))
            if item.get('type') == 'agent_message' and item.get('text'): self.response()

    def finish(self):
        if not self.enabled or self.native:
            return
        try:
            now = time.monotonic()
            for _, start, end in self.gaps:
                self.emit('runner_event_gap', self.name, start, end)
            self.emit('runner_tail_gap', self.name, self.last, now)
            for name, start in self.tools.values():
                self.emit('tool_unfinished', name, start, now, tool_status='end event unavailable')
            self.emit('runner_observation', self.name, self.tick, now,
                      event_count=self.count, first_response_received=self.responded,
                      completed_tool_pairs=self.paired, unpaired_tools=self.unpaired, unfinished_tools=len(self.tools), gaps_retained=len(self.gaps))
        except Exception:
            pass


def checklist(action, value, status='finished'):
    directory = os.environ.get('UNCLE_TIMING_DIR')
    if not directory or os.environ.get('WORKFLOW_METRICS', '1') != '1':
        if action == 'check-start': print('disabled')
        return
    root = Path(directory) / 'checklist'
    if action == 'check-start':
        if not re.fullmatch(r'MC-\d+', value):
            raise ValueError('Expected a checklist ID such as MC-001')
        token = uuid.uuid4().hex
        write_json(root / (token + '.json'), dict(name=value, started_at=time.time(),
                   monotonic=time.monotonic(), workflow_state=os.environ.get('UNCLE_TIMING_STAGE', 'EXECUTE_CHECKLIST')))
        print(token)
    elif value != 'disabled':
        if not re.fullmatch(r'[a-f0-9]{32}', value): raise ValueError('Invalid checklist timing token')
        path = root / (value + '.json')
        row = json.loads(path.read_text())
        if row.get('ended_at') is not None: return
        row.update(ended_at=time.time(), elapsed_seconds=max(0., time.monotonic() - row['monotonic']),
                   observation_status=status if status in ('finished', 'blocked', 'failed') else 'finished')
        write_json(path, row)


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'stream':
        observer = RunnerTiming(sys.argv[2])
        try:
            for line in sys.stdin.buffer:
                sys.stdout.buffer.write(line); sys.stdout.buffer.flush()
                try: observer.observe(json.loads(line))
                except (ValueError, UnicodeError): pass
        finally:
            observer.finish()
    else:
        try:
            checklist(action, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'finished')
        except Exception:
            if action == 'check-start': print('disabled')
            # Timing is optional evidence, never an acceptance or execution gate.

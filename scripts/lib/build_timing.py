"""Best-effort build timelines: explicit spans plus sampled descendant processes.

Records contain executable names, not command arguments, prompts or environment.
Instrumentation never decides workflow success. Samples are not exact lifetimes.
"""
from contextlib import ContextDecorator
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid


def write_json(path, value):
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(value), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def event(kind, name, started, elapsed, status=None, **fields):
    directory = os.environ.get('UNCLE_TIMING_DIR')
    if not directory or os.environ.get('WORKFLOW_METRICS', '1') != '1':
        return
    try:
        write_json(Path(directory) / 'events' / (uuid.uuid4().hex + '.json'),
                   dict(kind=kind, name=name, started_at=started,
                        elapsed_seconds=elapsed, process_exit=status,
                        pid=os.getpid(), **fields))
    except (OSError, ValueError):
        pass


def stage(name):
    directory = os.environ.get('UNCLE_TIMING_DIR')
    if directory:
        try:
            write_json(Path(directory) / 'events' / (uuid.uuid4().hex + '.json'),
                       dict(kind='stage_boundary', name=name, started_at=time.time(),
                            monotonic=time.monotonic()))
        except (OSError, ValueError):
            pass


def cpu_seconds(value):
    days, _, clock = value.rpartition('-')
    parts = clock.split(':')
    result = 0.0
    for part in parts:
        result = result * 60 + float(part)
    return result + (int(days) * 86400 if days else 0)


def snapshot():
    if os.name == 'nt':
        import ctypes
        from windows_driver import api, ProcessEntry
        from ctypes import wintypes
        kernel = api()
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        for name in ('Process32FirstW', 'Process32NextW'):
            getattr(kernel, name).argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
            getattr(kernel, name).restype = wintypes.BOOL
        handle = kernel.CreateToolhelp32Snapshot(2, 0)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError('Process snapshot unavailable')
        rows = []
        try:
            entry = ProcessEntry(); entry.size = ctypes.sizeof(entry)
            present = kernel.Process32FirstW(handle, ctypes.byref(entry))
            while present:
                rows.append((entry.pid, entry.parent, entry.exe, None))
                present = kernel.Process32NextW(handle, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(handle)
        return rows
    output = subprocess.run(['ps', '-axo', 'pid=,ppid=,time=,comm='],
                            capture_output=True, text=True, timeout=2, check=True)
    rows = []
    for line in output.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            pid, parent, cpu, name = parts
            # Do not attribute the observer's ps invocation to the build.
            if int(parent) == os.getpid() and Path(name).name == 'ps':
                continue
            rows.append((int(pid), int(parent), Path(name).name, cpu_seconds(cpu)))
    return rows


def descendants(rows, root):
    selected = {root}
    while True:
        added = {pid for pid, parent, _, _ in rows if parent in selected} - selected
        if not added:
            break
        selected.update(added)
    return [row for row in rows if row[0] in selected and row[0] != root]


class BuildTiming(ContextDecorator):
    def __init__(self, state):
        self.state = Path(state)
        self.enabled = False
        self.stop = threading.Event()
        self.samples = {}
        self.errors = 0
        self.status = None

    def __enter__(self):
        self.previous = os.environ.get('UNCLE_TIMING_DIR')
        self.started = time.time()
        self.tick = time.monotonic()
        if os.environ.get('WORKFLOW_METRICS', '1') != '1':
            return self
        try:
            self.interval = max(.1, min(10., float(os.environ.get('WORKFLOW_PROFILE_INTERVAL', '.5'))))
            self.directory = (self.state / 'performance' / uuid.uuid4().hex).resolve()
            write_json(self.directory / 'run.json', dict(started_at=self.started, status='running',
                       sample_interval_seconds=self.interval))
            os.environ['UNCLE_TIMING_DIR'] = str(self.directory)
            self.enabled = True
            self.thread = threading.Thread(target=self.observe, daemon=True)
            self.thread.start()
        except (OSError, ValueError, RuntimeError):
            self.enabled = False
            if self.previous is None:
                os.environ.pop('UNCLE_TIMING_DIR', None)
            else:
                os.environ['UNCLE_TIMING_DIR'] = self.previous
        return self

    def observe(self):
        while not self.stop.is_set():
            try:
                rows = descendants(snapshot(), os.getpid())
                now, tick = time.time(), time.monotonic()
                try:
                    state = (self.state / 'state').read_text().strip().split(':')[-1]
                except OSError:
                    state = 'STARTUP'
                live = set()
                for pid, parent, name, cpu in rows:
                    key = (pid, name, state)
                    live.add(key)
                    if key not in self.samples:
                        self.samples[key] = dict(kind='sampled_process', name=name, pid=pid,
                            parent_pid=parent, workflow_state=state, started_at=now,
                            first_tick=tick, last_tick=tick, cpu_first=cpu, cpu_last=cpu, observations=0)
                    row = self.samples[key]
                    row.update(last_tick=tick, cpu_last=cpu, observations=row['observations'] + 1)
                # Flush vanished processes: a reused PID gets a new observation span.
                for key in list(self.samples):
                    if key not in live:
                        self.flush_sample(self.samples.pop(key))
            except (OSError, ValueError, subprocess.SubprocessError):
                self.errors += 1
            self.stop.wait(self.interval)

    def flush_sample(self, row):
        elapsed = row.pop('last_tick') - row.pop('first_tick')
        first, last = row.pop('cpu_first'), row.pop('cpu_last')
        row['elapsed_seconds'] = elapsed
        row['cpu_seconds'] = max(0., last - first) if first is not None and last is not None else None
        write_json(self.directory / 'events' / (uuid.uuid4().hex + '.json'), row)

    def __exit__(self, exc_type, exc, traceback):
        if self.enabled:
            ended, end_tick = time.time(), time.monotonic()
            self.stop.set()
            self.thread.join(timeout=3)
            try:
                if not self.thread.is_alive():
                    for row in self.samples.values():
                        self.flush_sample(row)
                elapsed = end_tick - self.tick
                write_json(self.directory / 'run.json', dict(started_at=self.started, ended_at=ended,
                    elapsed_seconds=elapsed, ended_monotonic=end_tick, process_exit=self.status, status='interrupted' if exc_type else 'finished',
                    sample_interval_seconds=self.interval, sampling_errors=self.errors))
                render(self.directory)
            except Exception:
                # Reporting is observational, even if a record or renderer is faulty.
                pass
        if self.previous is None:
            os.environ.pop('UNCLE_TIMING_DIR', None)
        else:
            os.environ['UNCLE_TIMING_DIR'] = self.previous
        return False


def render(directory):
    metadata = json.loads((directory / 'run.json').read_text())
    records = []
    for path in (directory / 'events').glob('*.json'):
        try:
            records.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
    # Existing model/check/approval metrics are correlated to this invocation.
    for path in (directory.parent.parent / 'metrics').glob('*.json'):
        try:
            row = json.loads(path.read_text())
            if row.get('run_id') == directory.name:
                row['name'] = row.get('stage', row['kind'])
                row.setdefault('started_at', row.get('ended_at', time.time()) - row['elapsed_seconds'])
                records.append(row)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for path in (directory / 'checklist').glob('*.json'):
        try:
            row = json.loads(path.read_text())
            row['kind'] = 'checklist_item' if 'ended_at' in row else 'checklist_unfinished'
            row.setdefault('elapsed_seconds', max(0., metadata.get('ended_monotonic', time.monotonic()) - row['monotonic']))
            records.append(row)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    boundaries = sorted((r for r in records if r['kind'] == 'stage_boundary'), key=lambda r: r['monotonic'])
    end = metadata.get('ended_at', time.time())
    if boundaries:
        records.append(dict(kind='workflow_stage', name='STARTUP', started_at=metadata['started_at'],
                            elapsed_seconds=max(0., boundaries[0]['started_at'] - metadata['started_at'])))
    completed = {r.get('span_id') for r in records if r['kind'] == 'process'}
    for row in list(records):
        if row['kind'] == 'process_start' and row.get('span_id') not in completed:
            records.append(dict(row, kind='unfinished_process', elapsed_seconds=max(0., end - row['started_at'])))
    for index, row in enumerate(boundaries):
        following = boundaries[index + 1] if index + 1 < len(boundaries) else None
        records.append(dict(kind='workflow_stage', name=row['name'], started_at=row['started_at'],
                            elapsed_seconds=max(0., following['monotonic'] - row['monotonic'] if following else metadata.get('ended_monotonic', time.monotonic()) - row['monotonic'])))
    spans = [r for r in records if 'elapsed_seconds' in r and r['kind'] != 'process_start']
    from timing_usage import attribute, combine, number
    spans = attribute(spans)
    write_json(directory / 'parts.json', spans)
    lines = ['# Build timing', '', f"Run: `{directory.name}`", '',
             f"Elapsed wall time: {metadata.get('elapsed_seconds', end - metadata['started_at']):.3f}s", '',
             f"Process sampling interval: {metadata['sample_interval_seconds']}s; sampling errors: {metadata.get('sampling_errors', 0)}.", '',
             'Token and cost coverage shows known records/records in each row; partial sums are not complete totals. Unknown prices or usage remain unavailable.',
             'Interval token attribution is shared usage reported while the interval was active; it is not an exclusive charge for a tool/check and is never prorated from duration.',
             'Times overlap across stages, subprocesses, and parallel work; do not add categories together.',
             'Sampled process spans are approximate observed lifetimes. Short processes may be missed; CPU is unavailable on Windows.',
             'Checklist times require explicit timer commands; missing timers mean unavailable, not zero or passed. Tool times are observed event intervals, not isolated CPU time.',
             'Model usage spans are runner-reported API continuations, commonly one continuation after each tool result. They are not independent user turns. Cache-read totals sum the reused conversation prefix across continuations, not unique bytes reread from disk.',
             'Runner event gaps include any work or wait between received events; they do not prove API latency or model reasoning time. The 20 largest gaps per attempt are retained.',
             'Unfinished processes have no completion event; their displayed span ends at report time or run termination, not a confirmed process exit.',
             'Stage durations include waiting for people and tools. Model, approval, and check rows below include only this invocation.', '']
    lines += ['## Stage context size', '',
              'Context is input tokens in an individual model request, including cached input; it is not cumulative stage usage or the model context-window limit. Peak and latest are observed values; unavailable means the runner supplied no request-level context measurement.', '',
              '| Stage | Latest context tokens | Peak context tokens |', '|---|---:|---:|']
    stages = sorted({r.get('workflow_state') or r['name'] for r in spans
                     if r['kind'] in ('agent', 'reviewer', 'runner_observation', 'model_context')})
    for stage_name in stages:
        contexts = sorted((r for r in spans if r['kind'] == 'model_context'
                           and (r.get('workflow_state') or r['name']) == stage_name
                           and number(r.get('context_tokens'))), key=lambda r: r['started_at'])
        latest = str(contexts[-1]['context_tokens']) if contexts else 'Unavailable'
        peak = str(max(r['context_tokens'] for r in contexts)) if contexts else 'Unavailable'
        label = stage_name.replace('|', '&#124;').replace('\n', ' ')
        lines.append(f'| {label} | {latest} | {peak} |')
    lines.append('')
    for kind in ('workflow_stage', 'agent', 'reviewer', 'model_usage', 'approval', 'check', 'integrity', 'checklist_item', 'checklist_unfinished', 'tool_call', 'tool_unpaired', 'tool_unfinished', 'runner_first_event', 'runner_first_response', 'runner_event_gap', 'runner_tail_gap', 'runner_observation', 'read_cache', 'process', 'unfinished_process', 'sampled_process'):
        totals = {}
        usage_rows = {}
        for row in spans:
            if row['kind'] != kind:
                continue
            key = (row['name'], row.get('workflow_state', ''))
            usage_rows.setdefault(key, []).append(row)
            total = totals.setdefault(key, [0, 0., 0., 0])
            total[0] += 1; total[1] += row['elapsed_seconds']
            if row.get('cpu_seconds') is not None:
                total[2] += row['cpu_seconds']; total[3] += 1
        title = 'Model API Continuation' if kind == 'model_usage' else kind.replace('_', ' ').title()
        lines += [f'## {title}', '', '| Name | State | Spans | Seconds | CPU seconds | Input | Output | Cache read | Cache write | Total tokens | Token coverage | Reported USD | Estimated USD | Cost coverage |', '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|']
        for (name, state), (count, elapsed, cpu, known) in sorted(totals.items(), key=lambda item: item[1][1], reverse=True):
            usage = combine(usage_rows[(name, state)])
            name = name.replace('|', '&#124;').replace('\n', ' ')
            def cell(key, cost=False):
                value = usage.get(key)
                return (f'{value:.6f}' if cost else f'{value:g}') if number(value) else 'Unavailable'
            lines.append(f'| {name} | {state} | {count} | {elapsed:.3f} | {f"{cpu:.3f}" if known else "Unavailable"} | '
                         + ' | '.join(cell(key) for key in ('input_tokens','output_tokens','cache_read_tokens','cache_write_tokens','total_tokens'))
                         + f" | {usage['total_tokens_coverage']} | {cell('reported_cost_usd', True)} | {cell('estimated_cost_usd', True)} | {usage['estimated_cost_usd_coverage']} |")
        lines.append('')
    caches = [row for row in records if row['kind'] == 'read_cache']
    if caches:
        lines += ['## Read cache', '',
                  'Entries offered are validated context, not proof that the model skipped a tool call.', '',
                  '| Entries offered | Entries invalidated | Context bytes | Validation seconds |',
                  '|---:|---:|---:|---:|',
                  f"| {sum(r.get('offered_entries', 0) for r in caches)} | {sum(r.get('invalidated_entries', 0) for r in caches)} | {sum(r.get('context_bytes', 0) for r in caches)} | {sum(r['elapsed_seconds'] for r in caches):.3f} |", '']
    observations = [row for row in records if row['kind'] == 'runner_observation']
    if observations:
        lines += ['## Runner timing coverage', '',
                  '| Stage | Events received | First response observed | Paired tools | Unpaired ends | Missing ends |',
                  '|---|---:|---|---:|---:|---:|']
        for row in observations:
            name = row['name'].replace('|', '&#124;').replace('\n', ' ')
            lines.append(f"| {name} | {row['event_count']} | {'yes' if row['first_response_received'] else 'unavailable'} | {row['completed_tool_pairs']} | {row.get('unpaired_tools', 0)} | {row.get('unfinished_tools', 0)} |")
        lines.append('')
    (directory / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    trace = [dict(name=row['name'], cat=row['kind'], ph='X', ts=row['started_at'] * 1e6,
                  dur=row['elapsed_seconds'] * 1e6, pid=row.get('pid', 0), tid=row['kind'],
                  args={k: v for k, v in row.items() if k not in ('name', 'started_at', 'elapsed_seconds')}) for row in spans]
    write_json(directory / 'timeline.json', dict(traceEvents=trace))


if __name__ == '__main__':
    if sys.argv[1] == 'stage':
        stage(sys.argv[2])
    elif sys.argv[1] == 'report':
        project = Path(sys.argv[2])
        runs = list((project / '.uncle/workflow/performance').glob('*/run.json'))
        if runs:
            directory = max(runs, key=lambda p: p.stat().st_mtime).parent
            render(directory)
            print((directory / 'report.md').read_text())
            print(f'Timeline: {directory / "timeline.json"}')
        else:
            print('No build timelines recorded yet.')

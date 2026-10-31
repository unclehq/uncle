"""Publication-only recovery for implementation sections the deterministic reader cannot read."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading

import plan_steps
from runner_schema import strict_schema, validate

STRINGS = {'type': 'array', 'items': {'type': 'string'}}
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['steps'], 'properties': {
    'steps': {'type': 'array', 'minItems': 1, 'maxItems': 100, 'items': {
        'type': 'object', 'additionalProperties': False,
        'required': ['label', 'title', 'owns', 'depends_on', 'line'], 'properties': {
            'label': {'type': 'string', 'minLength': 1}, 'title': {'type': 'string', 'minLength': 1},
            'owns': STRINGS, 'depends_on': STRINGS,
            'line': {'type': 'integer', 'minimum': 1}}}}}}


def settings(root, stage):
    from self_hosted import config_stage
    from self_hosted_http import _config_values
    from unit_scheduler import option
    config = _config_values(os.environ.get('UNCLE_CONFIG') or str(Path(root) / '.uncle/config'))
    parent = config_stage(stage, config)
    runner = config.get(stage + '.runner', config.get(parent + '.runner', config.get('runner', 'claude')))
    if runner in ('opencode', 'aider'):
        runner = 'self-hosted'
    return runner, config, lambda name, default: option(runner, stage, name, default, config)


def request_steps(section, root, stage, runner, config, limit, seconds):
    """One bounded schema request, with no repository exploration or repair conversation."""
    from self_hosted import config_stage
    parent = config_stage(stage, config)
    prompt = ('Extract implementation steps from the section below. Return only the required JSON. '
              'Copy titles, labels, ownership paths and dependency labels; invent nothing. '
              'line is the 1-based line of each step heading in this section. '
              'An unnumbered step may use its position as label. Preserve source order.\n\n' + section)
    if runner in ('self-hosted', 'opencode', 'aider'):
        from self_hosted import settings as connection_settings
        from self_hosted_http import constrained_completion, connection_scope
        values = connection_settings(os.environ.get('UNCLE_CONFIG') or str(Path(root) / '.uncle/config'), stage)
        with connection_scope() as connections:
            connections.reconnect_seconds = 0
            connections.connect_seconds = seconds
            timer = threading.Timer(seconds, connections.abort)
            timer.daemon = True
            timer.start()
            try:
                answer, reason, _, _ = constrained_completion(values, [{'role': 'user', 'content': prompt}],
                                                              SCHEMA, 'plan_steps', limit, timeout=seconds)
                if connections.aborting.is_set():
                    raise TimeoutError('step extraction timed out')
            finally:
                timer.cancel()
        if reason != 'stop':
            raise ValueError('step extraction did not complete')
        return json.loads(answer)
    model = config.get(stage + '.model', config.get(parent + '.model', config.get('model', '')))
    with tempfile.TemporaryDirectory(prefix='uncle-plan-steps-') as directory:
        schema = Path(directory) / 'schema.json'
        schema.write_text(json.dumps(strict_schema(SCHEMA)), encoding='utf-8')
        output = Path(directory) / 'answer.json'
        env = os.environ.copy()
        # A nested formatting request must not replace the stage's artifact or status.
        for key in ('UNCLE_STATUS_FILE', 'UNCLE_ARTIFACT_DELIVERY', 'UNCLE_STRUCTURED_OUTPUT_PATH',
                    'UNCLE_OUTPUT_SCHEMA_FILE', 'UNCLE_WORKER_SCHEMA_FILE', 'UNCLE_STEERING'):
            env.pop(key, None)
        if runner == 'claude':
            command = [os.environ.get('WORKFLOW_CLAUDE_CMD', 'claude'), '-p', '--output-format', 'json',
                       '--json-schema', json.dumps(SCHEMA), '--max-turns', '1', '--tools', '']
            env['CLAUDE_CODE_MAX_OUTPUT_TOKENS'] = str(limit)
        elif runner == 'codex':
            command = [os.environ.get('WORKFLOW_CODEX_CMD', 'codex'), 'exec', '--skip-git-repo-check',
                       '--sandbox', 'read-only', '--output-schema', str(schema), '--output-last-message', str(output)]
        else:
            adapter = Path(__file__).resolve().parents[1] / ('agent-' + runner + '.sh')
            if not adapter.is_file():
                raise ValueError('no structured step extractor for configured runner')
            command = ['bash', str(adapter), '-p', '--max-turns', '1']
            env['UNCLE_OUTPUT_SCHEMA_FILE'] = str(schema)
            env['UNCLE_STRUCTURED_OUTPUT_PATH'] = str(output)
            prompt += '\nRequired JSON schema:\n' + json.dumps(SCHEMA)
        if model:
            command += ['--model', model]
        done = subprocess.run(command, input=prompt, text=True, capture_output=True,
                              cwd=directory, env=env, timeout=seconds, check=True)
        if output.is_file():
            return json.loads(output.read_text(encoding='utf-8'))
        if runner not in ('claude', 'codex'):
            from structured_output import extract, reply_texts
            log = Path(directory) / 'events.jsonl'
            log.write_text(done.stdout, encoding='utf-8')
            value = extract(log)
            if value is not None:
                return value
            for reply in reply_texts(log):
                try:
                    return json.loads(reply)
                except ValueError:
                    continue
        value = json.loads(done.stdout)
        return value.get('structured_output', value)


def recovered_body(body, answer):
    """Anchor every returned record to its source; retain the step's complete instruction text."""
    from plan_model import render_block, valid_path
    validate(answer, SCHEMA)
    steps = answer['steps']
    source = body.splitlines()
    labels = {step['label']: n for n, step in enumerate(steps, 1)}
    if len(labels) != len(steps) or not any(step['owns'] for step in steps):
        raise ValueError('empty or ambiguous recovered steps')
    starts = [step['line'] - 1 for step in steps]
    if starts != sorted(set(starts)) or starts[-1] >= len(source):
        raise ValueError('invalid source lines')
    fence = ''
    for i, line in enumerate(source):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            fence = '' if fence == marker[1][0] else marker[1][0]
            continue
        if not fence and re.match(r'^\s*(?:#{1,6}\s+|[-*+]\s+)?(?:\*\*|__)?Step\s+[^:]+:', line, re.I) and i not in starts:
            raise ValueError('recovery omitted a source step')
    records = []
    for n, step in enumerate(steps, 1):
        start = starts[n - 1]
        end = starts[n] if n < len(steps) else len(source)
        chunk = '\n'.join(source[start:end])
        if step['title'] not in plan_steps.plain(source[start]):
            raise ValueError('step title is not grounded in its source line')
        if any(not valid_path(path) or not re.search(r'(?<![\w./*?\[\]@-])' + re.escape(path) + r'(?![\w./*?\[\]@-])', chunk)
               for path in step['owns']):
            raise ValueError('step ownership is not grounded in its source')
        if any(dep not in labels for dep in step['depends_on']):
            raise ValueError('unknown recovered dependency')
        # Preserve all following prose, including annotations on metadata lines.
        suffix = source[start].split(step['title'], 1)[1].lstrip('*_ —–-')
        text = '\n'.join(([suffix] if suffix else []) + source[start + 1:end]).strip()
        records.append(dict(id='step-%d' % n, number=n, title=step['title'], text=text,
                            owns=step['owns'], depends_on=[labels[dep] for dep in step['depends_on']]))
    from plan_model import validate as validate_plan
    candidate = dict(title='', intro='', sections=[dict(id='s1', heading='Implementation order', blocks=[
        dict(id='s1.1', kind='steps', items=records)])])
    errors, _ = validate_plan(candidate)
    if errors:
        raise ValueError(errors[0])
    prefix = '\n'.join(source[:starts[0]]).strip()
    return '\n' + (prefix + '\n\n' if prefix else '') + render_block({'kind': 'steps', 'items': records}) + re.search(r'\s*$', body)[0]


def recover_once(body, root, stage, runner, config, limit, seconds):
    """Preview and publication can see the same packet in different processes."""
    from self_hosted import config_stage
    parent = config_stage(stage, config)
    model = config.get(stage + '.model', config.get(parent + '.model', config.get('model', '')))
    key = hashlib.sha256(json.dumps([body, parent, runner, model, limit, seconds]).encode()).hexdigest()
    cache = Path(root) / '.uncle/workflow/plan-step-recovery' / (key + '.json')
    if cache.is_file():
        answer = json.loads(cache.read_text(encoding='utf-8'))
        if answer is None:
            raise ValueError('step extraction already failed for this section')
        return recovered_body(body, answer)
    answer = None
    try:
        candidate = request_steps(body, root, stage, runner, config, limit, seconds)
        recovered = recovered_body(body, candidate)
        answer = candidate
        return recovered
    finally:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(answer) + '\n', encoding='utf-8')


def normalize_publication(narrative, root, stage):
    runner, config, option = settings(root, stage)
    if option('plan-step-normalize', 'on') in ('off', '0', 'false'):
        return narrative
    if option('plan-step-recovery', 'on') not in ('off', '0', 'false'):
        for section in plan_steps.sections(narrative):
            body = narrative[section['body_start']:section['end']]
            steps, _ = plan_steps.extract_body(body)
            if ((steps and not any(step['owns'] for step in steps)) or
                    (not steps and re.search(r'\bStep\b|^\s*\d+[.)]', body, re.M | re.I))):
                try:
                    limit = max(256, min(16384, int(option('plan-step-answer-tokens', '4096'))))
                    seconds = max(1, min(300, int(option('plan-step-seconds', '60'))))
                    recovered = recover_once(body, root, stage, runner, config, limit, seconds)
                    narrative = narrative[:section['body_start']] + recovered + narrative[section['end']:]
                except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
                    pass  # Existing validation and ownership gates still decide acceptance.
                break
    return plan_steps.normalize(narrative)

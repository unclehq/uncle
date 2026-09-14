"""Gate identity and supervisor-answer receipts shared by the drivers and the TUI.

A driver names every prompt it reads (run UUID + monotonic prompt id) in a
`gate_open` status event that also carries the prompt text, its kind, its
sensitivity class and the allowed choices. The TUI may answer a prompt on a
human's request: it writes an envelope under
`.uncle/workflow/supervision/answers/<run>/<prompt>.json` before the stdin
write, and the driver's read wrapper consumes the envelope only when the run,
prompt and answer all match. The attribution the driver records is built
here from that receipt, never from prompt text or model output (D-5, D-6).
"""
import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from supervisor import atomic_write  # noqa: E402

RECEIPTS = 'gate-answers.jsonl'
MAX_TEXT = 2000
MAX_INPUT = 400
KINDS = ('confirm', 'audit', 'enter', 'input')
SENSITIVE = ('signing', 'publication', 'waiver')
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
_PUBLISH = re.compile(r'(?i)\b(push|publish|pull request|create the pr)\b')
_AUDIT_KEY = re.compile(r'\[([a-z])\]')


def classify(text, class_hint='', signing=False):
    """(kind, class, reason, choices) for one prompt, decided from the driver's
    own prompt text and hints; model output never reaches this function."""
    plain = str(text or '')
    upper = plain.upper()
    choices = []
    if signing or plain.startswith(('Commit signing needs your help.', 'Commit needs your help.')):
        return 'enter', 'sensitive', 'signing', choices
    if plain.startswith('PR title [default:'):
        return 'input', 'sensitive', 'publication', choices
    if plain.startswith('Audit finding ') and '[s] Skip' in plain:
        choices = sorted(set(_AUDIT_KEY.findall(plain)))
        kind = 'audit'
    elif '[Y/N]' in upper:
        kind, choices = 'confirm', ['y', 'n']
    elif 'PRESS ENTER' in upper:
        kind = 'enter'
    else:
        kind = 'input'
    hint = str(class_hint or '').strip()
    if hint.startswith('sensitive'):
        return kind, 'sensitive', hint.partition(':')[2] or 'waiver', choices
    if re.search(r'(?i)\bwaive', plain):
        return kind, 'sensitive', 'waiver', choices
    if _PUBLISH.search(plain):
        return kind, 'sensitive', 'publication', choices
    return kind, 'routine', '', choices


def validate_answer(kind, answer, choices=()):
    """The literal stdin line for `answer` under `kind`, or ValueError. Paths and
    command text are ordinary input; control characters and newlines are not."""
    if not isinstance(answer, str):
        raise ValueError('answer must be a string')
    if _CONTROL.search(answer):
        raise ValueError('answer contains control characters or a newline')
    if kind == 'confirm':
        word = answer.strip().lower()
        if word in ('y', 'yes'):
            return 'y'
        if word in ('n', 'no'):
            return 'n'
        raise ValueError('a [Y/N] prompt takes y or n')
    if kind == 'audit':
        key = answer.strip().lower()
        if len(key) == 1 and key in [c.lower() for c in choices]:
            return key
        raise ValueError('an audit prompt takes one of: ' + ', '.join(choices))
    if kind == 'enter':
        if answer.strip() == '':
            return ''
        raise ValueError('a press-Enter prompt takes an empty answer')
    if kind == 'input':
        text = answer.strip()
        if len(text) > MAX_INPUT:
            raise ValueError('input answers are limited to %d characters' % MAX_INPUT)
        return text
    raise ValueError('unknown prompt kind %r' % (kind,))


def attribution(source, name):
    """`supervisor:<explicit|standing>:<name>`; never a bare human name."""
    if source not in ('explicit', 'standing'):
        raise ValueError('delegation source must be explicit or standing')
    return 'supervisor:%s:%s' % (source, re.sub(r'[\r\n]', ' ', str(name or '')))


def answers_dir(state_dir, run):
    return Path(state_dir) / 'supervision' / 'answers' / re.sub(r'[^A-Za-z0-9_.-]', '_', str(run))


def envelope_path(state_dir, run, prompt_id):
    return answers_dir(state_dir, run) / (re.sub(r'[^A-Za-z0-9_.-]', '_', str(prompt_id)) + '.json')


def receipt(state_dir, **row):
    """Append one receipt row; the receipts file is the audit trail (SI-4)."""
    directory = Path(state_dir) / 'supervision'
    directory.mkdir(parents=True, exist_ok=True)
    row = dict(row, time=int(time.time()))
    with open(directory / RECEIPTS, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(row, sort_keys=True) + '\n')
    return row


def write_envelope(state_dir, run, prompt_id, answer, source, name, request, rationale, kind, text,
                   config_key='', config_value=''):
    """Persist request+rationale+answer atomically before any stdin write; an
    OSError here means the answer must not be sent (D-6)."""
    answer_id = uuid.uuid4().hex
    record = {'schema': 1, 'answer_id': answer_id, 'run': str(run), 'prompt': str(prompt_id), 'kind': kind,
              'text': str(text)[:MAX_TEXT], 'answer': answer, 'source': source, 'name': str(name or ''),
              'attribution': attribution(source, name), 'request': str(request)[:MAX_TEXT],
              'rationale': str(rationale)[:MAX_TEXT], 'config_key': config_key, 'config_value': config_value,
              'status': 'attempted', 'created': int(time.time())}
    atomic_write(envelope_path(state_dir, run, prompt_id), json.dumps(record, sort_keys=True))
    receipt(state_dir, **record)
    return record


def update_envelope(state_dir, run, prompt_id, status, detail=''):
    path = envelope_path(state_dir, run, prompt_id)
    try:
        with open(path, encoding='utf-8') as fh:
            record = json.load(fh)
    except (OSError, ValueError):
        return None
    record['status'] = status
    if detail:
        record['detail'] = str(detail)[:400]
    atomic_write(path, json.dumps(record, sort_keys=True))
    receipt(state_dir, answer_id=record.get('answer_id'), run=record.get('run'), prompt=record.get('prompt'),
            status=status, detail=str(detail)[:400], attribution=record.get('attribution'))
    return record


def discard_envelope(state_dir, run, prompt_id, reason):
    """Remove an unsent envelope (takeover, cancel, close) so no later read can consume it."""
    record = update_envelope(state_dir, run, prompt_id, 'discarded', reason)
    try:
        os.unlink(envelope_path(state_dir, run, prompt_id))
    except OSError:
        pass
    return record


def consume(state_dir, run, prompt_id, answer):
    """The attribution for a line the driver just read, or '' when no envelope
    for this exact run/prompt carries this exact answer. A mismatched envelope
    is recorded and removed without conferring any attribution."""
    path = envelope_path(state_dir, run, prompt_id)
    try:
        with open(path, encoding='utf-8') as fh:
            record = json.load(fh)
    except (OSError, ValueError):
        return ''
    try:
        os.unlink(path)
    except OSError:
        pass
    same = (str(record.get('run')) == str(run) and str(record.get('prompt')) == str(prompt_id)
            and record.get('answer') == answer and record.get('status') in ('attempted', 'delivered'))
    if not same:
        receipt(state_dir, answer_id=record.get('answer_id'), run=str(run), prompt=str(prompt_id),
                status='mismatch', attribution='')
        return ''
    try:
        label = attribution(record.get('source'), record.get('name'))
    except ValueError:
        receipt(state_dir, answer_id=record.get('answer_id'), run=str(run), prompt=str(prompt_id),
                status='mismatch', attribution='')
        return ''
    receipt(state_dir, answer_id=record.get('answer_id'), run=str(run), prompt=str(prompt_id),
            status='consumed', attribution=label, request=record.get('request', ''),
            rationale=record.get('rationale', ''), answer=answer)
    return label


def _event(path, data):
    if not path:
        return
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(data) + '\n')


def next_prompt_id(state_dir=None):
    """Monotonic within a driver run (nanosecond clock); no file is touched, so
    a run with supervision disabled leaves no supervision directory behind."""
    return str(time.time_ns())


def open_gate(state_dir, status_file, stage, run, text, class_hint='', gate_file='', signing=False):
    """Allocate the prompt id and emit `gate_open` with identity and classification."""
    prompt_id = next_prompt_id(state_dir)
    kind, klass, reason, choices = classify(text, class_hint, signing)
    _event(status_file, {'event': 'gate_open', 'stage': stage or '', 'prompt': str(text)[:80], 'run': str(run),
                         'prompt_id': prompt_id, 'text': str(text)[:MAX_TEXT], 'kind': kind, 'class': klass,
                         'reason': reason, 'choices': choices, 'file': gate_file or ''})
    return prompt_id


def close_gate(state_dir, status_file, stage, run, prompt_id, answer, answered_by):
    _event(status_file, {'event': 'gate_answer', 'stage': stage or '', 'run': str(run), 'prompt_id': str(prompt_id),
                         'answered_by': answered_by or 'human', 'answer_len': len(answer or '')})
    _event(status_file, {'event': 'gate_close', 'stage': stage or '', 'run': str(run), 'prompt_id': str(prompt_id)})


class Gate:
    """In-process helper for Python read sites (change-pr.sh's `ask`)."""

    def __init__(self, state_dir='.uncle/workflow', environ=None):
        env = os.environ if environ is None else environ
        self.state_dir = state_dir
        self.status_file = env.get('UNCLE_STATUS_FILE', '')
        self.stage = env.get('UNCLE_STATUS_STAGE', '')
        self.run = env.get('UNCLE_GATE_RUN') or uuid.uuid4().hex
        self.prompt_id = ''

    def open(self, text, signing=False, class_hint=''):
        try:
            self.prompt_id = open_gate(self.state_dir, self.status_file, self.stage, self.run, text,
                                       class_hint=class_hint, signing=signing)
        except OSError:
            self.prompt_id = ''
        return self.prompt_id

    def read(self, answer):
        """Attribution for the line just read; also closes the gate."""
        label = ''
        if self.prompt_id:
            try:
                label = consume(self.state_dir, self.run, self.prompt_id, answer)
                close_gate(self.state_dir, self.status_file, self.stage, self.run, self.prompt_id, answer, label)
            except OSError:
                label = ''
        self.prompt_id = ''
        return label


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='action')
    p = sub.add_parser('open')
    p.add_argument('--state-dir', default='.uncle/workflow')
    p.add_argument('--file', default='')
    p.add_argument('--stage', default='')
    p.add_argument('--run', required=True)
    p.add_argument('--text', required=True)
    p.add_argument('--class', dest='class_hint', default='')
    p.add_argument('--gate-file', default='')
    p = sub.add_parser('consume')
    p.add_argument('--state-dir', default='.uncle/workflow')
    p.add_argument('--file', default='')
    p.add_argument('--stage', default='')
    p.add_argument('--run', required=True)
    p.add_argument('--prompt-id', required=True)
    p.add_argument('--answer', required=True)
    p = sub.add_parser('run-id')
    ns = parser.parse_args(argv)
    if ns.action == 'open':
        print(open_gate(ns.state_dir, ns.file, ns.stage, ns.run, ns.text, ns.class_hint, ns.gate_file))
        return 0
    if ns.action == 'consume':
        label = consume(ns.state_dir, ns.run, ns.prompt_id, ns.answer)
        close_gate(ns.state_dir, ns.file, ns.stage, ns.run, ns.prompt_id, ns.answer, label)
        print(label)
        return 0
    if ns.action == 'run-id':
        print(uuid.uuid4().hex)
        return 0
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

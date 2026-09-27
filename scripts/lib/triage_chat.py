"""Triage master turns: prompt composition, runner launch, reply parsing.

The runner is the agent-side shim of the configured `triage.runner`, launched
with the same flags the drivers use for an agent stage and the prompt on
stdin. Its stream-json goes to `.uncle/workflow/logs/triage-<n>.jsonl`; the
reply is the last `assistant` text event in that stream, which every shim
produces (claude natively; codex, cline, and kimi through their translators).
The `result` event is read only for its error flag.
"""
import json
import os
import queue
import re
import subprocess
import threading
from pathlib import Path

from process_tree import launch_command, kill_tree, group_options

CLASSES = ('code defect', 'requirement gap', 'needs owner decision', 'tool bug')
MAX_REPLY = 1024 * 1024
TIMEOUT_TICKS = 1500  # 0.2 s each: five minutes, as HomeRequest
SCRUBBED_ENV = ('UNCLE_STATUS_FILE', 'UNCLE_PROJECT_ROOT', 'UNCLE_STEERING', 'STAGEGATE_RUN_ID',
                'STAGEGATE_ORIGIN_REPO', 'STAGEGATE_ORIGIN_ISSUE', 'UNCLE_STATUS_STAGE',
                'UNCLE_DRIVER_SUPERVISED', 'DOCUMENT_BUDGET_SOURCE')
DIAGNOSIS_TOOLS = 'Read,Grep,Glob,Bash,Edit,Write,MultiEdit'
EXECUTE_TOOLS = 'Read,Grep,Glob,Bash,Edit,Write,MultiEdit'

# Markdown emphasis around the label and its value. Models write
# "**Proposal 1:** ..." and "Classification: `tool bug`" as readily as the plain
# form, and rejecting those threw away a reply that followed the contract in
# every way that matters -- leaving the operator a diagnosis they could read but
# not act on.
_EMPH = r'[*_`]*'
_CLASS_RE = re.compile(r'^\s*%s\s*Classification\s*%s\s*:\s*(.+?)\s*$' % (_EMPH, _EMPH),
                       re.IGNORECASE | re.MULTILINE)
_PROPOSAL_RE = re.compile(r'^\s*%s\s*Proposal\s+([1-3])\s*%s\s*:%s\s*(.*)$' % (_EMPH, _EMPH, _EMPH),
                          re.IGNORECASE | re.MULTILINE)
_RESUME_RE = re.compile(r'^\s*%s\s*Offer\s*%s\s*:\s*%s\s*resume\s*%s\s*$' % (_EMPH, _EMPH, _EMPH, _EMPH),
                        re.IGNORECASE | re.MULTILINE)


def _plain(value):
    """A label's value without the emphasis a model wrapped it in."""
    return re.sub(r'^[*_`]+|[*_`]+$', '', (value or '').strip()).strip()


def parse_reply(text):
    """The classification and proposals a reply carries, or None.

    None means the reply did not follow the contract: it is shown verbatim
    and nothing in it is selectable. A classification outside the four
    classes, or a proposal list that is empty or skips a number, is the same
    failure: a half-parsed reply would offer the operator a half-checked
    action.
    """
    match = _CLASS_RE.search(text or '')
    if not match:
        return None
    klass = _plain(match.group(1)).lower()
    if klass not in CLASSES:
        return None
    proposals = []
    for number, body in _PROPOSAL_RE.findall(text):
        proposals.append((int(number), _plain(body)))
    numbers = [n for n, _ in proposals]
    if not numbers or numbers != list(range(1, len(numbers) + 1)):
        return None
    return {'classification': klass, 'proposals': proposals,
            'offer_resume': bool(_RESUME_RE.search(text))}


# Proposals that must not auto-resume after /do: the contract's [stop] and
# [manual] tags, and the phrase families that mean a person still has work to
# do. Unclear wording errs toward holding; a false hold costs one /resume.
_HOLD_TAG_RE = re.compile(r'^\s*[*_`]*\s*\[(stop|manual)\]', re.IGNORECASE)
_HOLD_PHRASES = (
    (re.compile(r'\b(?:stop|halt|abort)\s+(?:the\s+)?(?:build|run|workflow)\b', re.IGNORECASE),
     'stop proposal (halts the build)'),
    (re.compile(r'\bmanual(?:ly)?\b|\bby\s+hand\b|\byourself\b|\b(?:operator|owner|you)\s+must\b', re.IGNORECASE),
     'manual proposal (needs a person)'),
    (re.compile(r'\bcredentials?\b|\bsecrets?\b|\bpasswords?\b|\bapi[\s-]?keys?\b'
                r'|\b(?:rotate|provide|set|supply)\s+(?:an?\s+|the\s+)?(?:\w+\s+)?tokens?\b', re.IGNORECASE),
     'manual proposal (credentials or secrets)'),
    (re.compile(r'\brestart\s+(?:the\s+|a\s+)?(?:\w+\s+)?(?:server|service)s?\b', re.IGNORECASE),
     'manual proposal (server or service restart)'),
    (re.compile(r'\bdraft\s+(?:an?\s+)?issue\b', re.IGNORECASE),
     'manual proposal (issue draft needs follow-up)'),
)


def hold_reason(proposal_text):
    """Why a proposal must not auto-resume after /do, or '' when it may.

    Reads the raw stored proposal text, so a tag shown verbatim still counts.
    """
    text = proposal_text or ''
    tag = _HOLD_TAG_RE.match(text)
    if tag:
        kind = tag.group(1).lower()
        return '%s proposal ([%s] tag)' % (kind, kind)
    for pattern, reason in _HOLD_PHRASES:
        if pattern.search(text):
            return reason
    return ''


def _text_of(content):
    if isinstance(content, str):
        return content
    parts = []
    for item in content or []:
        if isinstance(item, dict) and item.get('type') == 'text':
            parts.append(str(item.get('text', '')))
    return ''.join(parts)


def extract_reply(lines):
    """(reply_text, error) from stream-json lines.

    The reply is the last non-empty assistant text. The terminal `result`
    event contributes only its error flag and detail; its `.result` string is
    not read because not every shim fills it (AR-011).
    """
    last = ''
    error = ''
    for line in lines:
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get('type')
        if kind == 'assistant':
            text = _text_of((event.get('message') or {}).get('content'))
            if text.strip():
                last = text
        elif kind == 'result':
            flag = event.get('is_error')
            if flag is True or str(flag).lower() == 'true':
                error = str(event.get('error_detail') or event.get('subtype') or 'runner reported an error')
    return last, error


def extract_reply_from_log(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        return extract_reply(fh)


def runner_flags(effort, model, tools, turns=40):
    """The agent-stage flag set the shims translate; the prompt goes on stdin."""
    flags = ['-p']
    if model:
        flags += ['--model', model]
    flags += ['--effort', effort or 'low', '--strict-mcp-config', '--max-turns', str(turns),
              '--output-format', 'stream-json', '--verbose', '--allowedTools', tools]
    return flags


def scrub_env(env):
    env = dict(env)
    for name in SCRUBBED_ENV:
        env.pop(name, None)
    return env


def compose_prompt(template, bundle, transcript, mode, proposal=None, followup='', driver_tail=''):
    """The prompt for one turn: contract, bundle, driver tail, prior turns, the ask.

    The driver tail is what the TUI saw the driver print last: on request at
    a gate there is no failing log, and the pending prompt is the context.
    """
    parts = [template.rstrip(), '', '---', '', '# TRIAGE.md', '', bundle.rstrip(), '']
    if driver_tail.strip():
        parts += ['---', '', '# Driver output (tail)', '', '```text', driver_tail.rstrip(), '```', '']
    if transcript:
        parts += ['---', '', '# Conversation so far', '']
        for role, text in transcript:
            parts += ['%s:' % role, text.rstrip(), '']
    parts += ['Standing operator authorization: you may edit any project Markdown (.md) file and any file under the project .uncle directory, including workflow state, approval and waiver records, during this conversation. Preserve evidence and report what changed; accurately distinguish operator authorization, edits and observed test results; never invent execution evidence. Edits outside these paths require an execute request. This overrides older diagnosis-only Markdown restrictions.', '', '---', '']
    if mode == 'execute':
        parts += ['Execute Proposal %d only: %s' % (proposal[0], proposal[1]),
                  'Do nothing beyond it. Finish with the paragraph the execute-turn contract asks for.']
    elif followup:
        parts += ['Operator follow-up (Markdown and .uncle edits persist; other changes require a fix request):', '', followup.rstrip(), '',
                  'Reply under the diagnosis reply contract.']
    else:
        parts += ['Diagnosis turn: reply under the diagnosis reply contract.']
    return '\n'.join(parts) + '\n'


class TriageRequest:
    """One master turn in the background, logged to `log_path`."""

    def __init__(self, command, prompt, env, cwd, log_path):
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.log_path = str(log_path)
        self.thread = threading.Thread(target=self._run, args=(command, prompt, env, cwd), daemon=True)
        self.thread.start()

    def cancel(self):
        self.cancelled.set()

    def _run(self, command, prompt, env, cwd):
        process = None
        try:
            Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
            prompt_path = self.log_path + '.prompt'
            with open(prompt_path, 'w', encoding='utf-8') as fh:
                fh.write(prompt)
            # The prompt goes in on stdin, as the drivers do: --allowedTools is
            # variadic and would swallow a positional prompt.
            with open(self.log_path, 'wb') as log, open(prompt_path, 'rb') as stdin:
                process = subprocess.Popen(launch_command(command), cwd=cwd, env=env, stdin=stdin,
                                           stdout=log, stderr=subprocess.STDOUT, **group_options())
                streamed = ''
                try:
                    for _ in range(TIMEOUT_TICKS):
                        if self.cancelled.is_set():
                            raise ValueError('Triage turn cancelled')
                        # Show the reply forming instead of one blob at exit:
                        # the newest assistant text so far, as it lands.
                        try:
                            if os.path.exists(self.log_path):
                                text, _ = extract_reply_from_log(self.log_path)
                                if text != streamed:
                                    streamed = text
                                    self.events.put(('delta', streamed))
                        except OSError:
                            pass
                        try:
                            code = process.wait(timeout=0.2)
                            break
                        except subprocess.TimeoutExpired:
                            continue
                    else:
                        raise ValueError('Triage turn timed out after five minutes. Check Configure and retry.')
                finally:
                    if process is not None:
                        kill_tree(process)
                        process.wait()
            if os.path.getsize(self.log_path) > MAX_REPLY:
                raise ValueError('Triage reply exceeds 1 MiB; discarded.')
            reply, error = extract_reply_from_log(self.log_path)
            if error:
                raise ValueError('Triage runner reported an error: %s' % error)
            if code:
                raise ValueError('Triage runner exited with status %s. Log: %s' % (code, self.log_path))
            # An empty reply is not necessarily nothing: an execute-mode turn
            # can still have made a real edit the guard's own diff will show,
            # and this class has no notion of mode to tell those apart. Let
            # it through as an ordinary (possibly empty) reply and leave that
            # judgment to the caller, which knows what turn this was.
            self.events.put(('reply', reply))
        except (OSError, ValueError) as exc:
            self.events.put(('error', str(exc)))

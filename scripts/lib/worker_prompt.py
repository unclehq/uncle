#!/usr/bin/env python3
"""Lay a panel worker's prompt out so that workers share a prefix.

A vLLM server reuses cached prefill only for the leading tokens two requests have in
common.  Each worker's prompt used to be: shared instructions, then its lens, then a shared
contract, then its delivery path -- it diverged a few hundred tokens in, and the plan and
review it needed arrived later as tool results, which no prefix could cover.

The layout here is: shared instructions, the shared input documents (embedded, compact,
byte-stable), the shared contract, and only then everything that differs per worker (its
lens, its delivery path).  Workers 2..n of a panel then prefill only their own tail.

usage: worker_prompt.py [--contract implementation] PROMPT_FILE OUT_FILE [INPUT ...]   (.json, .md or .tsv)

Inputs come from the "Read only ..." sentences of the prompt's own "## Canonical inputs
(binding)" section when it has one, else from the arguments.  The lens is whichever
"## Assigned ..." heading comes first (review lens, audit lens, checklist lens, acceptance-gate
row).  Exit status 3 means "leave the prompt as it was": no lens heading,
no usable input, an input missing, or the embedded documents too large to be worth sending.
"""
import json
import re
import sys
from pathlib import Path

LENS = re.compile(r'\n## Assigned [^\n]*')
# A sentence ends at a period followed by space or the end; the paths inside it contain dots.
READ_SENTENCE = re.compile(r'(?:Read only|Do not inspect any rendered|Do not enumerate)(?:[^.]|\.(?!\s|$))*\.(?=\s|$)\s*')
INPUTS = '## Canonical inputs (binding)'
LIMIT_BYTES = 160 * 1024
# What the embedded documents mean to the worker.  `packet` workers are read-only specialists that
# return one JSON packet; `implementation` workers write code and may read any project file.
CONTRACTS = {'implementation': '''## Shared inputs are embedded

The requirements, the requirements interpretation, the approved updated plan and the preflight report
(when one exists) are embedded above: they are the files this prompt's first instruction asks you to
read. Do not read them again; go straight to your assigned step. Read any other project file your
step needs.
'''}
CONTRACT = '''## Compact worker contract (binding)

The input documents are embedded above. Do not read them again, and do not enumerate
`.uncle/workflow/documents/`, inspect the repository, or make exploratory tool calls.
Do not read rendered Markdown approvals, worker directories, output rules, or gates.
Return exactly the one JSON worker packet requested by the prompt, with no
analysis, Markdown fence, or duplicate draft. The parent stage collates and
validates all evidence, dispositions, and final documents.
'''


def split_prompt(text):
    """(shared head, shared remainder of the inputs section, per-worker tail, named paths) or None.

    Only the sentences that tell the worker to go and read files are dropped from the inputs
    section -- the documents are embedded now.  Whatever else it says (the manual-checklist
    section also carries the no-Git-history rules) stays, as shared text after the documents.
    """
    section = re.search(r'\n' + re.escape(INPUTS) + r'(.*?)(?=\n## |\Z)', text, re.S)
    named, kept = [], ''
    if section:
        body = section.group(1)
        named = re.findall(r'`([^`]+\.(?:json|md|tsv))`', ' '.join(READ_SENTENCE.findall(body)))
        rest = READ_SENTENCE.sub('', body).strip()
        kept = ('## Input notes\n\n' + rest) if rest else ''
        text = text[:section.start()] + '\n' + text[section.end():]
    match = LENS.search(text)
    if not match:
        return None
    return text[:match.start()], kept, text[match.start() + 1:].strip('\n'), named


def render(path):
    """One embedded input.  JSON is compacted and key-sorted (stable bytes); text is kept as written."""
    raw = Path(path).read_text(encoding='utf-8')
    if path.endswith('.json'):
        return json.dumps(json.loads(raw), sort_keys=True, separators=(',', ':'), ensure_ascii=False), 'json'
    return raw.rstrip('\n'), 'text'


SUPERSEDED = (('PROJECT_PLAN.json', 'UPDATED_PROJECT_PLAN.json'), ('PROJECT_PLAN.md', 'UPDATED_PROJECT_PLAN.md'))


def drop_superseded(paths):
    """(the inputs to embed, the ones left out): the approved updated plan is the original plan with the review's dispositions
    applied, so a worker that is handed both gets only the updated one. Carrying both was most of what pushed a small
    application's checklist workers over LIMIT_BYTES, which left them reading the same files turn by turn."""
    dropped = []
    for old, new in SUPERSEDED:
        for path in paths:
            if path.endswith('/' + new) or path == new:
                original = path[:-len(new)] + old
                if original in paths and original not in dropped:
                    dropped.append(original)
    return [path for path in paths if path not in dropped], dropped


def embed(paths):
    parts, total = [], 0
    for path in paths:
        try:
            body, language = render(path)
        except (OSError, ValueError):
            return None
        total += len(body.encode('utf-8'))
        fence = '```' if '```' not in body else '~~~~'
        parts.append('### `%s`\n%s%s\n%s\n%s' % (path, fence, language, body, fence))
    return None if total > LIMIT_BYTES else '\n\n'.join(parts)


def main(argv):
    contract = CONTRACT
    usage = 'usage: worker_prompt.py [--contract implementation] PROMPT_FILE OUT_FILE [INPUT ...]   (.json, .md or .tsv)'
    if argv[:1] == ['--contract']:
        if len(argv) < 3 or argv[1] not in CONTRACTS:
            raise SystemExit(usage)
        contract, argv = CONTRACTS[argv[1]], argv[2:]
    if len(argv) < 2:
        raise SystemExit(usage)
    text = Path(argv[0]).read_text(encoding='utf-8')
    split = split_prompt(text)
    if split is None:
        return 3
    head, kept, tail, named = split
    paths = named or list(argv[2:])
    if not paths:
        return 3
    paths, superseded = drop_superseded(paths)
    if superseded:
        kept = (kept + '\n\n' if kept else '## Input notes\n\n') + (
            '%s is superseded by the updated plan embedded above: it is not embedded and you must not read it.'
            % ', '.join('`%s`' % path for path in superseded))
    embedded = embed(paths)
    if embedded is None:
        return 3
    pieces = [head.rstrip('\n'), '## Shared inputs (read-only, embedded)\n\n' + embedded, contract.rstrip('\n')]
    if kept:
        pieces.append(kept)
    pieces.append(tail)
    Path(argv[1]).write_text('\n\n'.join(pieces) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

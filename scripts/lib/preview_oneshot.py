#!/usr/bin/env python3
"""The preview page in one model call: no tool turns at all.

The tool-based preview makes several round trips -- read the brief, write the file, say it is done --
and each is a full API call over a prompt of tens of thousands of cached tokens.  Everything the model
needs fits in the prompt, and everything it produces is one HTML document, so the prompt embeds the
brief, the interpretation and (when it exists) the plan, and the model answers with the page as plain
text.  The driver pulls the document out of the reply and publishes it.  One call; nothing to read or
write by tool.

If the reply holds no usable document, the caller falls back to the tool-based preview.

usage:
  preview_oneshot.py prompt PROJECT_ROOT              (the prompt on stdout)
  preview_oneshot.py extract STREAM_LOG OUTPUT_HTML   (exit 0 if a page was written)
"""
import json
from pathlib import Path
import re
import sys

LIMIT = 9000        # characters of each input; a preview needs the look, not every assumption

BRIEFS = ('REQUIREMENTS.md', '.uncle/docs/REQUIREMENTS.md')
INTERPRETATION = '.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json'
PLAN = '.uncle/workflow/documents/PROJECT_PLAN.json'

RULES = '''You are building a throwaway first-look preview of the application described below.

Reply with exactly one complete HTML document, starting with `<!doctype html>`, and nothing else: no
explanation, no Markdown fence, no comment before or after it. Do not call any tool; everything you need
is below. A later stage builds the real application and rewrites this page, so this is only a look at the
main screen, its theme and the primary interaction.

- One file: inline CSS and a little inline JavaScript, about 150 lines at most, written compactly (short
  names, no comments, no padding). Make the main interaction work; skip edge cases and error handling.
- No bundler, no `npm`, no CDN `<script>` or font links.
- Use plain HTML, CSS and vanilla JavaScript unless the brief or the plan calls for React. For React, load
  exactly these local copies, in this order, and write the components as JSX in one inline
  `<script type="text/babel">` (`React` and `ReactDOM` are globals; mount with
  `ReactDOM.createRoot(document.getElementById('root')).render(...)`):

  <script src=".uncle/vendor/react.production.min.js"></script>
  <script src=".uncle/vendor/react-dom.production.min.js"></script>
  <script src=".uncle/vendor/babel.min.js"></script>

- Style values in the interpretation (colors, fonts, layout) are binding: use them exactly.
'''


def read(root, names):
    for name in names:
        try:
            text = (Path(root) / name).read_text(encoding='utf-8')
        except OSError:
            continue
        if text.strip():
            return text.strip()
    return ''


def clip(text):
    if len(text) <= LIMIT:
        return text
    return text[:LIMIT] + '\n... (truncated)'


def build_prompt(root):
    sections = [RULES]
    for heading, names in (('Brief', BRIEFS), ('Requirements interpretation', (INTERPRETATION,)),
                           ('Plan (not yet reviewed; may change)', (PLAN,))):
        text = read(root, names)
        if text:
            sections.append('## %s\n\n%s\n' % (heading, clip(text)))
    return '\n'.join(sections)


def reply_text(log):
    """The model's final answer from a stream-json log: the result event, else the assistant text."""
    result, texts = '', []
    try:
        lines = Path(log).read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return ''
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'result' and isinstance(event.get('result'), str) and event['result'].strip():
            result = event['result']
        message = event.get('message')
        if event.get('type') == 'assistant' and isinstance(message, dict) and isinstance(message.get('content'), list):
            for block in message['content']:
                if isinstance(block, dict) and block.get('type') == 'text' and block.get('text'):
                    texts.append(block['text'])
    return result or '\n'.join(texts)


def document(text):
    """The HTML document inside a reply, tolerating a Markdown fence or a sentence around it."""
    fenced = re.search(r'```(?:html)?\s*\n(.*?)```', text, re.S | re.I)
    if fenced and re.search(r'<html|<!doctype', fenced.group(1), re.I):
        text = fenced.group(1)
    start = re.search(r'<!doctype html|<html', text, re.I)
    if not start:
        return ''
    end = text.lower().rfind('</html>')
    if end < start.start():
        return ''
    return text[start.start():end + len('</html>')].strip() + '\n'


def extract(log, output):
    page = document(reply_text(log))
    # A page with no markup to show or no body is not a preview.
    if len(page) < 200 or not re.search(r'<body', page, re.I):
        return 1
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tmp')
    temporary.write_text(page, encoding='utf-8')
    temporary.replace(target)
    return 0


def main(argv):
    if argv[:1] == ['prompt'] and len(argv) == 2:
        sys.stdout.write(build_prompt(argv[1]))
        return 0
    if argv[:1] == ['extract'] and len(argv) == 3:
        return extract(argv[1], argv[2])
    raise SystemExit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

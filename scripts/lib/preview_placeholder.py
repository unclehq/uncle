#!/usr/bin/env python3
"""An instant first look for the preview tab, with no model in the loop.

A model-written page takes 15-40 seconds even on a fast model, and most of that is generation that no
prompt trims reliably (measured on haiku: 3k to 9k output tokens for the same 4 KB page).  The tab does
not have to wait for it.  The brief and the interpretation already hold the title, a summary, and often
the palette, so the driver paints a themed page from them in well under a second, and the model's page
replaces it when it lands (the tab reloads on every change).

Only written when there is no page yet, atomically, and never fails a stage.

usage: preview_placeholder.py PROJECT_ROOT
"""
import html
import json
import os
from pathlib import Path
import re
import sys

BRIEFS = ('REQUIREMENTS.md', '.uncle/docs/REQUIREMENTS.md')
INTERPRETATION = '.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json'
HEX = re.compile(r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b')


def read(root, names):
    for name in names:
        try:
            text = (Path(root) / name).read_text(encoding='utf-8')
        except OSError:
            continue
        if text.strip():
            return text
    return ''


def brief_parts(text):
    """(title, [summary lines]) from a Markdown brief."""
    title, lines = '', []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(('```', '|', '---')):
            continue
        heading = re.match(r'^#{1,3}\s+(.*)$', line)
        if heading:
            if not title:
                title = heading.group(1)
            continue
        line = re.sub(r'^[-*+]\s+|^\d+[.)]\s+', '', line)
        line = re.sub(r'[*_`]', '', line)
        if len(lines) < 5:
            lines.append(line[:150])
    generic = {'application brief', 'project brief', 'brief', 'requirements', 'project requirements', 'summary', 'overview'}
    if (not title or title.strip().lower() in generic) and lines:
        title = lines.pop(0)
    return title[:80] or 'Preview', lines


def normalise(color):
    color = color.lower()
    if len(color) == 4:
        color = '#' + ''.join(c * 2 for c in color[1:])
    return color


def palette(root, brief):
    colors = []
    for text in (read(root, (INTERPRETATION,)), brief):
        for found in HEX.findall(text):
            value = normalise(found)
            if value not in colors:
                colors.append(value)
    return colors[:6]


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def page(title, lines, colors):
    base = colors[0] if colors else '#20232a'
    second = colors[1] if len(colors) > 1 else base
    ink = '#1b1b1b' if luminance(base) > 0.4 else '#fafafa'
    card = 'rgba(255,255,255,.88)' if ink == '#1b1b1b' else 'rgba(0,0,0,.32)'
    swatches = ''.join('<i style="background:%s"></i>' % c for c in colors)
    items = ''.join('<li>%s</li>' % html.escape(line) for line in lines)
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>%s</title>\n<style>\n'
            '*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;'
            'font:16px/1.5 system-ui,sans-serif;color:%s;background:linear-gradient(135deg,%s,%s)}\n'
            'main{width:min(92vw,520px);padding:28px;border-radius:20px;background:%s;box-shadow:0 10px 40px rgba(0,0,0,.25)}\n'
            'h1{margin:0 0 8px;font-size:28px}ul{margin:12px 0;padding-left:20px}'
            '.sw{display:flex;gap:8px;margin:16px 0}.sw i{flex:1;height:28px;border-radius:8px;border:1px solid rgba(0,0,0,.15)}\n'
            '.note{font-size:13px;opacity:.75;display:flex;align-items:center;gap:8px}'
            '.dot{width:10px;height:10px;border-radius:50%%;background:%s;animation:p 1s infinite alternate}'
            '@keyframes p{to{opacity:.25}}\n</style></head>\n<body><main><h1>%s</h1><ul>%s</ul>'
            '<div class="sw">%s</div><div class="note"><span class="dot"></span>Building the first look&hellip; '
            'this page updates by itself.</div></main></body></html>\n'
            % (html.escape(title), ink, base, second, card, second if second != base else ink,
               html.escape(title), items, swatches))


def write_if_absent(root):
    target = Path(root) / 'index.html'
    if target.exists():
        return False
    brief = read(root, BRIEFS)
    title, lines = brief_parts(brief)
    text = page(title, lines, palette(root, brief))
    temporary = target.with_name('index.html.tmp%d' % os.getpid())
    temporary.write_text(text, encoding='utf-8')
    if target.exists():
        temporary.unlink()
        return False
    os.replace(temporary, target)
    return True


def main(argv):
    try:
        if len(argv) == 1:
            write_if_absent(argv[0])
    except Exception:    # a convenience, never a reason to stop
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

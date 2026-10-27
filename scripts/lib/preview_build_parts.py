#!/usr/bin/env python3
"""The preview page written in parts by parallel workers, then stitched into one index.html.

A single model writing a page spends most of its time decoding one stream.  The page splits cleanly
once the names are fixed: a short contract (which elements and ids exist, what the state and the
behavior are, the theme) comes first, then the markup, the styles and the script are written beside each
other and the driver assembles them.  The delivered page is still exactly one `index.html` with inline
styles and script -- no extra files to own, clean up or lose -- so everything downstream (the live-reload
server, the implementation that later rewrites it in place) is unchanged.

    phase 1  contract                    framework, title, elements, state, behavior, theme
    phase 2  markup  styles  script      the body, the CSS, the JavaScript (no markup for React)

`assemble` repairs the one slip models make here -- wrapping a part in the tag it is about to be put
inside -- and refuses anything else, so the driver can fall back to the single-pass preview.

usage:
  preview_build_parts.py names DIRECTORY PHASE   (the workers of phase 1 or 2; phase 2 depends on the contract)
  preview_build_parts.py prompt NAME DIRECTORY BASE_PROMPT OUTPUT_PROMPT
  preview_build_parts.py assemble DIRECTORY OUTPUT
  preview_build_parts.py watch DIRECTORY OUTPUT STOPFILE   (show the page as parts arrive until STOPFILE exists)
"""
import os
import re
import sys
import time
from pathlib import Path

PARTS = {'contract': 'contract.md', 'markup': 'markup.html', 'styles': 'styles.css', 'script': 'script.js'}
VENDOR = ('react.production.min.js', 'react-dom.production.min.js', 'babel.min.js')

SPECIFIC = {
    'contract': (
        'You are first; the markup, styles and script workers start the moment you finish and read only your file, '
        'so it must be short (about 25 lines) and exact. Begin with two lines, `framework: vanilla` or '
        '`framework: react` (react only when the brief or the plan calls for it) and `title: <the page title>`. '
        'Then three short sections: `## Elements` (every element the script touches or the styles target, as '
        '`#id` or `.class` with what it is), `## Behavior` (state, and what each interaction does), `## Theme` '
        '(the exact colors, fonts and layout the styles must use). For react, the elements are the components and '
        'their class names; the root is `#root`. Do not write any HTML, CSS or JavaScript.'),
    'markup': (
        'Write the contents of `<body>` only: no `<html>`, `<head>`, `<body>`, `<style>` or `<script>`. Use exactly '
        'the ids and classes the contract lists. Static structure and visible text only.'),
    'styles': (
        'Write plain CSS only, no `<style>` tag. Style exactly the ids and classes the contract lists, with the theme '
        'values it names. Include the layout and the responsive behavior that makes it look intentional.'),
    'script': (
        'Write the JavaScript only, no `<script>` tag. It runs after the body exists. Use exactly the ids and classes '
        'the contract lists and implement the behavior it describes. For react, write the components as JSX; `React` '
        'and `ReactDOM` are globals and the page already has `<div id="root"></div>`: finish with '
        '`ReactDOM.createRoot(document.getElementById("root")).render(<App/>)`.'),
}


def framework(directory):
    """`react` or `vanilla`, from the contract's first lines; anything unreadable is vanilla."""
    try:
        text = (Path(directory) / PARTS['contract']).read_text(encoding='utf-8')
    except OSError:
        return 'vanilla'
    match = re.search(r'^\s*framework\s*:\s*(\w+)', text, re.I | re.M)
    return 'react' if match and match.group(1).lower() == 'react' else 'vanilla'


def title(directory):
    try:
        text = (Path(directory) / PARTS['contract']).read_text(encoding='utf-8')
    except OSError:
        return 'Preview'
    match = re.search(r'^\s*title\s*:\s*(.+)$', text, re.I | re.M)
    value = match.group(1).strip() if match else ''
    return re.sub(r'[<>&]', '', value)[:80] or 'Preview'


def phases(directory):
    second = ('styles', 'script') if framework(directory) == 'react' else ('markup', 'styles', 'script')
    return (('contract',), second)


def phase_names(directory, phase):
    """The workers of phase 1 or 2; phase 2 depends on what the contract chose."""
    return phases(directory)[phase - 1]


def contract(name, directory):
    target = '%s/%s' % (directory, PARTS[name])
    lines = ['', '## Part mode (binding; overrides the output instructions above)', '',
             'This page is written by several workers at once and the driver assembles it into `index.html`. Do not write '
             '`index.html` or any other file. Write only `%s`, in a single Write call, then stop.' % target, '']
    if name != 'contract':
        lines += ['Read `%s/%s` first. It is binding: use its element names, state and theme exactly.' % (directory, PARTS['contract']), '']
    lines += [SPECIFIC[name], '']
    return '\n'.join(lines)


def build_prompt(name, directory, base):
    return base.rstrip('\n') + '\n' + contract(name, directory)


def unfence(text):
    """Drop a surrounding Markdown fence a model put around a part."""
    match = re.match(r'^\s*```[\w-]*\n(.*?)\n```\s*$', text, re.S)
    return match.group(1) if match else text


def body_of(markup):
    match = re.search(r'<body[^>]*>(.*)</body>', markup, re.S | re.I)
    return match.group(1) if match else markup


def strip_tag(text, tag):
    match = re.match(r'^\s*<%s[^>]*>(.*)</%s>\s*$' % (tag, tag), text, re.S | re.I)
    return match.group(1) if match else text


def read(directory, name):
    path = Path(directory) / PARTS[name]
    try:
        text = unfence(path.read_text(encoding='utf-8'))
    except OSError:
        raise ValueError('%s: the part was not written' % path.name)
    if not text.strip():
        raise ValueError('%s: the part is empty' % path.name)
    return text.strip()


BUILDING = '<main style="font:16px system-ui;padding:2rem;color:#666">Building your preview&hellip;</main>'


def assemble(directory, partial=False):
    """The page.  `partial` shows whatever parts exist, with a placeholder for the rest, so the tab can open
    at once and fill in; the strict form refuses a missing or empty part."""
    kind = framework(directory)

    def part(name):
        try:
            return read(directory, name)
        except ValueError:
            if not partial:
                raise
            return ''

    css = strip_tag(part('styles'), 'style')
    js = strip_tag(part('script'), 'script')
    if kind == 'react':
        body = '<div id="root">%s</div>' % (BUILDING if partial and not js else '')
    else:
        body = body_of(part('markup'))
        if not body.strip():
            if not partial:
                raise ValueError('markup.html: the part is empty')
            body = BUILDING
    js = js.replace('</script', '<\\/script')
    scripts = ''
    if kind == 'react' and js:
        scripts = ''.join('<script src=".uncle/vendor/%s"></script>\n' % name for name in VENDOR)
    script_open = '<script type="text/babel">' if kind == 'react' else '<script>'
    script = '%s\n%s\n</script>\n' % (script_open, js) if js else ''
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>%s</title>\n'
            '<style>\n%s\n</style>\n</head>\n<body>\n%s\n%s%s</body>\n</html>\n'
            % (title(directory), css, body, scripts, script))


def write_atomic(target, text):
    target = Path(target)
    temporary = target.with_name(target.name + '.tmp%d' % os.getpid())
    temporary.write_text(text, encoding='utf-8')
    os.replace(temporary, target)


def watch(directory, target, stop, interval=0.4):
    """Write the partial page now and again whenever it changes, until the stop file appears."""
    last = None
    parent = os.getppid()
    while True:
        if os.getppid() != parent:      # the driver went away: never outlive the run
            return
        page = assemble(directory, partial=True)
        if page != last:
            try:
                write_atomic(target, page)
                last = page
            except OSError:
                pass
        if Path(stop).exists():
            return
        time.sleep(interval)


def main(argv):
    try:
        if argv[:1] == ['names'] and len(argv) == 3 and argv[2] in ('1', '2'):
            print(' '.join(phase_names(argv[1], int(argv[2]))))
        elif argv[:1] == ['prompt'] and len(argv) == 5:
            _, name, directory, base, output = argv
            Path(output).write_text(build_prompt(name, directory, Path(base).read_text(encoding='utf-8')), encoding='utf-8')
        elif argv[:1] == ['assemble'] and len(argv) == 3:
            write_atomic(argv[2], assemble(argv[1]))
        elif argv[:1] == ['watch'] and len(argv) == 4:
            watch(argv[1], argv[2], argv[3])
        else:
            raise SystemExit(__doc__)
    except ValueError as error:
        print('preview build parts: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

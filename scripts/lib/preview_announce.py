#!/usr/bin/env python3
"""Say where the preview is, in every run: the same line for the screen, `--noui` and a hosted run.

    preview_announce.py watch <state-dir> <driver-pid>

Polls the driver's preview records (preview-server.url, preview-vite.url, and the pids that say they are alive) and
prints one line per new address, flushed, so the driver's own output carries it. Stops when the driver is gone.

A link is `Local preview:` only when the run is not hosted and the address is loopback. Anything else is
`Preview (not local):`, so a reader never takes a host-bound address for one on their own machine. A Vite
dev server is named as such, because it replaces the static page's address."""
import os
import re
import sys
import time
from urllib.parse import urlparse

LOOPBACK = ('127.0.0.1', 'localhost', '::1')
URL = re.compile(r'^https?://[A-Za-z0-9.\-\[\]:]+(/[^\s]*)?$')
POLL_SECONDS = 0.5


def hosted(env=None):
    return (os.environ if env is None else env).get('UNCLE_HOSTED') == '1'


def is_local(url, is_hosted=False):
    if is_hosted:
        return False
    try:
        return urlparse(url).hostname in LOOPBACK
    except ValueError:
        return False


def line(url, vite=False, is_hosted=False):
    """The announcement for one address."""
    if is_local(url, is_hosted):
        return 'Local preview (Vite): %s' % url if vite else 'Local preview: %s' % url
    return 'Preview (not local, Vite): %s' % url if vite else 'Preview (not local): %s' % url


def _read(path):
    try:
        with open(path, encoding='utf-8') as handle:
            return handle.read(2048).strip()
    except OSError:
        return ''


def _alive(path):
    try:
        os.kill(int(_read(path)), 0)
    except (ValueError, OSError):
        return False
    return True


def scan(state_dir, seen, is_hosted=False):
    """New announcement lines; `seen` is updated so each address is said once."""
    lines = []
    for name, vite in (('preview-server', False), ('preview-vite', True)):
        if not _alive(os.path.join(state_dir, name + '.pid')):
            continue
        url = _read(os.path.join(state_dir, name + '.url'))
        if not URL.match(url):
            continue
        # The static server's record is rewritten to the Vite address on handoff: that is the Vite line, said once.
        vite = vite or (name == 'preview-server' and (_alive(os.path.join(state_dir, 'preview-vite.pid'))
                                                      and url == _read(os.path.join(state_dir, 'preview-vite.url'))))
        if url in seen:
            continue
        seen.add(url)
        text = line(url, vite, is_hosted)
        # Hosted: the address above is loopback inside the container. Also say what the server was asked to bind and bound.
        bind = _read(os.path.join(state_dir, 'preview-server.bind')) if is_hosted else ''
        lines.append(text + (' [%s]' % bind if bind else ''))
    return lines


def watch(state_dir, driver_pid, is_hosted=False, out=None, sleep=time.sleep):
    out = out or sys.stdout
    seen = set()
    while True:
        for text in scan(state_dir, seen, is_hosted):
            out.write(text + '\n')
            out.flush()
        try:
            os.kill(driver_pid, 0)
        except OSError:
            return 0
        sleep(POLL_SECONDS)


def main(argv):
    if len(argv) == 3 and argv[0] == 'watch' and argv[2].isdigit():
        return watch(argv[1], int(argv[2]), hosted())
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

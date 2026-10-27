#!/usr/bin/env python3
"""React and Babel for the preview build, fetched by the driver while the model writes the page.

The preview's cost is the text the model writes, and a React page written by hand drags in a CDN
link the browser then waits on.  The driver already knows which libraries a React preview needs, so
it downloads them beside the model, in parallel and once per machine (a cache under
~/.cache/uncle/vendor), and puts copies in `.uncle/vendor/` of the project: served by the preview
server, ignored by every ownership and scope check, and never part of the delivered project.  The
model only has to write `<script src=".uncle/vendor/...">`.

If a download did not finish or failed (offline, a proxy), `rewrite` points those script tags at the
CDN instead, so the page still loads.  Nothing here ever fails a stage.

usage:
  preview_vendor.py fetch ROOT      download (or reuse) the libraries and copy them into ROOT/.uncle/vendor
  preview_vendor.py rewrite ROOT    in ROOT/index.html, send any missing local library to the CDN
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.request import Request, urlopen

# name -> CDN URL.  Pinned: a preview must not change under someone between runs.
LIBRARIES = {
    'react.production.min.js': 'https://unpkg.com/react@18.3.1/umd/react.production.min.js',
    'react-dom.production.min.js': 'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js',
    'babel.min.js': 'https://unpkg.com/@babel/standalone@7.24.7/babel.min.js',
}
LOCAL_PREFIX = '.uncle/vendor/'
TIMEOUT = 30


def cache_dir():
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')
    return Path(base) / 'uncle' / 'vendor'


def download(url, target):
    """Atomic: a half-written file is never visible under its final name."""
    request = Request(url, headers={'User-Agent': 'uncle-preview'})
    with urlopen(request, timeout=TIMEOUT) as response:
        data = response.read()
    if not data:
        raise OSError('empty response')
    handle, temporary = tempfile.mkstemp(dir=str(target.parent), prefix=target.name + '.')
    try:
        with os.fdopen(handle, 'wb') as output:
            output.write(data)
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def fetch(root, libraries=None, cache=None):
    """Make every library available under root/.uncle/vendor; return the names that are."""
    libraries = libraries or LIBRARIES
    cache = Path(cache) if cache else cache_dir()
    destination = Path(root) / '.uncle' / 'vendor'
    try:
        cache.mkdir(parents=True, exist_ok=True)
        destination.mkdir(parents=True, exist_ok=True)
    except OSError:
        return []

    def one(item):
        name, url = item
        cached = cache / name
        try:
            if not (cached.is_file() and cached.stat().st_size):
                download(url, cached)
            shutil.copyfile(cached, destination / name)
            return name
        except (OSError, ValueError):
            return None

    with ThreadPoolExecutor(max_workers=len(libraries)) as pool:
        return [name for name in pool.map(one, libraries.items()) if name]


def rewrite(root, libraries=None):
    """Send each `.uncle/vendor/<name>` reference whose file is missing to the CDN; return the count."""
    libraries = libraries or LIBRARIES
    page = Path(root) / 'index.html'
    try:
        text = page.read_text(encoding='utf-8')
    except OSError:
        return 0
    count = 0
    for name, url in libraries.items():
        local = LOCAL_PREFIX + name
        present = (Path(root) / local).is_file() and (Path(root) / local).stat().st_size > 0
        if local in text and not present:
            text = text.replace(local, url)
            count += 1
    if count:
        try:
            page.write_text(text, encoding='utf-8')
        except OSError:
            return 0
    return count


def main(argv):
    if len(argv) != 2 or argv[0] not in ('fetch', 'rewrite'):
        raise SystemExit(__doc__)
    try:
        if argv[0] == 'fetch':
            names = fetch(argv[1])
            print('Preview libraries ready: %s.' % (', '.join(names) or 'none (the page will use the CDN)'))
        else:
            count = rewrite(argv[1])
            if count:
                print('Preview page: %d missing local librar%s pointed at the CDN.' % (count, 'y' if count == 1 else 'ies'))
    except Exception as error:  # a convenience, never a reason to stop
        print('Preview libraries: skipped (%s).' % error)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

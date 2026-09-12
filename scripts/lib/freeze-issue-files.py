#!/usr/bin/env python3
"""Freeze files attached to an issue into reference/, with provenance.

A GitHub issue carries its attachments as remote URLs: screenshots, but also
PDFs, logs, CSVs and archives. No workflow stage can fetch them -- stage
network access is off by default, and a user-attachments asset on a private
repo needs an authenticated request. So the brief arrives describing evidence
nothing downstream can open.

This runs at seed time, where `gh` is already authenticated, and rewrites each
reference to the local path it wrote.

What it fetches, and what it leaves alone: every embedded image, and every link
whose host is a GitHub attachment store. A link to a web page is a citation,
not an attachment, and downloading it would turn a brief into a crawl.

Type comes from the file's own magic bytes, because a user-attachments URL is
a bare UUID with no extension. Image geometry is recorded when the header
gives it, so a later stage can state capture scale without guessing. A format
we cannot identify is still frozen and recorded -- unknown is not a reason to
drop evidence.

Reads the body on stdin, writes the rewritten body to stdout. Progress and
failures go to stderr so the rewritten body stays clean.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

EMBED = (re.compile(r'!\[[^\]]*\]\(\s*(?P<url>[^)\s]+)[^)]*\)'),
         re.compile(r'<img\b[^>]*?\bsrc\s*=\s*["\'](?P<url>[^"\']+)["\'][^>]*>', re.I))
LINK = (re.compile(r'(?<!!)\[[^\]]*\]\(\s*(?P<url>[^)\s]+)[^)]*\)'),
        re.compile(r'<a\b[^>]*?\bhref\s*=\s*["\'](?P<url>[^"\']+)["\'][^>]*>', re.I))

# Where GitHub actually stores an uploaded file. A link anywhere else is a
# citation the author chose to make, not something they attached.
ATTACHMENT_HOSTS = ('github.com/user-attachments/',
                    'objects.githubusercontent.com/',
                    'raw.githubusercontent.com/',
                    'user-images.githubusercontent.com/')
ATTACHMENT_PATH = re.compile(r'https://github\.com/[^/]+/[^/]+/files/', re.I)

MAGIC = ((b'\x89PNG\r\n\x1a\n', '.png'), (b'\xff\xd8\xff', '.jpg'),
         (b'GIF87a', '.gif'), (b'GIF89a', '.gif'), (b'%PDF-', '.pdf'),
         (b'PK\x03\x04', '.zip'), (b'\x1f\x8b', '.gz'), (b'BM', '.bmp'),
         (b'\x00\x00\x01\x00', '.ico'), (b'ID3', '.mp3'), (b'OggS', '.ogg'),
         (b'%!PS', '.ps'), (b'{\\rtf', '.rtf'))
KNOWN = {suffix for _, suffix in MAGIC} | {
    '.webp', '.svg', '.txt', '.log', '.csv', '.tsv', '.json', '.yaml', '.yml',
    '.md', '.xml', '.html', '.mp4', '.mov', '.webm', '.tar', '.patch', '.diff'}


def geometry(data):
    """Width and height from the file header, or None when unmeasurable."""
    try:
        if data.startswith(b'\x89PNG\r\n\x1a\n') and data[12:16] == b'IHDR':
            return (int.from_bytes(data[16:20], 'big'),
                    int.from_bytes(data[20:24], 'big'))
        if data.startswith(b'\xff\xd8'):
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker, length = data[i + 1], int.from_bytes(data[i + 2:i + 4], 'big')
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    return (int.from_bytes(data[i + 7:i + 9], 'big'),
                            int.from_bytes(data[i + 5:i + 7], 'big'))
                i += 2 + length
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return (int.from_bytes(data[6:8], 'little'),
                    int.from_bytes(data[8:10], 'little'))
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP' and data[12:16] == b'VP8 ':
            return (int.from_bytes(data[26:28], 'little') & 0x3FFF,
                    int.from_bytes(data[28:30], 'little') & 0x3FFF)
    except (IndexError, ValueError):
        pass
    return None


def extension(data, url):
    for magic, suffix in MAGIC:
        if data.startswith(magic):
            return suffix
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return '.webp'
    head = data[:512].lstrip()
    if head.startswith(b'<svg') or (head.startswith(b'<?xml') and b'<svg' in data[:2048]):
        return '.svg'
    suffix = Path(url.split('?', 1)[0].split('#', 1)[0]).suffix.lower()
    if suffix in KNOWN:
        return suffix
    try:
        data.decode('utf-8')
        return '.txt'
    except UnicodeDecodeError:
        return '.bin'


def is_attachment(url):
    lowered = url.lower()
    return (any(host in lowered for host in ATTACHMENT_HOSTS)
            or bool(ATTACHMENT_PATH.match(url)))


def fetch(url):
    """Authenticated first: a private asset is a 404 to an anonymous request."""
    if 'github.com/' in url or 'githubusercontent.com/' in url:
        try:
            result = subprocess.run(['gh', 'api', '--method', 'GET', url],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except (OSError, subprocess.SubprocessError):
            pass
    request = urllib.request.Request(url, headers={'User-Agent': 'uncle'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def freeze(body, root):
    directory = root / 'reference'
    records, seen = [], {}
    counter = {'n': 0}

    def substitute(match, embedded):
        url = match.group('url')
        if not url.lower().startswith(('http://', 'https://')):
            return match.group(0)                 # already local
        if url in seen:
            return match.group(0).replace(url, seen[url])
        if not embedded and not is_attachment(url):
            return match.group(0)                 # a citation, not an attachment
        try:
            data = fetch(url)
        except Exception as error:                # noqa: BLE001 - reported, never fatal
            print('  could not fetch %s: %s' % (url, error), file=sys.stderr)
            return match.group(0)
        counter['n'] += 1
        index = counter['n']
        suffix = extension(data, url)
        stem = Path(url.split('?', 1)[0].split('#', 1)[0]).stem
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,48}', stem or ''):
            stem = ''
        if index == 1 and suffix in ('.png', '.jpg'):
            name = 'source' + suffix           # the first screenshot, by convention
        elif stem:
            name = '%s%s' % (stem, suffix)
        else:
            name = 'attachment-%d%s' % (index, suffix)
        directory.mkdir(parents=True, exist_ok=True)
        while (directory / name).exists() and seen.get(url) != 'reference/' + name:
            name = 'attachment-%d-%s' % (index, name)
        (directory / name).write_bytes(data)
        size = geometry(data)
        records.append({'file': 'reference/' + name, 'sourceUrl': url,
                        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                        'geometry': {'width': size[0], 'height': size[1]} if size else None})
        seen[url] = 'reference/' + name
        print('  froze %s -> reference/%s (%d bytes%s)'
              % (url, name, len(data), ', %dx%d' % size if size else ''), file=sys.stderr)
        return match.group(0).replace(url, seen[url])

    for pattern in EMBED:
        body = pattern.sub(lambda m: substitute(m, True), body)
    for pattern in LINK:
        body = pattern.sub(lambda m: substitute(m, False), body)

    if records:
        provenance = directory / 'provenance.json'
        existing = []
        if provenance.exists():
            try:
                previous = json.loads(provenance.read_text())
                existing = previous if isinstance(previous, list) else [previous]
            except ValueError:
                existing = []
        known = {record['sourceUrl'] for record in records}
        merged = [record for record in existing
                  if isinstance(record, dict) and record.get('sourceUrl') not in known]
        provenance.write_text(json.dumps(merged + records, indent=2) + '\n')
    return body


if __name__ == '__main__':
    root = Path(os.environ.get('UNCLE_PROJECT_ROOT') or Path.cwd())
    sys.stdout.write(freeze(sys.stdin.read(), root))

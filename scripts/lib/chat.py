"""Memory-only chat input and exclusive workflow seed primitives.

Reference lookup and reads share a no-follow traversal rooted in the project.
Native transports must accept only sanitized text, never reference paths.
"""
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat

TRANSCRIPT_LIMIT = 1024 * 1024
REFERENCE_LIMIT = 256 * 1024
_REFERENCE = re.compile(r'@(?:"([^"\n]+)"|([^\s"@]+))')
_SECRET = re.compile(
    r'(?im)(\b[\w.-]*(?:secret|password|passwd|token|api[_-]?key|credential)[\w.-]*\s*[:=]\s*)[^\n]+')


def sanitize(text):
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|\Z)',
                  '[REDACTED PRIVATE KEY]', text, flags=re.S)
    text = re.sub(r'(?im)(authorization\s*:\s*)[^\n]+', r'\1[REDACTED]', text)
    text = _SECRET.sub(r'\1[REDACTED]', text)
    # Terminal controls must not be interpreted by the chat renderer.
    return ''.join(c for c in text if c in '\n\t' or (ord(c) >= 32 and ord(c) != 127))


class References:
    def __init__(self, root):
        self.root = Path(root)

    @staticmethod
    def parts(name):
        path = PurePosixPath(name)
        if (not name or path.is_absolute() or '\\' in name or
                any(p in ('', '.', '..') for p in name.split('/'))):
            raise ValueError('Reference must be inside the project')
        for part in path.parts:
            lower = part.lower()
            if (lower.startswith('.env') or lower in
                    ('.git', '.uncle', '.ssh', '.aws', '.codex', '.cline', '.kimi',
                     'credentials', 'credentials.json', 'auth.json', 'providers.json') or
                    lower.startswith(('id_rsa', 'id_ed25519', 'id_ecdsa')) or
                    lower.endswith(('.pem', '.key', '.p12', '.pfx', 'self-hosted-keys.json'))):
                raise ValueError('Excluded reference')
        return path.parts

    def open(self, name, flags=os.O_RDONLY, mode=0o600):
        parts = self.parts(name)
        parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=parent)
                os.close(parent)
                parent = child
            return os.open(parts[-1], flags | os.O_NOFOLLOW | os.O_NONBLOCK,
                           mode, dir_fd=parent)
        finally:
            os.close(parent)

    def _parent_reference(self, name):
        """Resolve paths explicitly supplied by the chat user."""
        if not getattr(self, 'allow_parent', False):
            return self, name
        if name.startswith('~/') or name == '~':
            return References(Path.home()), name[2:] if name.startswith('~/') else ''
        if name.startswith('/'):
            path = Path(name)
            if name.endswith('/'):
                return References(path.resolve()), ''
            return References(path.parent.resolve()), path.name
        if not name.startswith('../'):
            return self, name
        root = self.root.absolute()
        while name.startswith('../'):
            root = root.parent
            name = name[3:]
        return References(root), name

    def read(self, name):
        target, relative = self._parent_reference(name)
        if target is not self:
            return target.read(relative)
        try:
            with os.fdopen(self.open(name), 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o444:
                    raise ValueError('Reference is not a readable regular file')
                raw = stream.read(REFERENCE_LIMIT + 1)
            if len(raw) > REFERENCE_LIMIT:
                raise ValueError('Referenced text exceeds 256 KiB limit')
            if b'\0' in raw:
                raise ValueError('Binary reference')
            return raw.decode('utf-8')
        except (OSError, UnicodeError):
            raise ValueError('File not found or unsafe reference') from None

    def browse(self, prefix):
        """List every directory; apply attachment restrictions only to files."""
        if prefix == '~' and getattr(self, 'allow_parent', False):
            prefix = '~/'
        target, relative = self._parent_reference(prefix)
        if target is not self:
            leading = prefix[:len(prefix) - len(relative)] if relative else prefix
            return [leading + name for name in target.browse(relative)]
        directory, _, leaf = prefix.rpartition('/')
        parent = directory + '/' if '/' in prefix else ''
        folder = self.root
        if directory:
            if any(part in ('.', '..') for part in PurePosixPath(directory).parts):
                raise ValueError('Use leading ../ segments to browse parent directories')
            folder = folder / directory
        elif parent:
            raise ValueError('Reference must be inside the project')
        result = []
        for child in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            name = parent + child.name
            if not child.name.startswith(leaf):
                continue
            if child.is_dir():
                result.append(name + '/')
            elif not child.is_symlink() and self._allowed(name):
                try:
                    self.read(name)
                    result.append(name)
                except ValueError:
                    continue
        return result

    def suggestions(self, prefix):
        result = []
        for base, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = [d for d in dirs if self._allowed(Path(base, d).relative_to(self.root).as_posix())
                       and not Path(base, d).is_symlink()]
            for file in files:
                name = Path(base, file).relative_to(self.root).as_posix()
                if name.startswith(prefix):
                    try:
                        self.read(name)
                    except ValueError:
                        continue
                    result.append(name)
        return sorted(result)

    def _allowed(self, name):
        try:
            self.parts(name)
            return True
        except ValueError:
            return False

    def reference(self, name):
        self.read(name)
        if '"' in name or '\n' in name:
            raise ValueError('Unsupported reference name')
        return '@"' + name + '"' if any(c.isspace() for c in name) else '@' + name

    def expand(self, text):
        total = 0

        def replace(match):
            nonlocal total
            name = match.group(1) or match.group(2)
            body = self.read(name)
            total += len(body.encode('utf-8'))
            if total > REFERENCE_LIMIT:
                raise ValueError('Referenced text exceeds 256 KiB limit')
            return '\n[file ' + name + ']\n' + sanitize(body) + '\n'

        if len(text.encode('utf-8')) > TRANSCRIPT_LIMIT:
            raise ValueError('Transcript exceeds 1 MiB limit')
        return sanitize(_REFERENCE.sub(replace, text))


class Seed:
    def __init__(self, root, kind):
        if kind not in ('app', 'change'):
            raise ValueError('Choose app or change')
        self.refs = References(root)
        self.name = 'REQUIREMENTS.md' if kind == 'app' else 'CHANGE_REQUEST.md'
        self.identity = None

    @staticmethod
    def fingerprint(stream):
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Seed is not a regular file')
        return info.st_dev, info.st_ino, hashlib.sha256(stream.read()).hexdigest()

    def commit(self, preview):
        if self.identity is not None:
            raise ValueError('Seed already committed; verify before retrying launch')
        summary = re.search(r'^## Summary\s*\n(.*?)(?=^## |\Z)', preview, re.M | re.S)
        if not summary or not summary.group(1).strip():
            raise ValueError('Brief requires a nonempty Summary')
        data = sanitize(preview).encode('utf-8')
        if len(data) > TRANSCRIPT_LIMIT:
            raise ValueError('Brief exceeds 1 MiB limit')
        fd = self.refs.open(self.name, os.O_RDWR | os.O_CREAT | os.O_EXCL)
        with os.fdopen(fd, 'w+b') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            stream.seek(0)
            self.identity = self.fingerprint(stream)

    def verify(self):
        try:
            with os.fdopen(self.refs.open(self.name), 'rb') as stream:
                actual = self.fingerprint(stream)
        except OSError:
            raise ValueError('Committed seed was replaced; launch refused') from None
        if self.identity is None or actual != self.identity:
            raise ValueError('Committed seed changed; launch refused')


class Conversation:
    """Curses-owned draft state; display references without retaining file bodies."""
    fields = {
        'app': ('Summary', 'Problem', 'Scope', 'Non-goals', 'Functional requirements',
                'User-visible behavior', 'Domain rules and invariants', 'Data and state',
                'Interfaces', 'Constraints', 'Failure behavior', 'Verification',
                'Definition of done', 'Open questions'),
        'change': ('Change Type', 'Summary', 'Motivation', 'Observed Current Behavior',
                   'Desired Behavior', 'Reproduction', 'Constraints', 'Known Relevant Files',
                   'Out of Scope', 'Success Criteria'),
    }

    def __init__(self, root):
        self.refs = References(root)
        directory = Path(root).absolute()
        self.kind = 'change' if any((p / '.git').exists()
                                    for p in (directory, *directory.parents)) else 'app'
        self.messages = []
        self.preview = ''
        self.seed = None

    def send(self, message):
        if not message.strip():
            raise ValueError('Enter a message first')
        candidate = '\n'.join(self.messages + [message])
        self.refs.expand(candidate)  # Validate the complete request before acceptance.
        clean = sanitize(message)
        if len('\n'.join(self.messages + [clean]).encode('utf-8')) > TRANSCRIPT_LIMIT:
            raise ValueError('Transcript exceeds 1 MiB limit')
        self.messages.append(clean)

    def payload(self):
        if not self.messages:
            raise ValueError('Enter a message first')
        return self.refs.expand('\n'.join(self.messages))

    def commit(self):
        if self.seed is None:
            if self.kind not in self.fields:
                raise ValueError('Choose app or change')
            for field in self.fields[self.kind]:
                section = re.search(r'^## ' + re.escape(field) +
                                    r'[ \t]*\n(.*?)(?=^## |\Z)', self.preview, re.M | re.S)
                if not section or not section.group(1).strip():
                    raise ValueError('Brief requires a nonempty ' + field)
            seed = Seed(self.refs.root, self.kind)
            seed.commit(self.preview)
            self.seed = seed
        self.seed.verify()

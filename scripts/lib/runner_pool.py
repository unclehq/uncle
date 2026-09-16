#!/usr/bin/env python3
"""Keep a native runner process alive for the lifetime of one workflow.

The native stage adapter still owns prompts, permissions, steering, metrics and
stage completion. This module only replaces its child process with a local TCP
proxy. The proxy owns the real CLI and accepts one stage connection at a time.
It is bound to loopback, authenticated with a random token, scoped by command
and working directory, and exits as soon as the workflow driver disappears.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from process_tree import finish_check, group_options, kill_tree


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def identity(command, cwd, runner, side, slot=0):
    raw = json.dumps([str(Path(cwd).resolve()), runner, side, slot, command], separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def paths(root, key):
    base = Path(root)
    return base / (key + '.json'), base / (key + '.lock'), base / (key + '.log')


def read_descriptor(path, owner, digest):
    try:
        value = json.loads(path.read_text())
        if (value.get('owner') == owner and value.get('digest') == digest
                and alive(value.get('pid')) and isinstance(value.get('port'), int)
                and isinstance(value.get('token'), str)):
            return value
    except (OSError, ValueError, TypeError):
        pass
    return None


def acquire(lock, deadline):
    while time.monotonic() < deadline:
        try:
            lock.mkdir()
            return
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 15:
                    shutil.rmtree(lock, ignore_errors=True)
                    continue
            except OSError:
                pass
            time.sleep(.05)
    raise RuntimeError('runner pool startup lock timed out')


def ensure(root, owner, runner, side, command, slot=0):
    Path(root).mkdir(parents=True, exist_ok=True)
    digest = identity(command, os.getcwd(), runner, side, slot)
    descriptor, lock, log = paths(root, digest)
    existing = read_descriptor(descriptor, owner, digest)
    if existing:
        return existing
    acquire(lock, time.monotonic() + 20)
    try:
        existing = read_descriptor(descriptor, owner, digest)
        if existing:
            return existing
        descriptor.unlink(missing_ok=True)
        with open(log, 'ab', buffering=0) as output:
            subprocess.Popen(
                [sys.executable, '-B', str(Path(__file__).resolve()), 'serve',
                 '--root', root, '--owner', str(owner), '--runner', runner,
                 '--side', side, '--digest', digest, '--', *command],
                stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                cwd=os.getcwd(), close_fds=True, start_new_session=(os.name != 'nt'))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            existing = read_descriptor(descriptor, owner, digest)
            if existing:
                return existing
            time.sleep(.05)
        detail = log.read_text(errors='replace')[-1000:] if log.exists() else ''
        raise RuntimeError('runner pool did not start' + (': ' + detail if detail else ''))
    finally:
        shutil.rmtree(lock, ignore_errors=True)


def connect(args, command):
    sock = reader = None
    for slot in range(4):
        descriptor = ensure(args.root, args.owner, args.runner, args.side, command, slot)
        sock = socket.create_connection(('127.0.0.1', descriptor['port']), timeout=30)
        sock.settimeout(None)
        sock.sendall((json.dumps({'token': descriptor['token']}) + '\n').encode())
        reader = sock.makefile('rb')
        hello = json.loads(reader.readline())
        if hello.get('ok'):
            break
        sock.close()
        sock = reader = None
        if hello.get('error') != 'busy':
            raise RuntimeError(hello.get('error') or 'runner pool refused connection')
    if sock is None:
        raise RuntimeError('all runner pool workers are busy')
    sys.stdout.write(json.dumps({'type': 'runner_pool', 'reused': bool(hello.get('reused')),
                                 'pool_pid': descriptor['pid']}) + '\n')
    sys.stdout.flush()

    def send_input():
        try:
            for line in sys.stdin.buffer:
                sock.sendall(line)
        except (BrokenPipeError, OSError):
            pass
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    threading.Thread(target=send_input, daemon=True).start()
    try:
        for line in reader:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
    finally:
        sock.close()
    return 0


class Server:
    def __init__(self, args, command):
        self.args = args
        self.command = command
        self.root = Path(args.root)
        self.descriptor, _lock, self.log = paths(self.root, args.digest)
        self.token = secrets.token_urlsafe(32)
        self.active = None
        self.active_lock = threading.Lock()
        self.stop = threading.Event()
        self.initialized = None
        self.initializing = None
        self.initialized_notified = False
        self.session_id = None
        self.child = None
        self.connections = 0

    def send_active(self, line):
        with self.active_lock:
            active = self.active
        if active is not None:
            try:
                active.sendall(line)
            except OSError:
                pass

    def child_output(self):
        for line in self.child.stdout:
            try:
                value = json.loads(line)
            except ValueError:
                value = None
            if (self.initializing is not None and isinstance(value, dict)
                    and value.get('id') == self.initializing and 'result' in value):
                self.initialized = value.get('result', {})
                self.initializing = None
            if isinstance(value, dict) and value.get('type') == 'system' and value.get('session_id'):
                self.session_id = value['session_id']
            self.send_active(line.encode())
        self.stop.set()
        with self.active_lock:
            active = self.active
        if active is not None:
            try:
                active.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def workflow_watch(self):
        while not self.stop.wait(.25):
            if not alive(self.args.owner):
                self.stop.set()
                return

    def forward(self, connection, line):
        try:
            value = json.loads(line)
        except ValueError:
            value = None
        if isinstance(value, dict) and value.get('method') == 'initialize':
            if self.initialized is not None:
                connection.sendall((json.dumps({'jsonrpc': '2.0', 'id': value.get('id'),
                                                'result': self.initialized}) + '\n').encode())
                return
            self.initializing = value.get('id')
        if isinstance(value, dict) and value.get('method') == 'initialized':
            if self.initialized_notified:
                return
            self.initialized_notified = True
        if (self.args.runner == 'claude' and isinstance(value, dict)
                and value.get('type') == 'user' and not value.get('session_id')
                and self.session_id):
            value['session_id'] = self.session_id
            line = json.dumps(value, separators=(',', ':')) + '\n'
        self.child.stdin.write(line)
        self.child.stdin.flush()

    def client(self, connection):
        stream = connection.makefile('rb')
        try:
            auth = json.loads(stream.readline())
        except (ValueError, TypeError):
            auth = {}
        if not secrets.compare_digest(str(auth.get('token', '')), self.token):
            connection.sendall(b'{"ok":false,"error":"authentication failed"}\n')
            return
        with self.active_lock:
            if self.active is not None:
                connection.sendall(b'{"ok":false,"error":"busy"}\n')
                return
            self.active = connection
        reused = self.connections > 0
        self.connections += 1
        connection.sendall((json.dumps({'ok': True, 'reused': reused}) + '\n').encode())
        try:
            for raw in stream:
                self.forward(connection, raw.decode())
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            with self.active_lock:
                if self.active is connection:
                    self.active = None

    def run(self):
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        listener.listen(8)
        listener.settimeout(.25)
        self.child = subprocess.Popen(self.command, stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=sys.stderr,
                                      text=True, encoding='utf-8', bufsize=1,
                                      **group_options())
        payload = {'pid': os.getpid(), 'owner': self.args.owner,
                   'port': listener.getsockname()[1], 'token': self.token,
                   'digest': self.args.digest, 'runner': self.args.runner,
                   'side': self.args.side}
        temporary = self.descriptor.with_suffix('.tmp-' + str(os.getpid()))
        temporary.write_text(json.dumps(payload) + '\n')
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.descriptor)
        threading.Thread(target=self.child_output, daemon=True).start()
        threading.Thread(target=self.workflow_watch, daemon=True).start()
        try:
            while not self.stop.is_set():
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                def serve_client(sock=connection):
                    try:
                        self.client(sock)
                    finally:
                        sock.close()
                threading.Thread(target=serve_client, daemon=True).start()
        finally:
            listener.close()
            if self.child.poll() is None:
                kill_tree(self.child)
                self.child.wait()
            finish_check(self.child)
            try:
                current = json.loads(self.descriptor.read_text())
                if current.get('pid') == os.getpid():
                    self.descriptor.unlink()
            except (OSError, ValueError):
                pass
        return 0


def main():
    argv = sys.argv[1:]
    try:
        boundary = argv.index('--')
    except ValueError:
        boundary = len(argv)
    command = argv[boundary + 1:] if boundary < len(argv) else []
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['connect', 'serve'])
    parser.add_argument('--root', required=True)
    parser.add_argument('--owner', required=True, type=int)
    parser.add_argument('--runner', required=True)
    parser.add_argument('--side', required=True)
    parser.add_argument('--digest')
    args = parser.parse_args(argv[:boundary])
    if not command:
        parser.error('runner command is required')
    if args.action == 'connect':
        return connect(args, command)
    return Server(args, command).run()


if __name__ == '__main__':
    raise SystemExit(main())

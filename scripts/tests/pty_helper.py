"""Tiny pty helper for headless tests: run a callable with a pty on stdin."""
import os
import pty


def with_pty_stdin(func, feed=b""):
    """Call func(stdin_fd) with a pty slave fd; feed bytes via the master."""
    master, slave = pty.openpty()
    try:
        if feed:
            os.write(master, feed)
        return func(slave), master
    finally:
        os.close(slave)
        os.close(master)

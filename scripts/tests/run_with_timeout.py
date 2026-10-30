"""Bound fixture commands on macOS and Linux, including child cleanup."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from process_tree import KEEP_STDIN, finish_check, start_check, wait_check


if __name__ == '__main__':
    child = start_check(sys.argv[2:], prompt=KEEP_STDIN)
    try:
        status = wait_check(child, float(sys.argv[1]), sys.stdout.buffer)
    finally:
        finish_check(child)
    raise SystemExit(status)

#!/usr/bin/env python3
"""A worker that prints its packet in chat is recovered; prose and foreign JSON are not."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import structured_output  # noqa: E402

PACKET = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-worker-packet', 'dispositions': []}


def log_of(text):
    path = Path(tempfile.mkdtemp()) / 'w.jsonl'
    path.write_text(json.dumps({'type': 'result', 'result': text}) + '\n')
    return path


class Recover(unittest.TestCase):
    def test_fenced_packet_after_prose(self):
        text = 'Rejected both.\n\n```json\n%s\n```\n' % json.dumps(PACKET, indent=2)
        self.assertEqual(structured_output.recover(log_of(text)), PACKET)

    def test_last_packet_wins_and_braces_in_prose_are_skipped(self):
        later = dict(PACKET, dispositions=[{'finding': 'A'}])
        text = 'use {x} here %s then %s' % (json.dumps(PACKET), json.dumps(later))
        self.assertEqual(structured_output.recover(log_of(text)), later)

    def test_no_packet(self):
        self.assertIsNone(structured_output.recover(log_of('done')))
        self.assertIsNone(structured_output.recover(log_of('{"kind": "x"}')))
        self.assertIsNone(structured_output.recover(Path('/nonexistent')))


if __name__ == '__main__':
    unittest.main()

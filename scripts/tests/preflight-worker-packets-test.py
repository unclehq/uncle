import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
spec = importlib.util.spec_from_file_location('preflight_worker_packets', Path(__file__).resolve().parents[1] / 'lib/preflight_worker_packets.py')
pwp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pwp)


def packet(rows):
    return json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'preflight-worker-packet', 'rows': rows})


class PreflightWorkerPacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, lens, rows):
        (self.root / (lens + '.json')).write_text(packet(rows))

    def test_merges_disjoint_lenses_in_order(self):
        self.write('tooling', [{'id': 'G-1', 'required': True, 'status': 'PASS', 'evidence': 'node --version -> v20'}])
        self.write('data', [{'id': 'G-2', 'required': True, 'status': 'BLOCKED-SETUP', 'evidence': 'no fixture; generate it'}])
        out = self.root / 'PREFLIGHT_REPORT.json'
        payload = pwp.collate(self.root, out, [('tooling', self.root / 'tooling.json'), ('data', self.root / 'data.json')])
        self.assertEqual(payload['schema'], 'uncle.artifact/v1')
        self.assertEqual(payload['kind'], 'acceptance-report')
        self.assertEqual([r['id'] for r in payload['rows']], ['G-1', 'G-2'])
        self.assertEqual(json.loads(out.read_text())['rows'][1]['status'], 'BLOCKED-SETUP')

    def test_rejects_id_collision_across_lenses(self):
        self.write('tooling', [{'id': 'G-1', 'required': True, 'status': 'PASS', 'evidence': 'a'}])
        self.write('data', [{'id': 'G-1', 'required': True, 'status': 'FAIL', 'evidence': 'b'}])
        with self.assertRaisesRegex(pwp.PacketError, 'both the tooling and data lenses'):
            pwp.collate(self.root, self.root / 'out.json', [('tooling', self.root / 'tooling.json'), ('data', self.root / 'data.json')])

    def test_missing_worker_file_is_a_clear_error(self):
        self.write('tooling', [{'id': 'G-1', 'required': True, 'status': 'PASS', 'evidence': 'a'}])
        with self.assertRaisesRegex(pwp.PacketError, 'missing \\(lens data\\)'):
            pwp.collate(self.root, self.root / 'out.json', [('tooling', self.root / 'tooling.json'), ('data', self.root / 'data.json')])

    def test_no_rows_anywhere_is_rejected_not_silently_empty(self):
        self.write('tooling', [])
        self.write('data', [])
        with self.assertRaisesRegex(pwp.PacketError, 'no acceptance-gate rows'):
            pwp.collate(self.root, self.root / 'out.json', [('tooling', self.root / 'tooling.json'), ('data', self.root / 'data.json')])

    def test_malformed_rows_rejected(self):
        cases = [
            [{'id': '', 'required': True, 'status': 'PASS', 'evidence': 'a'}],
            [{'id': 'G-1', 'required': 'yes', 'status': 'PASS', 'evidence': 'a'}],
            [{'id': 'G-1', 'required': True, 'status': 'MAYBE', 'evidence': 'a'}],
            [{'id': 'G-1', 'required': True, 'status': 'PASS', 'evidence': ''}],
            [{'id': 'G|1', 'required': True, 'status': 'PASS', 'evidence': 'a'}],
            [{'id': 'G-1', 'required': True, 'status': 'PASS', 'evidence': 'a|b'}],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                self.write('tooling', rows)
                with self.assertRaises(pwp.PacketError):
                    pwp.collate(self.root, self.root / 'out.json', [('tooling', self.root / 'tooling.json')])

    def test_wrong_schema_or_kind_rejected(self):
        (self.root / 'tooling.json').write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report', 'rows': []}))
        with self.assertRaisesRegex(pwp.PacketError, 'preflight-worker-packet'):
            pwp.collate(self.root, self.root / 'out.json', [('tooling', self.root / 'tooling.json')])

    def test_invalid_json_rejected(self):
        (self.root / 'tooling.json').write_text('{not json')
        with self.assertRaises(pwp.PacketError):
            pwp.collate(self.root, self.root / 'out.json', [('tooling', self.root / 'tooling.json')])


if __name__ == '__main__':
    unittest.main()

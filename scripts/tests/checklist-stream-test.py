import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('checklist_stream', ROOT / 'scripts/lib/checklist_stream.py')
stream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stream)


def packet(*ids):
    return {'schema': 'uncle.artifact/v1', 'kind': 'checklist-execution-worker-packets',
            'workers': [], 'results': [{'id': ident, 'status': 'PASS'} for ident in ids]}


class ChecklistStream(unittest.TestCase):
    def test_completed_ids_are_removed_before_the_normal_fanout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checklist = root / 'checklist.json'
            complete = root / 'complete.json'
            remaining = root / 'remaining.json'
            checklist.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'manual-checklist',
                                              'checks': [{'id': 'MC-100'}, {'id': 'MC-200'}]}))
            complete.write_text(json.dumps(packet('MC-100')))
            stream.remaining(checklist, complete, remaining)
            self.assertEqual([row['id'] for row in json.loads(remaining.read_text())['checks']], ['MC-200'])

    def test_merge_preserves_each_lane_once_and_orders_by_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, output = root / 'first.json', root / 'second.json', root / 'out.json'
            first.write_text(json.dumps(packet('MC-200')))
            second.write_text(json.dumps(packet('MC-100')))
            stream.merge(output, first, second)
            self.assertEqual([row['id'] for row in json.loads(output.read_text())['results']], ['MC-100', 'MC-200'])

    def test_duplicate_ids_fail_instead_of_silently_overwriting_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / 'first.json', root / 'second.json'
            first.write_text(json.dumps(packet('MC-100')))
            second.write_text(json.dumps(packet('MC-100')))
            with self.assertRaises(ValueError):
                stream.merge(root / 'out.json', first, second)


if __name__ == '__main__':
    unittest.main()

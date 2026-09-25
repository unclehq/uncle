#!/usr/bin/env python3
"""Regression coverage for execute-checklist's compact JSON worker handoff."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('packets', ROOT / 'scripts/lib/checklist_worker_packets.py')
PACKETS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PACKETS)
recovery_spec = importlib.util.spec_from_file_location('recovery', ROOT / 'scripts/lib/recover_worker_packet.py')
RECOVERY = importlib.util.module_from_spec(recovery_spec)
recovery_spec.loader.exec_module(RECOVERY)


def packet(identifier, status='PASS'):
    return {'schema': 'uncle.artifact/v1', 'kind': 'checklist-execution-worker-packet',
            'results': [{'id': identifier, 'action': 'run ' + identifier,
                         'expected_result': 'passes', 'actual_result': 'passed',
                         'evidence': 'command output', 'status': status,
                         'defect_reference': 'None'}]}


class ChecklistWorkerPackets(unittest.TestCase):
    def write(self, directory, name, body):
        (directory / (name + '.json')).write_text(json.dumps(body), encoding='utf-8')

    def test_collates_four_batches_in_check_id_order(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            names = ('group-1-batch-1', 'group-1-batch-2', 'group-2-batch-1', 'group-2-batch-2')
            for name, identifier in zip(names, ('MC-4', 'MC-2', 'MC-3', 'MC-1')):
                self.write(directory, name, packet(identifier))
            result = PACKETS.collate(directory, directory / 'combined.json', names)
            self.assertEqual([row['id'] for row in result['results']], ['MC-1', 'MC-2', 'MC-3', 'MC-4'])
            self.assertEqual(len(result['workers']), 4)

    def test_rejects_missing_invalid_and_duplicate_worker_results(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with self.assertRaisesRegex(PACKETS.PacketError, 'missing'):
                PACKETS.collate(directory, directory / 'out.json', ('group-1-batch-1',))
            self.write(directory, 'group-1-batch-1', packet('MC-1', 'MAYBE'))
            with self.assertRaisesRegex(PACKETS.PacketError, 'invalid status'):
                PACKETS.collate(directory, directory / 'out.json', ('group-1-batch-1',))
            self.write(directory, 'group-1-batch-1', packet('MC-1'))
            self.write(directory, 'group-1-batch-2', packet('MC-1'))
            with self.assertRaisesRegex(PACKETS.PacketError, 'duplicate check ID'):
                PACKETS.collate(directory, directory / 'out.json', ('group-1-batch-1', 'group-1-batch-2'))

    def test_recovers_final_packet_from_event_log_without_worker_file_write(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            body = packet('MC-1')
            log = directory / 'worker.jsonl'
            log.write_text('\n'.join((
                json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'working'}]}}),
                json.dumps({'type': 'result', 'result': json.dumps(body)}),
            )) + '\n', encoding='utf-8')
            output = directory / 'group-1-batch-1.json'
            RECOVERY.recover(log, output, 'checklist-execution-worker-packet')
            self.assertEqual(json.loads(output.read_text()), body)

    def test_recovers_complete_fenced_packet_after_runner_narration(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            body = packet('MC-2')
            log = directory / 'worker.jsonl'
            response = ('All assigned checks completed.\\n```json\\n' +
                        json.dumps(body) + '\\n```')
            log.write_text(json.dumps({'type': 'result', 'result': response}) + '\n', encoding='utf-8')
            output = directory / 'group-1-batch-1.json'
            RECOVERY.recover(log, output, 'checklist-execution-worker-packet')
            self.assertEqual(json.loads(output.read_text()), body)

    def test_normalizes_only_explicit_statuses_from_nonconforming_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            checklist = directory / 'MANUAL_CHECKLIST.json'
            checklist.write_text(json.dumps({
                'checks': [
                    {'id': 'MC-1', 'exact_action': 'do one', 'expected_result': 'one'},
                    {'id': 'MC-2', 'exact_action': 'do two', 'expected_result': 'two'},
                ],
            }))
            prompt = directory / 'worker.md'
            prompt.write_text('- Execute `MC-1`.\n- Execute `MC-2`.\n')
            log = directory / 'worker.jsonl'
            log.write_text(json.dumps({'type': 'result', 'result':
                '| **MC-1** | PASS | observed expected result |\n'
                '| **MC-2** | FAIL | observed defect |'}) + '\n')
            output = directory / 'packet.json'
            RECOVERY.recover_checklist_summary(log, output, checklist, prompt)
            results = json.loads(output.read_text())['results']
            self.assertEqual([(r['id'], r['status']) for r in results],
                             [('MC-1', 'PASS'), ('MC-2', 'FAIL')])
            self.assertEqual(results[0]['action'], 'do one')
            self.assertIn('Driver-normalized', results[1]['evidence'])

    def test_summary_recovery_never_infers_a_pass_for_an_unnamed_row(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            checklist = directory / 'MANUAL_CHECKLIST.json'
            checklist.write_text(json.dumps({'checks': [
                {'id': 'MC-1', 'exact_action': 'do one', 'expected_result': 'one'},
                {'id': 'MC-2', 'exact_action': 'do two', 'expected_result': 'two'},
            ]}))
            prompt = directory / 'worker.md'
            prompt.write_text('- Execute `MC-1`.\n- Execute `MC-2`.\n')
            log = directory / 'worker.jsonl'
            log.write_text(json.dumps({'type': 'result', 'result': 'MC-1 PASS: observed.'}) + '\n')
            output = directory / 'packet.json'
            RECOVERY.recover_checklist_summary(log, output, checklist, prompt)
            results = json.loads(output.read_text())['results']
            self.assertEqual(results[1]['status'], 'NOT RUN')

    def test_both_drivers_use_unique_packets_and_only_collated_handoff(self):
        for source in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            text = (ROOT / source).read_text()
            start = text.index('run_parallel_checklist_workers()')
            end = text.index('\n}\n', start) + 2
            block = text[start:end]
            self.assertIn('group-$group_index-batch-$batch_index', block)
            self.assertIn('checklist_worker_packets.py', block)
            self.assertIn('recover_worker_packet.py', block)
            self.assertIn('--checklist "$STATE_DIR/documents/MANUAL_CHECKLIST.json"', block)
            self.assertIn('WORKFLOW_EXECUTE_CHECKLIST_COMPACT_BATCH_SIZE', block)
            self.assertIn('EXECUTE_CHECKLIST_WORKERS.json', block)
            self.assertIn('Do not read the worker directory', block)
            self.assertNotIn('every listed evidence file', block)
        worker = (ROOT / 'prompts/change/execute-checklist-worker.md').read_text()
        self.assertIn('checklist-execution-worker-packet', worker)
        self.assertIn('never write separate', worker)
        self.assertIn('evidence files', worker)
        self.assertIn('final response', worker)
        self.assertNotIn('assigned packet path', worker)


if __name__ == '__main__':
    unittest.main()

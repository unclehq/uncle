import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'lib'))
spec = importlib.util.spec_from_file_location('packet', Path(__file__).resolve().parents[1]/'lib/manual-checklist-context.py')
packet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packet)

class Packet(unittest.TestCase):
    def test_checklist_json_export_preserves_scheduler_fields(self):
        import json
        script = Path(__file__).resolve().parents[1]/'lib/checklist_document.py'
        spec = importlib.util.spec_from_file_location('checklist_document', script)
        document = importlib.util.module_from_spec(spec); spec.loader.exec_module(document)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); docs = root/'.uncle/docs'; docs.mkdir(parents=True)
            checklist = docs/'MANUAL_CHECKLIST.md'
            checklist.write_text('### MC-1: Smoke\n- Exclusive resources: port:3000\n- Depends on: none\n- Exact action: open app\n- Expected result: app opens\n')
            document.export_json(checklist, root)
            payload = json.loads((root/'.uncle/workflow/documents/MANUAL_CHECKLIST.json').read_text())
            self.assertEqual(payload['checks'][0]['id'], 'MC-1')
            self.assertEqual(payload['checks'][0]['exclusive_resources'], ['port:3000'])

    def test_base_uses_frozen_inputs_only_and_delta_includes_current_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root/'.uncle/workflow'
            state.mkdir(parents=True)
            (root/'.uncle/docs').mkdir(parents=True)
            (root/'.uncle/docs/CHANGE_SPEC.md').write_text('| AC-1 | required |')
            (state/'green-check.md').write_text('live implementation result')
            (root/'.uncle/docs/IMPLEMENTATION_NOTES.md').write_text('changing implementation')
            base = packet.render(root, state, 'manual-checklist-base')
            self.assertIn('AC-1', base)
            self.assertNotIn('live implementation result', base)
            self.assertNotIn('IMPLEMENTATION_NOTES.md', base)
            delta = packet.render(root, state, 'manual-checklist-delta')
            self.assertIn('live implementation result', delta)
            self.assertIn('IMPLEMENTATION_NOTES.md', delta)
            (state/'green-check.md').write_text('new failure')
            self.assertIn('new failure', packet.render(root, state, 'manual-checklist-delta'))

if __name__ == '__main__':
    unittest.main()

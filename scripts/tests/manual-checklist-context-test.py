import importlib.util
from pathlib import Path
import tempfile
import unittest
spec = importlib.util.spec_from_file_location('packet', Path(__file__).resolve().parents[1]/'lib/manual-checklist-context.py')
packet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packet)

class Packet(unittest.TestCase):
    def test_base_uses_frozen_inputs_only_and_delta_includes_current_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root/'.uncle/workflow'
            state.mkdir(parents=True)
            (root/'CHANGE_SPEC.md').write_text('| AC-1 | required |')
            (state/'green-check.md').write_text('live implementation result')
            (root/'IMPLEMENTATION_NOTES.md').write_text('changing implementation')
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

import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import implementation_notes as notes


class Validate(unittest.TestCase):
    def test_single_invocation_json_is_rendered_and_stored(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / 'IMPLEMENTATION_NOTES.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes',
                       'changed_files': [{'path': 'a.py', 'purpose': 'add feature'}],
                       'deviations': [{'file': 'b.py', 'reason': 'needed helper'}],
                       'deliveries': [{'id': 'AC-1', 'status': 'IMPLEMENTED',
                                       'changed_code': 'a.py', 'observed_verification': 'pytest ok'}]}
            path.write_text(json.dumps(payload))
            self.assertTrue(notes.validate(root, 'IMPLEMENTATION_NOTES.md'))
            text = path.read_text()
            self.assertIn('`a.py`', text)
            self.assertIn('## Acceptance delivery', text)
            self.assertEqual(text.count('## Acceptance delivery'), 1)
            self.assertIn('| AC-1 | IMPLEMENTED | a.py | pytest ok |', text)
            stored = json.loads((root / '.uncle/workflow/documents/IMPLEMENTATION_NOTES.json').read_text())
            self.assertEqual(len(stored['fragments']), 1)

    def test_legacy_markdown_is_a_noop(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / 'IMPLEMENTATION_NOTES.md'
            path.write_text('# Implementation notes\n\nfree text\n')
            self.assertFalse(notes.validate(root, 'IMPLEMENTATION_NOTES.md'))
            self.assertEqual(path.read_text(), '# Implementation notes\n\nfree text\n')

    def test_wrong_kind_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / 'IMPLEMENTATION_NOTES.md'
            path.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': 'x'}))
            with self.assertRaises(ValueError):
                notes.validate(root, 'IMPLEMENTATION_NOTES.md')


class Append(unittest.TestCase):
    def test_fragments_merge_across_steps_with_one_deliveries_table(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            frag1 = root / 'step-1.json'
            frag1.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes',
                                          'changed_files': [{'path': 'a.py'}],
                                          'deliveries': [{'id': 'AC-1', 'status': 'INCOMPLETE',
                                                          'changed_code': 'a.py', 'observed_verification': 'n/a'}]}))
            frag2 = root / 'step-2.json'
            frag2.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes',
                                          'changed_files': [{'path': 'b.py'}],
                                          'deliveries': [{'id': 'AC-1', 'status': 'IMPLEMENTED',
                                                          'changed_code': 'a.py, b.py', 'observed_verification': 'pytest ok'}]}))
            target = root / 'IMPLEMENTATION_NOTES.md'
            notes.append(root, frag1, 'IMPLEMENTATION_NOTES.md', 'Step 1')
            notes.append(root, frag2, 'IMPLEMENTATION_NOTES.md', 'Step 2')
            text = target.read_text()
            self.assertIn('## Step 1', text)
            self.assertIn('## Step 2', text)
            self.assertEqual(text.count('## Acceptance delivery'), 1)
            self.assertIn('| AC-1 | IMPLEMENTED | a.py, b.py | pytest ok |', text)
            self.assertNotIn('INCOMPLETE', text)
            stored = json.loads((root / '.uncle/workflow/documents/IMPLEMENTATION_NOTES.json').read_text())
            self.assertEqual(len(stored['fragments']), 2)

    def test_non_json_fragment_is_preserved_as_raw_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            frag = root / 'step-1.json'
            frag.write_text('# Implementation step 1 handoff\n\n- Changed files: c.py\n')
            target = root / 'IMPLEMENTATION_NOTES.md'
            notes.append(root, frag, 'IMPLEMENTATION_NOTES.md', 'Step 1')
            text = target.read_text()
            self.assertIn('Changed files: c.py', text)

    def test_fenced_json_fragment_still_parses(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            frag = root / 'step-1.json'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes',
                       'unresolved_concerns': ['none']}
            frag.write_text('```json\n' + json.dumps(payload) + '\n```')
            target = root / 'IMPLEMENTATION_NOTES.md'
            notes.append(root, frag, 'IMPLEMENTATION_NOTES.md', 'Step 1')
            self.assertIn('Unresolved concerns', target.read_text())


if __name__ == '__main__':
    unittest.main()

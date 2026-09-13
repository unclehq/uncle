import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from read_cache import ReadCache
from native_stage import Stage


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.file = self.root / 'PLAN.md'
        self.file.write_text('original plan')
        self.cache = ReadCache(self.root)

    def read(self, arguments=None, result='original plan', failed=False):
        self.cache.observe({'message': {'content': [dict(type='tool_use', id='one', name='Read', input=arguments or {'file_path': str(self.file)})]}})
        self.cache.observe({'message': {'content': [dict(type='tool_result', tool_use_id='one', content=result, is_error=failed)]}})

    def test_reuses_only_explicit_inputs_and_retains_ranges(self):
        self.read({'file_path': str(self.file), 'offset': 1, 'limit': 1})
        self.assertEqual(self.cache.context('Read OTHER.md'), '')
        self.assertEqual(self.cache.context('Read OLD_PLAN.md'), '')
        context = self.cache.context('Read PLAN.md')
        self.assertIn('original plan', context)
        self.assertIn('"limit": 1', context)
        self.assertIn('never fresh verification evidence', context)

    def test_content_change_invalidates_even_with_unchanged_stat_times(self):
        self.read()
        before = self.file.stat()
        self.file.write_text('modified plan')
        os.utime(self.file, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(self.cache.context('Read PLAN.md'), '')
        self.assertEqual(list(self.cache.directory.glob('*.json')), [])

    def test_delete_or_symlink_replacement_is_not_reused(self):
        self.read()
        self.file.unlink()
        self.assertEqual(self.cache.context('Read PLAN.md'), '')
        target = self.root / 'other.md'
        target.write_text('original plan')
        try:
            self.file.symlink_to(target)
        except OSError:
            return  # Symlink creation is not available on every Windows runner.
        self.assertEqual(self.cache.context('Read PLAN.md'), '')

    def test_change_during_read_is_not_cached(self):
        self.cache.begin('one', 'Read', {'file_path': str(self.file)})
        self.file.write_text('changed')
        self.cache.end('one', 'original plan')
        self.assertEqual(self.cache.context('Read PLAN.md'), '')

    def test_errors_side_effects_images_and_hidden_files_are_not_cached(self):
        self.read(failed=True)
        for tool in ('Bash', 'Write', 'Edit', 'Glob', 'Grep'):
            self.cache.begin('one', tool, {'file_path': str(self.file)})
            self.cache.end('one', 'not a read')
        self.read(result=[{'type': 'image', 'data': 'not cached'}])
        hidden = self.root / '.env'
        hidden.write_text('secret')
        self.read({'file_path': str(hidden)}, 'secret')
        self.assertEqual(self.cache.context('Read PLAN.md and .env'), '')

    def test_bounded_context_and_disable(self):
        self.read()
        self.cache.CONTEXT_LIMIT = 1
        self.assertEqual(self.cache.context('Read PLAN.md'), '')
        with patch.dict(os.environ, WORKFLOW_READ_CACHE='0'):
            self.assertEqual(ReadCache(self.root).context('Read PLAN.md'), '')

    def test_bad_cache_data_does_not_break_stage(self):
        self.cache.directory.mkdir(parents=True)
        (self.cache.directory / 'bad.json').write_text('{')
        self.assertEqual(self.cache.context('Read PLAN.md'), '')

    def test_stage_receives_cache_and_preserves_task(self):
        self.read()
        with patch('os.getcwd', return_value=str(self.root)):
            stage = Stage('claude', 'agent', 'implementation', [], prompt='Read PLAN.md and implement it.')
        self.assertIn('Read PLAN.md and implement it.', stage.prompt)
        self.assertIn('original plan', stage.prompt)


if __name__ == '__main__':
    unittest.main()

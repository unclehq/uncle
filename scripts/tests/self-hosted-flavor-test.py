"""Server-flavor detection is skipped, forced or cached across processes (issue 204)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import self_hosted_http as h


def not_found(url, *a, **k):
    raise HTTPError(url, 404, 'nf', {}, None)


class Flavor(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        env = mock.patch.dict(os.environ, {'UNCLE_OUTAGE_DIR': d.name})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('UNCLE_SELF_HOSTED_FLAVOR', None)

    def test_hosted_path_makes_no_requests(self):
        with mock.patch.object(h, '_request', side_effect=not_found) as r:
            self.assertEqual(h.detect_flavor('https://api.x.com/publishers/p/v1', 'k'), 'generic')
        r.assert_not_called()

    def test_root_probed_once_then_cached(self):
        with mock.patch.object(h, '_request', side_effect=not_found) as r:
            self.assertEqual(h.detect_flavor('https://x.com/v1', 'k'), 'generic')
            self.assertEqual(r.call_count, 2)
            self.assertEqual(h.detect_flavor('https://x.com/v1', 'k'), 'generic')
            self.assertEqual(r.call_count, 2)

    def test_detects_vllm_and_caches(self):
        def fake(url, *a, **k):
            if url.endswith('/version') and '/api/' not in url:
                return {'version': '1'}
            not_found(url)
        with mock.patch.object(h, '_request', side_effect=fake):
            self.assertEqual(h.detect_flavor('https://y.com/v1', 'k'), 'vllm')
        with mock.patch.object(h, '_request', side_effect=not_found) as r:
            self.assertEqual(h.detect_flavor('https://y.com/v1', 'k'), 'vllm')
        r.assert_not_called()

    def test_setting_skips_detection(self):
        with mock.patch.dict(os.environ, {'UNCLE_SELF_HOSTED_FLAVOR': 'ollama'}), \
                mock.patch.object(h, '_request', side_effect=not_found) as r:
            self.assertEqual(h.detect_flavor('https://z.com/v1', 'k'), 'ollama')
        r.assert_not_called()
        with mock.patch.dict(os.environ, {'UNCLE_SELF_HOSTED_FLAVOR': 'bogus'}):
            with self.assertRaises(ValueError):
                h.detect_flavor('https://z.com/v1', 'k')


if __name__ == '__main__':
    unittest.main()

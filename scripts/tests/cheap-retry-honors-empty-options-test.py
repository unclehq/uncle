#!/usr/bin/env python3
"""The updated-plan cheap retry must not send chat_template_kwargs when the operator set request-options to {}."""
from pathlib import Path
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import self_hosted_http as http  # noqa: E402


class CheapRetryOptions(unittest.TestCase):
    def setUp(self):
        os.environ['UNCLE_UPDATED_PLAN_CHEAP_RETRY'] = '1'
        self.addCleanup(os.environ.pop, 'UNCLE_UPDATED_PLAN_CHEAP_RETRY', None)

    def test_explicit_empty_options_opt_out(self):
        values = http.configure_request_options({}, 'updated-plan', {'self-hosted.request-options': '{}'})
        self.assertEqual(values['_request_options'], {})

    def test_unconfigured_still_turns_thinking_off(self):
        values = http.configure_request_options({}, 'updated-plan', {})
        self.assertEqual(values['_request_options'], {'chat_template_kwargs': {'enable_thinking': False}})


if __name__ == '__main__':
    unittest.main()

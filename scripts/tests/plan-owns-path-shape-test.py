#!/usr/bin/env python3
"""Owns tokens that cannot be files are dropped with a warning; every previously valid token is kept (issue 231)."""
import contextlib
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import plan_model  # noqa: E402
import plan_steps  # noqa: E402

PLAN = '## Implementation sequence\n\n### Step 1: Build\nOwns: %s\n'


def captured(function, *args):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        result = function(*args)
    return result, err.getvalue()


def step_owns(owns_line):
    steps, err = captured(lambda text: plan_steps.extract_body(text)[0], PLAN % owns_line)
    return steps[0]['owns'], err


class ParserRoute(unittest.TestCase):
    def test_ticked_line_ignores_prose(self):
        dropped = []
        self.assertEqual(plan_steps.paths('`a.py` and the helper `b/c.py`, plus notes', dropped), ['a.py', 'b/c.py'])
        self.assertEqual(dropped, [])

    def test_no_ticks_plain_tokens(self):
        self.assertEqual(plan_steps.paths('a.py, src/*.py, b.txt'), ['a.py', 'src/*.py', 'b.txt'])

    def test_ticked_whitespace_dropped(self):
        dropped = []
        self.assertEqual(plan_steps.paths('`foo bar`, `a.py`', dropped), ['a.py'])
        self.assertEqual(dropped, ['foo bar'])

    def test_parent_segments_dropped_dotted_names_kept(self):
        dropped = []
        kept = plan_steps.paths('`../x`, `a/../../b`, `a/..`, `..`, `/abs`, `a..b.py`', dropped)
        self.assertEqual(kept, ['a..b.py'])
        self.assertEqual(dropped, ['../x', 'a/../../b', 'a/..', '..'])  # /abs is dropped silently, as before

    def test_previously_valid_tokens_kept_and_agree_with_validator(self):
        corpus = ['src/{a,b}.py', '~', '+', '=', 'src/**', '.gitignore', 'a..b.py', 'src/', 'x/y.c']
        for token in corpus:
            dropped = []
            self.assertEqual(plan_steps.paths('`%s`' % token, dropped), [token], token)
            self.assertEqual(dropped, [], token)
        for token in ['a b', '../x', 'a/../b']:
            if plan_model.valid_path(token):
                self.fail('validator accepts %r' % token)
            self.assertTrue(plan_steps.is_owns_junk(token), token)

    def test_directory_like_token_passes_shape_but_validator_rejects(self):
        self.assertFalse(plan_steps.is_owns_junk('src/'))
        self.assertFalse(plan_model.valid_path('src/'))

    def test_golden_previously_valid_line_has_empty_stderr(self):
        owns, err = step_owns('`src/a.py`, `tests/**`, `README.md`')
        self.assertEqual(owns, ['src/a.py', 'tests/**', 'README.md'])
        self.assertEqual(err, '')

    def test_one_exact_warning_per_dropped_token_per_parse(self):
        owns, err = step_owns('`a.py`, `foo bar`, `../x`')
        self.assertEqual(owns, ['a.py'])
        self.assertEqual(err.splitlines(), ['warning: step 1 owns: dropped foo bar', 'warning: step 1 owns: dropped ../x'])

    def test_all_dropped_gives_empty_owns_with_warning(self):
        owns, err = step_owns('`foo bar`, `../x`')
        self.assertEqual(owns, [])
        self.assertEqual(len(err.splitlines()), 2)

    def test_safe_token_strips_control_and_truncates(self):
        self.assertEqual(plan_steps.safe_token('a\x1b[31mb\nc\x07'), 'abc')
        long = plan_steps.safe_token('x' * 200)
        self.assertEqual(len(long), 80)
        self.assertTrue(long.endswith('...'))


class JsonRoute(unittest.TestCase):
    def test_owns_list_filters_with_same_warning(self):
        kept, err = captured(plan_model.owns_list, ['a.py', 'foo bar', '../x', 'a..b.py', 'src/{a,b}.py'], 3)
        self.assertEqual(kept, ['a.py', 'a..b.py', 'src/{a,b}.py'])
        self.assertEqual(err.splitlines(), ['warning: step 3 owns: dropped foo bar', 'warning: step 3 owns: dropped ../x'])

    def test_clean_list_is_silent(self):
        kept, err = captured(plan_model.owns_list, ['a.py', 'b/**'], 1)
        self.assertEqual((kept, err), (['a.py', 'b/**'], ''))

    def test_all_dropped_gives_empty_owns_then_validator_runs(self):
        kept, err = captured(plan_model.owns_list, ['x y', 'a/../../b'], 2)
        self.assertEqual(kept, [])
        self.assertEqual(len(err.splitlines()), 2)

    def test_parser_and_json_routes_use_one_predicate(self):
        for token in ['foo bar', '../x', 'a/../../b', '-- end', 'ok.py', 'a..b']:
            _, err = captured(plan_model.owns_list, [token], 1)
            self.assertEqual(bool(err), plan_steps.is_owns_junk(token), token)


if __name__ == '__main__':
    unittest.main()

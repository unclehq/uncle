"""Per-stage USD budget helpers: turn cost, spend ledger, stop rule, warn-once marker."""
import importlib.util
import math
import os
import stat
import sys
from pathlib import Path

MARKER_NAME = 'max-budget-unpriced-warned'

_prices = None


def _price_module():
    global _prices
    if _prices is None:
        spec = importlib.util.spec_from_file_location('budget_prices', Path(__file__).with_name('usage-cost.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _prices = module
    return _prices


class BudgetExceeded(ValueError):
    pass


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _tokens(usage, *names):
    for name in names:
        if _number(usage.get(name)):
            return usage[name]
    return None


def _record(usage, model):
    cache_read = _tokens(usage, 'cache_read_tokens', 'cache_read_input_tokens')
    cache_write = _tokens(usage, 'cache_write_tokens', 'cache_creation_input_tokens')
    return {
        'model': model or '',
        'input_tokens': _tokens(usage, 'input_tokens', 'prompt_tokens'),
        'output_tokens': _tokens(usage, 'output_tokens', 'completion_tokens'),
        'cache_read_tokens': 0 if cache_read is None else cache_read,
        'cache_write_tokens': 0 if cache_write is None else cache_write,
    }


def turn_cost(usage, model):
    """USD cost of one reply, or None when unknown.

    A finite numeric usage.cost >= 0 wins; an unusable reported cost is ignored and the
    token estimate is used; with neither, the cost is unknown (None) and never raises.
    """
    if not isinstance(usage, dict) or not usage:
        return None
    if _number(usage.get('cost')):
        return float(usage['cost'])
    try:
        row = _price_module().enrich(_record(usage, model))
    except Exception:
        return None
    value = row.get('estimated_cost_usd')
    return float(value) if _number(value) else None


def model_priced(model):
    """True when the price table has a rate for the model."""
    try:
        row = _price_module().enrich({'model': model or '', 'input_tokens': 1, 'output_tokens': 1,
                                      'cache_read_tokens': 0, 'cache_write_tokens': 0})
    except Exception:
        return False
    return _number(row.get('estimated_cost_usd'))


class Ledger:
    """Stage-wide spend. One per stage process, shared by nested runs."""

    def __init__(self):
        self.spent = 0.0
        self.last_turn = 0.0

    @property
    def spent_usd(self):
        return self.spent

    def add(self, cost):
        """Charge a reply cost; None (unknown) adds $0 and keeps last_turn."""
        if not _number(cost):
            return
        self.spent += cost
        if cost > 0:
            self.last_turn = cost

    def charge(self, usage, model):
        self.add(turn_cost(usage, model))

    def would_exceed(self, cap):
        if cap is None:
            return False
        return self.spent >= cap or self.spent + self.last_turn > cap

    def check(self, cap):
        if self.would_exceed(cap):
            raise BudgetExceeded(f'Stage stopped: spent ${self.spent:.2f} of ${cap:.2f} budget (--max-budget-usd); '
                                 'stopping before the next model request.')


def would_exceed(ledger, cap):
    return ledger.would_exceed(cap)


def warn_unpriced_once(workflow_dir='.uncle/workflow'):
    """True when the caller should print the unpriced warning (best effort, once per build).

    The first caller creates the marker and warns; later callers see a regular file and stay quiet.
    Any I/O trouble, symlink or non-regular marker means warn (never silent)."""
    path = os.path.join(str(workflow_dir), MARKER_NAME)
    try:
        os.makedirs(str(workflow_dir), exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0)
        os.close(os.open(path, flags, 0o644))
        return True
    except FileExistsError:
        try:
            return not stat.S_ISREG(os.lstat(path).st_mode)
        except OSError:
            return True
    except OSError:
        return True


def warn_once(message, workflow_dir='.uncle/workflow'):
    """Print message to stderr unless this build already warned."""
    if warn_unpriced_once(workflow_dir):
        print(message, file=sys.stderr)

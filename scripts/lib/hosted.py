"""Hosted mode: one switch (UNCLE_HOSTED=1) for running under a managed environment."""
import os

HINT = ('Hosted mode: set OPENAI_BASE_URL, OPENAI_API_KEY and SEREN_MODEL (or UNCLE_MODEL), '
        'or the UNCLE_SELF_HOSTED_* variables')


def is_hosted(env=None):
    """True only when UNCLE_HOSTED is exactly the string 1 (no trimming)."""
    env = os.environ if env is None else env
    return env.get('UNCLE_HOSTED') == '1'


def _clean(env, name):
    return (env.get(name) or '').strip()


def standard_model_settings(env=None):
    """base_url/api_key/model from the standard names; empty or blank counts as unset."""
    env = os.environ if env is None else env
    return dict(base_url=_clean(env, 'OPENAI_BASE_URL'),
                api_key=_clean(env, 'OPENAI_API_KEY'),
                model=_clean(env, 'SEREN_MODEL') or _clean(env, 'UNCLE_MODEL'))

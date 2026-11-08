"""Environment hygiene for launching the claude CLI as a stage.

A gateway or provider override left in the operator's shell redirects the claude CLI away from their own login, so the
login token is sent to a server that rejects it ("401 Invalid bearer token", or 403 authentication_failed). The login
has to be what authenticates a claude stage. Other runners (Self Hosted, Bedrock, Codex, Kimi) read their own settings and
must keep these variables, so this is applied only where claude itself is launched.
"""

CLAUDE_ROUTING_ENV = (
    'ANTHROPIC_BASE_URL', 'ANTHROPIC_BEDROCK_BASE_URL', 'ANTHROPIC_VERTEX_BASE_URL', 'ANTHROPIC_FOUNDRY_BASE_URL',
    'ANTHROPIC_FOUNDRY_API_KEY', 'ANTHROPIC_CUSTOM_HEADERS',
    'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY',
    'AWS_BEARER_TOKEN_BEDROCK',
)


def scrub_claude_env(env):
    """Drop the routing variables from `env` (a dict) in place and return it."""
    for key in CLAUDE_ROUTING_ENV:
        env.pop(key, None)
    return env

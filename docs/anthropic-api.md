# Anthropic API runner

`anthropic-api` is a profile of the Self Hosted runner class, like `aws-bedrock`.
It speaks the Anthropic Messages API and talks to one endpoint, `https://api.anthropic.com`,
with an API key. It is offered everywhere the local model is: the stage Configure screens (TUI and
the shell fallback), the supervisor, the home chat and hosted runs. It never sends a `temperature` field.

## Configure

In the TUI Configure menu choose **Configure Anthropic API** and set:

- **Anthropic API Key**: a single line of printable ASCII, stored in `.uncle/anthropic-api-keys.json`
  (mode 0600). The save is refused if the file cannot be added to `.uncle/.gitignore`.

Saving the key lists the models it can use (`GET /v1/models`); a failed discovery keeps the previous
catalog. Then set a stage runner, e.g. `<stage>.runner anthropic-api`, and pick the stage's model from
the discovered list. There is no Base URL or API Compatibility field: the endpoint is fixed, so a key can
only ever be sent to Anthropic, and requests are never redirected.

The shell fallback (`uncle` -> Configure) has the same entry as item 4, lists `anthropic-api` last in the
runner prompt, and works even when no runner binaries are on `PATH`.

## Settings

| Config key | Environment variable |
|---|---|
| `anthropic-api.model` / `<stage>.model` | `UNCLE_ANTHROPIC_API_MODEL` |
| (key) | `UNCLE_ANTHROPIC_API_KEY`, then `ANTHROPIC_API_KEY` |

Key lookup order: `UNCLE_ANTHROPIC_API_KEY`, the saved connection, the stage's stored key, then
`ANTHROPIC_API_KEY`. Model lookup order: `UNCLE_ANTHROPIC_API_MODEL`, `<stage>.model`, `anthropic-api.model`.
`UNCLE_SELF_HOSTED_*` values are never read for this runner.

Other `WORKFLOW_SELF_HOSTED_*` settings (except temperature) apply, and `WORKFLOW_ANTHROPIC_API_*` is part of
the result-reuse key. Temperature settings and any `temperature` key in `<stage>.request-options` are ignored.

## How requests map

OpenAI-style turns become Messages API turns: tool calls become `tool_use` blocks, tool results become
user `tool_result` blocks, and consecutive turns of one role merge. A schema-constrained answer is one forced
tool (`tool_choice`), whose arguments are the answer; a model that refuses a forced tool is asked for plain JSON
instead. `429`, `500`, `502`, `503` and `529` are retried with backoff (honoring `Retry-After`); a request whose
`max_tokens` exceeds the model's ceiling is retried once at 4096.

## Isolation from Self Hosted

The runner has its own key file and model sources. A missing key or model raises an Anthropic-worded error;
it never falls back to Self Hosted credentials, and Self Hosted state is not rewritten by this feature.

## Limitations

Live compatibility with the real API has not been verified here: the tests exercise the request and response
mapping, retries and configuration against stand-ins, not api.anthropic.com. Extended thinking, prompt caching
and streaming are not used.

# Learned budgets and exact result reuse

The direct HTTP self-hosted runner enables both features by default. Hosted
runners and the legacy OpenCode transport do not enter these code paths.
No model calls, Git commits or clean working tree are needed to manage the state.

Configure these lines in the project's `.uncle/config`. Environment variables
take precedence: prefix with `WORKFLOW_SELF_HOSTED_`, uppercase the option name,
and replace hyphens with underscores (for example,
`WORKFLOW_SELF_HOSTED_RESULT_REUSE=off`). Boolean options accept on/off,
true/false or 1/0; numeric options must be positive integers.

| Option | Default | Purpose |
| --- | --- | --- |
| `self-hosted.learned-budgets` | `on` | Learn and intervene on excessive generation and repeated tools |
| `self-hosted.budget-max-tokens` | `16384` | Ceiling for expected and soft-intervention budgets |
| `self-hosted.reasoning-output-tokens` | `32768` | Separate reasoning reserve added to the server completion limit; stage/parent/global overrides follow output-cap precedence |
| `self-hosted.budget-repeat-turns` | `3` | Consecutive identical small read/search/list batches and results before intervention; minimum 2 |
| `self-hosted.result-reuse` | `on` | Reuse validated answers for eligible read-only schema steps |
| `self-hosted.reuse-nonzero-temperature` | `off` | Explicitly allow reuse when effective temperature is above zero |
| `self-hosted.reuse-max-bytes` | `16777216` | Total result-entry storage limit; oldest access is evicted first |

## Budgets

`.uncle/self-hosted-performance/history.json` keeps the most recent 256 step
observations: stage family, deliverable kind and bytes, total completion tokens,
answer tokens and reasoning tokens per turn (null when not independently
reported), turns and valid/invalid/retried outcome. Byte-based answer and
reasoning estimates are stored separately. Predictions use answer tokens, or
answer-byte estimates when measured answer tokens are unavailable. Older
history containing only mixed completion totals is ignored for prediction. Retried and
invalid observations do not inflate the learned successful-output budget.

The estimate is the nearest-rank 90th percentile of successful turns in the
same family and kind. With no history, defaults are 1,024 tokens for edit or
resolution operations, 2,048 for review/worker packets, 4,096 for outlines and
8,192 for documents. Expected output has a 128-token floor and is bounded by
the existing turn cap and `budget-max-tokens`. Streaming intervention starts
above twice the expected budget, also bounded by those caps.

During SSE reception, only chat content and tool-call arguments consume the
answer cap and learned budget. Reasoning fields and leading `<think>` blocks
are excluded. The early signal is UTF-8 answer bytes / 4, or independently
reported answer tokens when larger. When the server provides completion-token
details, answer tokens are total completion tokens minus reasoning tokens.
A total-only completion count is never treated as answer tokens when reasoning
has been observed. Estimates are approximate and model/language dependent.

`turn-output-tokens` and `final-output-tokens` now cap deliverable output.
The 4,096-token default applies only to mechanical edit/resolution operations,
outlines and section packets. Review/audit lenses and other judgment workers
use the normal 32,768-token default. Stage, parent and global config/environment
overrides retain their precedence.

OpenAI `max_tokens` and native Ollama `num_predict` count reasoning too, so the
server receives the answer cap **plus** `reasoning-output-tokens` (default
32,768). The reserve is added even if a server omits or rejects `reasoning_effort`;
that field does not reliably disable thinking. Reasoning retains the existing
whitespace/repetition guards and request timeout, without a small streaming
budget intervention. APIs with only a combined limit cannot enforce an exact
independent reasoning ceiling: their final backstop is the combined allowance.
Non-streaming fallback uses that same allowance and checks the answer before
capture or tool execution, but cannot interrupt generation mid-response.

The first budget intervention stops the response and asks once for only the
final deliverable. Complete, independently validated text already received
uses the normal capture path; partial tool calls never execute. After that,
existing output, whitespace, repetition and time caps apply. Three identical
small read/search/list batches with identical results also ask for the final
answer without tools; continued tool calls fail rather than loop. Changed
results reset the repeated-tool count. The final-deliverable retry does not raise either configured allowance.

`self_hosted_budget_intervention` events describe soft/hard actions and their
reason, without content or tool arguments. `self_hosted_stream_stop` and
`self_hosted_turn` retain their existing diagnostic roles. An interrupted
stream often has no token usage; estimates are never billed as measured usage.

## Reuse

Eligibility requires a schema, a read-only/no-shell tool policy, no live
steering session, and temperature zero unless explicitly opted in. All
write-capable and shell-capable steps remain ineligible, even when a particular
execution happens not to write. This includes implementation, verification
commands and arbitrary document writers.

The SHA-256 identity includes model, Base URL identity (never the API key),
effective request options, effort, temperature, complete gated and prefetched
prompt bytes, project path, tool definitions, schema, delivery path, stage,
limits, relevant configuration and runtime implementation digests. URLs with
userinfo or query/fragment fields are ineligible.

File identity is a byte snapshot of the tool-visible project, including
untracked files and supplied `.uncle/docs` and `.uncle/workflow` inputs. It also
captures names for directory/search sensitivity. Hidden credential contents
are never opened. Symlinks, special files, unreadable inputs and snapshots over
64 MiB or 20,000 entries disable reuse. Snapshots are checked again before
storage, along with full bytes actually read and read/search/list results,
including detection of transient changes reverted during the step.

Runner-owned `workflow/logs`, `workflow/read-cache` and the configured status
file are excluded only when the prompt does not reference them. A step that
reads those paths or searches/lists an ancestor is not stored. This prevents a
step's own telemetry from invalidating its cache entry while keeping every
actual task input covered.

This conservative approach can miss on unrelated changes, inspection of runner
diagnostics, or temporary planning roots. There is no sharing across projects.
It does not require commits or a clean tree. An unchanged input snapshot is
necessary even when filenames, file sizes and mtimes are unchanged.

Entries store schema-validated final text, never tool calls. A hit is streamed
through the same SSE assembler and normal answer capture/schema checks, then
returned to the ordinary driver publication and gate paths. Downstream semantic
validators and gates still run and may reject it; a hit is not a gate pass or
fresh verification evidence. `self_hosted_reuse` records the digest and byte
count. Reuse generates zero model requests and no invented token usage.

Storage uses atomic replacement and a project-local lock. Results are evicted
by oldest access within the byte limit. Corrupt entries are misses; oversized
results are not saved. State has its own ignore file as well as the normal
`.uncle/*` ignore rule. Storage failures do not fail a valid delivery.

Clear results while keeping learned history, from the project root:

```sh
python3 /path/to/uncle/scripts/lib/self_hosted_performance.py clear --root .
```

Tests use loopback stub servers and temporary files, with no model or signing
key. Run the focused regression with
`python3 scripts/tests/self-hosted-budget-reuse-test.py`; run the shell regression
with `bash scripts/run-shell-tests.sh`.

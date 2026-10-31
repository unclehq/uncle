# Updated-plan edit writers

The ops writer path assigns at most two findings per initial group. The number
of groups is independent of the dispatcher's concurrency limit: a large review
queues more small groups instead of enlarging each writer's assignment. The
existing overlap resolvers and single-finding retries retain their contracts.

Writers receive the complete plan model, verification commands, protected paths,
and review in a shared prefix, followed by their assigned findings/corrections.
They are told to deliver immediately without investigation. Keeping the common
review prefix preserves prefix caching across the protected-path owner and its
siblings. No input is fetched by a model just to reconstruct this context.

Settings in `.uncle/config`:

| Setting | Default | Meaning |
| --- | ---: | --- |
| `updated-plan.group-size` | 2 | Maximum initial findings per ops writer |
| `updated-plan.writer-turns` | 3 | Writer tool-turn budget |
| `updated-plan.ops-per-finding` | 4 | Expected operations for answer sizing |
| `updated-plan.tokens-per-op` | 512 | Token allowance per expected operation |

Environment overrides use `WORKFLOW_UPDATED_PLAN_GROUP_SIZE`,
`WORKFLOW_UPDATED_PLAN_WRITER_TURNS`, `WORKFLOW_UPDATED_PLAN_OPS_PER_FINDING`,
and `WORKFLOW_UPDATED_PLAN_TOKENS_PER_OP`. Change workflows accept corresponding
`updated-change-plan.*` / `WORKFLOW_UPDATED_CHANGE_PLAN_*` overrides, then inherit
`updated-plan.*`. Environment settings precede config. The older
`WORKFLOW_UPDATED_PLAN_EDIT_SLICE` and `WORKFLOW_UPDATED_PLAN_PARALLEL_SLICE`
remain supported when the new group-size environment setting is absent.
Values must be positive integers.

Self-hosted writers and resolvers start with the generic edit-op schema, with
row fields restricted to the actual kind of each target in the plan model. When a
local plan validator rejects a packet, only that group retries with its scoped,
per-kind schema and the precise rejection. A failed or interrupted writer is
retried one finding at a time with a scoped schema and thinking disabled. This
retry uses constrained final delivery even when the first attempt was configured
for tools. Only a finding that still fails gets the final tool-loop attempt. `updated-plan.strict-schema` selects `retry` (default),
`first` (strict on the first attempt only), or `always`. Its environment override
is `WORKFLOW_UPDATED_PLAN_STRICT_SCHEMA`, with the same change-stage inheritance
and precedence above. `updated-plan.strict-op-schemas 0` disables strict schemas
on both attempts. Claude and Codex retain their existing schema selection.

Self-hosted writers stop after 45 seconds without streamed progress. Set
`self-hosted.writer-no-progress-seconds` or
`WORKFLOW_SELF_HOSTED_WRITER_NO_PROGRESS_SECONDS` to change this window.
The absolute ceiling defaults to `max(600, 60 * writer-jobs)` seconds (720 at
the default 12 concurrent writers); `self-hosted.writer-seconds` or
`WORKFLOW_SELF_HOSTED_WRITER_SECONDS` overrides it. The ceiling covers streaming,
tool calls and protocol retries in one runner invocation. Continuous progress
cannot extend it. A silent or expired runner and its descendants are stopped;
its completed siblings remain available.

`self-hosted.writer-jobs` / `WORKFLOW_SELF_HOSTED_WRITER_JOBS` bounds updated-plan
writers separately from the provider-wide pool; the smaller limit wins. These
positive-integer options also accept stage-specific config keys and environment
suffixes, using the same worker-to-stage mapping as model configuration. Specific
environment overrides precede global environment values, then stage config and
self-hosted config. Claude and Codex scheduling is unchanged.

Previous attempt logs, JSONL and packets are retained with `-rN` suffixes before
canonical paths are reused. Failed writers record their exit status and error
detail in the stage and speculative logs. Exhausted writer attempts and read-only
preflight violations stop automatic speculation/fallback/triage restarts. Explicit
operator recovery remains available through the existing commands.

New implementation steps use `insert_step` with `after` or `before` naming an
existing step (`after: "end"` appends). The `new` object contains `title`, `text`,
`owns`, and `depends_on`, never a number or id. Dependencies name existing step
ids or `new:N`, the Nth inserted step in that packet. Existing `set_step` edits
can also reference `new:N`. The driver isolates these references per packet,
merges in slice order, and assigns consecutive numbers and ids while rewriting
dependencies. Two writers inserting after the same anchor keep slice order
without requiring a resolver. Rendered plans and their approval gates retain
the same shape.

The derived self-hosted answer cap is
`max(4096, 1024 + findings * (512 + ops_per_finding * tokens_per_op))`:
4,096 tokens for one finding, 6,144 for two, 8,704 for three. Existing explicit
self-hosted turn/final output-token overrides retain precedence, and the model's
output limit remains an upper bound. A streamed `answer_cap` stop returns to the
driver immediately; only the failed group is split and retried.

The HTTP runner asks for final delivery without tools when the tool budget is
exhausted. Other runners use their existing turn-limit controls. The current Codex and
Kimi adapters discard `--max-turns`; they receive the same prefetched prompts
and packet salvage but do not gain a hard tool-count ceiling from this change. A completed
file packet can be salvaged even if the runner exits unsuccessfully afterward;
the same merge and schema checks still apply. These workers never double their
turn budget automatically. A complete first edit/resolution object followed by
another object or text is accepted; malformed JSON is not repaired by capture.

Structural retries operate on the current updated plan. Accepted dispositions
that unambiguously name a missing path and an implementation step take priority.
Otherwise, a `name.test.ext` / `name.spec.ext` file can inherit the unique owner
of a source file with the same basename and extension. Ambiguous gaps get one
bounded edit-op request containing the implementation steps and affected paths.
Ownership repairs cannot remove existing ownership or protected paths, change
commands/dispositions, or edit unrelated ids. Other structural defects receive
only implementation and verification/test sections plus the execution contract.
The normal validators run again before approval. Speculative synthesis is never
reused for a structural retry.

Regression commands:

```sh
python3 -I scripts/tests/updated-plan-slicing-test.py
python3 -I scripts/tests/updated-plan-ops-test.py
bash scripts/run-shell-tests.sh
```

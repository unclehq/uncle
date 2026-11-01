# Changes from Uncle Satellite

Work done on a copy of [unclehq/uncle](https://github.com/unclehq/uncle), starting
from `b03a324` ("more work on change requests to get them to build.", 2026-10-29).
Everything is on the `brian-handoff` branch.

Every "before → after" below was measured on the same machines. Where something
was not measured, this page says so. Where a change did not help, or made things
worse, it says that too.

## Headline

### Claude as the model: 12.1 min → 7.5 min

Same command, same machine, started at the same moment, Uncle defaults (Claude, low effort):

| | `b03a324` (upstream) | `brian-handoff` |
|---|---:|---:|
| Wall clock, groovy calculator | **724.7 s (12.1 min)** | **451.8 s (7.5 min)** |
| Requirements | 15 s | 16 s |
| Project plan | 41 s | 96 s (hit the `.gitignore` detection bug below, since fixed) |
| Adversarial review | 23 s | 15 s |
| Updated plan | 23 s | 23 s |
| Implement | 65 s | 181 s |
| Test review → repair loop | 49 s + 111 s repair, then review again | no repair needed |
| Final audit | NOT READY | NOT READY |

Caveats:
- This is **one run each.** The single biggest difference is that upstream needed a
  repair loop and this branch did not, which can vary from run to run.
- **Both audits say NOT READY for the same reason**, unrelated to either codebase:
  on the test machine the Claude CLI asked for permission before running the dev
  server and browser checks, and in unattended mode nobody approved, so 10
  required live checks were BLOCKED. On a machine where those commands are
  pre-approved for Uncle's Claude runs, this should not occur. That is not yet
  verified.

### DeepSeek V4 Flash as the model: planning ~2× faster; end-to-end not yet measured

Upstream's DeepSeek build was reported at about 2 hours. No run on either codebase
has yet been timed end to end on DeepSeek, so there is **no end-to-end number yet**.
Measured stage times, same command and server:

| Stage | Upstream | `brian-handoff` (best run) |
|---|---:|---:|
| Requirements | 85 s | 51–56 s |
| Project plan | 448 s | 244–274 s |
| Adversarial review | 155 s | 140–381 s (varies; see known issues) |
| Updated plan | 488 s+ (unfinished) | 441–797 s |

Server for these numbers: vLLM 0.29, DeepSeek V4 Flash, tensor-parallel across 4
NVIDIA DGX Spark (GB10) nodes.

## What made self-hosted runs slow, and what fixed it

On a self-hosted model the binding cost is **tokens generated**: about 30 tokens/s
per request and 70–200 tokens/s for the whole server. Reading prompts is mostly
cached (65–90% prefix-cache hits). So every fix below is about **generating less**.

| # | Cause (measured) | Fix | Effect |
|---|---|---|---|
| 1 | The model's thinking arrived inside the answer text and was carried into later turns. | Server: vLLM `--reasoning-parser deepseek_v4`. Uncle: strips leaked thinking and never sends reasoning back. | Clean answers; thinking no longer re-read. |
| 2 | No way to turn thinking off for mechanical steps. | New **per-stage request options** (`<stage>.request-options` JSON), model-agnostic. For DeepSeek: `{"chat_template_kwargs":{"thinking":false}}`. | Planner turn 1 went from 9,814 tokens (38 KB of thinking) to a single plan write; planning ~4.5 min vs 7.5. |
| 3 | The planner rewrote the whole plan 3–4 times (27,791 tokens for a ~7k-token plan). | Write once; repairs are anchored edits to the draft. | One write in later runs. |
| 4 | Edit writers drafted their packet in chat 4–5 times, then delivered it again. | **Capture, don't regenerate:** a valid deliverable that already appeared in chat is adopted through the same validators. | Removes repeat drafts. |
| 5 | One writer generated 32,768 tokens of pure whitespace (28 min) under JSON-schema decoding. | Server: vLLM `--structured-outputs-config '{"backend":"guidance","disable_any_whitespace":true}'`. Uncle: **streaming** with early stop on whitespace or repetition runaways, plus small output caps for mechanical packets. | No whitespace runaways since. |
| 6 | Every planning section repeated stage-wide duties (`.gitignore`, app launch) and ~30% shared boilerplate. | Section prompts carry only section work; one stage-duty step afterwards. | ~30% smaller section prompts; fewer format retries. |
| 7 | Prompts broke the server's prefix cache early. | Stable shared content first, per-worker content last. | Modest (seconds). |

### Tried, and did not help (or hurt)

- **Sending `reasoning_effort` (low).** No measurable effect on tool-using requests,
  and on DeepSeek V4 it **re-enables thinking** even when request options turn it
  off. This silently undid fix #2 for several runs. **Now off by default**
  (`self-hosted.reasoning-effort on` to opt in).
- **Splitting planning into 22 parallel sections on DeepSeek.** Total tokens
  generated mattered more than parallelism. Use `WORKFLOW_PROJECT_PLAN_SECTIONS=0`
  for single-pass planning on a self-hosted model. Claude is fine either way.
- **Compact (single-line) JSON by instruction.** Slower, and produced invalid JSON.
- **Conversation reuse across steps.** Evaluated and deliberately not enabled: it
  would carry stale plans and other reviewers' answers across approval gates.
- **Skipping "mechanical" review findings.** 0 of 37 findings in two runs were
  safely mechanical. Not included in this branch.

## Recommended configuration for DeepSeek V4 Flash on vLLM

In `.uncle/config`:

```text
requirements.request-options {"chat_template_kwargs":{"thinking":false}}
project-plan.request-options {"chat_template_kwargs":{"thinking":false}}
preview-build.request-options {"chat_template_kwargs":{"thinking":false}}
updated-plan.request-options {"chat_template_kwargs":{"thinking":false}}
preflight.request-options {"chat_template_kwargs":{"thinking":false}}
execute-checklist.request-options {"chat_template_kwargs":{"thinking":false}}
implementation.request-options {"chat_template_kwargs":{"thinking":false}}
self-hosted.stage-jobs 8
```

Plus `WORKFLOW_PROJECT_PLAN_SECTIONS=0`. Judgment stages (adversarial review, test
review, final audit) keep thinking on. Server flags: see fixes #1 and #5.

## Bugs fixed

Each has a test that fails without the fix.

| # | Area | Symptom | Fix |
|---|---|---|---|
| 1 | Checklist scheduling | Checks that declared no resources were treated as independent and could run in parallel with conflicting checks. | Undeclared means serial, as documented. |
| 2 | Checklist fallback | A missing canonical checklist left the previous README's schedule behind. | Replaced with a run-serially notice. |
| 3 | Acceptance IDs | JSON acceptance accepted IDs that the Markdown gate rejects. | Same ID rule in both. |
| 4 | Supervisor retry | A `change-plan` retry during combined planning jumped to PLAN and stopped. | Resumes the analysis producer. |
| 5 | Supervisor validation | A diagnosis that quoted a driver-supplied absolute path was rejected. | Allowed only when it equals the cited evidence. |
| 6 | Green check | Checks disabled or absent recorded no DISABLED / NOT RUN evidence. | Calls the existing reporter. |
| 7 | Verification envelope | Published before background checks finished. | Published after collection. |
| 8 | Final audit rerun | A stale `FINAL_AUDIT.json` meant a fresh audit was never produced. | Removed with its view. |
| 9 | Audit override | Overriding a driver-downgraded NOT_READY failed. | The recorded digest proves the audit is unchanged; edits still block. |
| 10 | Checklist report | A delivered Markdown report was not validated before the fallback. | Validated first. |
| 11 | Checklist fallback | `CHECKLIST-EVIDENCE-MISSING` could be dropped. | Retained. |
| 12 | macOS process groups | Darwin's ambiguous EPERM read as failure (3 of 400 concurrent launches). | Confirmed via `ps`; 400 of 400 correct. |
| 13 | Delivery status | Explicit INCOMPLETE delivery was ignored. | Honored. |
| 14 | Stage `.gitignore` check | Words like "next" and "trust" selected Next.js and Rust outputs, failing the check and discarding the sectioned plan. | Whole-word detection. |

## Test suite

`bash scripts/run-shell-tests.sh` on macOS (bash 3.2.57):

| | Passed | Failed | Skipped |
|---|---:|---:|---:|
| `b03a324` (upstream) | 108 | 23 | 1 |
| `brian-handoff` | 135 | 0 | 1 (runner not installed) |

Most failures were stale harnesses: tests copied functions out of the drivers
with `extract_fns`, and refactors had made those functions call helpers that
were not copied. Other causes: Markdown-only fixtures after the move to canonical
JSON, macOS lacking `timeout`, and position-based text checks. No assertion was
removed or loosened.

## Structure

Behavior-preserving refactor, steps 1–6 of a 10-step plan. Shared code moved out of
`stagegate.sh` and `change-workflow.sh` into sourceable, tested libraries
(prompts, records, paths, approval gates, implementation gates, stage config,
reviewer artifacts, runtime status, and shared Python event and evidence
helpers). The drivers shrank by about 830 lines. Tests now source library code
instead of extracting functions by text, which removes the cause of most of the
23 failures. Steps 7–10 (verification orchestration, schedulers, a
provider-neutral stage interface, thin drivers) are planned, not done.

## New settings

| Key | Default | Purpose |
|---|---|---|
| `<stage>.request-options`, `self-hosted.request-options` | none | Extra JSON merged into self-hosted requests. Protected keys cannot be overridden; rejected options are dropped per server. |
| `self-hosted.reasoning-effort` | `off` | Send the stage effort as `reasoning_effort`. |
| `self-hosted.stage-jobs` | 4 (1–8) | Parallel planning and updated-plan workers. |
| `self-hosted.stream-whitespace-chars` | 2000 | Early stop on a whitespace runaway. |
| `self-hosted.stream-repetition-count` | 8 | Early stop on repetition. |
| `<stage>.turn-output-tokens`, `<stage>.final-output-tokens` | 4096 for mechanical packets, else 32768 | Output caps. Judgment workers never get the small turn cap. |
| `self-hosted.prefetch` | on | Supply explicitly requested small inputs before turn 1. |

New telemetry: `self_hosted_turn` (per turn: tool names and argument sizes, chat
text and reasoning sizes, output tokens; never content), `self_hosted_capture`,
and `self_hosted_stream_stop`. The performance report no longer double-counts
stage output.

## Known issues and suggestions

- **Updated plan on DeepSeek is still the slowest planning stage** (7–13 min). Edit
  writers still narrate and draft at length before answering. The next lever is
  learned output budgets (built, but held back until they stop counting thinking
  toward the limit).
- **Adversarial review on DeepSeek varies a lot (2–6 min)** with thinking on.
- **Unattended Claude runs need command permissions** for the dev server and
  browser, or live checks are BLOCKED and the audit is NOT READY.
- Two attestation tests can launch the real Claude CLI if a fixture branch is taken
  (test isolation gap).
- `supervision-driver`, `gates` and `updated-change-plan-edits-driver` can fail under
  heavy parallel load and pass alone (timing-sensitive).
- CI runs only installer checks, so the shell suites aren't run in CI. Running them
  in CI would have caught the 23 failures.

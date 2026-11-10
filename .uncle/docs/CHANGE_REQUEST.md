# Change Request

Issue 232

Seeded from [unclehq/uncle#232](https://github.com/unclehq/uncle/issues/232).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Reviewer prompts over 120 KB still fail in hosted runs after #214: the self-hosted reviewer starts through reviewer-self-hosted.sh, which the prompt-file check does not recognize

## Motivation

## Summary

The fix for #214 (PR #222) gives a reviewer its prompt as a file only when the reviewer command starts with `python3`. Hosted runs use the self-hosted runner, and its reviewer command is the wrapper `scripts/reviewer-self-hosted.sh`. The wrapper runs `self_hosted.py`, which reads `--prompt-file`, but `stagegate.sh` doesn't recognize it. The prompt stays a single command-line argument, and the new size guard refuses it.

The result is the same as #214: every adversarial-review lens fails before any reviewer starts, and the build exits 1. Only the message changed.

## What happened (2026-11-10, UTC)

A headless hosted run (`UNCLE_HOSTED=1`, self-hosted runner, Linux sandbox) built a small app: one cabal program, `base` as the only dependency, three modules. The build included PR #222, since the guard message below first appears in `a1d6abcf`. The project plan was written and approved. At `ADVERSARIAL_REVIEW`, all four lenses (requirements, regression, security and testability) and their retries failed the same way:

```
Reviewer adversarial-review-worker-requirements: prompt is 148103 bytes, over Linux's 131,072-byte per-argument limit (guard 120000); this reviewer command cannot read the prompt from a file. Shorten the prompt or use a file-capable reviewer (self_hosted.py / native_stage.py).
Adversarial-review worker failed validation; stopping the panel.
uncle --noui: driver exited with status 1
```

**Shortening the plan doesn't get under the limit.** This three-module plan still produced a 148,103-byte review prompt, close to the 150,668 bytes in #214's larger run. So most of the prompt is fixed text, and nearly every hosted build will hit this. A headless run also can't act on the message's advice.

## Code paths (main `5a5cd30`)

Blame is `git blame -w`.

| Where | What it does | Last changed in |
|---|---|---|
| `scripts/lib/stage-config.sh:47-49` | Hosted mode makes `self-hosted` the default runner. | `688d2194` 2026-11-09 (#211) |
| `scripts/lib/stage-config.sh:241-243` | A reviewer on `aider`, `opencode` or `self-hosted` runs `scripts/reviewer-self-hosted.sh`. | `b122fc32` 2026-09-10 |
| `scripts/stagegate.sh:2259-2268` | `client_cmd=("$cmd")`. It is replaced with `python3 native_stage.py` only when the runner is **not** `self-hosted` (`:2264`). For self-hosted, `client_cmd[0]` stays the wrapper's path. | `ceae3faa` 2026-09-15, `cc340817` 2026-09-12 |
| `scripts/reviewer-self-hosted.sh:8` | `exec python3 "$ROOT/scripts/lib/self_hosted.py" reviewer "$@"`, which passes every argument through, including `--prompt-file`. | `4b8f4b6e` 2026-09-09 |
| `scripts/lib/self_hosted.py:452-492` | Parses and checks `--prompt-file` for the reviewer. So the wrapper's target can already take the prompt as a file. | `a1d6abcf` 2026-11-09 (#214), `ade8195a`, `4b8f4b6e` |
| `scripts/stagegate.sh:2355-2363` | **The gap.** `prompt_kind=file` only if `client_cmd[0] == python3`. The wrapper fails that test, so the prompt goes as one argument (`prompt_kind=argv`). | `a1d6abcf` 2026-11-09 (#214) |
| `scripts/stagegate.sh:2364-2367` | Runs the guard. On failure it writes the message to the lens log and sets `status=1`. The retry fails the same way. | `a1d6abcf` 2026-11-09 (#214) |
| `scripts/lib/reviewer-prompt.sh:11-17, 36-39` | `reviewer_prompt_guard` refuses an argument prompt over 120,000 bytes. That is correct for real argument-only clients; here the client was classified wrong. | `a1d6abcf` 2026-11-09 (#214) |
| `scripts/change-workflow.sh:2595-2597` | Same gap in the change workflow. It matches `*self_hosted.py*` or `*native_stage.py*` anywhere in the command, or a basename of `self_hosted.py` or `native_stage.py`. `reviewer-self-hosted.sh` matches none of these. | `a1d6abcf` 2026-11-09 (#214) |
| `scripts/stagegate.sh:2343-2350`, `:2157-2159` | The only reviewer path that already passes `--prompt-file` on self-hosted: the candidate race, used when more than one candidate is configured. The count defaults to 1 (`:1345`), so a default hosted run takes the single-reviewer path above. | `61633718` 2026-09-28, `a1d6abcf` 2026-11-09 |
| `scripts/tests/reviewer-prompt-file-test.py:204, 220, 240` | The tests set `client_cmd=(python3 "<fake runner>")` directly. None of them launches through `reviewer-self-hosted.sh`, so the hosted path is untested. | `a1d6abcf` 2026-11-09 (#214) |

**Provenance.** #214 was closed by PR #222 (merged 2026-11-10 00:03 UTC). The PR's own audit verdict was "NOT READY". Its finding FA-004 says the Linux check and the stage-level guard behavior were never run (no Linux host, and the new Linux CI workflow had not run yet). Only helper-level tests and grep checks of the wiring were in place, which is how a launch path the tests don't cover got through.

## Fix

1. **Decide file mode by what the command runs, in one shared place.** Add a helper to `scripts/lib/reviewer-prompt.sh`, for example `reviewer_prompt_kind CMD...`. It returns `file` for `python3 … self_hosted.py|native_stage.py` and for `scripts/reviewer-self-hosted.sh`, which only `exec`s `self_hosted.py reviewer "$@"`. Everything else gets `argv`. Call it from `stagegate.sh:2358-2363` and `change-workflow.sh:2595-2597` instead of the two separate checks, so they can't drift apart again.
2. **Keep the guard as it is** for real argument-only clients (`codex`, `claude`, `reviewer-kimi.sh`, `reviewer-claude.sh`).
3. **Tests that use the real wrapper.** Point `UNCLE_RUNTIME_ROOT` at a temporary root that contains the real `scripts/reviewer-self-hosted.sh` and a fake `scripts/lib/self_hosted.py` that records its arguments. With a 200,000-byte prompt, in both `stagegate.sh` and `change-workflow.sh`, check that:
   - the fake receives `--prompt-file <path>`;
   - no argument is over 120,000 bytes;
   - the guard message never appears.
4. **An end-to-end case for hosted mode:** `UNCLE_HOSTED=1` with no runner in `.uncle/config`, so the default runner resolution (`stage-config.sh:47-49` → `:243` → `stagegate.sh:2264`) is covered, not only a hand-set `client_cmd`.
5. **Run these in the Linux CI workflow added by #222,** where the per-argument limit actually applies.

## Checks after the fix

- A hosted run on Linux (`UNCLE_HOSTED=1`, no runner config) whose review prompts are over 128 KB. Each lens log shows `Launching reviewer (.../reviewer-self-hosted.sh)`, there is no `prompt is N bytes` line, every lens writes its packet, and the panel finishes.
- The same run with two candidates (`self-hosted.candidates 2`) still passes, so the race path is unchanged.

Related: #214 (closed by PR #222), #230, #231.


### Comment from taariq

Seen again on 2026-11-10 at 18:39 UTC in a hosted run. The plan step finished and was approved. Then all four reviewers (requirements, regression, security and testability) and their retries were refused with:

> prompt is 146375 bytes, over Linux's 131,072-byte per-argument limit (guard 120000); this reviewer command cannot read the prompt from a file.

That's the second hosted build that day to fail this way, after the 148,103-byte case in this report. One other build that day did get past review, so whether a build fails seems to depend on how large the reviewer prompt turns out. Each failed attempt spends several dollars of model calls on planning before the panel stops it.

Hosted builds can't get through review reliably until this is fixed. Could it be prioritized?

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.

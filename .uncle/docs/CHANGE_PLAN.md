# Change plan — issue 267

Seeded from [unclehq/uncle#267](https://github.com/unclehq/uncle/issues/267).
Omitted sections: Schema/persistence (none); Migration (none); Feature flag (none, bug fix); Concurrency (no shared state added); Observability beyond stop-reason (none).

Issue 267

## 1. Selected technical approach

1. In `updated_plan_fast_path.py` add `executed_paths(commands)`: parse each command line as text without executing it (shell-style tokenization). A candidate is a token in command position, or the script operand of an interpreter (`bash sh zsh python python3 node ruby perl`). To find the script operand, skip interpreter options (flags beginning with `-`, e.g. `bash -e`, `python3 -u`, `-x`); an option that takes a value (`-c`, `-m`, `-e`/`-E`/`-p` for node/ruby/perl, `--eval`, `--command`, `-r`, `-I`) consumes its value; the first remaining non-option token is the operand. Inline-code invocations (`python3 -c ...`, `bash -c ...`, `node -e ...`, `perl -e ...`) and module invocations (`python3 -m ...`) yield no candidates, and their code strings and arguments are never scanned as executed files (so `python3 -c 'scripts/check.py'` yields nothing). Only literal script operands qualify; option values are never script paths. Strip a leading `./`, keep repository-relative tokens that contain a `/` OR a file extension (either suffices; extensionless paths such as `scripts/check` qualify, bare tool names such as `bash`, `make`, `npm` or `pytest` with neither a slash nor an extension do not), apply the existing exclusion filter. CHANGE_SPEC §15 is aligned to this rule (slash or extension, not extension only). Tests: positive `scripts/check` (extensionless, with slash); negative bare tool names; `bash -e scripts/x.sh` and `python3 -u tests/run.py` yield the script; `python3 -c`, `python3 -m`, `bash -c`, `node -e` yield nothing. `derive_protected_paths` returns the named-test result; only when that is empty does it return `executed_paths`. All callers (ops 945/959, publish_agent_artifact 160, plus the new Markdown ingest) inherit it. [D-1]
2. In `updated_plan_edits.py:767` replace the bare refusal check with the same derivation fallback so both merge paths agree; refusal message kept. [D-2]
3. Markdown fallback: in the project-plan Markdown ingest, when payload lacks `protected_verification_paths`, set it from `derive_protected_paths(narrative, commands)` if non-empty, marking it ingest-derived (not explicitly supplied). In `updated_plan_ops.py` merge, ingest-derived paths are never trusted as-is: whenever merged steps or commands differ from the base, recompute from the merged plan and commands (`derive_protected_paths(pm.render(new_model), commands)`) and apply `owned_protected_paths` ownership filtering, so a renamed or removed protected script cannot survive as a stale path. Explicitly supplied paths (writer or payload) are preserved unchanged. [D-3]
4. Stop reason: `Conflict` in `updated_plan_ops.main` exits 4 (other errors stay 1) and the message goes to stderr as today. `stagegate.sh` merge call (3119) captures stderr to `$directory/merge.err`, replays it, and on status 4 calls new `workflow_merge_conflict updated-plan "<message>"` in `model-jobs.sh`, which writes the same flag file plus stop-reason `updated-plan: merge conflict: <message>`; any other nonzero status keeps `workflow_writer_exhausted`, and status 0 writes neither. The dispatch is testable at the stagegate level (statuses 0, 4, 1), not just via the helper. Message normalization (done in `workflow_merge_conflict`): strip the leading `updated-plan ops:` prefix, replace each run of whitespace (including newlines) with one space, trim, then retain the first 500 Unicode characters; an empty result yields the literal message `unspecified`, so the stop reason is always single-line and non-empty. [D-4]

## 2. Alternatives considered
| Alt | Rejected because |
|---|---|
| Treat everything under `scripts/` as tests | Over-protects product scripts; breaks B-5 intent |
| Make merge succeed with empty protected paths | Weakens I-3 / SI-4 |
| Parse the stop reason from log text in the shell | Fragile; exit status is explicit |

## 3. Why preferred
Smallest change at the single derivation point, matches the request literally, keeps named-test behavior identical (SB-2).

## 4. Components not to modify
Writer prompts, resolver code, `change-workflow.sh`, `artifact_json.py` validators (unless the A2 check shows the field is rejected; then record the deviation), approval gates.

## 6. Data-flow change
Project-plan Markdown ingest now also emits protected paths; derivation gains an executed-file fallback; merge Conflict carries a distinct exit status to the shell.

## 8. Interface changes

`updated_plan_ops.py merge` exit status 4 = merge conflict (new). stop-reason text `updated-plan: merge conflict: <msg>` (new variant). Message normalization (strip prefix, collapse whitespace, trim, cap 500 characters) lives only in `workflow_merge_conflict` in `model-jobs.sh` (S-4); S-2 leaves the stderr message unmodified.

## 10. Compatibility
Prefix `updated-plan:` retained; flag file retained; named-test plans unchanged.

## 12. Error and recovery
Commands executing no repo file and no named tests: still refuses (SB-4), now with the correct reason. Recovery is operator/plan edit, as before.

## 14. Rollback plan
Revert the change set; no persisted formats or state files change (the flag and stop-reason files are rewritten each run, stagegate 5756).

## 16. Automated-test strategy

Python: extend `updated-plan-fast-path-test.py` (AC-1, AC-2) and `updated-plan-ops-test.py` (AC-3, AC-4); new `plan-context-protected-test.py` (AC-5). Fast-path cases: positive `bash scripts/check`, `./scripts/check` and `scripts/check.sh`; negative bare tool names such as `bash`, `make`, `npm test`; interpreter option handling where `python3 -u scripts/check.py` yields scripts/check.py, while `python3 -c 'scripts/check.py'`, `python3 -m pkg.mod scripts/x.py` and `bash -c 'scripts/check.sh'` yield no candidates. Shell: new `updated-plan-merge-conflict-test.sh` (AC-6) sources `model-jobs.sh` helpers in a temp STATE_DIR and must exercise stagegate's merge dispatch itself, not only the helpers: with the merge command stubbed to exit 0, 4 and 1, it asserts the resulting stop-reason text, flag file and replayed output for each (0: no stop reason and no flag; 4: `updated-plan: merge conflict: <message>` and flag; 1: the existing writer-exhausted reason and flag). To make that possible the merge call-site dispatch is factored into a function sourceable by the test, or stagegate is run with a stubbed merge command. The test also asserts the exact normalized stop-reason message: multiline stderr has newlines collapsed to single spaces after prefix stripping and trimming, empty stderr yields `unspecified`, and over-limit stderr is truncated to exactly 500 characters. All new or modified fixtures and their subprocesses (AC-3 and AC-6 included) disable commit and tag signing through command flags (`-c commit.gpgsign=false -c tag.gpgsign=false`) and repository-local config, retain explicit `--no-gpg-sign` on commits and `--no-sign` on tags, and verify helpers with an isolated failing fake signer that must never run. Commands are the baseline `verification_commands`; the explicit per-suite commands are required because ops, fast-path and the new suites are outside the default tier.

## 17. Regression-test strategy

Existing ops-test:160-180 and writer-retries tests must stay unmodified and green. Bug regression test: AC-3 test fails before the fix (Conflict at ops 947) and passes after. Required additional cases: (a) AC-3 negative: when the only command is `python3 -c 'scripts/check.sh'`, merge still raises Conflict (SB-4); (b) AC-5 and an edits.py agreement test, required and never cut: a Markdown-ingest plan and an ops-merge plan derive identical protected paths; (c) ingest-then-merge rename: ingest a Markdown plan, merge a review edit that renames a protected script, and assert only the new path is protected, the stale path is absent, and explicitly supplied paths are preserved.

## 18. Manual verification
None required; optionally rerun a hosted build with `scripts/check-*.sh` checks to see the plan pass the merge (LIVE_VERIFICATION, not a coding prerequisite).

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | REPOSITORY | CLAUDE.md git signing | AC-3, AC-6 | Test fixtures and their subprocesses never sign commits or tags | Every new or modified fixture and subprocess sets repository-local `commit.gpgsign=false` and `tag.gpgsign=false`, passes `-c commit.gpgsign=false -c tag.gpgsign=false`, and keeps `--no-gpg-sign` on commits and `--no-sign` on tags. New helpers are verified with an isolated failing fake signer (gpg.program) that must never be invoked. | policy | CAP-shell | CODING |
| R-2 | USER | CHANGE_REQUEST fix 1 | AC-1..4 | Fallback only when no test named | precedence in derive | request text | CAP-py | CODING |
| R-3 | DESIGN | stop-reason readers | AC-6 | Keep `updated-plan:` prefix and flag file | helper writes both | relay compat | CAP-shell | CODING |

Feasibility: runners `scripts/run-python-tests.sh` and `scripts/run-shell-tests.sh` inspected (usage lines accept `-- suite`). Decisions D-1..D-4 are DESIGN choices revisable after approval. No live-authentication prerequisite exists.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| scripts/lib/updated_plan_fast_path.py | add `executed_paths`; fallback in `derive_protected_paths` | Fix 1 | Over/under-protection | fast-path-test, ops-test |
| scripts/lib/updated_plan_ops.py | Conflict exits 4 in `main` | Fix 3 | Callers treating nonzero generically | ops-test |
| scripts/lib/updated_plan_edits.py | use derivation fallback at 767 | Consistency | Low | ops-test |
| scripts/lib/plan_context.py | Markdown plan payload gets protected paths | Fix 2 | Validator rejects field (A2) | plan-context-protected-test |
| scripts/stagegate.sh | merge call site handles status 4 | Fix 3 | Stop-reason regression | merge-conflict shell test |
| scripts/lib/model-jobs.sh | add `workflow_merge_conflict` | Fix 3 | Terminal-failure flag | merge-conflict shell test |
| scripts/tests/updated-plan-fast-path-test.py | new cases incl. interpreter options and inline/module invocations (`-u`, `-c`, `-m`, `bash -c`) | AC-1,2; AR-009 | None | self |
| scripts/tests/updated-plan-ops-test.py | new cases | AC-3,4 | None | self |
| scripts/tests/plan-context-protected-test.py | new suite | AC-5 | None | self |
| scripts/tests/updated-plan-merge-conflict-test.sh | new suite | AC-6, SI-5 | None | self; drives stagegate merge dispatch with statuses 0, 4, 1 |
| .uncle/docs/IMPLEMENTATION_NOTES.md | record deviations | Workflow rule | None | n/a |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| Fix 1 | SB-1, 2, 3, 4 | SI-1, 3, 4 | fast_path, edits | AC-1, 2, 3, 4 tests, interpreter option/inline-code derivation cases | none |
| Fix 2 | SB-5 | SI-3 | plan_context | AC-5 test | none |
| Fix 3 | SB-6, 7, 8 | SI-5 | ops, stagegate, model-jobs | AC-4, AC-6 tests | optional hosted rerun |

## Implementation sequence

Step 2 and step 3 are ordered: step 3 (Markdown ingest) follows both step 1 and step 2 because its ingest-then-merge rename test relies on the S-2 recompute in `updated_plan_ops.py`. Steps 3 and 4 share no files and may run in parallel once step 2 is done; step 4 follows step 2 because the shell test relies on the merge exit status.

1. [S-1] Derivation fallback and its Python tests (D-1, D-2; AC-1, AC-2). Script-operand extraction skips interpreter options, treats inline-code (`-c`) and module (`-m`) invocations as yielding no path, accepts only literal operands, and never executes anything. Eligibility is slash OR extension. Positive tests: `bash scripts/check.sh`, `./scripts/check.sh`, `bash -e scripts/check.sh`, `python3 -u scripts/check.py`, and extensionless `bash scripts/check` (yields `scripts/check`). Negative tests (yield no path): `python3 -c 'scripts/check.py'`, `bash -c 'scripts/check.sh'`, `python3 -m pkg.mod`, and bare tool names such as `pytest` and `bash` alone.
   Owns: `scripts/lib/updated_plan_fast_path.py`, `scripts/lib/updated_plan_edits.py`, `scripts/tests/updated-plan-fast-path-test.py`
2. [S-2] Merge exit status and ops tests (AC-3, AC-4); merge recomputes ingest-derived protected paths from the merged plan/commands with ownership filtering and preserves explicit paths (D-3); regression case: Markdown-ingest-to-merge where a review renames a protected script, asserting only the new path survives and the old path is absent
   Owns: `scripts/lib/updated_plan_ops.py`, `scripts/tests/updated-plan-ops-test.py`
   Depends on: 1
3. [S-3] REQUIRED (not cuttable): Markdown plan ingest protected paths and its test (D-3; AC-5; check the validator first; if it rejects the field, resolve the incompatibility and record the deviation rather than omitting the derivation); ingest marks derived paths as ingest-derived so the merge in S-2 can recompute them; test that explicitly supplied paths are left untouched
   Owns: `scripts/lib/plan_context.py`, `scripts/tests/plan-context-protected-test.py`
   Depends on: 1, 2
4. [S-4] Stop reason: `workflow_merge_conflict` (strip `updated-plan ops:` prefix, collapse whitespace runs to one space, trim, cap at 500 characters, empty becomes `unspecified`), stagegate merge call-site dispatch (structured so the shell test can drive it), and a shell test that exercises stagegate's dispatch with merge statuses 0, 4 and 1 and covers multiline, empty and over-limit stderr, asserting stop reason, flag and output (D-4; AC-6)
   Owns: `scripts/lib/model-jobs.sh`, `scripts/stagegate.sh`, `scripts/tests/updated-plan-merge-conflict-test.sh`
   Depends on: 2
5. [S-5] Reconcile: record deviations in IMPLEMENTATION_NOTES.md
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 3, 4

## 21. Scope cuts under time pressure

S-3 (Markdown ingest, fix 2; AC-5/SB-5) and the `edits.py` consistency change in S-1 (D-2) are required and are never cut: both merge paths must agree and the Markdown ingest must emit protected paths. Never cut S-2/S-4 (honest stop reason) or the regression tests. If time expires, cut only the optional hosted rerun (manual verification) and any non-required cleanup.

## 22. Risks and unresolved questions

| ID | Handling | Risk |
|---|---|---|
| R-A | Ownership filter B-5 limits to step-owned files; acceptable per request | Heuristic picks non-test scripts (e.g. `bash scripts/build.sh`) |
| R-B | Implementer checks `artifact_json.py:414` first; if the validator rejects `protected_verification_paths` on the project-plan payload, resolve that incompatibility (permit the field in the validator and record the deviation in IMPLEMENTATION_NOTES.md) before completion. Dropping Markdown derivation is not an allowed outcome; AC-5 must pass. | project-plan payload validator rejects new field (A2) |
| R-C | Implementer greps `writer attempts exhausted` once; keep prefix | Other readers match the old stop-reason text |

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Cutting S-3 or the edits.py change, or dropping Markdown derivation on validator rejection, would leave AC-5/SB-5 and D-2 unmet. | Section 21 (s17.1) no longer cuts S-3 or the edits.py change; R-B now requires resolving a validator rejection; step-3 text states S-3 is required. |
| AR-002 | Accepted | Plan D-1 (slash or extension) and spec §15 (extension) disagreed; the plan's looser rule is the intended one, so the spec is aligned to it. | Section 1 item 1 and step-1 now state that a slash or extension qualifies and require scripts/check as a positive AC-1 example. |
| AR-003 | Accepted | Option handling and inline-code modes were undefined; a precise extraction rule removes false protection and missed scripts. | Edit s1.1.i1 and step-1 to define option skipping, inline/module yielding no path, and tests for -u, -c, -m, bash -e/-c. |
| AR-004 | Accepted | Ingest-time paths could survive a later rename in review; merge must recompute from the merged plan, so ingest paths must not be treated as authoritative. | Revise D-3 (s1.1.i3), steps 2 and 3 to recompute from merged plan with ownership filtering, preserve explicit paths, and add a rename regression test. |
| AR-005 | Accepted | D-1 left interpreter options and inline code undefined, so strings like `python3 -c 'scripts/check.sh'` could be protected as files. | Edit s1.1.i1 and step-1 to define script-operand extraction: skip options, inline/module modes yield nothing, literal operands only, no execution; add tests. |
| AR-006 | Accepted | Real gap: the signing mechanism omitted tag signing, repository-local config and fake-signer verification, and was scoped only to AC-6 though AC-3 also builds fixtures. | Rewrote R-1 mechanism and requirements, and extended s10.1 so every new or modified fixture disables commit and tag signing and is verified with a failing fake signer. |
| AR-007 | Accepted | A helper-only test could pass while stagegate's merge dispatch still misreports conflicts as writer exhaustion. | Edits §16 (s10.1), D-4 (s1.1.i4), step-4 and s14.1.r10 so the shell test drives stagegate's merge dispatch with statuses 0, 4 and 1. |
| AR-008 | Accepted | D-1 (slash or extension) and the spec's extension-only rule conflict; slash-or-extension is the plan's intent and extensionless scripts like scripts/check must qualify. | Section 1 D-1 states the eligibility rule; section 16 and S-1 require positive tests for scripts/check and negative tests for bare tool names. |
| AR-009 | Accepted | Interpreter option and inline-code handling was undefined; a fixed rule and tests are needed so parsers and oracles agree. | Edit D-1 (s1.1.i1), s10.1 test list, s14.1.r7, s15.1.r1 and step-1 to define option skipping, no candidates for -c/-m, and tests. |
| AR-010 | Accepted | The single-line truncated conflict message needs a precise transformation so AC-6 can assert an exact stop-reason value. | D-4 (s1.1.i4), s10.1 and step-4 now specify strip prefix, collapse whitespace, trim, 500-char cap, and multiline/empty/over-limit tests. |

You are the primary existing-code analyst.

Read:

- README.md
- CHANGE_REQUEST.md
- repository documentation
- build and dependency files
- relevant source code
- existing tests

Inspect the current repository before changing anything.

Create BASELINE_REPORT.md containing:

1. Change-request summary
2. Repository architecture
3. Relevant code paths
4. Current observable behavior
5. Existing invariants
6. Current API, schema, and interface contracts
7. Existing automated-test coverage
8. Exact build and test commands executed
9. Baseline test results
10. Existing failures, warnings, and flaky behavior
11. Reproduction result for the reported bug, if applicable
12. Likely change surface
13. Regression-sensitive components
14. Areas explicitly outside the change
15. Unknowns and assumptions
16. Initial risk assessment

For each existing behavior include:

| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|

For each existing invariant include:

| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|

Do not modify source code.
Do not fix the issue.
Do not create an implementation plan.

## Context economy

Everything a tool returns stays in context and is re-sent on every later turn
of this stage. A large command output read early is paid for many times over.
This stage reads more of the repository than any other, so the discipline
matters most here.

- Run test suites with the quietest flag that still reports failures. Record
  the summary line and the names of failures; never paste passing output.
- Pipe commands whose output is unbounded through `tail`, `wc -l`, or a
  summary flag. `find`, `ls -R`, and full-tree greps need a bound.
- Use Grep with a targeted pattern in preference to reading a large file end
  to end. Never read a file longer than about 300 lines end to end: grep for
  the symbols CHANGE_REQUEST.md names and read the surrounding lines. One
  whole large module is a third of this stage's context.
- Write BASELINE_REPORT.md as soon as sections 8 and 9 have their evidence,
  before any reading for later documents. A report on disk survives a context
  that runs out; one still in your head does not.
- Cite code by path and line rather than quoting it. The report is read by
  five later stages; quoted source is paid for in each of them.
- Do not re-read a file you have already read in this stage.

## Output economy

Length is a cost. Write the shortest report a reviewer can act on. Six later
stages read this report, and each of them re-sends it on every turn, so a word
here is paid for six times over.

- Use the appended budget and enforcement mode; no separate word limit.
- Omit any numbered section with no substantive content for this change.
- Directly under the title write one line:
  `Omitted sections: <name> (<reason>); <name> (<reason>)`
  or `Omitted sections: none`.
- Do not restate CHANGE_REQUEST.md. Cite it and move on.
- Prefer tables and short declarative clauses over prose.
- Never omit a section to avoid resolving something. If a section applies but
  you cannot complete it, keep it and mark it UNRESOLVED with the reason.

Section 8 and section 9 are never omitted: the exact commands you ran and their
results are the evidence the rest of the workflow depends on.

## Section 8 is executed, not just read

The driver re-runs section 8 itself — once now, against the unmodified tree,
and once after the change — and compares the two. That is how the workflow
knows a check passed, rather than taking the implementation stage's word for
it. So write section 8 as a command list a shell can run:

- one fenced block, immediately under the heading, and nothing else in it;
- one command per line, exactly as you ran it, from the repository root;
- no prompt prefixes, no comments, no prose, no placeholders;
- no command that needs a human, a password, an interactive browser, or a network service
  you cannot reach here — leave those to the manual checklist instead;
- no command that changes the repository. These run twice, and the first run
  must leave the tree exactly as it found it.

A check that is already failing is still listed. The driver records that it
failed before the change, so it will not be blamed on the change; omitting it
only hides it.

Prefer the project's documented test runner over constructing shell loops.
When analyzing Uncle itself, if `scripts/run-shell-tests.sh` exists, use
`bash scripts/run-shell-tests.sh` for its shell regression suites and record
that exact command. It already parallelizes suites and aggregates failures;
do not also run those suites individually or wrap them in a serial loop.

It takes about three minutes at the default four jobs; allow ten before
treating it as hung. Two things make that worse rather than better: cutting it
off early and retrying, and lowering `--jobs`, which only makes the same work
take longer. Run it with `bash` -- the suites are shell scripts, and `python3`
on one fails with a parse error that reads like a broken test rather than the
wrong interpreter.
For other projects, inspect their runner and fixture isolation before choosing
parallelism; do not assume this Uncle-specific script exists.

Automated browsers and local test servers are permitted when required for
acceptance. Run independent test suites in parallel by default. Append
`## Parallel verification groups` for independent suites, holding one
fenced block and nothing else — bare rows of consecutive, one-based command
positions, one group per line:

```text
2 3
5 6
```

Rows must be ordered and disjoint; no bullets, labels, backticked numbers, or
prose in the block. Group only commands with independent ports, outputs,
fixtures, and state, and explain their independence in the test coverage
section.
The driver uses the approved groups for both baseline and post-change checks;
do not regroup commands after approval.

Write BASELINE_REPORT.md and stop.

## Bounded baseline and compact first draft

Start with CHANGE_REQUEST.md and the repository's documented verification entry
points. Build a short map of affected symbols, their callers and relevant tests.
Read only documentation and code needed to establish current behavior, invariants
and regression risks for this change. Expand discovery only to answer a concrete
unresolved question; do not read remaining large-file sections for completeness.
Batch independent reads. Existing reports are navigation hints, not fresh PASS
evidence, and reports from other issues must not become this baseline.

Choose the documented relevant checks once, including any repository-mandated
full suite. Execute each selected command once and capture full stdout/stderr
and its real exit status in workflow logs. For Uncle use run-shell-tests.sh;
do not run its selected suites again individually. Group other independent
commands only when their fixtures, ports and outputs are isolated. Do not overlap
a full suite with its constituent tests. Poll an active command rather than
launching it again. Inspect a failing check's saved log before considering a
rerun; rerun only for a specific reproduction or flakiness question and record why.
Do not pipe a check through tail in a way that loses its failure exit status.

Compose the report after collecting evidence: one canonical row per behavior,
invariant and executed result, referenced elsewhere by ID. Preserve exact commands,
exit codes, failures, evidence paths and unknowns. Reconcile sections 8/9 and
parallel groups once. No repeated narrated format sweeps or whole-report rereads
without a specific discrepancy. In advisory-budget mode perform ZERO size-only
compaction passes; mandatory evidence survives above the guide. The driver
measures the report. Enforced budgets retain the two-pass limit.

Return/write the complete BASELINE_REPORT.md under the runner contract. Steering
questions do not replace the task: answer them, then finish the baseline. Never
substitute a conversation summary, filename or progress note for the report.
Do not modify source code or create project commits.

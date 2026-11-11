# Change plan — Issue 248

Seeded from [unclehq/uncle#248](https://github.com/unclehq/uncle/issues/248).

Issue 248

Omitted sections: Schema/persistence beyond new JSON (additive), Migration (none), Concurrency (per-command files, no shared writes), Feature flag (none; additive)

## 1. Selected technical approach
New pure module `scripts/lib/check_record.py` owns the record, environment block, allow-list, and rerun comparison. Runners emit one sidecar JSON per command into a record dir (`UNCLE_CHECK_RECORD_DIR`); `check_record.py assemble` merges them in tsv line order into `green-check.json` and flags untrustworthy entries. `build_attestation.py` reads it. `uncle-verify.py --rerun` calls the module.

## 2-3. Alternatives and why

| Alternative | Rejected because |
|---|---|
| Parse the log to derive output per command | Parallel logs interleave; digest must come from the captured spool |
| Put the record in the tsv | Breaks consumers (SI-5) |
| Rerun inside the driver only | Issue asks for a reviewer-run `uncle verify --rerun` |

Decisions: D-1 sidecar per command (no shared file under parallelism). D-2 `--rerun` opt-in, not default for PRs (deferred); when rerun was not requested, final audit receives a structured result {status: unavailable, reason: 'not requested'}, keeps its existing completion behavior, never infers a rerun pass from the transcript, and never launches rerun implicitly; a requested rerun supplies its actual outcome. D-3 allow-list is a `check_record.py` constant that enumerates every permitted environment-variable name explicitly; values are captured only for those exact names, prefixes and setter provenance never grant inclusion, and credential-bearing variables are excluded even when Uncle sets them. D-4 (replaces git archive) rerun restores an immutable executed-file snapshot, not a git archive: when the checks run, `check_record.py` records an inventory of the files actually checked (path, sha256, mode), including modified and untracked files and any recorded copy rewrites, and stores the snapshot (file contents plus a content-addressed manifest); the manifest digest is written into the record and bound to the attestation. Rerun materializes that snapshot into a temp dir, verifies every file hash against the recorded digest before executing any command, and fails with a nonzero 'snapshot-mismatch' result if any differ or are missing. Verification and rerun never require a project commit or a clean working tree. D-5 cwd containment: the sidecar stores each cwd relative to the executed root (never absolute). On rerun, each cwd is resolved inside the rerun root, and before any command executes, absolute paths, `..` traversal, and symlink resolution outside the rerun root are rejected, reporting unavailable with a nonzero exit.

D-5 (AR-014): stagegate.sh always passes the final audit a structured rerun result with a status of passed, mismatch, or unavailable. When rerun is not requested the result is {status: unavailable, reason: 'not requested'}. The final audit keeps its existing completion behavior, must not launch a rerun implicitly, and must not infer a rerun pass from the transcript. Requested reruns supply their actual outcome.

## 4. Restrictions

| ID | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|
| R-1 | USER (request Questions) | AC-6 | no credential recorded; only explicitly enumerated variable names captured, PATH omitted | allow-list constant in check_record.py holding an exact, finite enumeration of environment-variable names. Values are captured only for names in that list. No selection by name prefix or by who set the variable ("Uncle-set" provenance never grants inclusion). Credential-bearing variables (tokens, keys, secrets, passwords, auth/cookie variables) are excluded even when Uncle sets them. PATH is omitted from value capture; only resolved tool versions are recorded. Any name not listed is absent from the record. | Absence tests assert the recorded environment keys are a subset of the constant and that a planted credential-named variable (including one with an Uncle prefix) never appears. | CAP-env | CODING |
| R-2 | REPOSITORY (tsv consumers) | AC-1, AC-9 | tsv unchanged | sidecar only |  | CAP-tsv | CODING |
| R-3 | USER (proposal 4) | AC-4 | unavailable not pass | assemble validates |  | CAP-assemble | CODING |

Rerun timeout rule: for each recorded command the effective timeout is the lesser of its recorded timeout and a positive `--rerun-timeout S` value. Omitting the option preserves the recorded timeout; a longer S never extends it. S must be a finite number greater than zero: zero, negative, non-numeric, NaN or infinite values are rejected before any command executes, with a nonzero exit and a usage message. A command exceeding its effective timeout is reported as a mismatch (timed out), not a pass.

Feasibility: shell_syntax.py:57 and run_check.py:36-52 and parallel_checks.py:209 inspected; all can emit the sidecar. Rerun needs git and a temp dir; no live credentials.

## 5. Not to modify
Signing code, gate logic, `green_classify`, `envelope.py` (use existing `extra`/`evidence`).

## 6. Data flow
command → runner writes `<dir>/<n>.json` (argv, cwd, status, pipefail, start, duration, timeout, output sha256) → assemble → `green-check.json` → build_attestation (evidence digest + env block via `extra`) → uncle-verify --rerun.

## 8. Interfaces
`uncle verify --rerun [--rerun-timeout S]`; `check_record.py assemble|environment|rerun`. Envelope gains `environment` and `executed_tree` keys via `extra`.

## 12. Error behavior
See spec section 8. Rerun runs only after checks 1-9 succeed; prints each command before running it.

## 14. Rollback
Revert the commit; additive files only; old attestations still verify.

## 16-17. Test strategy

New `scripts/tests/check-record-test.py` (hyphenated), added to `critical-suites.txt`; each field has a remove-it-and-fail assertion; pipefail tests through all three wrappers. Rerun cases: match/mismatch; dirty fixture repo (signing disabled, no new commit) with modified and untracked files and a recorded rewritten copy must match and replay; snapshot-digest tamper reports snapshot-mismatch before any command runs; each recorded environment field altered one at a time and a missing tool each give nonzero environment-mismatch with a sentinel file proving no command ran; browser-requiring record gives unavailable, nonzero, sentinel absent; absolute, `..` and symlink-escaping cwd rejected before execution; parameterized --rerun-timeout (omitted, shorter, longer, zero, negative, malformed); legacy attestation fixture asserts base verification success plus rerun unavailable and nonzero exit. Environment: recorded keys are a subset of the enumerated constant, canary credential variables (including an Uncle-prefixed one) are absent from the environment block and green-check.json, and a canary exported in the parent is absent from a rerun child that dumps its environment. Existing build-attestation, green-check and tree-attested-final-audit tests extended; the latter asserts the no-rerun audit input is exactly unavailable with reason 'not requested' and that no rerun process is spawned.

## 18. Manual verification
Run `uncle verify --rerun` on a real attestation and confirm a deliberately altered command output reports a mismatch.

## 19. Observability
Rerun prints per-command match/mismatch lines.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/check_record.py` (new) | record, assemble, env, rerun | AC-1..7 | Low | check-record-test.py |
| `scripts/lib/run_check.py` | emit sidecar (cwd stored relative to executed root) | AC-1,4 | Medium | green-check-test.sh |
| `scripts/lib/parallel_checks.py` | emit sidecar (cwd stored relative to executed root) | AC-1,4 | Medium | green-check-test.sh |
| `scripts/lib/green-check.sh` | set record dir, call assemble | AC-1 | Medium | green-check tests |
| `scripts/lib/background-verify.sh` | note ran-in-copy and rewrites; record snapshot inventory and digest of the executed copy | AC-3 | Low | check-record-test.py (untracked file and rewrite captured in snapshot) |
| `scripts/lib/build_attestation.py` | read json, env block, unavailable rule | AC-2,4 | Medium | build-attestation-test.py |
| `scripts/uncle-verify.py` | `--rerun [--rerun-timeout S]`. Preflight, all before any recorded command executes (any failure exits nonzero, runs nothing, never claims a match): (1) validate S up front as a positive finite number (omitted is allowed); invalid S exits nonzero; the per-command timeout is min(recorded timeout, S). (2) A valid legacy attestation without a command record reports rerun unavailable and exits nonzero, while the successful base-verification result is preserved and reported separately. (3) Restore the recorded executed-file snapshot (manifest of hashes plus copied files, incl. untracked files and rewrites) into a temp dir, and verify the manifest digest bound to the record; no commit or clean tree required. (4) Resolve each recorded cwd relative to the rerun root (the temp dir); reject absolute, `..` traversal, or symlink-escaping cwd. (5) Compare every recorded environment field (tool versions, platform, allow-listed variable values) exactly against the rerun host, with no normalization; a missing tool or differing value yields a nonzero environment-mismatch result naming each differing field. (6) Scan recorded commands for browser-requiring checks (recorded browser flag or known browser-driver invocation); if any, report unavailable (reason 'browser required') and exit nonzero, with no skip-and-pass. Only then replay. Ordinary verification unchanged. | AC-7, AR-005 | Medium | check-record-test.py: timeout omitted, shorter, longer, zero, negative, malformed; legacy attestation (unavailable, nonzero, base verification result preserved); snapshot digest match, tampered file, untracked input, dirty tree without commit; absolute cwd, `..` traversal, symlink escape, in-root cwd pass; env match, differing value, missing tool (nonzero, no command executed); browser-command fixture (unavailable, nonzero, no command executed, no skip-and-pass). |
| `scripts/stagegate.sh` | pass structured rerun result to final audit; when rerun is not requested pass {status: unavailable, reason: 'not requested'} without launching or executing a rerun and without inferring a pass; audit completion is unchanged | AC-8 | Medium | tree-attested-final-audit-test.sh (cases: rerun match, rerun mismatch, rerun unavailable, not requested; not-requested must complete as before and not trigger a rerun) |
| `scripts/tests/check-record-test.py` (new), `scripts/tests/critical-suites.txt`, `scripts/README.md` | tests, registry, docs | AC-9 | Low | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | SB-1, 2 | SI-3, 5 | run_check, parallel_checks, green-check.sh | check-record-test.py | none |
| AC-2,3 | SB-3, 4 | SI-2 | build_attestation, background-verify | check-record-test.py | inspect envelope |
| AC-4,5 | SB-5, 6 | SI-1, 4 | check_record, wrappers | check-record-test.py | none |
| AC-6 (record capture and rerun execution): no credential recorded, and rerun launches commands with a fresh environment containing only explicitly permitted execution variables; credential variables are never inherited from the reviewer's environment. | SB-3 | SI-2, rerun execution environment is built from an explicit allow-list, never from os.environ inheritance | check_record | check-record-test.py (capture absence test, plus rerun child-environment test: seed fake credential variables in the parent, run a recorded command that dumps its environment, assert none are present and only permitted names appear) | none |
| AC-7,8: rerun replays from the immutable executed-file snapshot bound by digest to the record and compares the recorded environment exactly before execution; any missing or differing field gives a nonzero environment-mismatch result and no commands run; a legacy attestation without a command record makes --rerun report unavailable and exit nonzero while base verification stays successful | SB-7, 8, 9, rerun with a browser-requiring recorded command reports unavailable, nonzero, executes nothing | — | uncle-verify, stagegate | check-record-test.py, check-record-test.py: rerun replays modified and untracked files from the snapshot in a dirty tree with no commit or clean tree; manifest digest mismatch, tampered or missing snapshot file reports snapshot-mismatch before any command runs, check-record-test.py: rerun of a record containing a browser-requiring command reports unavailable, exits nonzero, executes no commands, check-record-test.py: env-diff and missing-tool cases assert nonzero exit and zero commands executed, check-record-test.py: rerun-timeout cases (omitted keeps recorded; shorter wins; longer does not extend; zero, negative and malformed rejected before execution), check-record-test.py: legacy fixture asserts both rerun exit nonzero/unavailable and base verification success | rerun on real attestation |

Rerun execution-environment policy (AR-008): `check_record.py rerun` starts every recorded command with a fresh environment built from an explicit constant of permitted execution variable names (for example the minimal PATH, HOME pointing at the temp dir, locale and the Uncle-set non-credential variables recorded in the environment block). It never copies the parent environment wholesale; names are matched exactly, not by prefix or provenance, and credential-bearing variables (tokens, keys, secrets, cloud and git credentials) are never passed even if present in the reviewer's shell. This policy is separate from the capture allow-list, and a test seeds fake credentials in the parent and asserts the child cannot see them.

## Implementation sequence

1. Record module and tests. Owns snapshot capture and restore (executed files, untracked files, recorded copy rewrites, snapshot manifest digest bound to the record), the finite environment allow-list, the rerun execution-environment policy, cwd containment, timeout rule, browser scan, and environment comparison, all in check_record.py. Steps 2 and 3 only invoke these functions; they do not implement snapshot handling themselves.
   Owns: `scripts/lib/check_record.py`, `scripts/tests/check-record-test.py`, `scripts/tests/critical-suites.txt`
2. Runner emission. green-check.sh and background-verify.sh only invoke check_record.py snapshot capture (Owns text: they hold no snapshot logic of their own); run_check.py and parallel_checks.py emit sidecars with cwd relative to the executed root.
   Owns: `scripts/lib/run_check.py`, `scripts/lib/parallel_checks.py`, `scripts/lib/green-check.sh`, `scripts/lib/background-verify.sh`
   Depends on: 1
3. Attestation
   Owns: `scripts/lib/build_attestation.py`
   Depends on: 1
4. Rerun and audit
   
   Steps 2 and 3 are independent (different files) and may be batched.
   Owns: `scripts/uncle-verify.py`, `scripts/stagegate.sh`, `scripts/README.md`
   Depends on: 1, 3

## Scope cuts under time pressure

Cut first: the AC-8 requested-rerun result wiring in audit (the structured 'not requested' unavailable result of D-5 stays as the default, so audit behavior is unchanged and final audit remains well defined), then AC-3 background-verify note, then browser-driver version capture. Never cut AC-4, AC-5, AC-6, nor the immutable executed-file snapshot digest binding that makes a rerun reproduce the checked files.

## Risks
- Sidecar emission in the parallel runner could slow checks: keep it to one small file write per command.
- Rerun executes recorded commands: gated behind explicit flag and prior verification success.
- Whether the main green check ever runs in an isolated copy is unconfirmed; the record handles both.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Replay source was ambiguous: git archive ignores untracked files and copy rewrites, so replay could test different inputs than were checked. | D-4 replaced by an immutable executed-file snapshot bound by digest to the record; s12.1 rows, traceability and scope cuts updated to match. |
| AR-002 | Accepted | "Uncle-set variables" is open-ended and could admit credentials; an explicit finite name list closes the boundary. | R-1 mechanism and s3.1 restriction now require an exact enumerated name list with no prefix/provenance selection, PATH omitted. |
| AR-003 | Accepted | Rerun is opt-in (D-2), so audit wiring needs a defined absent-result state rather than silently requiring a rerun. | Add decision D-5 (structured not-requested result) to s2.2, update s12.1.r8 change/risk, and clarify AC-8 cut in s15.1. |
| AR-004 | Accepted | Replaying every recorded command conflicts with excluding browsers; silent skipping could report a false full match, so an explicit unavailable outcome is needed. | Rerun change-impact row and AC-7/8 traceability row now state: browser-requiring recorded command makes rerun report unavailable, nonzero, before executing anything. |
| AR-005 | Accepted | git archive of a commit omits modified and untracked files and would imply a commit prerequisite, contradicting the no-commit rule. | Replace D-4 with a file snapshot (manifest of hashes plus copied files incl. untracked) and update rerun row and AC-7 traceability. |
| AR-006 | Accepted | Rerun is opt-in, so final audit needs a defined not-requested input that preserves existing completion behavior. | D-2 (s2.2), s12.1.r8 stagegate row and s15.1 cut note define a structured not-requested rerun result; audit never launches rerun. |
| AR-007 | Accepted | Browser-requiring recorded commands cannot be replayed in rerun, so a full match is unprovable; an explicit unavailable outcome prevents false success or browser launches. | Rerun row (s12.1.r7) and traceability row (s13.1.r5) now state browser-dependent recorded checks yield unavailable, nonzero exit, before any command executes. |
| AR-008 | Accepted | Capture allow-list does not stop subprocesses inheriting reviewer secrets; a separate execution-environment policy is needed. | Traceability AC-6 extended and a rerun execution-environment policy block added under Traceability (s13). |
| AR-009 | Accepted | Recorded cwd needs a relocation and containment rule so replay cannot run outside its temp root. | Added decision D-5 in s2.2 (relative cwd, containment checks before execution) and aligned the rerun and runner rows. |
| AR-010 | Accepted | An open-ended 'Uncle-set variables' category could admit credentials; an explicit name list removes the ambiguity. | Edit R-1 mechanism and D-3 in s2.2 to require an explicitly enumerated name constant with no prefix or provenance selection. |
| AR-011 | Accepted | Environment comparison had no oracle; an exact pre-execution comparison makes match and env-diff tests enforce one behavior. | Rerun row (s12.1.r7) and traceability row s13.1.r5 now specify exact field comparison and a nonzero environment-mismatch result before any command runs. |
| AR-012 | Accepted | The timeout override had no precedence rule against recorded timeouts, so tests had no single expected result; the lesser-of rule is simple and keeps recorded constraints binding. | Added a rerun-timeout rule block to section 4 and updated the s12.1.r7 change and s13.1.r5 tests to cover omitted, shorter, longer, zero, negative and malformed values. |
| AR-013 | Accepted | Legacy rerun exit code was unspecified; defining it separately from base-verification status removes contradictory CLI expectations. | Edit s12.1.r7 change text and s13.1.r5 requirement/tests to state unavailable rerun exits nonzero while base verification stays successful. |
| AR-014 | Accepted | Rerun is opt-in, so final audit needs a defined not-requested input and a test for it. | Added decision D-5 in s2.2, updated s12.1.r8 stagegate row, and s15.1 cut order. |

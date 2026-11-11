# Change plan

Omitted sections: Schema/persistence (none); Concurrency (none); Migration (none); Feature flag (additive files, none needed); Observability (none)

Issue 251

Seeded from [unclehq/uncle#251](https://github.com/unclehq/uncle/issues/251).

## 1. Selected technical approach
The grant and build-script fixes live outside this repo and cannot be done here. In-repo, add (D-1) a standalone pure-Python grant checker, (D-2) its Python test suite, (D-3) a handoff doc. Existing code is untouched. The plan does NOT claim to close the issue: AC-5..AC-7 stay open.

## 2. Alternatives
- Edit host_preview.py to request signed links: rejected, host already works and issue says the build script owns it.
- Do nothing in-repo: rejected, issue Tests section asks for a pre-publish grant check.

## 3. Why preferred
Smallest additive surface, testable with fixtures, zero regression risk.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
`scripts/lib/host_preview.py`, `scripts/lib/host_preview_hook.sh`, `scripts/lib/stage-config.sh`, `scripts/stagegate.sh`, `scripts/change-workflow.sh`, `skills/uncle-build/SKILL.md`, `scripts/tests/critical-suites.txt`.

## 8. Interface

CLI: `python3 -B scripts/lib/check_release_grants.py <release-definition.json>`. Exit 0 prints `OK` on stdout; exit 1 means syntactically valid JSON with no qualifying grant; exit 2 means malformed JSON, missing/unreadable file, or usage error. Every failure writes a one-line sanitized reason to stderr (no input values) and nothing to stdout. JSON objects with duplicate keys are rejected with a nonzero exit and a fixed value-free diagnostic. Only JSON boolean false qualifies for require_approval. Pure function `find_signed_link_grant(data)` returns bool.

## 12. Error and recovery
All failure paths exit nonzero with a one-line reason on stderr; no token or secret is printed.

## Decisions and restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Fix 1, Tests | AC-1, AC-2 | Grant present with require_approval false | Recursive JSON walk for matching object; parse with an object_pairs_hook that rejects duplicate keys in every JSON object. CLI contract: exit 0 prints `OK` on stdout; syntactically valid JSON with no qualifying grant exits 1; malformed JSON, duplicate keys, missing/unreadable file or usage error exits 2; every failure writes a one-line sanitized reason to stderr (fixed diagnostic for duplicate keys, containing no input values) and nothing to stdout. | Release format unknown (DESIGN, revisable) | CAP-PY (python3 present; scripts/run-python-tests.sh exists) | CODING |
| R-2 | USER | CHANGE_REQUEST Fix 3 | AC-4 | UNCLE_PREVIEW_HOST default unchanged | No edit to host_preview.py | Verified live per issue | none | CODING |
| R-3 | DESIGN | Context | AC-1 | New suite actually runs | Name `scripts/tests/release-grants-test.py`; baseline command 3 runs it explicitly | Runner default tier skips it | CAP-PY | CODING |
| R-4 | USER | CHANGE_REQUEST Fix 1,2,4 | AC-5..7 | Real release/build script/live proof | Human/external action documented in handoff | Out of repo | CAP-RELEASE, CAP-BUILD-REPO, CAP-LIVE-DAYTONA (unavailable here) | LIVE_VERIFICATION |

Coding prerequisites: none missing. Live prerequisites: release definition access, build-script repo access, hosted Daytona; evidence paths none recorded (no secrets). Live checks: issue checks 1-5, to be run by a human and posted on #251.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/check_release_grants.py` | New | Pre-publish grant check | None (new) | release-grants-test.py |
| `scripts/tests/release-grants-test.py` | New | Verify checker, defect cases | None | self; run by command 3 |
| `docs/preview-link-release.md` | New | Handoff of external work and live checks | None | test asserts presence of grant path |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1. All AC-1 and AC-2 test cases are mandatory and cannot be cut under time pressure; this supersedes §21. | SB-1 | I-5 | check_release_grants.py | release-grants-test.py ok case (require_approval is JSON boolean false; only boolean false qualifies): asserts exit 0 and stdout `OK` | none |
| AC-2. Each case (missing grant, require_approval true or absent, wrong publisher, wrong method, wrong path, invalid JSON, missing file) is mandatory and must be verified with a nonzero exit and reason text. All AC-1 and AC-2 cases are mandatory and cannot be cut under time pressure; time pressure may defer completion but must not remove their verification. This supersedes §21. | SB-2 | I-5 | check_release_grants.py | release-grants-test.py negative cases: assert exact exit codes (1 for valid JSON without a qualifying grant; 2 for malformed JSON, missing file, usage), stdout OK only on success, and a one-line stderr reason, release-grants-test.py type-strictness cases: require_approval values 0, null, "false", arrays and objects must each be rejected (exit 1, one-line reason on stderr); only JSON boolean false qualifies, release-grants-test.py duplicate-key case: an object with both require_approval:true and require_approval:false (and a duplicate key in a nested object) exits 2 with the fixed value-free diagnostic | none |
| AC-3 | n/a | n/a | docs/preview-link-release.md | doc presence test | read doc |
| AC-4 | SB-3, SB-4 | I-1..I-3 | none modified | existing suites | File-snapshot comparison: before implementation, hash and path-inventory protected inputs (all existing files outside the three new files, including pre-existing modified and untracked files); immediately before checks, snapshot protected test paths; compare afterward without refreshing either snapshot |
| AC-5 | SB-5 | n/a | external release | none | run checker then publish |
| AC-6 | SB-6 | I-4 | external build script | external | external |
| AC-7 | SB-7 | n/a | hosted build | none | issue checks 1-5 |

## 16. Automated-test strategy

Python unittest in `release-grants-test.py` with temp-file fixtures: valid grant (nested in a list and top-level; asserts exit 0 and stdout `OK`), missing grant, require_approval true, require_approval absent, require_approval values 0, null, "false", array and object (type strictness), duplicate-key objects (including conflicting require_approval values and a nested duplicate), wrong publisher, wrong method, wrong path, invalid JSON, missing file, doc exists and names path. Failure cases assert exact exit codes (1 for valid JSON without qualifying grant; 2 for malformed JSON, missing file, usage) and a one-line stderr reason. Each negative case is a defect-injection witness: starting from the valid fixture, mutate exactly one field.

## 17. Regression strategy

Baseline commands 1 and 2 (parallel) compared pre/post. Preservation evidence: snapshot protected inputs before implementation and protected test paths immediately before checks, using hashes and path inventories that include untracked files; compare afterward without refreshing either snapshot. No existing file may differ.

## 18. Manual verification
Human runs checker on the real release definition before publishing, records the revision, runs issue checks 1-5 on a hosted build. Executed only if access exists; otherwise BLOCKED-HUMAN, never PASS.

## 14. Rollback plan
Delete the three new files. No state, schema or config changed.

## Implementation sequence

1. **Snapshot protected inputs** — Before any change, snapshot hashes and path inventories (including untracked files and pre-existing modifications) of all protected inputs outside the three new files. Write the snapshot to a driver-owned artifact path; never refresh it afterward.
2. Checker and tests: write `scripts/lib/check_release_grants.py` and `scripts/tests/release-grants-test.py` together (the test imports the checker, so they are one dependent unit). Exit codes: 0 OK (stdout `OK`); 1 valid JSON without a matching/qualifying grant; 2 malformed JSON, duplicate keys, unreadable/missing file or usage error. The checker parses JSON with a duplicate-key-rejecting object_pairs_hook that emits a fixed diagnostic and never echoes input values. Every failure writes a sanitized one-line reason to stderr. Tests assert exact exit codes, `OK` on stdout for success, the one-line stderr reason for each failure, and include a duplicate-key case. All AC-1 and AC-2 cases are mandatory and cannot be cut under time pressure; this supersedes §21 scope-cut wording. Reqs AC-1, AC-2; decisions R-1, R-3.
   Owns: `scripts/lib/check_release_grants.py`, `scripts/tests/release-grants-test.py`
   Depends on: 1
3. Handoff doc: `docs/preview-link-release.md` listing the grant, build-script requirements, live checks, and that they are not done here. Reqs AC-3. Independent of step 1 except the doc names the CLI usage (path fixed above).
   Owns: `docs/preview-link-release.md`
   Depends on: 1
4. Reconcile: before step 1, snapshot protected inputs, and immediately before checks, snapshot protected test paths, using file hashes and path inventories that include untracked files (do not rely on git diff alone). Run `bash scripts/run-python-tests.sh -- release-grants`, then compare against the snapshots without refreshing either one and confirm the only differences are the three new files in the change-impact table and no edits outside the table.
   Depends on: 2, 3, 1

Scope-cut override: all AC-1 and AC-2 test cases are mandatory and cannot be cut under time pressure; this supersedes the 'negative cases beyond missing grant/require_approval' cut in section 21. Only the doc-presence test (AC-3) may be cut first.

## 21. Scope cuts under time pressure

All AC-1 and AC-2 test cases are mandatory and cannot be cut under time pressure. Only the doc-presence test (AC-3) may be cut first, and only if AC-3 is verified by a manual read of the doc.

## 22. Risks and unresolved questions
| ID | Risk | Handling |
|---|---|---|
| K-1 | Release definition format differs from checker assumption (key names) | Tolerant walk; revise mechanism once real file is seen (DESIGN) |
| K-2 | In-repo merge mistaken for issue closure | Plan and doc state AC-5..AC-7 remain open |
| K-3 | New suite not run by default tier | Baseline command 3 runs it explicitly |

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Real conflict: the section 21 cut rule allowed dropping negative cases that AC-2 requires. | AC-2 and an s15 block make all AC-1/AC-2 cases mandatory and uncuttable, overriding section 21. |
| AR-002 | Accepted | Git diff cannot show preservation against the starting workspace with pre-existing and untracked changes; hash and inventory snapshots can. | AC-4 manual evidence and step-3 now require pre-change/pre-check hash and path-inventory snapshots including untracked files, compared without refresh. |
| AR-003 | Accepted | Malformed JSON had no assigned exit code; fixing it to 2 makes the CLI contract unambiguous and testable. | Section 8 interface (s8.1 R-1 mechanism) and step-1 now state malformed JSON exits 2 with a one-line stderr reason; valid JSON without a matching grant exits 1; AC-2 asserts exact codes. |
| AR-004 | Accepted | Git diff alone misses untracked and pre-existing changes; hash and inventory snapshots make preservation evidence reproducible. | AC-4 traceability and step-3 now require pre/post hash and path-inventory snapshots including untracked files, compared without refreshing. |
| AR-005 | Accepted | Duplicate keys let conflicting require_approval values pass depending on parser precedence, so exact matching needs a defined policy. | R-1 mechanism, AC-2 requirement/tests and step-1 now reject duplicate keys with a fixed value-free diagnostic. |
| AR-006 | Accepted | Exact matching (I-5) requires JSON boolean false only; Python 0 == False would otherwise slip through untested. | AC-2 traceability row now requires tests rejecting require_approval 0, null, "false", arrays and objects; AC-1 notes only boolean false qualifies. |
| AR-007 | Partially accepted | Real conflict: §21 allowed cutting AC-2 cases. I can't edit §21 here, so a binding no-cut rule goes in AC-1, AC-2 and step-1, which supersedes §21. | AC-1, AC-2 and step-1: all AC-1/AC-2 cases are mandatory and cannot be cut under time pressure; this overrides §21. |
| AR-008 | Accepted | Malformed JSON had no exit-code class and nonzero-only assertions allow incompatible CLIs; exact codes and streams are cheap to pin. | Edit AC-1, AC-2, R-1 and step-1 to fix malformed JSON as exit 2, no-grant as exit 1, and assert exact exit codes, stdout OK and one-line stderr reasons. |

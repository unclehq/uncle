# Change plan - Issue 280 (--no-footprint)

Seeded from [unclehq/uncle#280](https://github.com/unclehq/uncle/issues/280).

Issue 280

Omitted sections: Schema/persistence (one journal key only, in 9); Concurrency (single-process engine, unchanged); Migration (none); Observability (one terminal line)

## 1. Selected technical approach

Flag `--no-footprint` sets `UNCLE_NO_FOOTPRINT=1`; the PR engine records `no_footprint` in its journal at `start` and every later action reads the journal. A new pure module `scripts/lib/footprint.py` holds the domain logic (disclosure resolution, body rendering, vendor-line stripping, vocabulary scan). The engine's `snapshot` gets a bare variant that omits `.uncle/**`, root FINAL_AUDIT.md, attestation files and managed `.gitignore` lines. Exact path rule for bare snapshots: everything under `.uncle/` is excluded; root-level files whose stem (name without extension) is PROJECT_PLAN, CHANGE_PLAN, CHANGE_SPEC, IMPLEMENTATION_NOTES or VERIFICATION_REPORT are excluded; root FINAL_AUDIT.md and explicitly identified attestation outputs are excluded; every other path outside `.uncle/` is preserved unchanged, so legitimate source files with similar names in subdirectories are never dropped. All new behavior sits behind `if no_footprint(j)` so the default path executes the same code as today.

## 2-3. Alternatives and why
| Alternative | Rejected because |
|---|---|
| Post-filter the commit tree after snapshot | `validate` rebinds the tree at several points; filtering in one place diverges |
| Rewrite the PR after creation | pushes artifacts first; trace remains in history |
| Separate engine copy | duplicates 2000 lines; default drift risk |
| Selected: variant parameter in `snapshot` plus pure helper module | single binding point, default path untouched |

## 4. Components to modify
See change-impact table.

## 5. Not to modify
`attestation.py`, `build_attestation.py`, `handoff_export.py`, `uncle verify`, audit/verdict scripts, gate scripts, agent adapters, the `closing_trailer` BEGIN/END block (reused as is).

## 6. Data flow
`uncle --no-footprint` -> env -> `change_pr_engine start` -> journal `no_footprint=true` -> `snapshot(bare)` for reviewed_tree/commit_tree -> `handoff`: `footprint.render_body(inputs)` -> `footprint.scan(title, body, message, branch)` -> `automatic_commit` with composed message -> push -> `gh pr create`.

## 7. State transitions
None new. Phases unchanged.

## 8. Interface changes
- CLI: `--no-footprint` (usage text, pre-scan lists at `uncle:233,252,341`, parse at `:347`).
- Config keys `footprint.disclosure`, `footprint.trailer`, `footprint.name_uncle`; env `UNCLE_FOOTPRINT_DISCLOSURE`, `UNCLE_FOOTPRINT_TRAILER` (env beats config beats default).
- `footprint.py` API: `resolve_disclosure(config, env)`, `render_body(summary, why, testing, followups, closing, disclosure)`, `render_message(title, summary, trailer)`, `strip_vendor_lines(text)`, `scan(fields, allow_uncle)`.

## 9. Persistence
Journal gains optional boolean `no_footprint`; absent = false.

## 10. Compatibility
Flag absent => flag-off branches only. Old journals valid.

## 12. Error and recovery
Scan failure raises ValueError before the `prepared` phase save, so no commit/push occurs; rerun after the text is corrected. In bare mode `assert_tree_matches_attested` requires zero tracked/staged `.uncle/` paths and skips the ignored-artifact check (artifacts are intentionally untracked). A `.gitignore` whose stripped content is empty and absent at HEAD is omitted from the tree.

## 13-14. Rollback
Flag-off path is the existing code; revert the commit or stop passing the flag. No data migration.

## 15. Containment
Opt-in flag; default untouched; journal records the mode so a resume cannot flip it.

## Decisions (routine, resolved)

| ID | Decision | Reason |
|---|---|---|
| D-1 | Trailer default `Assisted-by: AI tooling`; body line per spec assumptions | neutral, matches emerging projects' policy form |
| D-2 | Policy override via `.uncle/config` + env (env beats config beats default). Validation: an empty or whitespace-only disclosure override, from env or config, is invalid and rejects publication before any publication write (no fallback to the default, no silent removal); only the commit trailer may be empty, which omits the trailer. | existing config style; no new file; keeps the mandatory body disclosure (I-3) from being erased by configuration |
| D-3 | Driver alone composes the commit message (text only); vendor lines stripped from generated text. Composing the message never invokes git signing. | agent CLI attribution (Q4) is replaced by the one disclosure; message preparation is separated from signed commit execution (see D-8) |
| D-8 | Signing boundary: automatic_commit never invokes a signer, GPG agent or pinentry. When a project commit requires signing, the driver presents the exact git command (with the composed message) for the user to run, then verifies the resulting commit; it never retries or falls back to an unsigned commit. Test fixtures commit with -c commit.gpgsign=false, --no-gpg-sign. | binding Git-signing rules prohibit automatic use of the user's signing keys |
| D-4 | NOT_READY/unattended-waiver details stay local; PR is draft with one neutral note | keeps gates (draft) without Uncle audit vocabulary |
| D-5 | What/Why from the change request Summary/Motivation or the human's prompt answers; Testing from the plan's verification commands | project's own commands |
| D-6 | Branch fallback prefix `change/`; no labels | removes `uncle/` |
| D-7 | Greenfield `stagegate.sh` attestation generation is skipped when the persisted journal mode is no-footprint; the guard is mandatory and not cuttable. On resume, stagegate derives its attestation decision from the persisted journal mode; `UNCLE_NO_FOOTPRINT=1` selects the mode only when initializing a new run. | no attestation file in mode (AC-2 forbids producing one, so the guard cannot be a scope cut); the journal is authoritative, so a resume with a different env value can neither suppress attestation in a default-mode journal (AC-7) nor produce it in a no-footprint journal |

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Desired behavior | AC-1 | no Uncle files in diff | bare `snapshot` | CAP-GIT | `snapshot` change-pr.sh:918-1060 inspected; temp index, no user-index writes | CODING |
| R-2 | USER | CHANGE_REQUEST Decisions | AC-2 | no attestation | skip `attest`, attach, handoff export, stagegate attest (stagegate guard mandatory, not cuttable) | CAP-GIT | attest call sites 1919-1932, 212, stagegate.sh:490 | CODING |
| R-3 | USER | CHANGE_REQUEST | AC-3, AC-5 | maintainer-style, no Uncle vocabulary | `footprint.render_body`, `scan`; the scan runs before any publication write: leak rejection precedes branch/index updates, commits, pushes and gh mutations, while temporary-index snapshots and local object creation may occur before scanning | CAP-PY | pure Python, stdlib | CODING |
| R-4 | USER | CHANGE_REQUEST | AC-4 | disclosure present | defaults + overrides; scan(fields, allow_uncle) gives tracked project content no exemption: publication fields (title, body, message, branch) may never name Uncle, and Uncle is permitted only in the rendered disclosure line, and only when footprint.name_uncle is true (allow_uncle applies to that line alone) | CAP-PY | config read pattern uncle:478 | CODING |
| R-5 | USER | CHANGE_REQUEST Open Q2 | AC-6 | gates not weakened | no edits to `validate` gate logic | CAP-GIT | validate 1117-1146 | CODING |
| R-6 | USER | CHANGE_REQUEST | AC-7 | default byte-identical | flag-off branches; golden test | CAP-PY | existing suites | CODING |
| R-7 | REPOSITORY | AGENTS/CLAUDE rules | all | no weakening of existing tests; new suite in critical tier | add to critical-suites.txt | CAP-PY | scripts/tests/critical-suites.txt | CODING |

Runner binding: Python tests via `bash scripts/run-python-tests.sh`; fixture git commands use `-c commit.gpgsign=false`, `--no-gpg-sign`. LIVE_VERIFICATION: none needs credentials; `gh` calls are stubbed in tests; a real PR creation is a manual check only.

## 16. Automated-test strategy

New `scripts/tests/no-footprint-test.py` (hyphenated name; loads the engine the way `pr-auto-commit-test.py` does, and `footprint.py` directly). Required explicit command beyond baseline: `bash scripts/run-python-tests.sh -- no-footprint`; the suite is also added to `critical-suites.txt` so default runs include it. Cases map to AC-1..AC-8; leak-injection and staged-artifact negatives are the defect-injection evidence. Additional cases: (a) bare-tree inventory with root files of each listed stem (PROJECT_PLAN, CHANGE_PLAN, CHANGE_SPEC, IMPLEMENTATION_NOTES, VERIFICATION_REPORT), FINAL_AUDIT.md, plus a legitimate nested file with a similar name and an unrelated file, asserting exactly the specified paths are excluded and all others preserved; (b) leak injection snapshots refs and the user index before and after the rejected run, asserting both unchanged and zero commit, push and gh mutation calls; (c) a stub gpg program recording invocation, run with commit.gpgsign=true, asserting the signer is never invoked and the exact user-run command is emitted; (d) a fixture repo whose tracked files contain the word uncle, asserting rejection in title/branch/message/non-disclosure body and acceptance only in the disclosure line with name_uncle=true.

## 17. Regression strategy

Baseline commands `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` (group `1 2`) must match baseline; default-mode golden comparison (AC-7); `pr-closes-refs-test.sh` marker extraction must still work. Resume matrix tests: default-mode journal resumed with `UNCLE_NO_FOOTPRINT=1` still attests; no-footprint journal resumed without the env still skips attestation.

## 18. Manual verification
M-1: in a throwaway repo with a stub or fork remote, run a change with `--no-footprint`; `git show --stat` and the PR page show only source files, maintainer-style body, disclosure. M-2: same without flag shows today's output.

## 20. Implementation sequence

1. Pure helper module `scripts/lib/footprint.py` (disclosure resolution incl. empty/whitespace rejection, body/message rendering, vendor-line stripping, scan). Its tests live in step 5's `no-footprint-test.py`; step 1 owns no test file.
   Owns: `scripts/lib/footprint.py`
2. Engine changes: journal flag, bare snapshot, validate variant, `assert_tree_matches_attested` bare mode, body/commit/branch/attestation branches, scan call, handoff skip
   Owns: `scripts/lib/change-pr.sh`
   Depends on: 1, 3, 4
3. CLI flag, usage, exports, stagegate attestation guard
   Owns: `uncle`, `scripts/stagegate.sh`
4. Docs
   Owns: `README.md`
5. Test suite and tier registration (can be written alongside 1-3 from the contracts above; finalized after 2)
   Owns: `scripts/tests/no-footprint-test.py`, `scripts/tests/critical-suites.txt`
   Depends on: 1, 2
6. Reconcile: run the baseline commands and the explicit new-suite command; owns no source files, and routes any fix back to the step that owns the file.
   Owns: `[]`
   Depends on: 2, 3, 4, 5

## 21. Scope cuts under time pressure

Cut first: config-key policy overrides (keep env), opt-in naming (B-9), branch prefix (D-6). Never cut: bare tree (R-1), no attestation (R-2), scan (R-3), disclosure (R-4), default byte-identity (R-6). The stagegate attestation guard (D-7) is mandatory and cannot be cut; greenfield runs in no-footprint mode must not invoke attestation generation.

## 22. Risks
| Risk | Mitigation |
|---|---|
| Tree-binding divergence | one `bare` selector read from journal in every `snapshot` call; test validate round trip |
| Default drift | golden comparison; flag-off code unchanged |
| Failing audit hidden from PR reviewer | draft status plus neutral note; submitter sees findings locally; documented in README |
| Scan false positives (word `uncle` in project) | allowed only if present in the project's own tracked files; otherwise refuse and tell user to edit |

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/footprint.py` (new) | pure body/message/disclosure/scan logic | domain logic apart from engine | Low | no-footprint-test.py |
| `scripts/lib/change-pr.sh` | bare snapshot, journal flag, body/commit/branch/attestation branches, assert variant | core of the mode | High | no-footprint-test.py, pr-*-test |
| `uncle` | accept flag, usage, export env | entry point | Low | no-footprint-test.py |
| `scripts/stagegate.sh` | skip build_attestation when flag set | no attestation file | Low | no-footprint-test.py (grep/guard) |
| `scripts/tests/no-footprint-test.py` (new), `scripts/tests/critical-suites.txt` | new suite in critical tier | coverage | None | self |
| `README.md` | document mode, limits, disclosure | AC-8 | None | grep check |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | B-2, B-12, entry preflight: before `start` in no-footprint mode, reject repositories with excluded artifacts (.uncle/**, root FINAL_AUDIT.md, attestation outputs, managed .gitignore lines) tracked at HEAD or present in the user index, without altering either, and list the conflicting paths. | I-1 | change-pr.sh snapshot | no-footprint-test.py (includes negative cases: artifact tracked at HEAD and artifact staged in the user index each reject at start, leaving HEAD and index unchanged, with conflicting paths named) | M-1 |
| AC-2 | B-3 | I-1 | change-pr.sh, stagegate.sh | no-footprint-test.py | M-1 |
| AC-3 | B-4, B-10 | I-2, I-3 | footprint.py, change-pr.sh | no-footprint-test.py | M-1 |
| AC-4: The only exception for naming Uncle is the rendered disclosure line, and only when footprint.name_uncle is true; scan(fields, allow_uncle) applies allow_uncle to the disclosure line alone, not field-wide. The word 'uncle' in tracked project files grants no exemption, and titles, branches, messages and other body text are always scanned. The disclosure line is always present in the body. An empty or whitespace-only disclosure override (from config or env) is invalid and rejects publication before any publication write; only the commit trailer may be empty. | B-5, B-6, B-9 | I-3 | footprint.py | no-footprint-test.py (includes: word 'uncle' present in tracked project files still rejected in title/branch/message, name_uncle=true allows it only in the disclosure line, empty and whitespace-only disclosure override via config and via env each raise before any git/gh write, empty trailer override is accepted and yields no trailer while the body disclosure remains) | M-1 |
| AC-5 | B-7, B-8 | I-2 | footprint.py | no-footprint-test.py (records every git write and gh call after a leak is injected, asserts no branch/ref/index update, commit, push or gh mutation occurred, permitting only temporary-index snapshot and local object creation) | - |
| AC-6 | B-10 | I-4, I-5 | change-pr.sh validate | no-footprint-test.py, pr-auto-publish-test.sh | M-1 |
| AC-7 | B-11 | I-6 | all | golden test, full suites | M-2 |
| AC-8 | B-1 | - | uncle, README.md | no-footprint-test.py | - |

Entry preflight (AR-007): before starting no-footprint mode, the engine rejects repositories where any excluded artifact is tracked at HEAD or present in the user index. It does not alter HEAD, the index or the working tree, and it names the conflicting paths so the user can untrack them deliberately. This keeps the bare snapshot from producing deletion diffs and prevents the completion check on tracked/staged .uncle paths from failing only after work is done.

Disclosure validation rule (AR-014): `resolve_disclosure` rejects an empty or whitespace-only disclosure override, whether from `footprint.disclosure` or `UNCLE_FOOTPRINT_DISCLOSURE`, with ValueError before the `prepared` phase save and before any publication write. Only the commit trailer (`footprint.trailer` / `UNCLE_FOOTPRINT_TRAILER`) may be empty, meaning no trailer. An unset override falls back to the default disclosure.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Cutting the stagegate guard would allow a forbidden attestation, contradicting R-2 and AC-2. | Section 21 cut list drops D-7 and states the stagegate attestation guard is mandatory and cannot be cut. |
| AR-002 | Accepted | Real conflict: an env-based stagegate guard can flip attestation behavior on resume, contradicting journal-governed mode. | D-7 now keys stagegate suppression on the persisted journal mode; env selects mode only for new runs; AC-8 text unchanged. |
| AR-003 | Accepted | The tracked-file vocabulary exception in the risks section contradicts the spec's disclosure-only, opt-in naming rule. | R-4 mechanism now states Uncle is permitted only in the disclosure line when footprint.name_uncle is true, with no exemption for tracked project content. |
| AR-004 | Accepted | Real gap: override precedence had no value validation, so an empty disclosure could erase the required body disclosure (I-3) or silently fall back. | D-2 now states that an empty or whitespace-only disclosure override (env or config) is rejected before publication writes, and only the trailer may be empty. |
| AR-005 | Accepted | The plan lacked an exact path rule outside .uncle; a precise exclusion contract makes the bare snapshot testable and avoids leaks or dropped source files. | Edit s1.1 to state the exact root-path exclusion rule for bare snapshots. |
| AR-006 | Accepted | An env-based guard can change attestation behavior when a journal of the opposite mode is resumed, violating the journal-controls-resume rule and AC-7. | D-7 now derives the stagegate attestation decision from the persisted journal mode; the env applies only to a new run; AC-7 and regression strategy updated. |
| AR-007 | Accepted | Bare snapshots would delete tracked artifacts while completion rejects tracked .uncle paths; an entry-time rejection removes the conflict before any work is done. | Add a start-time preflight rejection to s22 and AC-1 (tracked at HEAD or staged excluded artifacts, no mutation, conflicting paths named). |
| AR-008 | Accepted | The tracked-file exception contradicts the spec's explicit opt-in, disclosure-only rule and would silently disable the scan; the risk-table wording is owned by another writer. | R-4 restriction now binds scan: tracked project content exempts nothing; Uncle is allowed only in the disclosure line when footprint.name_uncle is true. |
| AR-009 | Accepted | The driver must not invoke the user's signer automatically; message preparation and signed commit execution need an explicit boundary. | D-3 now separates message composition from commit execution; added a signing-boundary decision row D-8. |
| AR-010 | Accepted | The tracked-file exception in the risk row contradicts disclosure-only opt-in naming; tracked content must grant no vocabulary exemption. | AC-4 traceability row now states Uncle is permitted only in the disclosure line when footprint.name_uncle is true, with no tracked-file exemption, and tests cover it. |
| AR-011 | Accepted | Real gap: precedence rules without validation let an empty override erase the required body disclosure (I-3). | AC-4 row: empty/whitespace disclosure override (config or env) is rejected before publication writes; only the trailer may be empty; test added. |
| AR-012 | Accepted | The tracked-file exception contradicts the spec's disclosure-only, opt-in naming rule and gives tests conflicting oracles. | AC-4 traceability row now states the single exception: Uncle only on the disclosure line when footprint.name_uncle is true, no tracked-content exemption. |
| AR-013 | Accepted | The scan ordering was ambiguous between 'before any git write' and 'before commit/push'; an explicit ordering rule makes it testable. | Add scan-ordering rule to s14 (new restriction R-8 on R-3's mechanism) and extend AC-5 behaviors/tests to assert no publication writes before rejection. |
| AR-014 | Accepted | Empty disclosure override is undefined while I-3 requires a body disclosure; one rule for config and env gives tests a single expected result. | Edited AC-4 (requirement, tests) and added a rule block in s22: empty/whitespace disclosure override rejected before publication writes; only trailer may be empty. |
| AR-015 | Accepted | The cut list made the stagegate guard optional while R-2 and AC-2 require no attestation, so the guard must be mandatory. | Section 21 (s19.1) drops D-7 from cuttable items and states the guard is mandatory; D-7 and R-2 text updated to match. |

# Change Plan — Issue 185

Seeded from [unclehq/uncle#185](https://github.com/unclehq/uncle/issues/185).

Issue 185

Omitted sections: Schema/persistence, Concurrency, Migration, Feature flag, Observability, Data-flow and State-transition (pure constant edits; no flow change)

## 1. Selected technical approach
Edit three literals in place and add one guard test that ties them together. No shared constant is introduced (shell and Python cannot share one without new plumbing).

## 2. Alternatives considered
| Alt | Verdict |
|---|---|
| Single shared defaults file read by shell and TUI | Rejected: new plumbing, exceeds issue scope |
| Test-only agreement guard (selected) | Chosen |

## 3. Why preferred
Smallest change surface; the test makes future drift fail loudly.

## 4. Components to modify

See change-impact table. Additionally: any existing test asserting the old Claude catalog length (3) or the old default id `claude-sonnet-5` is updated to the new values (12 entries, `claude-sonnet-5-5`), and each such edit is listed in IMPLEMENTATION_NOTES.md. Such updates change only the expected values, never weaken assertions.

## 5. Components not to modify
Codex/Kimi catalogs and defaults, allowlist in `scripts/reviewer-claude.sh:89-96`, agent-*.sh shims, attestation tests.

## 8. Interface changes

Picker ids/labels only. Decision D-1: keep one group named "Claude"; test_catalog_exact asserts exactly one group, that name, 12 ordered pairs, and no duplicate ids. Decision D-2: update the comment at uncle_tui.py:475-481 to say the Claude default is the explicit id `claude-sonnet-5-5`, kept in sync with stagegate.sh and reviewer-claude.sh (enforced by the new test, test_comment, which asserts the comment above DEFAULT_MODEL_FOR_RUNNER contains that literal id and not the old tier-alias phrase). Decision D-4: a stored model id absent from the catalog (e.g. old `claude-sonnet-5`) is kept as the effective model and displayed verbatim; the picker still lists exactly 12 entries, highlights none, and the stored value is not rewritten or migrated (covered by a test in s11.1).

## 10. Compatibility strategy
Old stored ids remain accepted (allowlist unchanged, no validation against the catalog); overrides keep precedence.

## 12. Error and recovery
Unchanged.

## 14. Rollback plan
Revert the three edits and delete the new test file; no data migration to undo.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST.md Desired behavior | AC-1 | Exactly one Claude group named Claude with the exact 12-entry ordered list and no duplicate ids | Replace list in uncle_tui.py:445-447 | Direct | CAP-EDIT | CODING |
| R-2 | USER | CHANGE_REQUEST.md | AC-2 | One default value | Edit 3 literals | Direct | CAP-EDIT | CODING |
| R-3 | REPOSITORY | reviewer-claude.sh:89-96 | AC-3 | Every catalog id passes the script's allowlist (bash case authoritative) | Test extracts the case pattern from reviewer-claude.sh; bash `case` is the sole authority for allow/deny; Python fnmatch is only a cross-check. The test FAILS (never skips) if the pattern cannot be extracted. Pattern and each id are passed to `bash -c` as positional arguments ($1, $2), never interpolated into the shell string. | Avoids duplicating pattern; feasibility: pattern observed at those lines | CAP-PYTEST | CODING |
| R-4 | REPOSITORY | scripts/tests naming | AC-2, AC-3 | Python test named `*-test.py` | `claude-model-defaults-test.py` | Runner collects only hyphenated names | CAP-PYTEST | CODING |
| R-5 | REPOSITORY | CHANGE_SPEC SI-4 | AC-5 | Codex/Kimi catalogs and defaults unchanged (SI-4) | `test_other_runners_unchanged` in `claude-model-defaults-test.py` compares to pre-change literals | SI-4 had no existing coverage; snapshot test enforces it | CAP-PYTEST | CODING |

Runner binding: `bash scripts/run-python-tests.sh` (verified present). No live-authentication prerequisites; LIVE_VERIFICATION: none beyond the two baseline commands.

Stored-id and allowlist rules (AR-007, AR-008): A stored or overridden model id absent from the 12-entry catalog (e.g. old `claude-sonnet-5`) is kept as the effective model and is not rewritten, migrated or rejected; the picker still lists exactly 12 entries and opens with the default row highlighted. Model ids are passed to the CLI as a single quoted argument, never interpolated into a shell string; the allowlist in `scripts/reviewer-claude.sh` is a prefix filter, not an authorization control, and ids are not validated against the catalog.

## 16. Automated-test strategy

New `scripts/tests/claude-model-defaults-test.py` (importlib load of `uncle_tui.py` as in aws-bedrock-configure-test.py:28; regex on the two scripts; bash `case` run for allowlist with each id). Tests: test_catalog_exact asserts the Claude catalog has exactly one group named Claude, its entries equal the 12 (label,id) pairs in order, and there are no duplicate ids (AC-1); test_defaults_agree asserts defaults agree, are in the catalog, and the catalog entry for the default id has label `Claude Sonnet 5.5` (AC-2, SB-2); allowlist test (AC-3): the case pattern is extracted from reviewer-claude.sh and the test FAILS (not skips) if extraction does not yield a pattern; bash `case` is the sole authority and fnmatch is only a cross-check; the pattern and each id are passed to bash as positional arguments via a subprocess argv list (e.g. `bash -c 'case "$2" in $1) exit 0;; *) exit 1;; esac' _ "$pattern" "$id"`), never by string interpolation into the shell command; test_comment asserts the comment block above DEFAULT_MODEL_FOR_RUNNER contains the literal `claude-sonnet-5-5` and does not contain the old tier-alias phrase (AC-4); `test_other_runners_unchanged` / `test_other_catalogs_unchanged` (AC-5, SI-4) snapshots the Codex and Kimi catalogs and their entries in DEFAULT_MODEL_FOR_RUNNER as literals captured from the pre-change tree, asserts equality, and asserts no Codex id is in the blanked-tier set. Shell default extraction: the test reads each script's text (never sources or executes it, so a pre-set DEFAULT_MODEL or other env override cannot affect parsing) and matches the assignment form `DEFAULT_MODEL="${VAR:-default}"` (or plain `DEFAULT_MODEL=default`) with an anchored line regex; it FAILS (not skips) unless exactly one such DEFAULT_MODEL assignment is found in each of stagegate.sh and reviewer-claude.sh, and it compares the literal default portion. Stored-id test (D-4): feeding a stored id absent from the catalog (e.g. `claude-sonnet-5`) leaves it unchanged and displayed verbatim, the catalog still has exactly 12 entries, and no entry is selected/highlighted; the stored value is not rewritten. Not a bug fix, so no fails-before regression test is required, but the new tests fail against the current tree (old catalog/default).

## 17. Regression-test strategy

Run both baseline commands (group `1 2`) and compare to the driver baseline. Before that, the implementer searches existing tests for assertions on the old Claude catalog length or default id `claude-sonnet-5`; any found are updated to the new values and each edit is listed in IMPLEMENTATION_NOTES.md. AC-5 is verified by the two baseline commands plus a new test, `test_other_runners_unchanged`, in claude-model-defaults-test.py that compares the Codex and Kimi catalogs and defaults to their pre-change literals, so SB-5 and SI-4 are enforced by an automated test rather than by inspection alone.

## 18. Manual-verification strategy

Open the TUI model picker for a Claude stage: 12 entries in order, default row shows `claude-sonnet-5-5  Claude Sonnet 5.5`; scrolling/filter works with 12 entries. With a stored model id absent from the catalog (e.g. old `claude-sonnet-5`), confirm the picker still lists exactly 12 entries with the default row highlighted, and the stored value is not rewritten.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `uncle_tui.py` | Replace MODEL_CATALOG_CLAUDE entries (443-449); set DEFAULT_MODEL_FOR_RUNNER['claude']; fix comment (475-481) | AC-1, AC-2, AC-4, D-4 | Low: picker length 12 | New test (incl. test_comment positive/negative assertion and D-4 stored-id test); existing suites |
| `scripts/stagegate.sh` | Line 282 DEFAULT_MODEL -> `claude-sonnet-5-5` | AC-2 | Low | New test |
| `scripts/reviewer-claude.sh` | Line 37 default -> `claude-sonnet-5-5` | AC-2 | Low | New test |
| `scripts/tests/claude-model-defaults-test.py` | New | AC-1..AC-4 | None | Self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: the Claude catalog has exactly one group named Claude whose 12 (label,id) entries equal the specified ordered pairs, with no duplicate ids; the test asserts group count, group name, ordered pairs and id uniqueness. | SB-1 | — | uncle_tui.py | test_catalog_exact | Picker list |
| AC-2 | SB-2, SB-3 | SI-2, SI-3 | uncle_tui.py, stagegate.sh, reviewer-claude.sh | test_defaults_agree (ids agree, default in catalog, label is Claude Sonnet 5.5) | Default row |
| AC-3 | SB-1, Stored id absent from catalog is kept unrewritten; picker keeps 12 entries with default highlighted | SI-1 | uncle_tui.py, reviewer-claude.sh | test_allowlist (bash case authoritative, pattern extraction failure fails the test, fnmatch cross-check only, positional-argument passing) | — |
| AC-4: the comment block above DEFAULT_MODEL_FOR_RUNNER contains the literal claude-sonnet-5-5 and does not contain the old tier-alias phrase (opus is the tier alias). | SB-4 | — | uncle_tui.py | test_comment (asserts comment above DEFAULT_MODEL_FOR_RUNNER contains claude-sonnet-5-5 and not the old tier-alias phrase) | Inspection |
| AC-5 | SB-5, SB-6 | SI-4 | all | Both baseline commands, test_other_runners_unchanged, test_other_catalogs_unchanged | — |

## Implementation sequence

Steps 1 and 2 touch disjoint files and are independent.

1. S-1 Update TUI catalog, default, comment (R-1, R-2, D-2)
   Owns: `uncle_tui.py`
2. S-2 Update shell defaults (R-2)
   Owns: `scripts/stagegate.sh`, `scripts/reviewer-claude.sh`
3. **S-1b Update existing tests hard-coding old Claude values** — S-1b Grep existing tests for the old 3-entry Claude catalog length or the old default `claude-sonnet-5`; update only the expected values to the new ones (12 entries, `claude-sonnet-5-5`) without weakening assertions, and record each edit in IMPLEMENTATION_NOTES.md. Owns the specific existing test files the grep finds; if it finds none, this step owns only IMPLEMENTATION_NOTES.md and records that none were found. Files found are added to the protected/owned paths.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 1, 2
4. S-3 Add guard test (R-3, R-4)
   Owns: `scripts/tests/claude-model-defaults-test.py`
   Depends on: 1, 2, 3
5. S-4 Run both baseline commands via the driver and compare
   none (no file writes)
   Depends on: 4

## Scope cuts under time pressure
Cut first: comment-wording assertion (AC-4 test, keep the edit); then manual picker check. Never cut AC-1..AC-3 tests.

## Risks and unresolved questions
- Drift of duplicated literals: mitigated by the test.
- Long picker list at narrow terminal heights: Decision D-3: rely on existing picker scrolling; verify manually.
- Unresolved: none blocking implementation.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | AC-4 needs a positive and negative assertion on the comment so it is actually tested. | s11.1 and s14.1.r1 and AC-4 now say test_comment asserts the comment above DEFAULT_MODEL_FOR_RUNNER contains claude-sonnet-5-5 and not the old tier-alias phrase. |
| AR-002 | Accepted | Display of a stored id absent from the new catalog must be specified so the 12-entry picker stays well defined. | s6.1 adds decision D-4: a stored id absent from the catalog is kept verbatim, nothing is highlighted, 12 entries listed; s11.1 adds a test for it. |
| AR-003 | Accepted | SI-4 had no automated enforcement; a snapshot test of the Codex/Kimi catalogs and defaults gives it real coverage. | Add test_other_runners_unchanged to s11.1, add R-5 restriction, and add it to AC-5 traceability tests. |
| AR-004 | Accepted | SB-2 expects the default row label, so the default-agreement test must assert it, not just id equality. | Extend test_defaults_agree in s11.1 and AC-2 tests to assert the catalog label for the default id is Claude Sonnet 5.5. |
| AR-005 | Accepted | SI-4 and SB-5 had no automated enforcement; a snapshot test of Codex/Kimi catalogs and defaults is cheap and in the new test file. | Edit AC-5 traceability row and s12.1 to add a Codex/Kimi snapshot test; add it to the s4 modified-test note. |
| AR-006 | Accepted | Existing tests may hard-code the old Claude catalog length or default id; the plan must say they are updated and recorded. | Edit s4.1 and s12.1 to require updating any such existing test and listing each edit in IMPLEMENTATION_NOTES.md. |
| AR-007 | Accepted | Picker behavior for a stored id absent from the catalog was unspecified; stating it removes ambiguity. | Added s10.3 behavior statement; AC-3 behaviors and s11 test list note the stored value is not rewritten. |
| AR-008 | Accepted | The allowlist is a loose prefix filter; the plan should state ids are never interpolated into shell strings. | Added s10.3 rule that ids are one quoted argument and the allowlist is not an authorization control; s11.1 test passes ids as positional arguments. |
| AR-009 | Accepted | Interpolating ids or pattern into a shell string would be an injection and quoting risk; positional arguments avoid it. | R-3 mechanism and section 16 text state ids and pattern are passed to bash as positional arguments, never interpolated. |
| AR-010 | Accepted | fnmatch and bash case differ, and a missing pattern must not silently skip the allowlist check. | R-3, AC-3 and section 16 make bash case the sole authority, fnmatch a cross-check only, and extraction failure a test failure. |
| AR-011 | Accepted | The plan did not say how test_catalog_exact treats groups or duplicates; making it explicit removes ambiguity. | Updated AC-1, R-1, s11.1 and s6.1 so the test asserts one group named Claude, 12 ordered pairs, and no duplicate ids. |
| AR-012 | Accepted | The comment test needed a positive assertion; checking for the literal default id makes AC-4 testable. | Updated AC-4, s11.1 and s6.1 so test_comment asserts the comment block contains claude-sonnet-5-5 and not the old tier-alias phrase. |
| AR-013 | Accepted | SB-5/SI-4 claim Codex/Kimi are unchanged but nothing asserts it; a snapshot test is cheap. | s11.1 adds Codex/Kimi snapshot test; AC-5 traceability now cites test_other_catalogs_unchanged. |
| AR-014 | Accepted | Regex extraction needs a stated form and hard-fail behaviour to avoid silent false passes. | s11.1 specifies DEFAULT_MODEL parsing form, exactly-one-match failure, and env independence. |

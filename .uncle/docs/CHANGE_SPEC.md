# Change spec - Issue 280

Omitted sections: Performance (none), Migration (none), Prototype isolation (not a prototype)

## 1. Change type
Feature (opt-in mode).

## 2. Problem statement
PRs Uncle produces carry its footprint (`.uncle/docs` artifacts, FINAL_AUDIT.md, attestation, audit-style body). Some projects want an ordinary-looking, honestly AI-disclosed PR.

## 3. Current behavior
Baseline EB-1..EB-7.

## 4. Desired behavior
With `--no-footprint` (or `UNCLE_NO_FOOTPRINT=1`), the published commit/PR contains only intended source changes, maintainer-style text, and an AI-assistance disclosure. Without it nothing changes.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| B-1 | ADD | `uncle --no-footprint ...` or env `UNCLE_NO_FOOTPRINT=1` | flag refused as unknown | accepted; recorded in PR journal at `start`; later stages follow the journal, not the env | AT-1 |
| B-2 | ADD | publish in mode | tree holds `.uncle/docs/**`, root FINAL_AUDIT.md, `.uncle/attestation.*` | commit tree has no path under `.uncle/`, no root `FINAL_AUDIT.md`, no workflow-doc artifact (PROJECT_PLAN, CHANGE_PLAN, IMPLEMENTATION_NOTES, reports), no attestation files; `.gitignore` carries no Uncle-managed lines (and is omitted if it would be newly added empty) | AT-2 |
| B-3 | ADD | publish in mode | attestation sealed and attached | none produced, committed, attached or exported (incl. handoff publish mode); body never mentions `uncle verify` | AT-3 |
| B-4 | ADD | PR body built | Uncle report-style body | sections: Summary (what and why, `Closes #N`/`Refs #N` via existing evidence rule), Testing (project's own commands), Follow-ups, AI-assistance disclosure; no banners, stage/gate/audit/disposition content | AT-4 |
| B-5 | ADD | commit created | message = title | message = title + blank + short body + trailer `Assisted-by: AI tooling` (default); vendor attribution lines (`Co-Authored-By: <AI agent>`, `Generated with ...`) not present beyond the disclosure | AT-5 |
| B-6 | ADD | project policy | n/a | `.uncle/config` keys `footprint.disclosure` (PR-body line), `footprint.trailer` (full trailer line; empty = no trailer) override defaults; env `UNCLE_FOOTPRINT_DISCLOSURE`/`UNCLE_FOOTPRINT_TRAILER` override config | AT-6 |
| B-7 | ADD | title/body/commit message contains forbidden vocabulary | n/a | publish refused before any git/gh write with a message naming the term and field; PR stays pending | AT-7 |
| B-8 | ADD | branch/labels | `uncle/` fallback prefix | fallback prefix `change/`; no labels added by Uncle | AT-8 |
| B-9 | ADD | `footprint.name_uncle true` in config | n/a | disclosure line may name Uncle; vocabulary scan allows only that line | AT-9 |
| B-10 | PRESERVE | gates | human consent, READY-or-override, draft-on-NOT_READY | unchanged; draft PR in mode carries a neutral one-line draft note only | AT-10 |
| B-11 | PRESERVE | default mode | EB-1..EB-7 | byte-identical journal body, commit tree, commit message, branch name | AT-11 |
| B-12 | ADD | local run state | `.uncle/docs/**` on disk | still on disk untracked, never staged in the user's index; completion guard accepts it | AT-2 |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | NEW | In mode, no path under `.uncle/`, root FINAL_AUDIT.md or attestation file is in the commit tree or index | publish | `snapshot` bare variant + `assert_tree_matches_attested` | AT-2 |
| I-2 | NEW | In mode, title, body, commit message contain no forbidden vocabulary (unless opted in) | publish | `footprint.scan` before any write | AT-7 |
| I-3 | NEW | Disclosure present in body and (unless policy empties it) trailer | publish | `footprint.render_*` | AT-4, AT-5 |
| I-4 | STRENGTHENED | EI-1 tree binding holds for the bare tree at start, bind, validate and commit | publish | `validate` uses same variant | AT-12 |
| I-5 | EXISTING | EI-2 publication gates unchanged | publish | `validate`, `verdict-override` | AT-10 |
| I-6 | EXISTING | Default mode output byte-identical | publish | flag-off branches only | AT-11 |
| I-7 | EXISTING | EI-3, EI-4, EI-5 | publish | unchanged | existing tests |
No RELAXED or REMOVED invariants. EI-3 is not relaxed: in mode the allowlist is empty (stricter).

## 7. Compatibility
Flag absent => no change. Journals without `no_footprint` read as false.

## 8. Error and failure behavior
- Leak scan failure: raise ValueError, nothing committed or pushed, rerun after editing text.
- Journal/env mismatch on resume: journal wins.
- Failing/NOT_READY audit: draft PR, findings stay local; terminal says so.

## 10. Security
No secrets in text; scan covers title, body, commit message, branch name. Disclosure is never removable by the flag itself.

## 12. Rollback
Drop the flag; default path untouched. Unmerged PRs closed by the human.

## 14. Non-goals
Changing approval gates; hiding AI use; changing attestation or `uncle verify`; rewriting history of already-published PRs; scrubbing the agent CLIs' own logs.

## 15. Assumptions
Forbidden vocabulary (case-insensitive): `uncle`, `.uncle`, `attestation`, `uncle verify`, `FINAL_AUDIT`, `PROJECT_PLAN`, `CHANGE_PLAN`, `CHANGE_SPEC`, `IMPLEMENTATION_NOTES`, `VERIFICATION_REPORT`, `adversarial`, `gate`/`stage` as whole words with a following number or `approval`. Default disclosure: `This change was developed with AI assistance. The submitter has reviewed it and is accountable for it.` Trailer: `Assisted-by: AI tooling`.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | With --no-footprint (or UNCLE_NO_FOOTPRINT=1) the commit tree contains no path under .uncle/, no root FINAL_AUDIT.md, no workflow-document artifact and no attestation file; only source changes remain, and Uncle-managed .gitignore lines are absent. | scripts/tests/no-footprint-test.py builds a fixture repo with .uncle/docs artifacts, FINAL_AUDIT.md and a managed .gitignore, runs the engine snapshot in mode, and asserts the tree listing equals the source files only. Regression: staging an artifact makes it fail. |
| AC-2 | No attestation is produced, committed, attached to the body or exported in mode, and the PR text never references uncle verify. | no-footprint-test.py asserts attest() and attestation attach_body are not reached, no .uncle/attestation.* in tree, hand-off publish mode skips attest-handoff, and body lacks 'verify'. |
| AC-3 | The PR body is maintainer-style (Summary with issue link, Testing, Follow-ups, AI disclosure) and contains no Uncle stage, gate, audit, banner or disposition content, even when the audit verdict was NOT_READY or the run was unattended. | no-footprint-test.py renders bodies for READY, NOT_READY-override and unattended cases; asserts required headings and absence of the forbidden vocabulary and audit sections; a seeded audit section in the input makes the test fail. |
| AC-4 | The body carries the AI-assistance disclosure and the commit carries the Assisted-by trailer by default; project config/env can override text or empty the trailer; Uncle is named only with footprint.name_uncle true. | no-footprint-test.py checks default text, config override, env precedence over config, empty trailer, and opt-in naming. |
| AC-5 | Title, body, commit message and branch name containing forbidden vocabulary, or vendor attribution lines beyond the disclosure, are refused (vendor lines in generated text are stripped) before any git or gh write. | no-footprint-test.py injects leaks into each field and asserts ValueError with no commit/push/gh call recorded, and that vendor attribution lines are not in the final message. |
| AC-6 | Approval gates are unchanged in mode: consent prompt, READY-or-override rule, draft on NOT_READY, tree-binding validation; tree binding holds across start, bind, validate and commit. | no-footprint-test.py runs validate() on a mode journal and mutates a source file (expects refusal); existing pr-auto-publish-test.sh and pr-reconcile-test.py remain green. |
| AC-7 | Without the flag, journal body, commit tree, commit message and branch name are byte-identical to before the change. | no-footprint-test.py compares default-mode outputs to golden values captured from the pre-change code path; full existing suites (run-shell-tests.sh, run-python-tests.sh) stay green versus baseline. |
| AC-8 | uncle accepts --no-footprint, lists it in usage, and README documents the mode, its limits (draft/NOT_READY findings stay local, agent logs not scrubbed, gates unchanged) and the disclosure behavior and override keys. | no-footprint-test.py runs `uncle --help` and the flag parser; grep of README.md for the section and keys. |


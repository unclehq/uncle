# Baseline report - Issue 280 (--no-footprint)

Omitted sections: Existing failures/flaky (none documented in repo; driver baseline is authority); Reproduction (feature, not a bug)

## 1. Change-request summary
See CHANGE_REQUEST.md (Issue 280): opt-in `--no-footprint` so the PR looks like an ordinary contribution: no Uncle files in the diff, no attestation, maintainer-style text, AI-assistance disclosure, default mode byte-identical.

## 2. Repository architecture
- `uncle` (bash, 1199 lines): CLI flag parsing (`uncle:340-352`), mode resolution (`uncle:476-499`), exports env to workflow.
- `scripts/change-workflow.sh` (5323 lines): existing-code workflow; calls `change_pr_engine start` (`:4005`) and `bind` (`:5181`).
- `scripts/lib/change-pr.sh` (2201 lines): bash wrappers (`change_pr_complete_route` `:202`, `change_pr_publish` `:266`, `assert_tree_matches_attested` `:33`, `change_pr_engine` `:369`) plus an embedded Python engine (the PR journal state machine, `:384-2201`).
- `scripts/lib/attestation.py`, `build_attestation.py`, `handoff_export.py`: attestation sealing/attaching; `scripts/stagegate.sh:473-490,7271` attests greenfield builds.
- `scripts/lib/uncle_gitignore.py`: manages Uncle lines in the project `.gitignore`.

## 3. Relevant code paths (change-pr.sh engine)
| Symbol | Line | Role |
|---|---|---|
| `snapshot(audit, excludes, attestation)` | 918 | builds the tree that is committed: always adds `.uncle/docs/**` (936-940, keeps them past ignore at 949), adds root `FINAL_AUDIT.md` when audit (~1030), optionally attestation files; `.gitignore` managed lines stripped only when not audit |
| `handoff(j)` | 1805 | consent prompts, builds PR body: Work summary, Manual verification, warning/NOTE/override banners, `attest(j)`, `attestation().attach_body`, `closing_trailer` (1880-1936); push; `gh pr create` (2010) |
| `attest`/`sealed_attestation`/`attest_handoff` | 730/424/819 | seal attestation; hand-off export |
| `automatic_commit` / `prepare_commit` | 1271/1229 | `git commit --no-gpg-sign -m <title>`; signing handed to human when `commit.gpgsign` true |
| `validate(j)` | 1117 | re-snapshots and compares reviewed_tree/commit_tree |
| `sync_audit_copy` | 1258 | checks out root FINAL_AUDIT.md |
| `auto_summary` | 1366 | unattended summary text naming Uncle and `.uncle/docs/FINAL_AUDIT.md` |
| `closing_trailer` | 533 (BEGIN/END markers 485/588) | `Closes`/`Refs` + Still open |
| `label_prefix`/`branch_name` | 1408/1428 | branch prefix feat/ bug/ doc/ else `uncle/` |
| `assert_tree_matches_attested` | 33 (bash) | allowlists `.uncle/docs/*`, attestation files; errors if an attested `.uncle/docs` artifact is ignored |
| `main()` | 2035 | action dispatch (`start`, `bind`, `commit-tree`, `attest-handoff`, ...) |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| EB-1 | PR publish, default | commit tree includes `.uncle/docs/**` and root `FINAL_AUDIT.md` | change-pr.sh:936-940, ~1030 | Yes (default mode) |
| EB-2 | PR publish, default | attestation sealed, `.uncle/attestation.*` in tree, attestation block in body | change-pr.sh:1919-1932 | Yes |
| EB-3 | PR body | Work summary + Manual verification + banners + attestation + Closes/Refs | change-pr.sh:1891-1935 | Yes |
| EB-4 | commit | message is PR title only | change-pr.sh:1275 | Yes |
| EB-5 | NOT_READY audit | draft PR with warning banner and findings; human consent or override record | change-pr.sh:1895-1918, 2150-2165 | Yes (gate) |
| EB-6 | no issue label | branch `uncle/<slug>-<owner>` | change-pr.sh:1408-1430 | Yes |
| EB-7 | handoff publish mode | attest-handoff then handoff_export | change-pr.sh:212 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| EI-1 | Published tree equals audited commit_tree, byte for byte | `validate` 1117-1146 | pr-reconcile-test.py, pr-auto-commit-test.py | High |
| EI-2 | Publication needs READY verdict or recorded override/consent | `validate`, `verdict-override` 2150 | pr-auto-publish-test.sh | High |
| EI-3 | Nothing under `.uncle/` outside the allowlist is tracked/staged | `assert_tree_matches_attested` 33-46 | pr-publish-reason-test.sh | High |
| EI-4 | User's index/working files never overwritten; commit signing never invoked automatically | `snapshot` temp index; `--no-gpg-sign`; `prepare_commit` | pr-auto-commit-test.py | High |
| EI-5 | Closes only on evidence, else Refs | `closing_trailer` | pr-closes-refs-test.sh | High |

## 6. Current interface contracts
- CLI: `uncle` accepts a fixed flag set (`uncle:233-352`); unknown flags refused with code `UNCLE_REFUSE_CODE`.
- Journal `.uncle/workflow/pr/journal.json` keys incl. `reviewed_tree`, `commit_tree`, `title`, `body`, `draft`, `attestation`, `statement`.
- Config: `.uncle/config` lines `key value` (read with awk, e.g. `misc.auto_mode`, `uncle:478`).

## 7. Existing automated-test coverage
PR-related: `scripts/tests/pr-auto-commit-test.py`, `pr-reconcile-test.py`, `pr-auto-publish-test.sh`, `pr-closes-refs-test.sh` (extracts the closing_trailer block by BEGIN/END markers), `pr-publish-reason-test.sh`, `attestation-test.py`, `build-attestation-test.py`. Two runners: `scripts/run-shell-tests.sh`, `scripts/run-python-tests.sh`; default tier = `scripts/tests/critical-suites.txt`. Shell and Python suites use separate temp dirs and bind no common ports, so they form one parallel group.

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (the Uncle-documented runners). No pre-existing failure is documented here; some Python suites may fail on a clean checkout - the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. I ran no suite.

## 12. Likely change surface
`uncle`, `scripts/lib/change-pr.sh`, new pure module `scripts/lib/footprint.py`, `scripts/stagegate.sh` (attestation call guard), `scripts/tests/critical-suites.txt`, new test `scripts/tests/no-footprint-test.py`, `README.md`.

## 13. Regression-sensitive components
`snapshot` and `validate` (tree binding), `handoff` body assembly, `assert_tree_matches_attested`, `closing_trailer` helper (extracted by marker in a test - markers must stay), handoff export.

## 14. Outside the change
Attestation format/`uncle verify`, approval gates, audit verdict logic, agent CLI adapters, TUI.

## 15. Unknowns and assumptions
- Agent CLIs may add attribution lines (e.g. Co-Authored-By) only if the agent itself commits; the driver composes the PR commit message, so this is assumed not to occur in the published commit. UNRESOLVED only for agent-authored commits made before publish; handled by the leak scan.
- Whether the greenfield `stagegate.sh` merge path produces a PR is assumed no (it merges locally); guard there is for attestation file only.

## 16. Initial risk assessment
| Risk | Level |
|---|---|
| Tree-binding (`validate`) mismatch if snapshot variants diverge between start/bind/validate | High |
| Default-mode byte drift from refactoring shared body code | High |
| Uncle vocabulary leaking via model-written summary text | Medium |
| `.gitignore` managed-line residue | Medium |

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```


<<<<<<< HEAD
D = `.uncle/workflow/checklist-driver-checks/results.tsv` lines; assertions: adjacent `output.log`.
E = `/tmp/uncle-verification/`; H = `python3 -B /tmp/uncle-verification/checks.py`, exit 0; outputs/exits: E/MC-ID.json.
Baseline: `d22352cf33d4`; candidate: frozen `change.diff` applied.
Groups completed in order; all processes collected.
Expected: `MANUAL_CHECKLIST.md` IDs.
=======
## Summary
Implementation stopped under CHANGE_PLAN.md STOP-1. README.md:4,28 remain lowercase. Driver evidence covers MC-003/MC-004.

## Findings
>>>>>>> b449b41 (changes uncle to Uncle)

| ID | Action | Expected | Actual | Evidence | Status | Defect |
|---|---|---|---|---|---|---|
<<<<<<< HEAD
| MC-001 | D:2,6; H seed | MC-001 | Seed, isolation, no run/close verified | D:2,6 exit 0; H exit 0 | PASS | — |
| MC-002 | D:2; H reseed/byte comparison | MC-002 | Refusals pass; prefix loses blank line | E/MC-014.json: `Prefix\n\n` becomes `Prefix\n`, both revisions exit 0 | FAIL | D-1 |
| MC-003 | D:2; H invalid/parser-free/partial writes and retries | MC-003 | Errors refuse; 2-byte retry refuses; 64-byte retry replaces | D:2 exit 0; H exit 0 | PASS | — |
| MC-004 | D:2 barriers; H two writers | MC-004 | Collisions preserved; exactly one creator | D:2 exit 0; H exit 0 | PASS | — |
| MC-005 | Read D:1–4 and suite assertions | MC-005 | Syntax, routing, forwarding, ownership and close guards pass | D:1–4 exit 0 | PASS | — |
| MC-006 | Piped shell cases; `python3 -B /tmp/uncle-verification/tui.py` | MC-006 | PTY cases exit 0 and return; prefix loses newline | E/MC-006-final.json, MC-006-tui.json: `Prefix\n# Project brief` | FAIL | D-1 |
| MC-007 | Compare template/scope; attempt strace | MC-007 | Template matches; extra path; trace unavailable | E/MC-007.json: `.gitignore`; `strace: command not found`, exit 127 | FAIL | D-2; E-2 |
| MC-008 | H full-copy rollback of C-1–C-4 and suites | MC-008 | Seed hash unchanged; suites pass; absent target refuses | H exit 0; E/MC-008.json commands exit 0, probe 1 | PASS | — |
| MC-009 | Ignore/status probe; document/frozen diffs; `git diff --check` | MC-009 | Extra ignore rule unapproved; current whitespace clean | E/MC-009.json: `.gitignore:21:*.md release-probe.md`, exit 0 | FAIL | D-2 |
| MC-010 | `python3 -B /tmp/uncle-verification/suites.py`; baseline failure comparisons | MC-010 | 65 suites: 55 exit 0, 3 driver exits 0, 5 nonzero, 2 unavailable; skips unverified | E/MC-010.results and named suite logs: `PROJECT_ROOT: unbound variable`; limits E-1 | FAIL | D-3/D-4; E-1 |
| MC-011 | ShellCheck command on both revisions | MC-011 | Both exit 127 | E/MC-011.json: `shellcheck: command not found`; install ShellCheck | BLOCKED-SETUP | E-3 |
| MC-012 | Check supplied URL and `gh auth status` | MC-012 | Live seed/driver unexecuted; trace unmet | E/MC-012.json: URL absent, auth exit 1; Brian must supply issue/access/runners | BLOCKED-HUMAN | E-4 |
| MC-013 | Review baseline U-1 and notes U-2 | MC-013 | Reconstruction not executed | Reporter must supply original steps/files/environment; E/MC-013.log | BLOCKED-HUMAN | E-5 |
| MC-014 | H baseline/candidate probes; function diff; rollback inventory | MC-014 | Absent transition 1→0; prefix defect predates change; prompts present | H exit 0; E/MC-014.json, MC-008.json | PASS | D-1 |

## acceptance criteria summary
AC-1/AC-3 automated evidence passes; AC-2 fails D-1; AC-4 fails D-2/D-3/D-4; AR-001 barriers pass, syscall evidence missing (E-2).
## preserved behavior summary
MC-003/005/008 support baseline error/routing/ownership behavior; MC-014 corrects its prefix claim.
## changed behavior summary
MC-001/004/014: absent creation/collision refusal; MC-009: extra ignore rule.
## invariant summary
MC-001/004/005 support I-1–I-4; template shape matches I-5.
ASSUMPTION A-1: completed brief is consumed correctly; settle through MC-012 driver execution.
## regression summary
Baseline comparisons establish existing failures; no new runtime regression demonstrated.
## unresolved defects
D-1–D-4 and E-1–E-5 remain open; see DEFECTS.md.
## recommendation
Reject pending dispositions and remaining verification.
=======
| MC-001 | Validated PRE-1 (RT-2); ran T-1 with current README.md snapshot | T-1 green; only lines 4/28 change `uncle`→`Uncle` | T-1 red; lines 4/28 still lowercase | RT-2 counts passed; T-1 exit=1 AssertionError | BLOCKED-SETUP | D-001 |
| MC-002 | Ran `git diff -- README.md` and `git status --short` | Only P-1 introduced; other files preserved | README.md unchanged; 8 files modified | README diff empty; status lists 8 files | BLOCKED-SETUP | D-001 |
| MC-003 | Driver ran install-test.py | Exit 0; 10 pass, no skips | Exit 0; 10 pass, no skips | results.tsv:3; output.log OK | PASS | none |
| MC-004 | Driver ran `bash -n` on three files | Exit 0 | Exit 0 | results.tsv:4; output.log empty | PASS | none |
| MC-005 | No preview; inspected PE-1 | Heading/callout render `Uncle`; markup intact | Cannot render; Chrome probe exit 134 | PE-1 exit 134; README.md:4,28 lowercase | BLOCKED-SETUP | D-001 |
| MC-006 | Built archive+deb; compared packaged READMEs | Packaged READMEs equal candidate with changes | Packages built; extracted READMEs equal candidate but still lowercase | archive/deb exit 0; cmp passed; lines show `uncle` | FAIL | D-001 |
| MC-008 | Ran git status/diff/diffcheck/change.diff; inspected README.md:4,28 and CHANGE_TEST_REPORT.md:79,80 | Reconcile paths; empty diff does not establish completion | change.diff 0 bytes; README.md unmodified; 8 files modified (includes reviewer MANUAL_CHECKLIST.md); diffcheck exit 0 | status: 8 files; wc -c change.diff=0; diffcheck exit 0 | PASS | D-001 |
| MC-009 | Started Unix subset; stopped (no Windows runners) | All suites exit 0 on Unix+Windows | background-performance-test exit=1 (PROJECT_ROOT unbound); implementation-review-test exit=128 (gpg timeout); Windows unavailable | partial log; no Windows runner | BLOCKED-SETUP | D-002, D-003 |

## acceptance-criteria summary

| ID | Status | Checks |
|---|---|---|
| AC-1 | FAIL | MC-001/005 |
| AC-2 | FAIL | MC-001/005 |
| AC-3 | FAIL | MC-001/002 |
| AC-4 | PASS | MC-003 |
| AC-5 | PARTIAL | MC-002/004/005/008 |

## preserved-behavior summary

| ID | Status | Checks |
|---|---|---|
| B-3–B-5 | PASS | MC-001/002/005 |
| B-6 | PASS | MC-003/006 |

## changed-behavior summary

| ID | Status | Checks |
|---|---|---|
| B-1 | FAIL | MC-001/005/006 |
| B-2 | FAIL | MC-001/005/006 |

## invariant summary

| ID | Status | Checks |
|---|---|---|
| I-1 | PASS | MC-003 |
| I-2 | PASS | MC-003 |
| I-3 | FAIL | MC-001/005/006 |

## regression summary

| ID | Status | Checks |
|---|---|---|
| RG-1 | FAIL | MC-001/002/005 |
| RG-2 | PASS | MC-003/006 |
| RG-3 | PARTIAL | MC-002/004/008 |
| RG-4 | BLOCKED | MC-009 |

## unresolved defects

| ID | Defect | Affected | Fix |
|---|---|---|---|
| D-001 | README.md capitalization not implemented | MC-001/002/005/006 | Resume S-2/S-3; apply P-1; rerun T-1–T-3, M-1/M-2 |
| D-002 | background-performance-test.sh: PROJECT_ROOT unbound | MC-009 | Provide CI runner with PROJECT_ROOT |
| D-003 | implementation-review-test.sh: gpg signing timeout | MC-009 | Configure non-interactive GPG or CI agent |

## recommendation
Do not accept. Resume implementation, apply P-1, then rerun all checks. Re-run MC-009 on capable runners.

## Assumptions

| ID | Assumption | Settled by |
|---|---|---|
| A-1 | Current README.md is pre-edit state; S-1 evidence unavailable | Recovering S-1 or completing implementation |
| A-2 | Browser probe failure from PE-1 persists | Working preview or alternate M-1 method |

## Open questions

| ID | Question |
|---|---|
| O-1 | Can implementation resume with an alternative M-1 method? |
| O-2 | Are D-002/D-003 environmental or regressions? |
>>>>>>> b449b41 (changes uncle to Uncle)

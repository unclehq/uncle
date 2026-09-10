D = .uncle/workflow/checklist-driver-checks; E = /tmp/uncle-primary-verify-2103.
H = `python3 -B E/checks.py`; initial MC-001 used E/checks-initial.py.
Expected result references MANUAL_CHECKLIST.md by ID; evidence filenames below are relative to E.
MC-012 also supplied minimum-runtime evidence.

| Driver | Command record | Exit |
|---|---|---|
| D1 | D/results.tsv:1, close-flow-test.sh | 0 |
| D2 | D/results.tsv:2, pr-prompt-test.py | 0 |
| D3 | D/results.tsv:3, bash -n | 0 |
| D4 | D/results.tsv:4, tui-session-panel-test.sh | 0 |

| Check ID | Action actually performed | Expected result | Actual result | Evidence | Status | Defect reference |
|---|---|---|---|---|---|---|
| MC-001 | H MC-001, both origins | MC-001 | 12 usable defaults rejected; 20 edited submissions succeed | MC-001-*.log, exit 1: "must be nonempty" | FAIL | F-1 |
| MC-002 | H MC-002; D1 drift tests | MC-002 | Four regular defaults absent; symlink exclusion and no execution hold | MC-002.log, exit 1: "regular-default failures 4" | FAIL | F-1 |
| MC-003 | H MC-003; D1 recovery | MC-003 | Seven recovery cases retain v1 and prevent duplicates | H MC-003 exit 0; D1 exit 0 | PASS | None |
| MC-004 | H MC-004; routing-rest.py/routing-cli.py; D1 | MC-004 | Env flag prompts; CLI flag suppresses handoff | MC-004*.log: initial exit 1; "routing assertion False" | FAIL | F-3 |
| MC-005 | H MC-005; terminal cli.py | MC-005 | Framing fails; CLI backspace/edit submission succeeds | MC-005.log exit 1: "framing failures 342"; CLI exit 0 | FAIL | F-2, H-2 |
| MC-006 | Read R-2; no live publication | MC-006 | Brian's contract decision/account/sign-off absent | CHANGE_PLAN.md R-2: "UNRESOLVED" | BLOCKED-HUMAN | H-1 |
| MC-007 | Reused D1–4; inspected prompt/handoff assertions | MC-007 | Baseline counts match; planned assertions absent | D/output.log: 28/231, 5, 14; all exits 0; no P-19 tests | FAIL | F-1/2 |
| MC-008 | Revision/diff inspection; MC-012 minimum-runtime recovery | MC-008 | Minimum-runtime resume passes; rollback no-op; freeze candidate | MC-008.log; MC-012-min-recovery exit 0; MC-009-final.log adds paths | BLOCKED-SETUP | E-3 |
| MC-009 | Path/digest/source comparison | MC-009 | U-4 preserved; freeze/reconcile concurrent edits | MC-009-final.log: gates.sh/stagegate.sh/review-compaction-test.sh plus new helper | BLOCKED-SETUP | E-3 |
| MC-010 | extra.py MC-010; adapter suite; jq validation | MC-010 | 32 cases pass; rerun suite through unrestricted driver | MC-010-suite.log exit 1: "tee: /dev/fd/63: Operation not permitted" | BLOCKED-SETUP | E-1 |
| MC-011 | extra.py MC-011; three suites; minimum-runtime repeat | MC-011 | Native passes; provide Git Bash runner | MC-011-*.exit all 0; MC-012-min-env exit 0; no Windows runner | BLOCKED-SETUP | E-2 |
| MC-012 | remaining.py; minimum-runtime and budget diagnostics | MC-012 | 13/15 pass; two fail; criteria remain | MC-012-results.tsv; budget diagnostic "No such file"; background "PROJECT_ROOT: unbound variable" | FAIL | F-4/5, E-2, H-1/2/3 |

## acceptance criteria summary

| ID | Disposition |
|---|---|
| AC-1 | Existing titles covered by D1; MC-001 defaults fail |
| AC-2 | FAIL: MC-005 |
| AC-3 | FAIL: MC-001/002 |
| AC-4 | BLOCKED-HUMAN: H-1 |
| AC-5 | D1 preservation; MC-004 invocation mismatch |
| AC-6 | D1 drift and MC-002 exclusion pass; defaults incomplete |
| AC-7 | PASS: MC-003 |

## preserved behavior summary

D/output.log matches BASELINE_REPORT.md §9; MC-003 confirms recovery.

## changed behavior summary

F-1/2: planned defaults/framing remain absent; MC-010/011 cover supplied adapter/isolation edits.

## invariant summary

I-1–4 retain tested guards; I-5 title coverage remains; I-6 fails MC-001.

## regression summary

No failures in four baseline commands; F-3–5 lack executed historical-suite comparisons.

## unresolved defects

F-1–5 and E-1–3/H-1–3 in DEFECTS.md remain open.

## recommendation

Reject acceptance; resolve defects/prerequisites and verify a fixed candidate.

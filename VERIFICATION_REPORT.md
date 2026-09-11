D = `.uncle/workflow/checklist-driver-checks/results.tsv` lines; assertions: adjacent `output.log`.
E = `/tmp/uncle-verification/`; H = `python3 -B /tmp/uncle-verification/checks.py`, exit 0; outputs/exits: E/MC-ID.json.
Baseline: `d22352cf33d4`; candidate: frozen `change.diff` applied.
Groups completed in order; all processes collected.
Expected: `MANUAL_CHECKLIST.md` IDs.

| Check ID | Action actually performed | Expected result | Actual result | Evidence | Status | Defect reference |
|---|---|---|---|---|---|---|
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

# Final Change Audit: Issue 54 — Automatic Handoff Commit When Signing is Off

## Audit scope
Change diff: `.uncle/workflow/change.diff`
Specification: CHANGE_SPEC.md (AC-1..AC-7)
Plan: CHANGE_PLAN.md (C-1..C-8)
Implementation: change-pr.sh `prepare_commit` → `automatic_commit` / `manual_signed_commit`; uncle_tui.py `run_named_stage`, `_clear_workflow_identity`, `/run` command, fix/rerun prose detection
Verification: VERIFICATION_REPORT.md MC-001..MC-017
Defects: DEFECTS.md DF-1, DF-2

---

## 1. PASS claims not tied to executed evidence

All PASS results in VERIFICATION_REPORT.md document the exact command run and its exit code. All PASS results in CHANGE_TEST_REPORT.md (baseline tests, implementation checks, self-check) document execution. **No finding.**

## 2. Untested acceptance criteria

All seven ACs are tested by the T-1..T-12 tests defined in CHANGE_PLAN.md and implemented in pr-signing-test.py and pr-auto-commit-test.py. VERIFICATION_REPORT.md MC-001 runs both test files and reports exit 0 (PASS). MC-014/015/016 (PC-1/PC-2/PC-3 manual GPG checks) are BLOCKED-SETUP — they require a GPG key and cannot be run in this environment (see Finding F-2).

| AC | Test(s) | Result |
|----|---------|--------|
| AC-1 | T-1, T-6 | PASS |
| AC-2 | T-1, T-6 | PASS |
| AC-3 | T-3, T-9 | PASS |
| AC-4 | T-2, T-8 | PASS |
| AC-5 | T-2, T-11 | PASS |
| AC-6 | T-4, T-9 | PASS |
| AC-7 | T-10 | PASS |

## 3. Missing change artifacts

| Artifact | Present? | Note |
|----------|----------|------|
| CHANGE_SPEC.md | ✓ | |
| CHANGE_PLAN.md | ✓ | |
| BASELINE_REPORT.md | ✓ | Issue-49 baseline (unrelated) |
| IMPLEMENTATION_NOTES.md | ✓ | |
| CHANGE_TEST_REPORT.md | ✓ | |
| MANUAL_CHECKLIST.md | ✓ | Not updated to reflect PASS results |
| VERIFICATION_REPORT.md | ✓ | |
| DEFECTS.md | ✓ | |
| delivery-summary.tsv | ✓ | All AC rows marked INCOMPLETE despite passing verification |
| Waiver files (`.uncle/workflow/waivers/`) | ✗ | **F-1**: DEFECTS.md claims MC-014/015/016 "waived" but no waiver file exists |
| `.uncle/workflow/implementation-completion.txt` | ✗ | Absent |
| `.uncle/workflow/plan-recovery.json` | ✗ | Absent |
| `.uncle/workflow/plan-executability/assessment.md` | ✗ | Absent |

## 4. Implementation-to-spec gaps

**No gap found.** The implementation matches all seven ACs:

- **AC-1** (signing off → automatic commit): `prepare_commit()` at line 372 detects `git config --bool --get commit.gpgsign` returning `false` or exit 1 (unset); sets `requires_signature=False` and calls `automatic_commit()`.
- **AC-2** (correct tree, parent, message): `automatic_commit()` at line 396 calls `git commit-tree <tree> -p <original_head> -m <title>`.
- **AC-3** (signing error → fallback to person): `automatic_commit()` catches `ValueError`, matches against `SIGNING_ERROR` regex, stores the reason in `signing_fallback`, and calls `manual_signed_commit()`.
- **AC-4** (local false > global true): `prepare_commit()` delegates to `git config --bool --get` which merges all configuration levels per git semantics.
- **AC-5** (unreadable config → person): `prepare_commit()` checks `setting.returncode not in (0, 1)` and routes to `manual_signed_commit()` with `requires_signature=True`.
- **AC-6** (non-signing commit-tree failure → error, no prompt): `automatic_commit()` checks `SIGNING_ERROR.search(stderr)`; if no match, re-raises the original `ValueError`.
- **AC-7** (second handoff reuses existing commit): `handoff()` at line 763 checks `if not j['intended_head']` before calling `prepare_commit()`, reusing the existing commit on subsequent runs.

## 5. Known defects

| ID | Check | Severity | Blocking? | Analysis |
|----|-------|----------|-----------|----------|
| DF-1 | MC-007 (all-172-check.sh exit 1) | **Pre-existing** | NO | 33 of 172 checks fail in the pre-change baseline; this change does not affect them. |
| DF-2 | MC-012 (old-journal test) | **Pre-existing** | NO | Pre-existing behavior for v0.32.2 area-selection journals; not caused by this change. |

Neither defect blocks completion. Both are documented and predate this change.

## 6. Missing baseline coverage

BASELINE_REPORT.md documents 11 tests (7 in tui-complete-dialog-test.py, 4 in tui-support-test.py). The new pr-auto-commit-test.py (12 tests) and expanded pr-signing-test.py cover the new behavior. **No gap.**

## 7. NEW failures in baseline

VERIFICATION_REPORT.md MC-007 FAIL and MC-012 FAIL are both documented as pre-existing (DF-1, DF-2). CHANGE_TEST_REPORT.md noted pr-close-test.py and pr-cli-originless-test.py failures during implementation testing, but VERIFICATION_REPORT.md MC-005 and MC-006 show these as PASS after fixes. **No new baseline failures.**

## 8. NEW failures in targeted tests

VERIFICATION_REPORT.md MC-001 runs both pr-auto-commit-test.py and pr-signing-test.py and reports exit 0. **No new failures.**

## 9. Baseline-untested code branches

The new code branches are covered by tests:

| Code | Test coverage |
|------|--------------|
| `prepare_commit()` false/unset path → `automatic_commit()` | T-1 (pr-signing-test.py), T-6 (pr-auto-commit-test.py) |
| `prepare_commit()` true path → `manual_signed_commit()` | T-2 (pr-signing-test.py), T-8, T-11 (pr-auto-commit-test.py) |
| `automatic_commit()` signing error fallback | T-3 (pr-signing-test.py), T-9 (pr-auto-commit-test.py) |
| `automatic_commit()` non-signing error | T-4 (pr-signing-test.py) |
| `run_named_stage()` | MC-008 (triage-chat-test.py) |
| `_clear_workflow_identity()` | MC-008 (triage-chat-test.py) |
| `send_home_chat` fix/rerun detection | MC-008 (triage-chat-test.py) |

## 10. Interface/API/contract changes

No breaking interface changes. Additions:
- New `/run` slash command and `run_named_stage()` method in uncle_tui.py
- `send_home_chat()` now handles "fix ..." and "run X stage" prose as workflow commands
- `_clear_workflow_identity()` called on `/clear` (unlinks `state` and `origin`)
- `manual_signed_commit()` contract updated: uses `-S` / `--no-gpg-sign` based on `requires_signature` journal flag
- `change_pr_complete()` non-interactive path now calls `completed-signing-resume` for robustness

## 11. Incomplete or missing verification

**F-2**: MC-014, MC-015, MC-016 (manual GPG-signing checks PC-1/PC-2/PC-3) are BLOCKED-SETUP because no GPG key is configured. DEFECTS.md Observation 4 states "All three are waived — the auto test covers the new logic." However, **no waiver file exists** in `.uncle/workflow/waivers/`.

## 12. Brittle or non-reproducible results

All VERIFICATION_REPORT.md results are reproducible: the same commands run deterministically in isolated disposable repositories (git shim, fake gh). CHANGE_TEST_REPORT.md shows initial test failures during implementation that were fixed before verification — a valid development progression, not brittleness.

## 13. Missing manual steps

MANUAL_CHECKLIST.md was not updated from its pre-verification NOT RUN / FAIL statuses. VERIFICATION_REPORT.md serves as the de facto updated manual verification. The manual GPG steps (PC-1/PC-2/PC-3) are blocked as noted in F-2.

## 14. Missing waiver files

**F-1 (repeated):** No waiver files in `.uncle/workflow/waivers/`. DEFECTS.md claims MC-014/015/016 are waived but the waiver files were never created.

## 15. Environmental assumptions

- Git 2.x with `--bool --get` support
- Python 3
- GPG key (for MC-014/015/016; CI only)
- Network access for origin-based tests
- `gh` CLI authenticated for full PR-creation path

## 16. Documentation gaps

| Gap | Detail |
|-----|--------|
| `delivery-summary.tsv` | All AC rows show INCOMPLETE despite VERIFICATION_REPORT.md PASS for MC-001 |
| `MANUAL_CHECKLIST.md` | Not updated with verification results |
| Waiver files | Missing for MC-014/015/016 (claimed in DEFECTS.md) |

## 17. Risk assessment

**Low risk.** The change is narrow: it adds an automatic-commit path in `change_pr_engine prepare_commit` that is exercised only when `commit.gpgsign` reads as `false` or unset. The existing manual-signed-commit path is preserved for all signing-on configurations. Pre-existing failures (DF-1, DF-2) are unrelated. The three administrative gaps (F-1, delivery-summary.tsv, MANUAL_CHECKLIST.md) do not affect correctness.

---

## Findings

| ID | Severity | Evidence | Affected behavior | Affected invariant | Required correction | Blocks completion |
|----|----------|----------|-------------------|--------------------|--------------------|:---:|
| F-1 | MEDIUM | DEFECTS.md Obs 4; absent `.uncle/workflow/waivers/` | MC-014/015/016 verification blocked | All waived checks must have waiver files | Create waiver files documenting that GPG-signing checks require CI-only setup and that MC-001 covers the logic | NO |
| F-2 | LOW | `delivery-summary.tsv` all INCOMPLETE | Status tracking | Delivery summary must reflect current PASS/FAIL | Run `delivery-summary.sh` (or equivalent) to update AC statuses | NO |
| F-3 | LOW | `MANUAL_CHECKLIST.md` NOT RUN / FAIL | Manual verification tracking | Checklist should reflect VERIFICATION_REPORT.md results | Update MANUAL_CHECKLIST.md to match VERIFICATION_REPORT.md PASS/FAIL/BLOCKED | NO |

No blocking findings.

---

## Final Verdict

The implementation is correct, all seven acceptance criteria are tested and pass, the specification is satisfied, and the source code matches the diff. Pre-existing failures (DF-1, DF-2) are documented and do not affect this change. The three non-blocking findings are administrative (missing waiver files, stale delivery-summary.tsv, stale MANUAL_CHECKLIST.md) and can be resolved without code changes.

**READY WITH NON-BLOCKING ISSUES**

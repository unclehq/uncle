# Baseline Report

Omitted sections: Reproduction (not a reproducible in-repo bug; the failure needs real Daytona); Areas outside change folded into section 12

## 1. Change-request summary
Issue 235 (`.uncle/docs/CHANGE_REQUEST.md`): the hosted preview path never ran end to end. Most fixes live outside this repo (build script, release grants, Daytona sandbox settings). In-repo surface is small: a chat rule about Daytona's warning page, its test pattern, and a test pinning the `UNCLE_PREVIEW_HOST=0.0.0.0` path.

## 2. Repository architecture
Bash drivers (`scripts/stagegate.sh`, `scripts/change-workflow.sh`) call `uncle_host_preview_hook` (`scripts/lib/host_preview_hook.sh`) which runs `scripts/lib/host_preview.py serve`. Chat skill text in `skills/uncle-build/SKILL.md`, checked by `scripts/tests/chat-skill-test.py`.

## 3. Relevant code paths
- `scripts/lib/host_preview.py:50-63` `valid_host` / `urls_for` (0.0.0.0 accepted; URL shown as 127.0.0.1)
- `scripts/lib/host_preview.py:210-213` host from `UNCLE_PREVIEW_HOST`, default 127.0.0.1
- `skills/uncle-build/SKILL.md` rules 1-5 (16 lines)
- `scripts/tests/chat-skill-test.py:13-35` REQUIRED patterns, `:147-157` per-rule removal cases, MAX_BODY_LINES=60
- `scripts/tests/host-preview-test.py:199-207` `test_wildcard_host_records_loopback_url`

## 4/5. Current behavior and invariants
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Build output has `Preview:` line | Skill rules 1-5 relay link, expiry, no tab promise | SKILL.md | Yes |
| B-2 | `UNCLE_PREVIEW_HOST=0.0.0.0` | App binds wildcard; record url is `http://127.0.0.1:<port>/` | host-preview-test.py:199 | Yes |
| B-3 | Default host | Loopback bind | host-preview-test.py:191 | Yes |
| B-4 | Skill mentions warning page | No such rule | SKILL.md | No (ADD) |

| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Skill body <= 60 lines, every REQUIRED rule present, no forbidden tab-opening phrases | chat-skill-test.py:64 and REQUIRED | chat-skill-test.py | High |
| I-2 | Invalid hosts rejected without spawning | valid_host | host-preview-test.py:209 | High |
| I-3 | Loopback checks for wildcard host | urls_for | host-preview-test.py:199 | High |

## 6. Interface contracts
`.uncle/preview.json` records `host`, `url`, `status`. Build script (external) reads `UNCLE_PREVIEW_PORT=<n>` from serve stdout.

## 7. Existing coverage
host-preview suite is in `scripts/tests/critical-suites.txt` (default python tier). chat-skill suite is not in the critical list, so the default runner does not execute it; it must be run explicitly. The two Python commands use separate temp dirs.

## 9. Baseline test results
Commands come from `scripts/run-python-tests.sh` usage (supports `-- suite ...`). No results produced here; the driver baseline is authoritative. No documented pre-existing failure for these suites.

## 12. Likely change surface
`skills/uncle-build/SKILL.md`, `scripts/tests/chat-skill-test.py`, `scripts/tests/host-preview-test.py`.

## 13. Regression-sensitive components
SKILL.md line cap and forbidden-phrase list (a warning-page sentence must avoid 'will open', 'opens automatically' etc.).

## 14. Outside the change
Build script, release grants (#236), Daytona sandbox settings, `host_preview.py` logic, drivers, hook.

## 15. Unknowns and assumptions
- UNRESOLVED (needs live Daytona): whether link reaches 127.0.0.1; auto-stop behavior; signed-link call success. Cannot be verified in this repo.
- Assumption: the external build script is owned elsewhere; this repo only gets the 0.0.0.0 pinning test and chat rule.

## 16. Initial risk
Low for in-repo edits. High residual risk that the end-to-end path remains unproven until live checks run outside this repo.

## Exact build and test commands executed

```sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- chat-skill
```


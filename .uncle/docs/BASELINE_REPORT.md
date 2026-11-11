# Baseline report

Omitted sections: Reproduction (live-only, recorded in CHANGE_REQUEST.md); Current API/schema contracts (none touched); Existing failures (none documented in repo, driver baseline is authority)

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md` (Issue 252): hosted chat agent says previews are impossible because no rule says a hosted build ends with a preview link.

## 2. Repository architecture
Chat skill is a Markdown file `skills/uncle-build/SKILL.md` (front matter + numbered rules). Its text is checked by a pure-function checker in `scripts/tests/chat-skill-test.py`. The release's own chat instructions live outside this repo.

## 3. Relevant code paths
- `skills/uncle-build/SKILL.md:3` description says link is reported *after* the build script.
- `skills/uncle-build/SKILL.md:8-17` rules 1-6, all post-build.
- `scripts/tests/chat-skill-test.py:17-32` `REQUIRED` patterns; `:85-86` requires rules numbered exactly 1-6; `:31` warning-page regex anchors on `^6\.`; `:185-188` and `:190-204` repeat the 1-6 assumption; `:13` MAX_BODY_LINES=60 (body now ~8 lines).
- `scripts/tests/chat-skill-test.py:1` suite is not in the default tier (run with `-- chat-skill`); `:99-102` asserts it stays out of `critical-suites.txt`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Person asks for preview link before any build | Agent says previews are not possible, requires GitHub repo | CHANGE_REQUEST.md live test | No (the bug) |
| B-2 | Build output has `Preview:` line | Rules 1-5 relay link plain, with expiry, no tab promise | SKILL.md:12-16 | Yes |
| B-3 | Host warning page | Rule 6 tells person to continue past it | SKILL.md:17 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Skill passes all REQUIRED patterns, only placeholder URLs, none in code formatting | `check()` chat-skill-test.py:57 | `test_real_skill_passes_every_rule` | High |
| I-2 | No forbidden promise phrases (tab opens automatically etc.) | FORBIDDEN list :35 | `test_forbidden_promises_absent` | High |
| I-3 | Body <= 60 lines; front matter has name and description | :67, :64 | `test_front_matter_and_length` | High |
| I-4 | Rules numbered 1-6 in order; rule 6 is the warning-page rule | :84-86, :31 | `test_warning_rule_is_rule_6_and_body_within_cap` | High |

## 7. Existing automated-test coverage
`chat-skill-test.py` has file-text checks and defect-injection variants. It checks text only, not that a chat agent follows it. No chat-level test exists. The Python suite and shell suites use separate temp dirs.

## 9. Baseline test results
Commands from CLAUDE.md-style Uncle conventions: `scripts/run-python-tests.sh` and `scripts/run-shell-tests.sh` exist. Default Python tier excludes chat-skill, so it is listed explicitly. No results run here; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout.

## 12. Likely change surface
`skills/uncle-build/SKILL.md`; `scripts/tests/chat-skill-test.py`. Release instructions (external) need a matching edit.

## 13. Regression-sensitive components
Rule numbering (checker hardcodes 1-6, rule 6 regex); FORBIDDEN phrases (new wording must avoid 'will open', 'opens a tab' etc.); non-placeholder URL check (no real URLs in the skill).

## 14. Outside the change
Build script, preview hosting, release grant (#251), warning-page behavior, Python/shell suites other than chat-skill.

## 15. Unknowns and assumptions
- Release instructions are not in this repo; their edit and publish cannot be verified here.
- Decision 3(a) vs (b) from the request is not yet confirmed by the human.

## 16. Initial risk assessment
Low code risk (text + test). Medium behavioral risk: skill text may not override release instructions that say every build ends in a PR.

## Exact build and test commands executed

```sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- chat-skill
bash scripts/run-shell-tests.sh
```


# Baseline report

Omitted sections: Reproduction result (reasoned from code, suite not run per stage rules); Areas outside change folded into section 12

## 1. Change-request summary
Issue 272 (CHANGE_REQUEST.md): hosted/self-hosted new-app builds never class `small` because `interpretation_counts` reads only `R-n`/`D-n` ids, which the self-hosted investigation does not emit.

## 2. Repository architecture
Shell driver `scripts/stagegate.sh` calls Python helpers in `scripts/lib/`. `scripts/lib/change_class.py` computes the build class (features -> deterministic_class -> profile) and writes `change-class.json`.

## 3. Relevant code paths
- `scripts/stagegate.sh:4819-4835`: self-hosted requirements fast path copies investigation to REQUIREMENTS_INTERPRETATION.md, `requirements-context.py --export-json`.
- `scripts/lib/requirements-context.py:83-100` `export_json`: stores each section body as a raw Markdown string under `sections` (keys `required_functionality`, `definition_of_done`).
- `scripts/lib/change_class.py:215-223` `interpretation()`: sections as text.
- `scripts/lib/change_class.py:226-230` `interpretation_counts()`: counts distinct `R-\d+` / `D-\d+` only.
- `scripts/lib/change_class.py:245-260` `features()`: feeds counts as `requirements`, `criteria`.
- `scripts/lib/change_class.py:263-269` `app_is_small()`: needs 0<requirements<=6 and 0<criteria<=8, steps<=12, files<=30, no risk hits.
- `scripts/lib/change_class.py:272-286` `deterministic_class()`: `steps>=7 or files>=15 or directories>=6` -> large.
- `scripts/lib/change_class.py:556-579` `plan_budget`/`plan_word_scale`: terse-plan budget applies only when class is small.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | App interpretation with `R-n`/`D-n` ids, <=6 req, <=8 done, small plan, no risk | class small | change_class.py:263-269 | Yes |
| B-2 | App interpretation with plain bullets / id-less table (self-hosted path) | counts (0,0) -> never small | change_class.py:229-230, issue 272 | No (the bug) |
| B-3 | App plan with steps>=7 or files>=15 or dirs>=6, not small | large | change_class.py:282 | Yes |
| B-4 | family=change classification (docs, test-only, small, standard) | unchanged by interpretation counts | change_class.py:257-258,276-285 | Yes |
| B-5 | Risk keyword hit | risky | change_class.py:273 | Yes |
| B-6 | No interpretation file | counts (0,0), plan size decides alone | change_class.py:215-223, docstring 264-265 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Risk hits always yield `risky` regardless of size | deterministic_class first branch | scripts/tests/review-skip-test.py | Medium |
| I-2 | Small requires an interpretation to read | app_is_small `0 <` guards | none specific found | Medium |
| I-3 | Small limits: req<=6, done<=8, steps<=12, files<=30 | APP_SMALL | none specific found | Medium |

## 6. Contracts
`change-class.json` `features` keys (`requirements`, `criteria`, ...) are unchanged in shape. Interpretation JSON: `sections` map of Markdown strings (id-bearing R-/D- rows are also valid input).

## 7. Existing automated-test coverage
Change-class logic is exercised by `scripts/tests/review-skip-test.py` (and `.sh`), `scripts/tests/hosted-mode-test.py`. `review-skip` is not in `scripts/tests/critical-suites.txt`, so the default python runner skips it; an explicit command is listed. No test covers `interpretation_counts` on an id-less interpretation. The shell and python runners use separate temp dirs and share no ports, so they form a parallel group.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (CLAUDE-mandated Uncle runners). Not run in this stage; driver baseline is the authority. Python suites may have known pre-existing failures.

## 10. Existing failures
None recorded in repository docs for this surface.

## 11. Reproduction
Reasoned: interpretation JSON with 4 plain bullets and a 4-row id-less table gives `interpretation_counts == (0, 0)`, so `app_is_small` is False and the plan-recheck lands on `large` (issue 272 change-class.json shows requirements 0, criteria 0).

## 12. Likely change surface
`scripts/lib/change_class.py` (`interpretation_counts`, possibly `features`), `scripts/tests/review-skip-test.py`.

## 13. Regression-sensitive components
id-bearing interpretations (other requirements paths), family=change classing, risk detection, plan_budget/plan_word_scale (depend on class small).

## 15. Unknowns and assumptions
- Exact Markdown shape of investigation bullets/tables: prompts/requirements-investigate.md:15-30 lists the sections; assumed bullets (`-`, `*`, `1.`) and a pipe table with header and separator.
- Where stderr from change_class is surfaced is not confirmed; a log line is best-effort.

## 16. Initial risk assessment
Low: single pure function. Main risk is over-counting (header/separator rows, nested bullets) wrongly granting small, or under-counting restoring today's behavior.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- review-skip
```


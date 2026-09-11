## baseline result
<<<<<<< HEAD
| ID | Exact command | Result |
|---|---|---|
| BL-1 | `bash -n uncle scripts/from-issue.sh` | PASS baseline; 0 output lines. |
| BL-2 | `bash -o pipefail -c 'bash scripts/tests/issue-project-root-test.sh 2>&1 \| tail -8'` | PASS baseline; 1 output line. |
| BL-3 | `bash -o pipefail -c 'PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/menu-input-test.py -q 2>&1 \| tail -12'` | PASS baseline; 8 tests, 4 output lines. |
| BL-4 | `bash -o pipefail -c 'PYTHONDONTWRITEBYTECODE=1 bash scripts/tests/close-flow-test.sh 2>&1 \| tail -12'` | PASS initial batch; 231 checks and 28 Python tests, 6 output lines. |

## targeted tests
| ID | Exact command | Result |
|---|---|---|
| T-1 | `bash -o pipefail -c 'bash scripts/tests/issue-project-root-test.sh 2>&1 \| tail -8'` | PASS; T-1–T-4/T-6, four barriers; 2 output lines. |

## regression tests
| ID | Exact command | Result |
|---|---|---|
| R-1 | `bash -o pipefail -c 'bash scripts/tests/issue-project-root-test.sh 2>&1 \| tail -8'` | FAIL before fix: `REQUIREMENTS.md does not contain a '# Project brief' section; cannot seed new-app workflow.` Then PASS (T-1). |
| R-2 | `bash -o pipefail -c 'PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/menu-input-test.py -q 2>&1 \| tail -12'` | PASS; 9 tests, 4 output lines. |
| R-3 | `python3 -B -c 'import pathlib,subprocess; c=pathlib.Path("BASELINE_REPORT.md").read_text().split("```sh\n")[1].split("```",1)[0].splitlines()[5]; raise SystemExit(subprocess.call(c,shell=True,executable="/bin/bash"))'` | PASS; requirements created; 3 output lines. |
=======
| ID | Command / result |
|---|---|
| BL-1 | `PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/tests/install-test.py -q` — PASS, exit 0; 10 tests, no skips, 5 output lines |
| BL-2 | `bash -n install.sh scripts/install/homebrew.sh uncle` — PASS, exit 0; 0 output lines |
| BL-3 | `ruby -c Formula/uncle.rb` — PASS, exit 0; 1 output line |
| BL-4 | `for file in install.sh scripts/install/homebrew.sh uncle; do bash -n "$file" || exit; done` — PASS, exit 0; 0 output lines |

## targeted tests
| ID | Command / result |
|---|---|
| TT-1 | NOT RUN (post-edit T-2/T-3: implementation stopped before edits under CHANGE_PLAN.md STOP-1; baseline BL-1/BL-4 executed) |

## regression tests
| ID | Command / result |
|---|---|
| RT-1 | `before=$(mktemp); cp README.md "$before"` — PASS; snapshot created |
| RT-2 | `python3 -B - "$before"` with exact CHANGE_PLAN.md §16 T-1 heredoc — EXPECTED FAIL before edit: `File "<stdin>", line 6, in <module>` / `AssertionError`; both token-count assertions passed |
| RT-3 | NOT RUN (T-1 green requires S-2 implementation; stopped under STOP-1) |
>>>>>>> b449b41 (changes uncle to Uncle)

## full test suite
| ID | Result |
|---|---|
<<<<<<< HEAD
| FS-1 | NOT RUN (outside P-15; its three suites passed). |

## formatting
| ID | Exact command | Result |
|---|---|---|
| F-1 | `git diff --check -- scripts/from-issue.sh scripts/tests/issue-project-root-test.sh scripts/tests/menu-input-test.py scripts/README.md` | PASS; 0 output lines. |

## compiler or type checker
| ID | Exact command | Result |
|---|---|---|
| C-1 | `bash -n uncle scripts/from-issue.sh` | PASS; 0 output lines. |
| C-2 | `bash -n scripts/from-issue.sh` | PASS; 0 output lines. |
| C-3 | `python3 -B -c 'import ast,pathlib; ast.parse(pathlib.Path("scripts/tests/menu-input-test.py").read_text())'` | PASS; 0 output lines. |
=======
| FT-1 | NOT RUN (repository-wide workflow/TUI suites: implementation stopped; complete installer suite executed as BL-1) |

## formatting
| ID | Command / result |
|---|---|
| FM-1 | `git diff --check` — FAIL, exit 2; pre-existing `BASELINE_REPORT.md:10: trailing whitespace.` and `CHANGE_REQUEST.md:3: trailing whitespace.`; preserved |

## compiler or type checker
| ID | Command / result |
|---|---|
| CT-1 | N/A (README display-only scope has no compilation/type checking; syntax commands BL-2–BL-4 passed) |
>>>>>>> b449b41 (changes uncle to Uncle)

## linting
| ID | Result |
|---|---|
<<<<<<< HEAD
| L-1 | NOT RUN (shellcheck unavailable: `command -v shellcheck` returned no path). |

## integration tests
| ID | Exact command | Result |
|---|---|---|
| I-1 | `bash -o pipefail -c 'PYTHONDONTWRITEBYTECODE=1 bash scripts/tests/close-flow-test.sh 2>&1 \| tail -12'` | PASS; 231 checks, 1 output line. |
| I-2 | `PYTHONDONTWRITEBYTECODE=1 python3 -B /tmp/uncle-seed-check.py` | PASS M-1/rollback; 2 output lines. |
=======
| LN-1 | N/A (approved plan specifies no lint check for README capitalization) |

## integration tests
| ID | Command / result |
|---|---|
| IT-1 | `PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/tests/install-test.py -q` — PASS as BL-1; archive and real Debian package coverage, no skips |
>>>>>>> b449b41 (changes uncle to Uncle)

## frontend build
| ID | Result |
|---|---|
<<<<<<< HEAD
| FB-1 | N/A (shell seeding change; no frontend build). |
=======
| FB-1 | N/A (README display-only scope) |
>>>>>>> b449b41 (changes uncle to Uncle)

## migration tests
| ID | Result |
|---|---|
<<<<<<< HEAD
| M-1 | N/A (P-11: no migration). |

## rollback test
| ID | Exact command | Result |
|---|---|---|
| RB-1 | `PYTHONDONTWRITEBYTECODE=1 python3 -B /tmp/uncle-seed-check.py` | PASS scratch rollback suites; initial `FileNotFoundError` (missing `prompts/`) corrected; 2 output lines. |
=======
| MG-1 | N/A (CHANGE_PLAN.md P-12: no migration) |

## rollback test
| ID | Command / result |
|---|---|
| RB-1 | N/A (README.md was not edited; no implementation to reverse) |
>>>>>>> b449b41 (changes uncle to Uncle)

## performance checks
| ID | Result |
|---|---|
<<<<<<< HEAD
| P-1 | N/A (CHANGE_SPEC.md: no performance claims). |

## security checks
| ID | Exact command | Result |
|---|---|---|
| S-1 | `bash -o pipefail -c 'bash scripts/tests/issue-project-root-test.sh 2>&1 \| tail -8'` | PASS T-6; 2 output lines. |
=======
| PF-1 | N/A (README display-only scope) |

## security checks
| ID | Command / result |
|---|---|
| SC-1 | `PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/tests/install-test.py -q` — PASS as BL-1; existing symlink rejection, argument validation, payload isolation and formula hash coverage |
>>>>>>> b449b41 (changes uncle to Uncle)

## newly introduced warnings
| ID | Result |
|---|---|
<<<<<<< HEAD
| W-1 | None observed in T-1/R-2/I-1/C-1–C-3 output. |

## pre-existing failures
| ID | Exact command | Result |
|---|---|---|
| PF-1 | `git diff --check` | Existing: `BASELINE_REPORT.md:84: new blank line at EOF.` and `CHANGE_REQUEST.md:15: trailing whitespace.` Test whitespace fixed; F-1 passes. |
=======
| NW-1 | N/A (no implementation changes; BL-1–BL-4 emitted no warnings) |

## pre-existing failures
| ID | Command / result |
|---|---|
| PE-2 | `git diff --check` — FAIL as FM-1; both affected files match their pre-edit SHA-256 hashes |
| PE-1 | `'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless --disable-gpu --no-first-run --user-data-dir="$(mktemp -d)" --dump-dom 'data:text/html,<h1>Preview</h1>'` — FAIL, exit 134; 0 output lines; blocks required M-1 under STOP-1 |
>>>>>>> b449b41 (changes uncle to Uncle)

## untested areas
| ID | Result |
|---|---|
<<<<<<< HEAD
| U-1 | NOT RUN (TUI rendering, live GitHub, generated-input driver run; settle via end-to-end execution). |
=======
| UA-1 | NOT RUN (M-1 rendered README/remote asset validation: preview probe PE-1 failed; settle with working browser preview) |
| UA-2 | NOT RUN (post-implementation acceptance AC-1–AC-5: S-2 stopped; README unchanged) |
>>>>>>> b449b41 (changes uncle to Uncle)

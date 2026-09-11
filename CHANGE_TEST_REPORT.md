## baseline result
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

## full test suite
| ID | Result |
|---|---|
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

## linting
| ID | Result |
|---|---|
| L-1 | NOT RUN (shellcheck unavailable: `command -v shellcheck` returned no path). |

## integration tests
| ID | Exact command | Result |
|---|---|---|
| I-1 | `bash -o pipefail -c 'PYTHONDONTWRITEBYTECODE=1 bash scripts/tests/close-flow-test.sh 2>&1 \| tail -12'` | PASS; 231 checks, 1 output line. |
| I-2 | `PYTHONDONTWRITEBYTECODE=1 python3 -B /tmp/uncle-seed-check.py` | PASS M-1/rollback; 2 output lines. |

## frontend build
| ID | Result |
|---|---|
| FB-1 | N/A (shell seeding change; no frontend build). |

## migration tests
| ID | Result |
|---|---|
| M-1 | N/A (P-11: no migration). |

## rollback test
| ID | Exact command | Result |
|---|---|---|
| RB-1 | `PYTHONDONTWRITEBYTECODE=1 python3 -B /tmp/uncle-seed-check.py` | PASS scratch rollback suites; initial `FileNotFoundError` (missing `prompts/`) corrected; 2 output lines. |

## performance checks
| ID | Result |
|---|---|
| P-1 | N/A (CHANGE_SPEC.md: no performance claims). |

## security checks
| ID | Exact command | Result |
|---|---|---|
| S-1 | `bash -o pipefail -c 'bash scripts/tests/issue-project-root-test.sh 2>&1 \| tail -8'` | PASS T-6; 2 output lines. |

## newly introduced warnings
| ID | Result |
|---|---|
| W-1 | None observed in T-1/R-2/I-1/C-1–C-3 output. |

## pre-existing failures
| ID | Exact command | Result |
|---|---|---|
| PF-1 | `git diff --check` | Existing: `BASELINE_REPORT.md:84: new blank line at EOF.` and `CHANGE_REQUEST.md:15: trailing whitespace.` Test whitespace fixed; F-1 passes. |

## untested areas
| ID | Result |
|---|---|
| U-1 | NOT RUN (TUI rendering, live GitHub, generated-input driver run; settle via end-to-end execution). |

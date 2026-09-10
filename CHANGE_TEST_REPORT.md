## baseline result
| ID | Command / result |
|---|---|
| BL-1 | `bash scripts/tests/document-budget-test.sh` — exit 1 before C-1; 28 output lines; matches BASELINE_REPORT.md T-2. |

## targeted tests
| ID | Command / result |
|---|---|
| T-1 | `bash scripts/tests/document-budget-test.sh` — PASS, exit 0; 29 output lines. |
| T-2 | `bash scripts/tests/document-budget-prompt-test.sh` — PASS, exit 0; 24 output lines. |

## regression tests
| ID | Command / result |
|---|---|
| R-1 | `python3 -B -c 'import subprocess,sys; p=subprocess.run(["bash","-x","scripts/tests/document-budget-test.sh"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True); print("\n".join(p.stdout.splitlines()[-14:])); sys.exit(p.returncode)'` — before: exit 1 at `+ grep -q 'Document budget exceeded:' rejected`; after: PASS, exit 0, 14 output lines. |
| R-2 | `python3 -B scripts/tests/windows-portability-test.py -q` — PASS, exit 0; 4 output lines. |

## full test suite
| ID | Command / result |
|---|---|
| FT-1 | NOT RUN (repository-wide suites exceed CHANGE_PLAN.md §16 scope; all BASELINE_REPORT.md §8 commands ran). |

## formatting
| ID | Command / result |
|---|---|
| F-1 | `git diff --check -- scripts/tests/document-budget-test.sh` — PASS, exit 0; 0 output lines. |
| F-2 | `git diff --check` — FAIL: `README.md:10: trailing whitespace.`; existing user edit preserved. |

## compiler or type checker
| ID | Command / result |
|---|---|
| C-1 | `bash -n scripts/tests/document-budget-test.sh` — PASS, exit 0; 0 output lines. |
| C-2 | `bash -n install.sh scripts/install/homebrew.sh scripts/lib/gates.sh scripts/tests/document-budget-test.sh packaging/windows/python3` — PASS, exit 0; 0 output lines. |

## linting
| ID | Command / result |
|---|---|
| L-1 | NOT RUN (no lint command specified in BASELINE_REPORT.md §8 or CHANGE_PLAN.md §16). |

## integration tests
| ID | Command / result |
|---|---|
| IT-1 | `python3 -B scripts/tests/install-test.py -q` — PASS, exit 0; 5 output lines. |
| IT-2 | NOT RUN (AC-4/M-1 candidate Windows CI unavailable; settle with Windows Git Bash log). |

## frontend build
| ID | Command / result |
|---|---|
| FB-1 | N/A (fixture-only Bash change). |

## migration tests
| ID | Command / result |
|---|---|
| MT-1 | N/A (no schema or persistence change). |

## rollback test
| ID | Command / result |
|---|---|
| RB-1 | `bash scripts/tests/document-budget-test.sh` — temporarily removed C-1: expected exit 1, 28 output lines; restored C-1: PASS, exit 0, 29 output lines. |

## performance checks
| ID | Command / result |
|---|---|
| PC-1 | N/A (no production execution change). |

## security checks
| ID | Command / result |
|---|---|
| SC-1 | N/A (only copies an existing helper into a temporary test fixture). |

## newly introduced warnings
| ID | Command / result |
|---|---|
| W-1 | NOT RUN (warning-by-warning comparison; passing command output was summarized by line count). |

## pre-existing failures
| ID | Command / result |
|---|---|
| PF-1 | BL-1 reproduced and resolved; F-2 remains in unchanged README.md. |

## untested areas
| ID | Command / result |
|---|---|
| U-1 | NOT RUN (native Windows acceptance, repository-wide suites and warning comparison; settle IT-2, FT-1 and W-1 before claiming that coverage). |

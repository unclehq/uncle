## baseline result
| ID | Command and result |
|---|---|
| CT-1 | `python3 -` — executed BASELINE_REPORT.md §8 commands 1–6 before/after; exits 0,1,0,0,1,0 both times; logs `/private/tmp/uncle-implementation-start/{baseline,final}-*.log`, commands in commands.json. |
| CT-2 | `bash -c 'for f in uncle install.sh scripts/*.sh scripts/lib/*.sh scripts/tests/*.sh; do bash -n "$f" &#124;&#124; exit; done'` — PASS before/after; 0 lines. |
| CT-3 | `python3 -B scripts/tests/tui-support-test.py -q` — PASS before/after; 4 tests, 4 lines. |
| CT-4 | `python3 -B scripts/tests/early-prerequisites-test.py -q` — PASS before/after; 5 tests, 4 lines. |

## targeted tests
| ID | Command and result |
|---|---|
| CT-5 | `python3 -B scripts/tests/menu-input-test.py -q` — before: FAIL, 6 tests/11 failures; after: PASS, 8 tests/4 lines. |

## regression tests
| ID | Command and result |
|---|---|
| CT-6 | `python3 -B scripts/tests/menu-input-test.py -v` — PASS, 8 tests/13 lines; T1–T7. |

## full test suite
| ID | Command and result |
|---|---|
| CT-7 | `python3 -` — shell-suite harness executed `bash` for each scripts/tests/*-test.sh; 49 suites, 38 PASS/11 FAIL; exact paths, exit codes and line counts in /private/tmp/uncle-implementation-start/full-results.json; per-suite *.sh.log. |

## formatting
| ID | Command and result |
|---|---|
| CT-8 | `git diff --check` — PASS; 0 lines. |

## compiler or type checker
| ID | Command and result |
|---|---|
| CT-9 | `python3 -B -c 'from pathlib import Path; [compile(Path(p).read_bytes(), p, "exec") for p in ("uncle_tui.py", "scripts/tests/menu-input-test.py")]'` — PASS; 0 lines. |

## linting
| ID | Command and result |
|---|---|
| CT-10 | NOT RUN (shellcheck unavailable: `command -v shellcheck` returned no path). |

## integration tests
| ID | Command and result |
|---|---|
| CT-11 | `python3 -B scripts/tests/menu-input-test.py -v` — PASS; actual-driver T7 and shell fixtures; included CT-6. |

## frontend build
| ID | Command and result |
|---|---|
| CT-12 | N/A (Bash/Python TUI; BASELINE_REPORT.md §2). |

## migration tests
| ID | Command and result |
|---|---|
| CT-13 | N/A (CHANGE_PLAN.md §13: no migration). |

## rollback test
| ID | Command and result |
|---|---|
| CT-14 | `python3 -` — restored HEAD plus PC1 diff in disposable rollback directory; reran 11 failed suites, all same exit codes; rollback-results.json and *.rollback.log beside CT-7 logs; RB1 baseline commands 1–4,6 reproduce original exits 0,1,0,0,0 (rollback-baseline-*.log). |

## performance checks
| ID | Command and result |
|---|---|
| CT-15 | `bash scripts/tests/tui-performance-test.sh` — PASS, 4 tests; CT-7 log. |

## security checks
| ID | Command and result |
|---|---|
| CT-16 | `python3 -B scripts/tests/menu-input-test.py -v` — PASS; fixed root, nonfiles, TUI denial, symlinks, stub agents; CT-6. |

## newly introduced warnings
| ID | Command and result |
|---|---|
| CT-17 | N/A (none observed in menu-test output; actual-driver race stderr includes existing missing-source traceback and macOS confstr warning). |

## pre-existing failures
| ID | Command and result |
|---|---|
| CT-18 | `python3 -` — CT-14 reproduces all CT-7 failures, including F1; log examples: `PROJECT_ROOT: unbound variable`, `fatal: failed to write commit object`, `tee: /dev/fd/63: Operation not permitted`. |

## untested areas
| ID | Command and result |
|---|---|
| CT-19 | NOT RUN (native Windows Q2, interactive M1–M3, shell stat denial, standalone Python suites outside selected targets; native/restricted-identity runs settle these). |

# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| grep -n -i '7200\\|3600\\|expiresIn' docs/preview-link-release.md | PASS | Single match, line 38: 'use an expiry of at most 3600 seconds'. No 7200 in the repo. | AC-1 |
| targeted mocked-publisher tests | N/A | The build script is external to this repo. | AC-1, AC-2, AC-3, AC-4 |
| bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh | DRIVER PENDING | The driver owns the full regression run. | AC-4 |
| formatter, type check, lint, integration, frontend build, migration, rollback, performance, security | N/A | No source file changed. | None stated |

## Coverage gaps

- AC-1 to AC-4 are unverified: the build script is not in this repo.

## Next action

The owner picks option A (point at the build-script repo) or C (transfer the issue), then re-run implementation there.

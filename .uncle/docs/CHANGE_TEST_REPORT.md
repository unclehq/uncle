# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| bash scripts/run-python-tests.sh -- chat-skill | PASS | 21 tests OK, includes per-clause defect-injection rejections | AC-1, AC-2, AC-3, AC-4, AC-5 |
| bash scripts/run-python-tests.sh | DRIVER PENDING | Driver owns full run | AC-4 |
| bash scripts/run-shell-tests.sh | DRIVER PENDING | Driver owns full run | AC-4 |
| formatter / type checker / lint / frontend build / migration / rollback / performance / security | N/A | Not applicable to a markdown skill and a unittest file | None stated |
| live hosted check | BLOCKED | Needs release publish and grant #251 | AC-6 |

## Coverage gaps

- AC-6 live behavior unverified; file-text checks do not prove a chat agent follows the skill

## Next action

Driver runs full regression; human performs release edit and live check for AC-6.

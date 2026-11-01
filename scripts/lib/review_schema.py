#!/usr/bin/env python3
"""The schema a read-only review lens's packet must satisfy, for hosted runners that can enforce one (Claude `--json-schema`,
Codex `--output-schema`): the lens then answers in one schema-checked final message, valid by construction, with no Write tool and no
delivery file to repair afterwards. The same packet kinds the self-hosted loop answers schema-first.

    review_schema.py prepare PROMPT_FILE OUT_SCHEMA     write the schema and exit 0, or exit 1 when this prompt gets none
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Read-only review packets only. A worker that executes checks or inspects the machine (checklist-execution, preflight) needs its tools,
# and the plan writers answer through their own schemas.
KINDS = frozenset({'adversarial-review-worker-packet', 'manual-checklist-worker-packet', 'test-review-worker-packet',
                   'final-audit-worker-packet', 'updated-plan-worker-packet'})


def schema_for(prompt_text):
    import self_hosted
    kind = self_hosted.reviewer_artifact_kind(prompt_text)
    if kind not in KINDS:
        return None
    return self_hosted.artifact_schema(kind)


def main(argv):
    if len(argv) != 3 or argv[0] != 'prepare':
        print(__doc__, file=sys.stderr)
        return 2
    try:
        schema = schema_for(Path(argv[1]).read_text(encoding='utf-8'))
    except (OSError, ValueError, ImportError):
        return 1
    if not schema:
        return 1
    Path(argv[2]).write_text(json.dumps(schema, separators=(',', ':')) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

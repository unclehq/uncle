#!/usr/bin/env bash
# The PR journal and the audit verdict must bind to the same bytes.
#
# Both drivers record the verdict as sha256 of the canonical artifact:
#   change-workflow.sh:3781  "$(hash_file "$STATE_DIR/documents/FINAL_AUDIT.json")"
#   stagegate.sh:3873        "$(hash_file "$STATE_DIR/documents/FINAL_AUDIT.json")"
# while change-pr.sh's audit_hash() hashed .uncle/docs/FINAL_AUDIT.md, the
# rendered view. validate() compares them:
#   if len(verdict) != 3 or verdict[0] != j['verdict_run'] or verdict[2] != j['audit_hash']
# Two hashes of two different files are never equal, so every completed run
# raised "Verdict binding changed; rerun FINAL_AUDIT.". change_pr_publish
# treats any nonzero status that is not 3 as "leave it alone" and returns 0,
# so the run ended with no PR. Observed on a real COMPLETE run: the journal
# stayed at phase "bound" with base_repo empty and number null.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

project="$work/project"
mkdir -p "$project/.uncle/workflow/documents" "$project/.uncle/docs"
cd "$project"

# The rendered view and the canonical artifact necessarily differ in bytes.
printf '## Findings\n\nNo findings.\n\nREADY\n' > .uncle/docs/FINAL_AUDIT.md
printf '{"schema":"uncle.artifact/v1","kind":"final-audit","findings":[],"verdict":"READY"}\n' \
    > .uncle/workflow/documents/FINAL_AUDIT.json

fail() { echo "pr-verdict-binding-test.sh: FAIL: $*" >&2; exit 1; }

cat > harness.py <<'EOF'
import hashlib, sys
from pathlib import Path
STATE = Path('.uncle/workflow')
AUDIT = Path('.uncle/docs/FINAL_AUDIT.md')
EOF
# The real function, lifted from the library the driver actually runs.
awk '/^def audit_hash\(\)/{p=1} p{print} p && /^$/ && NR > 1 && p > 1 {exit} p{p++}' \
    "$ROOT/scripts/lib/change-pr.sh" | sed '/^$/q' >> harness.py
cat >> harness.py <<'EOF'
print(audit_hash())
EOF

journal_hash="$(python3 harness.py)"
verdict_hash="$(shasum -a 256 .uncle/workflow/documents/FINAL_AUDIT.json | awk '{print $1}')"
rendered_hash="$(shasum -a 256 .uncle/docs/FINAL_AUDIT.md | awk '{print $1}')"

[[ "$verdict_hash" != "$rendered_hash" ]] \
    || fail 'fixture is degenerate: the two files must differ'
[[ "$journal_hash" == "$verdict_hash" ]] \
    || fail "journal binds $journal_hash but the verdict binds $verdict_hash (the PR can never validate)"

# Legacy: a journal from before the canonical artifact existed still resolves.
rm .uncle/workflow/documents/FINAL_AUDIT.json
[[ "$(python3 harness.py)" == "$rendered_hash" ]] \
    || fail 'without the canonical artifact, the rendered view must still bind'

echo 'pr-verdict-binding-test.sh: the PR journal binds to the same artifact as the audit verdict'

# --- The same binding, at the close-eligibility gate -----------------------
# issue_close_eligible rehashes the audit file it is handed and compares it to
# the hash in the verdict record. change_pr_publish used to hand it
# .uncle/docs/FINAL_AUDIT.md while the record held the canonical JSON hash, so
# it always returned 1 with ".uncle/docs/FINAL_AUDIT.md changed after it was
# classified" and the caller's `|| return 0` turned that into a silent no-PR.
gate="$work/gate"
mkdir -p "$gate/.uncle/workflow/documents" "$gate/.uncle/docs" "$gate/bin"
cd "$gate"
printf '## Findings\n\nNo findings.\n\nREADY\n' > .uncle/docs/FINAL_AUDIT.md
printf '{"schema":"uncle.artifact/v1","kind":"final-audit","findings":[],"verdict":"READY"}\n' \
    > .uncle/workflow/documents/FINAL_AUDIT.json
printf 'owner/repo\t7\tgh\n' > .uncle/workflow/origin
canonical_hash="$(shasum -a 256 .uncle/workflow/documents/FINAL_AUDIT.json | awk '{print $1}')"
printf 'run-1\tREADY\t%s\n' "$canonical_hash" > .uncle/workflow/audit-verdict
# gh presence and auth are environment, not what this test is about.
printf '#!/bin/sh\nexit 0\n' > bin/gh; chmod +x bin/gh
export PATH="$gate/bin:$PATH"

# shellcheck disable=SC1090
. "$ROOT/scripts/lib/sha256.sh"
. "$ROOT/scripts/lib/issue-close.sh"

# The origin fields must match the repo/issue arguments.
eligible() {
    issue_close_eligible run-1 owner/repo 7 \
        .uncle/workflow/audit-verdict .uncle/workflow/origin "$1" \
        .uncle/workflow/close-marker 1 1 1 gh > /dev/null 2>&1
}

eligible .uncle/workflow/documents/FINAL_AUDIT.json \
    || fail 'the canonical artifact must satisfy the close-eligibility gate'
! eligible .uncle/docs/FINAL_AUDIT.md \
    || fail 'fixture is degenerate: the rendered view should not match the recorded hash'

if grep -A 4 'issue_close_eligible' "$ROOT/scripts/lib/change-pr.sh" \
        | grep -q '\.uncle/docs/FINAL_AUDIT\.md "\$MARKER_FILE"'; then
    fail 'change_pr_publish still hands the rendered Markdown to the close gate'
fi

echo 'pr-verdict-binding-test.sh: the close-eligibility gate binds to the canonical artifact too'

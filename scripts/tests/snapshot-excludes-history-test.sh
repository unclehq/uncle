#!/usr/bin/env bash
# snapshot() decides two things at once: which files the PR commits, and which
# files "Reviewed files changed; rerun FINAL_AUDIT." is computed over. It
# skipped `.uncle/workflow/` but not `.uncle/workflow-history/<uuid>/`, which
# workflow_family.py fills with a *previous* run's archived .uncle/workflow.
# The prefix carries a trailing slash, and "workflow-history" does not match it.
#
# review_paths.py and triage_guard.py already exclude the two together; this
# walk was the one that missed it. On a real checkout 2379 of the 2761 files
# snapshot() hashed were archived history and only 368 belonged to the project
# -- 34MB of a previous run's logs, hashed one `git hash-object` subprocess at
# a time, several times per publish, and committed into the PR. Excluding it
# took one validate (two snapshots) from 50.1s to 7.3s.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

project="$work/project"
mkdir -p "$project"
cd "$project"
git init -q .
git config user.email t@example.com
git config user.name test
# The fixture must not inherit the operator's signing config: a pinentry
# prompt here would hang the suite rather than fail it.
git config commit.gpgsign false
git config tag.gpgsign false

mkdir -p src .uncle/docs .uncle/workflow/logs .uncle/workflow-history/deadbeefcafe/logs
printf 'print("hi")\n'            > src/app.py
printf '# Change plan\n'          > .uncle/docs/CHANGE_PLAN.md
printf '# Final audit\n\nREADY\n' > .uncle/docs/FINAL_AUDIT.md
printf 'live run state\n'         > .uncle/workflow/state
printf 'live log\n'               > .uncle/workflow/logs/implementation.jsonl
printf 'archived state\n'         > .uncle/workflow-history/deadbeefcafe/state
printf 'archived log\n'           > .uncle/workflow-history/deadbeefcafe/logs/old.jsonl
printf '{}\n'                    > .uncle/attestation.json
printf 'misc.auto_mode true\n'   > .uncle/config
printf '{}\n'                    > .uncle/launch.json
mkdir -p .uncle/some-future-dir
printf 'whatever\n'              > .uncle/some-future-dir/state
# The canonical block _ensure_uncle_gitignored writes. Ignored paths are not
# hashed at all now, tracked or not, so `!.uncle/docs/` is what keeps the
# approved artifacts in the PR: without the negation they would drop out too.
printf '.uncle/*\n!.uncle/docs/\nnode_modules/\n' > .gitignore
mkdir -p node_modules/pkg
printf 'junk\n' > node_modules/pkg/index.js
git add -f node_modules/pkg/index.js
# Regular files are hashed in one batched `git hash-object --stdin-paths`
# call. That listing is newline-delimited and resolves symlinks, so these two
# shapes must stay on the per-file path and must not go missing.
ln -s app.py src/link.py
printf 'newline named\n' > "$(printf 'src/od\nd.py')"
git add src .uncle/docs
git commit -qm base

fail() { echo "snapshot-excludes-history-test.sh: FAIL: $*" >&2; exit 1; }

cat > harness.py <<'EOF'
import os, subprocess, tempfile
from pathlib import Path
STATE = Path('.uncle/workflow')
AUDIT = Path('.uncle/docs/FINAL_AUDIT.md')
ATTESTATION_FILES = ('.uncle/attestation.json', '.uncle/attestation.sig')
EOF
awk '/^def run\(/{p=1} p{print} p && /^    return result.stdout/{exit}' "$ROOT/scripts/lib/change-pr.sh" >> harness.py
printf '\n\ndef git(*args, **kwargs):\n    return run("git", *args, **kwargs)\n\n\n' >> harness.py
# Stop at the next top-level definition rather than at a guessed last line:
# an unmatched terminator silently swallows the rest of the file.
awk '/^def snapshot\(/{p=1; print; next} p && /^(def |[A-Za-z_]+ *=)/{exit} p{print}' \
    "$ROOT/scripts/lib/change-pr.sh" >> harness.py
cat >> harness.py <<'EOF'


print(snapshot())
EOF

tree="$(python3 harness.py)" || fail 'snapshot() raised'
listing="$(git ls-tree -r --name-only "$tree")"

printf '%s\n' "$listing" | grep -qx 'src/app.py' \
    || fail 'project files must be in the snapshot'
printf '%s\n' "$listing" | grep -qx '.uncle/docs/CHANGE_PLAN.md' \
    || fail 'audit-visible workflow documents must stay in the snapshot'

printf '%s\n' "$listing" | grep -q '^\.uncle/workflow/' \
    && fail 'the live workflow directory leaked into the snapshot'
printf '%s\n' "$listing" | grep -q '^\.uncle/workflow-history/' \
    && fail "a previous run's archived workflow directory leaked into the snapshot"

# The rule is the directory, not a list of its children: anything uncle
# writes outside .uncle/docs/ stays out, including names added later.
for leaked in .uncle/attestation.json .uncle/config .uncle/launch.json .uncle/some-future-dir/state; do
    printf '%s\n' "$listing" | grep -qx "$leaked" \
        && fail "uncle state leaked into the snapshot: $leaked"
done

# A tracked file that .gitignore covers is excluded from the hash as well:
# `ls-files --others --exclude-standard` never sees it, and check-ignore only
# reports it with --no-index.
printf '%s\n' "$listing" | grep -qx 'node_modules/pkg/index.js' \
    && fail 'a tracked but gitignored file was hashed'
printf '%s\n' "$listing" | grep -qx '.uncle/docs/FINAL_AUDIT.md' \
    && fail 'FINAL_AUDIT.md is added under the audit flag, not by the plain walk'

printf '%s\n' "$listing" | grep -qx 'src/link.py' \
    || fail 'a symlink went missing from the snapshot'
# ls-tree renders a path with a newline in git's quoted form, on one line.
printf '%s\n' "$listing" | grep -qF 'od\nd.py' \
    || fail 'a path containing a newline went missing from the snapshot'

# And a symlink is still stored as its target text, not as a copy of the file
# it points at: --stdin-paths would resolve it, the per-file call does not.
mode="$(git ls-tree -r "$tree" -- src/link.py | awk '{print $1}')"
[[ "$mode" == 120000 ]] || fail "symlink stored with mode '$mode', expected 120000"
[[ "$(git cat-file blob "$(git ls-tree -r "$tree" -- src/link.py | awk '{print $3}')")" == app.py ]] \
    || fail 'symlink blob is not its target text'

echo 'snapshot-excludes-history-test.sh: archived history excluded; symlinks and newline paths survive batching'

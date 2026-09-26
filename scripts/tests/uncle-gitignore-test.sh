#!/usr/bin/env bash
# One canonical ignore block, normalized wherever a run happens.
#
# This used to run only against the project root, so a worktree kept whatever
# .gitignore its commit carried. A project that adopted the block later gave
# every worktree the version without it -- and because change-pr.sh's
# snapshot() now skips whatever the ignore rules cover, an unconfigured
# worktree is also one whose uncle state gets hashed and committed. One real
# checkout carried 2379 archived .uncle/workflow-history files into a PR.
#
# The `.workflow` spellings predate the `.uncle/workflow` rename and name
# directories that no longer exist. They are uncle's own to retire.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODULE="$ROOT/scripts/lib/uncle_gitignore.py"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fail() { echo "uncle-gitignore-test.sh: FAIL: $*" >&2; exit 1; }

case_dir() { rm -rf "$work/c"; mkdir -p "$work/c"; printf '%s' "$1" > "$work/c/.gitignore"; }
run_it() { python3 "$MODULE" "$work/c"; }
body() { cat "$work/c/.gitignore"; }

# 1. Legacy .workflow entries are retired in place; user rules are untouched.
case_dir 'node_modules/
.workflow
.workflow/state
.workflow/logs/
*.log
'
run_it
body | grep -qx 'node_modules/' || fail 'an unrelated rule was dropped'
body | grep -qx '\*.log'        || fail 'an unrelated rule was dropped'
body | grep -q  '^\.workflow'   && fail 'a legacy .workflow rule survived'
[[ "$(body | grep -cx '\.uncle/\*')"      == 1 ]] || fail 'expected exactly one .uncle/* rule'
[[ "$(body | grep -cx '!\.uncle/docs/')"  == 1 ]] || fail 'expected exactly one !.uncle/docs/ rule'
# The block replaces the first managed entry, so it keeps that position.
[[ "$(body | sed -n '2p')" == '.uncle/*' ]] || fail "block did not keep its position: $(body | sed -n '2p')"

# 2. A bare `.uncle` is upgraded, not duplicated -- and re-running is a no-op.
case_dir 'a/
.uncle
b/
'
run_it
before="$(body)"
run_it
[[ "$(body)" == "$before" ]] || fail 'not idempotent'
[[ "$(body | grep -cx '\.uncle/\*')" == 1 ]] || fail 'a second run duplicated the block'

# 3. `!.uncle/docs/` must survive: snapshot() skips ignored paths, so without
#    the negation the approved artifacts would drop out of the PR.
body | grep -qx '!\.uncle/docs/' || fail 'the docs negation went missing'

# 4. No .gitignore means no file is created on the project's behalf.
rm -rf "$work/c"; mkdir -p "$work/c"
run_it
[[ ! -e "$work/c/.gitignore" ]] || fail 'created a .gitignore where the project had none'

# 5. A project with no managed entry at all gets the block appended, once,
#    and without gluing itself onto an unterminated last line.
case_dir 'only-rule'
run_it
[[ "$(body | tail -2 | head -1)" == '.uncle/*' ]] || fail "append landed wrong: $(body)"
body | grep -qx 'only-rule' || fail 'append swallowed the last line'

echo 'uncle-gitignore-test.sh: one canonical block, legacy spellings retired, idempotent'

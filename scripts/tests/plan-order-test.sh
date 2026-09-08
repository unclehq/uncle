#!/usr/bin/env bash
# A plan missing a machine-read block must be refused before a human reads it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/green-check.sh"
. "$ROOT/scripts/lib/verification-integrity.sh"
eval "$(awk '/^plan_structure_problem\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT; cd "$work"
fail() { echo "FAIL: $1" >&2; exit 1; }

full() {
    cat > PLAN.md <<'MD'
## Verification commands

```
python3 -m unittest discover
bash tests/browser.sh
```

## Protected verification paths

```
tests/
MD
    printf '```\n' >> PLAN.md
}

full
! plan_structure_problem PLAN.md > /dev/null || fail "a complete plan must pass: $(plan_structure_problem PLAN.md)"

# No commands at all.
printf '## Notes\n\nnothing machine-read here.\n' > PLAN.md
[ "$(plan_structure_problem PLAN.md)" = "no Verification commands block" ] \
    || fail "a missing commands block must be named: $(plan_structure_problem PLAN.md)"

# Commands but no protected paths -- the exact failure that cost an approval.
cat > PLAN.md <<'MD'
## Verification commands

```
python3 -m unittest discover
```
MD
[ "$(plan_structure_problem PLAN.md)" = "no Protected verification paths block" ] \
    || fail "a missing protected-paths block must be named: $(plan_structure_problem PLAN.md)"

# A shortened heading is read, not rejected. A plan that said
# "## Protected paths" -- block present, paths correct -- cost a run and a
# human approval to one missing word.
cat > PLAN.md <<'MD'
## Verification commands

```
python3 -m unittest discover
```

## Protected paths

```
tests/
```
MD
! plan_structure_problem PLAN.md > /dev/null \
    || fail "a shortened protected-paths heading must be read: $(plan_structure_problem PLAN.md)"

cat > PLAN.md <<'MD'
## Verification commands

```
python3 -m unittest discover
```

### 9. Protected Verification Paths

```
tests/
```
MD
! plan_structure_problem PLAN.md > /dev/null \
    || fail "a numbered, differently-cased heading must be read: $(plan_structure_problem PLAN.md)"

# The gate order itself: the check has to precede the approval call.
python3 - "$ROOT/scripts/stagegate.sh" <<'PY' || exit 1
import io, sys
s = io.open(sys.argv[1], encoding="utf-8").read()
branch = s[s.index("WAIT_UPDATED_PLAN_APPROVAL)"):]
branch = branch[:branch.index(";;")]
if "plan_structure_problem" not in branch:
    print("FAIL: the approval gate does not validate the plan first")
    raise SystemExit(1)
if branch.index("plan_structure_problem") > branch.index("review_and_approve"):
    print("FAIL: the plan is validated after the human is asked to approve it")
    raise SystemExit(1)
PY
echo 'plan-order-test.sh: an incomplete plan is refused before the approval gate'

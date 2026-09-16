#!/usr/bin/env bash
set -euo pipefail

# Fixture tests for scripts/lib/triage_guard.py: the sandbox and write guard
# around every triage master turn (AC-10, AC-11, AR-001/002/004/005).
#
# A "fake master" here is a few shell commands run with the sandbox as cwd,
# the way the runner would be launched, plus deliberate writes to live paths
# the way a model with Bash could reach them.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GUARD="$ROOT/scripts/lib/triage_guard.py"
. "$ROOT/scripts/lib/sha256.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
COUNT=0
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }
check_eq() {
    local name="$1" expected="$2" actual="$3"
    COUNT=$((COUNT + 1))
    [[ "$actual" == "$expected" ]] || fail "$name — expected '$expected', got '$actual'"
}
check_file_is() {
    local name="$1" expected="$2" file="$3"
    COUNT=$((COUNT + 1))
    if [[ ! -e "$file" ]]; then fail "$name — $file missing"; return; fi
    [[ "$(cat "$file")" == "$expected" ]] || fail "$name — $file is '$(cat "$file")'"
}
check_absent() {
    local name="$1" file="$2"
    COUNT=$((COUNT + 1))
    [[ ! -e "$file" ]] || fail "$name — $file exists"
}
check_row() {
    local name="$1" outcome="$2" path="$3" tsv="$4"
    COUNT=$((COUNT + 1))
    awk -F'\t' -v o="$outcome" -v p="$path" '$4 == o && $5 == p { found = 1 } END { exit !found }' "$tsv" \
        || fail "$name — no $outcome row for $path in $tsv"
}
json_field() { python3 -c 'import json,sys; v=json.load(sys.stdin)[sys.argv[1]]; print(json.dumps(v) if isinstance(v,(list,dict,bool)) else v)' "$1"; }

# project <name> [git|unborn|plain] -- a scratch project with the usual layout.
project() {
    local dir="$TMP/$1" kind="${2:-git}"
    rm -rf "$dir"
    mkdir -p "$dir/src" "$dir/.uncle/workflow/approvals" "$dir/.uncle/workflow/waivers"
    printf 'live\n' > "$dir/src/x"
    printf 'review\n' > "$dir/ADVERSARIAL_REVIEW.md"
    printf 'IMPLEMENT\n' > "$dir/.uncle/workflow/state"
    printf 'approved-hash\n' > "$dir/.uncle/workflow/approvals/CHANGE_PLAN.sha256"
    printf '# notes\n' > "$dir/IMPLEMENTATION_NOTES.md"
    if [[ "$kind" != plain ]]; then
        git -C "$dir" init -q .
        git -C "$dir" config commit.gpgsign false
        git -C "$dir" config tag.gpgsign false
        printf '.uncle/workflow/\nignored.txt\n' > "$dir/.gitignore"
        if [[ "$kind" == git ]]; then
            git -C "$dir" add -A
            git -C "$dir" -c user.email=t@t -c user.name=t commit --no-gpg-sign -qm init
        fi
    fi
    printf '%s' "$dir"
}

INSTALL="$TMP/install"
mkdir -p "$INSTALL/scripts/lib"
printf 'installed\n' > "$INSTALL/scripts/lib/thing.sh"
printf 'tui\n' > "$INSTALL/uncle_tui.py"

begin() {  # begin <project> <turn> <mode> [root]
    python3 "$GUARD" begin --state-dir .uncle/workflow --project "$1" --root "${4:-$INSTALL}" --turn "$2" --mode "$3"
}
end() {    # end <project> <turn> <mode> <digest> [root] [proposal]
    python3 "$GUARD" end --state-dir .uncle/workflow --project "$1" --root "${5:-$INSTALL}" --turn "$2" --mode "$3" --digest "$4" --proposal "${6:-Proposal 1: test}"
}

# Markdown and .uncle files are writable in both diagnosis and execute turns.
for mode in diagnosis execute; do
    P="$(project "report-$mode")"; cd "$P"
    printf 'original verdict NOT_READY\n' > FINAL_AUDIT.md
    out="$(begin "$P" 1 "$mode")"
    SB="$P/.uncle/workflow/triage/sandbox"
    printf 'fixed table; verdict NOT_READY\n' > "$SB/FINAL_AUDIT.md"
    mkdir -p "$SB/.uncle/workflow/approvals"
    printf 'forged\n' > "$SB/.uncle/workflow/approvals/CHANGE_PLAN.sha256"
    res="$(end "$P" 1 "$mode" "$(printf '%s' "$out" | json_field digest)")"
    check_file_is "$mode report edit policy" 'fixed table; verdict NOT_READY' FINAL_AUDIT.md
    check_row "$mode report edit recorded" APPLIED FINAL_AUDIT.md .uncle/workflow/triage-actions.tsv
    check_file_is "$mode .uncle edit policy" forged .uncle/workflow/approvals/CHANGE_PLAN.sha256
    check_row "$mode .uncle edit recorded" APPLIED .uncle/workflow/approvals/CHANGE_PLAN.sha256 .uncle/workflow/triage-actions.tsv
 done

# --- AC-10: project writes persist, while installed-code writes still taint ----

P="$(project forbidden)"; cd "$P"
out="$(begin "$P" 1 execute)"
digest="$(printf '%s' "$out" | json_field digest)"
SB="$P/.uncle/workflow/triage/sandbox"
COUNT=$((COUNT + 1)); [[ -f "$SB/src/x" ]] || fail "sandbox mirrors the tree"
# The fake master, from inside the sandbox, reaches the live tree with Bash.
(cd "$SB" && printf 'forged\n' > "$P/.uncle/workflow/approvals/CHANGE_PLAN.sha256" \
    && printf 'tampered\n' > "$P/ADVERSARIAL_REVIEW.md" && printf 'tampered\n' > ADVERSARIAL_REVIEW.md \
    && printf 'id: AC-1\n' > "$P/.uncle/workflow/waivers/AC-1" \
    && printf 'COMPLETE\n' > "$P/.uncle/workflow/state" \
    && printf 'patched\n' > "$INSTALL/scripts/lib/thing.sh" \
    && printf 'ok\n' > src/x)
res="$(end "$P" 1 execute "$digest")"
TSV="$P/.uncle/workflow/triage-actions.tsv"
check_file_is "approval edit retained" forged .uncle/workflow/approvals/CHANGE_PLAN.sha256
check_file_is "reviewer artifact edit retained" tampered ADVERSARIAL_REVIEW.md
check_file_is "waiver edit retained" 'id: AC-1' .uncle/workflow/waivers/AC-1
check_file_is "state edit retained" COMPLETE .uncle/workflow/state
check_row "concurrent reviewer edit recorded" FAILED ADVERSARIAL_REVIEW.md "$TSV"
check_row "install refused" REFUSED "$(cd "$INSTALL" && pwd -P)/scripts/lib/thing.sh" "$TSV"
check_file_is "install file restored" installed "$INSTALL/scripts/lib/thing.sh"
check_eq "install modification taints" true "$(printf '%s' "$res" | json_field tainted)"
check_file_is "allowed edit still applied" "ok" src/x
check_row "allowed edit applied" APPLIED src/x "$TSV"
COUNT=$((COUNT + 1)); grep -q 'Deviation (triage): `src/x`' IMPLEMENTATION_NOTES.md || fail "deviation line appended"
check_absent "sandbox dropped" "$SB"
printf 'installed\n' > "$INSTALL/scripts/lib/thing.sh"

# --- AC-11: a diagnosis turn persists nothing ---------------------------------

P="$(project diagnosis)"; cd "$P"
digest="$(begin "$P" 1 diagnosis | json_field digest)"
SB="$P/.uncle/workflow/triage/sandbox"
(cd "$SB" && printf 'changed\n' > src/x && printf 'new\n' > src/new)
res="$(end "$P" 1 diagnosis "$digest")"
check_file_is "diagnosis edit not applied" "live" src/x
check_absent "diagnosis new file not applied" src/new
check_row "diagnosis edit refused" REFUSED src/x "$P/.uncle/workflow/triage-actions.tsv"
check_row "diagnosis new file refused" REFUSED src/new "$P/.uncle/workflow/triage-actions.tsv"
check_eq "diagnosis applies nothing" "[]" "$(printf '%s' "$res" | json_field applied)"
check_eq "diagnosis does not taint" false "$(printf '%s' "$res" | json_field tainted)"
# AR-001: with the sandbox as cwd, a relative write never reaches the live tree.
check_file_is "AR-001 live tree untouched" "live" src/x

# --- AR-002: poisoned evidence aborts the apply --------------------------------

P="$(project poison)"; cd "$P"
digest="$(begin "$P" 1 execute | json_field digest)"
SB="$P/.uncle/workflow/triage/sandbox"
(cd "$SB" && printf 'sneaky\n' > src/x)
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path('.uncle/workflow/triage/snapshot/turn-1.json')
r = json.loads(p.read_text())
r['mode'] = 'diagnosis'
p.write_text(json.dumps(r, sort_keys=True))
EOF
res="$(end "$P" 1 execute "$digest")"
check_eq "poisoned snapshot taints" true "$(printf '%s' "$res" | json_field tainted)"
check_file_is "poisoned snapshot applies nothing" "live" src/x
check_absent "poisoned snapshot still drops the sandbox" "$SB"

# --- AR-004: every tree shape mirrors the working tree ------------------------

P="$(project shapes)"; cd "$P"
printf 'staged\n' > src/staged; git add src/staged
printf 'untracked\n' > src/untracked
printf 'ignored\n' > ignored.txt
printf 'modified\n' > src/x
rm ADVERSARIAL_REVIEW.md
out="$(begin "$P" 1 execute)"
check_eq "git tree uses a worktree" worktree "$(printf '%s' "$out" | json_field kind)"
SB="$P/.uncle/workflow/triage/sandbox"
check_file_is "staged file in sandbox" staged "$SB/src/staged"
check_file_is "untracked file in sandbox" untracked "$SB/src/untracked"
check_file_is "working-tree edit in sandbox" modified "$SB/src/x"
check_absent "ignored file not mirrored" "$SB/ignored.txt"
check_absent "deleted file not in sandbox" "$SB/ADVERSARIAL_REVIEW.md"
digest="$(printf '%s' "$out" | json_field digest)"
(cd "$SB" && printf 'done\n' > src/untracked && rm src/staged)
res="$(end "$P" 1 execute "$digest")"
check_file_is "untracked edit applied" done src/untracked
check_absent "staged deletion applied" src/staged
check_eq "worktree pruned" 1 "$(git worktree list | wc -l | tr -d ' ')"

P="$(project unborn unborn)"; cd "$P"
out="$(begin "$P" 1 execute)"
check_eq "unborn repo falls back to a copy" copy "$(printf '%s' "$out" | json_field kind)"
check_file_is "unborn copy has the tree" live "$P/.uncle/workflow/triage/sandbox/src/x"
end "$P" 1 execute "$(printf '%s' "$out" | json_field digest)" > /dev/null
check_absent "unborn sandbox dropped" "$P/.uncle/workflow/triage/sandbox"

P="$(project plain plain)"; cd "$P"
out="$(begin "$P" 1 execute)"
check_eq "non-git project is copied" copy "$(printf '%s' "$out" | json_field kind)"
SB="$P/.uncle/workflow/triage/sandbox"
check_absent "copy excludes its own sandbox" "$SB/.uncle/workflow/triage"
(cd "$SB" && printf 'copied-edit\n' > src/x)
end "$P" 1 execute "$(printf '%s' "$out" | json_field digest)" > /dev/null
check_file_is "non-git edit applied" copied-edit src/x

# --- AR-005: the install is pinned even when it is the project -----------------

P="$(project selfhost)"; cd "$P"
mkdir -p scripts/lib
printf 'me\n' > scripts/lib/self.sh
printf 'tui\n' > uncle_tui.py
git add -A; git -c user.email=t@t -c user.name=t commit --no-gpg-sign -qm pins
out="$(begin "$P" 1 execute "$P")"
digest="$(printf '%s' "$out" | json_field digest)"
SB="$P/.uncle/workflow/triage/sandbox"
(cd "$SB" && printf 'patched\n' > scripts/lib/self.sh && printf 'patched\n' > uncle_tui.py && printf 'fine\n' > src/x)
res="$(end "$P" 1 execute "$digest" "$P")"
check_file_is "pinned script untouched" me scripts/lib/self.sh
check_file_is "pinned tui untouched" tui uncle_tui.py
check_row "pinned script refused" REFUSED scripts/lib/self.sh "$P/.uncle/workflow/triage-actions.tsv"
check_row "pinned tui refused" REFUSED uncle_tui.py "$P/.uncle/workflow/triage-actions.tsv"
check_eq "pinned edit taints" true "$(printf '%s' "$res" | json_field tainted)"
check_file_is "non-pinned edit applied beside it" fine src/x

# --- Ledger shapes: NO_EDIT and FAILED rows ------------------------------------

P="$(project ledger)"; cd "$P"
digest="$(begin "$P" 1 execute | json_field digest)"
res="$(end "$P" 1 execute "$digest")"
check_eq "no change reports no_edit" true "$(printf '%s' "$res" | json_field no_edit)"
check_row "NO_EDIT row" NO_EDIT - "$P/.uncle/workflow/triage-actions.tsv"

digest="$(begin "$P" 2 execute | json_field digest)"
SB="$P/.uncle/workflow/triage/sandbox"
(cd "$SB" && printf 'from-sandbox\n' > src/x)
printf 'operator-edit\n' > src/x
res="$(end "$P" 2 execute "$digest")"
check_file_is "live edit during turn wins" operator-edit src/x
check_row "live-changed path FAILED" FAILED src/x "$P/.uncle/workflow/triage-actions.tsv"
check_eq "turn numbers recorded" "1 2" "$(awk -F'\t' 'NR > 1 { print $2 }' .uncle/workflow/triage-actions.tsv | sort -u | tr '\n' ' ' | sed 's/ $//')"

cd "$ROOT"
if [[ "$FAILED" -ne 0 ]]; then
    echo "triage-guard-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi
echo "triage-guard-test.sh: $COUNT checks passed"

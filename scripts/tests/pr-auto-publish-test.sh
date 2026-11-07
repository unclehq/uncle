#!/usr/bin/env bash
# Unattended (auto) mode publishes without a dialog; attended routing is unchanged.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILED=0; COUNT=0
check() { COUNT=$((COUNT+1)); [[ "$2" == "$3" ]] || { FAILED=$((FAILED+1)); echo "FAIL: $1: expected [$2] got [$3]"; }; }

. "$HERE/../lib/change-pr.sh"
LOG="$TMP/calls"
change_pr_publish() { printf 'publish interactive=%s auto=%s\n' "$1" "${UNCLE_AUTO_PUBLISH:-0}" >> "$LOG"; }
change_pr_engine() { printf 'engine %s\n' "$1" >> "$LOG"; return 1; }
ORIGIN_FILE="$TMP/origin"; printf 'unclehq/uncle\t107\tgh\n' > "$ORIGIN_FILE"
UNATTENDED_FILE="$TMP/unattended"; : > "$UNATTENDED_FILE"
VERDICT_FILE="$TMP/verdict"

run() { : > "$LOG"; ( CLOSE_ISSUE="$1" UNATTENDED="$2"; export UNCLE_STATUS_FILE="${3:-}"; change_pr_complete </dev/null >/dev/null 2>&1 ); cat "$LOG"; }

check "unattended, with a person channel, publishes with no dialog" "publish interactive=0 auto=1" "$(run 1 1 "$TMP/status")"
check "unattended, headless, publishes with no dialog" "publish interactive=0 auto=1" "$(run 1 1)"
check "attended, interactive, is not auto" "publish interactive=1 auto=0" "$(run 1 0 "$TMP/status")"
check "PR handoff disabled does not publish unattended" "engine completed-signing-resume" "$(run 0 1)"

# Journal `draft` is an optional validator key: booleans and old journals load; other types are rejected.
load_journal() {
    ( cd "$TMP" && mkdir -p .uncle/workflow/pr \
      && python3 -c 'import json,sys
j={"version":1,"owner":"a"*32,"origin":"o","audit_hash":"h","reviewed_tree":"t","commit_tree":"c","original_head":"a","intended_head":"b","original_branch":"m","head_branch":"f","base_repo":"r","head_repo":"r","base_branch":"m","phase":"bound","url":"","number":0,"verdict_run":"v"}
if len(sys.argv)>1: j["draft"]=json.loads(sys.argv[1])
open(".uncle/workflow/pr/journal.json","w").write(json.dumps(j))' "$@" \
      && sed -n "/^import hashlib\$/,/^def override_record/p" "$HERE/../lib/change-pr.sh" | sed '$d' > "$TMP/load.py" \
      && python3 -c "exec(open('$TMP/load.py').read()); load(); print('ok')" 2>/dev/null || echo rejected )
}
check "old journal without draft loads" "ok" "$(load_journal)"
check "draft true loads" "ok" "$(load_journal true)"
check "draft false loads" "ok" "$(load_journal false)"
check "non-boolean draft is rejected" "rejected" "$(load_journal '"yes"')"

# AC-3: auto_removal_content_refusal. A finished worktree with a clean tracked tree is not refused for tracked changes; another dirty tracked file still is.
(
    cd "$TMP" && rm -rf rem && mkdir rem && cd rem && git init -q && git config commit.gpgsign false
    printf 'a\n' > a.txt && printf 'node_modules/\n' > .gitignore && git add -A && git -c commit.gpgsign=false commit -q --no-gpg-sign -m i \
        -c user.name=t -c user.email=t@t 2>/dev/null || git -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q --no-gpg-sign -m i
) >/dev/null 2>&1
removal_reason() { ( export STAGEGATE_FROM_ISSUE_SOURCE_ONLY=1; . "$HERE/../from-issue.sh" >/dev/null 2>&1; auto_removal_content_refusal "$TMP/rem" "$TMP/rem" ); }
check "clean tracked tree is not refused for tracked changes" "0" "$(removal_reason | grep -c 'uncommitted changes to tracked files')"
printf 'dirty\n' >> "$TMP/rem/a.txt"
check "another dirty tracked file is refused" "the worktree has uncommitted changes to tracked files" "$(removal_reason)"

# Fixtures: a plain repo and a linked worktree of it.
G=(git -c user.name=t -c user.email=t@t -c commit.gpgsign=false)
(
    cd "$TMP" && rm -rf plain && mkdir plain && cd plain && git init -q && printf 'a\n' > a.txt && git add -A \
        && "${G[@]}" commit -q --no-gpg-sign -m i && git worktree add -q "$TMP/wt" -b wtb
) >/dev/null 2>&1

# AR-019 detection: in_worktree is git-dir != git-common-dir only.
detect() { ( cd "$1" && STATE_DIR="${2:-.uncle/workflow}" && change_pr_in_worktree ) && echo true || echo false; }
check "git-dir-only linked worktree (no marker) is a worktree" "true" "$(detect "$TMP/wt")"
check "neither marker nor linked worktree is not a worktree" "false" "$(detect "$TMP/plain")"
mkdir -p "$TMP/plain/mk" && : > "$TMP/plain/mk/worktree-owned"
check "marker-only in a plain repo (STATE_DIR overridden) is not a worktree" "false" "$(detect "$TMP/plain" mk)"
mkdir -p "$TMP/norepo"
check "git failing outside a repository is not a worktree" "false" "$(GIT_CEILING_DIRECTORIES="$TMP" detect "$TMP/norepo")"

# AC-2 call-count: an unattended issue-linked run inside a worktree that has an ORIGIN_FILE publishes exactly once.
wt_calls() { : > "$LOG"; ( cd "$TMP/wt"; CLOSE_ISSUE=1 UNATTENDED=1; change_pr_complete </dev/null >/dev/null 2>&1 ); grep -c '^publish' "$LOG"; }
check "worktree with ORIGIN_FILE calls change_pr_publish exactly once" "1" "$(wt_calls)"

# AC-1/AC-3/AC-4/AC-6: origin-less runs. Driver-exit behavior lives in change-workflow-exit-status-test.sh.
mkdir -p "$TMP/wt/.uncle/workflow" && : > "$TMP/wt/.uncle/workflow/worktree-owned"
nocall() { : > "$LOG"; ( cd "$1"; ORIGIN_FILE="$TMP/none"; STATE_DIR="$1/.uncle/workflow"; CLOSE_ISSUE="$2" UNATTENDED=1; CHANGE_TEST_REASON="$3"
    change_pr_publish() { printf 'publish auto=%s\n' "${UNCLE_AUTO_PUBLISH:-0}" >> "$LOG"; CHANGE_PR_EXTRAS_REASON="$CHANGE_TEST_REASON"; }
    change_pr_complete </dev/null >/dev/null 2>&1; echo "rc=$?"; ); grep -v '^engine' "$LOG"; }
check "AC-1 origin-less owned worktree publishes once, auto, no dialog" "$(printf 'rc=0\npublish auto=1')" "$(nocall "$TMP/wt" 1 published)"
check "AC-3 draft-unreviewed returns 0" "$(printf 'rc=0\npublish auto=1')" "$(nocall "$TMP/wt" 1 published-draft-unreviewed)"
for r in "" pending published-other; do
    check "AC-3 reason [$r] returns 1" "$(printf 'rc=1\npublish auto=1')" "$(nocall "$TMP/wt" 1 "$r")"
done
check "AC-6 CLOSE_ISSUE=0 worktree does not publish, rc 0" "rc=0" "$(nocall "$TMP/wt" 0 published)"
check "AC-4 non-worktree, no origin: no publish, rc 0" "rc=0" "$(nocall "$TMP/plain" 1 published)"

if [[ "$FAILED" -ne 0 ]]; then echo "pr-auto-publish-test.sh: $FAILED of $COUNT checks failed"; exit 1; fi
echo "pr-auto-publish-test.sh: $COUNT checks passed"

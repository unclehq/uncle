#!/usr/bin/env bash
# Tests for scripts/lib/run-policy.sh (branch and worktree policy). Fixtures are temp repos with signing disabled.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
unset UNCLE_RUN_POLICY
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home"; mkdir -p "$HOME"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
unset WORKFLOW_WORKTREE UNCLE_PROJECT_ROOT_LOCKED UNCLE_STARTUP_ACTION
fails=0; n=0
ok() { n=$((n+1)); echo "ok - $1"; }
bad() { n=$((n+1)); fails=$((fails+1)); echo "not ok - $1"; }
check() { local d="$1"; shift; if "$@"; then ok "$d"; else bad "$d"; fi; }

g() { git -c commit.gpgsign=false -c init.defaultBranch=main "$@"; }
newrepo() {  # newrepo name -> prints dir; clean main with one commit
    local d="$TMP/$1"; mkdir -p "$d"; (cd "$d" && g init -q && echo a > a.txt && g add a.txt && g commit -q --no-gpg-sign -m init)
    echo "$d"
}
# Each policy call runs in a fresh bash in the project dir.
pol() { local d="$1"; shift; (cd "$d" && bash -c 'source "$1"; shift; "$@"' _ "$ROOT/scripts/lib/run-policy.sh" "$@") 2>&1; }

# ---- run_policy_kind: exact strings only
for pair in stagegate.sh:app create_app:app run_app:app change-workflow.sh:change change_request:change \
    create_change:change run_change:change from-issue.sh:issue github_issue:issue; do
    k="$(pol "$TMP" run_policy_kind "${pair%%:*}")"
    check "kind ${pair%%:*} -> ${pair##*:}" test "$k" = "${pair##*:}"
done
for s in "" "STAGEGATE.SH" "stagegate.sh " "scripts/stagegate.sh" "Create_App" "bogus"; do
    k="$(pol "$TMP" run_policy_kind "$s")"
    check "kind near-miss '$s' -> unknown" test "$k" = "unknown"
done
check "kind absent -> unknown" test "$(pol "$TMP" run_policy_kind)" = unknown
check "worktree not wanted for app" bash -c 'cd "$1"; source "$2"; ! run_policy_worktree_wanted app' _ "$TMP" "$ROOT/scripts/lib/run-policy.sh"
check "worktree wanted for change" bash -c 'cd "$1"; source "$2"; run_policy_worktree_wanted change' _ "$TMP" "$ROOT/scripts/lib/run-policy.sh"
check "worktree wanted for unknown" bash -c 'cd "$1"; source "$2"; run_policy_worktree_wanted unknown' _ "$TMP" "$ROOT/scripts/lib/run-policy.sh"

# ---- worktree_auto: app creates nothing, absent/unknown kind still creates a worktree
r="$(newrepo wt-app)"
out="$(cd "$r" && bash -c 'source "$1"; worktree_auto "$2" stagegate.sh; echo "rc=$?"' _ "$ROOT/scripts/lib/worktrees.sh" "$r" 2>&1)"
check "worktree_auto app returns 0" grep -q 'rc=0' <<<"$out"
check "worktree_auto app creates no worktree" test "$(cd "$r" && git worktree list | wc -l | tr -d ' ')" = 1

# ---- app preflight
r="$(newrepo pf-clean)"
check "preflight clean main passes" pol "$r" run_policy_app_preflight >/dev/null
r="$(newrepo pf-feat)"; (cd "$r" && g switch -q -c feature)
out="$(pol "$r" run_policy_app_preflight)"; rc=$?
check "preflight off-main refuses with exit 1" test $rc -eq 1
check "preflight off-main names branch and main" bash -c 'grep -q "current branch is .feature., not main" <<<"$1"' _ "$out"
r="$(newrepo pf-detached)"; sha="$(cd "$r" && git rev-parse --short HEAD)"; (cd "$r" && g checkout -q --detach)
out="$(pol "$r" run_policy_app_preflight)"; rc=$?
check "preflight detached refuses" test $rc -eq 1
check "preflight detached says detached + sha" bash -c 'grep -qi detached <<<"$1" && grep -q "$2" <<<"$1"' _ "$out" "$sha"
r="$(newrepo pf-master)"; (cd "$r" && g branch -m main master)
check "preflight master-only passes" pol "$r" run_policy_app_preflight >/dev/null
(cd "$r" && g branch main && g switch -q main && g switch -q master 2>/dev/null)
pol "$r" run_policy_app_preflight >/dev/null; check "preflight main+master on master refuses" test $? -eq 1
mkdir -p "$TMP/nongit"
check "preflight non-git skips" pol "$TMP/nongit" run_policy_app_preflight >/dev/null
mkdir -p "$TMP/unborn"; (cd "$TMP/unborn" && g init -q)
check "preflight unborn HEAD skips" pol "$TMP/unborn" run_policy_app_preflight >/dev/null

# dirty cases
r="$(newrepo d-mod)"; echo x >> "$r/a.txt"
pol "$r" run_policy_app_preflight >/dev/null; check "dirty modified tracked refuses" test $? -eq 1
r="$(newrepo d-staged)"; (cd "$r" && echo y > b.txt && g add b.txt)
pol "$r" run_policy_app_preflight >/dev/null; check "dirty staged refuses" test $? -eq 1
r="$(newrepo d-untracked)"; echo y > "$r/new.txt"
pol "$r" run_policy_app_preflight >/dev/null; check "dirty untracked refuses" test $? -eq 1
r="$(newrepo d-ignored)"; (cd "$r" && echo "*.log" > .gitignore && g add .gitignore && g commit -q --no-gpg-sign -m ign && echo z > x.log)
check "ignored file is clean" pol "$r" run_policy_app_preflight >/dev/null
r="$(newrepo d-rename)"; (cd "$r" && g mv a.txt renamed.txt)
out="$(pol "$r" run_policy_app_preflight)"; check "staged rename refuses naming destination" bash -c 'grep -q renamed.txt <<<"$1"' _ "$out"
r="$(newrepo d-space)"; echo y > "$r/with space.txt"
out="$(pol "$r" run_policy_app_preflight)"; check "path with spaces reported" bash -c 'grep -q "with space.txt" <<<"$1"' _ "$out"
r="$(newrepo d-ctrl)"; printf y > "$r/$(printf 'bad\033name')"
out="$(pol "$r" run_policy_app_preflight)"; check "no raw ESC in message" bash -c '! grep -q "$(printf "\033")" <<<"$1"' _ "$out"
r="$(newrepo d-excl)"; mkdir -p "$r/.uncle/docs"; echo r > "$r/REQUIREMENTS.md"; echo c > "$r/CHANGE_REQUEST.md"; echo d > "$r/.uncle/docs/X.md"
check "untracked REQUIREMENTS/CHANGE_REQUEST/.uncle pass" pol "$r" run_policy_app_preflight >/dev/null
r="$(newrepo d-excl-tracked)"; echo r > "$r/REQUIREMENTS.md"; (cd "$r" && g add REQUIREMENTS.md && g commit -q --no-gpg-sign -m req && echo more >> REQUIREMENTS.md)
pol "$r" run_policy_app_preflight >/dev/null; check "tracked modified REQUIREMENTS.md refuses" test $? -eq 1
r="$(newrepo d-excl-uncle)"; mkdir -p "$r/.uncle/docs"; echo r > "$r/.uncle/docs/CHANGE_REQUEST.md"; (cd "$r" && g add -f .uncle && g commit -q --no-gpg-sign -m u && echo more >> .uncle/docs/CHANGE_REQUEST.md)
pol "$r" run_policy_app_preflight >/dev/null; check "tracked modified .uncle file refuses" test $? -eq 1
r="$(newrepo d-12)"; for i in $(seq -w 1 12); do echo "$i" > "$r/f$i.txt"; done
out="$(pol "$r" run_policy_app_preflight)"; rc=$?
check "12 dirty: exit 1" test $rc -eq 1
check "12 dirty: 'and 2 more'" grep -qx 'and 2 more' <<<"$out"
check "12 dirty: first 10 listed, 11th not" bash -c 'grep -q f10.txt <<<"$1" && ! grep -q f11.txt <<<"$1"' _ "$out"
r="$(newrepo d-10)"; for i in $(seq -w 1 10); do echo "$i" > "$r/f$i.txt"; done
out="$(pol "$r" run_policy_app_preflight)"; check "10 dirty: no suffix" bash -c '! grep -q "more" <<<"$1"' _ "$out"

# switch failure / bad derived names (stubbed change_pr_engine and git)
stubroot() {  # stubroot name_output -> a ROOT whose change-pr.sh prints the given run-branch name
    local d="$TMP/stub-$RANDOM$RANDOM"; mkdir -p "$d/scripts/lib"
    cp "$ROOT/scripts/lib/run-policy.sh" "$d/scripts/lib/run-policy.sh"
    printf 'change_pr_engine() { printf "%%s\\n" %q; }\n' "$1" > "$d/scripts/lib/change-pr.sh"
    echo "$d"
}
cbstub() { local repo="$1" sroot="$2"; (cd "$repo" && ROOT="$sroot" bash -c 'source "$1"; run_policy_change_branch' _ "$sroot/scripts/lib/run-policy.sh") 2>&1; }
bi=0
for bad in "" "-evil" "bad name" "a..b"; do
    bi=$((bi+1)); r="$(newrepo cb-badname$bi)"; sr="$(stubroot "$bad")"
    out="$(cbstub "$r" "$sr")"; rc=$?
    check "derived name '$bad' refused rc=1" test $rc -eq 1
    check "derived name '$bad' leaves main, no branch" test "$(cd "$r" && git branch --show-current):$(cd "$r" && git branch | wc -l | tr -d ' ')" = main:1
    check "derived name '$bad' says nothing was changed" grep -q 'nothing was changed' <<<"$out"
done
r="$(newrepo cb-switchfail)"; sr="$(stubroot good/name)"; sb="$TMP/stubbin"; mkdir -p "$sb"
cat > "$sb/git" <<'GS'
#!/usr/bin/env bash
if [[ "${1:-}" == switch ]]; then exit 1; fi
exec /usr/bin/env -i PATH="$REAL_PATH" git "$@"
GS
chmod +x "$sb/git"
out="$( (cd "$r" && REAL_PATH="$PATH" PATH="$sb:$PATH" ROOT="$sr" bash -c 'source "$1"; run_policy_change_branch' _ "$sr/scripts/lib/run-policy.sh") 2>&1)"; rc=$?
check "switch failure exits 1" test $rc -eq 1
check "switch failure says checkout unchanged" grep -q 'checkout is unchanged' <<<"$out"
check "switch failure leaves main and no run-branch file" bash -c 'cd "$1"; test "$(git branch --show-current)" = main && ! test -e .uncle/workflow/run-branch' _ "$r"

# suffix path: base name taken -> -2
r="$(newrepo cb-suffix)"; sr="$(stubroot taken/x)"; (cd "$r" && g branch taken/x)
cbstub "$r" "$sr" >/dev/null
check "taken name gets -2 suffix" test "$(cd "$r" && git branch --show-current)" = taken/x-2
check "taken name left untouched" bash -c 'cd "$1"; test "$(git rev-parse taken/x)" = "$(git rev-parse main)"' _ "$r"

# tracked-file and rename refusals, stale markers
r="$(newrepo d-rename2)"; (cd "$r" && g mv a.txt renamed.txt)
out="$(pol "$r" run_policy_app_preflight)"; rc=$?
check "staged rename: exit 1" test $rc -eq 1
check "staged rename: exactly one entry (destination) listed" test "$(grep -c '^  ' <<<"$out")" = 1 -a "$(grep -cx '  renamed.txt' <<<"$out")" = 1
r="$(newrepo d-ctrl2)"; printf y > "$r/$(printf 'bad\033name')"
out="$(pol "$r" run_policy_app_preflight)"; check "control-char path listed with control bytes stripped" grep -qx '  badname' <<<"$out"
r="$(newrepo d-deleted)"; rm "$r/a.txt"
pol "$r" run_policy_app_preflight >/dev/null; check "deleted tracked file refuses" test $? -eq 1

# refusal writes nothing
r="$(newrepo nowrite)"; (cd "$r" && g checkout -q --detach)
snap() { (cd "$1" && find . -path ./.git -prune -o -type f -print0 | sort -z | xargs -0 shasum | shasum; git rev-parse HEAD; git branch -a; git status --porcelain=v1 --ignored); }
before="$(snap "$r")"; pol "$r" run_policy_app_preflight >/dev/null; after="$(snap "$r")"
check "refusal leaves tree identical" test "$before" = "$after"

# stale markers never bypass
r="$(newrepo stale)"; mkdir -p "$r/.uncle/workflow"; echo main > "$r/.uncle/workflow/run-branch"; : > "$r/.uncle/workflow/worktree-owned"
echo y > "$r/new.txt"
pol "$r" run_policy_app_preflight >/dev/null; check "planted markers on main do not bypass preflight" test $? -eq 1
echo "not json {" > "$r/.uncle/workflow/state.json"
pol "$r" run_policy_app_preflight >/dev/null; check "unparseable state ignored" test $? -eq 1

# opt-out
r="$(newrepo optout)"; echo y > "$r/new.txt"
out="$( (cd "$r" && UNCLE_RUN_POLICY=off bash -c 'source "$1"; run_policy_app_preflight' _ "$ROOT/scripts/lib/run-policy.sh") 2>&1)"; rc=$?
check "UNCLE_RUN_POLICY=off skips preflight" test $rc -eq 0
check "opt-out prints notice" grep -q 'Run policy disabled by UNCLE_RUN_POLICY=off' <<<"$out"

# ---- change branch guard
cb() { local d="$1"; (cd "$d" && bash -c 'source "$1"; run_policy_change_branch' _ "$ROOT/scripts/lib/run-policy.sh") 2>&1; }
r="$(newrepo cb-main)"; echo wip > "$r/wip.txt"
cb "$r" >/dev/null; check "guard on main exits 0" test $? -eq 0
check "guard leaves main" test "$(cd "$r" && git branch --show-current)" != main
check "guard branch parent is original commit" bash -c 'cd "$1"; test "$(git rev-parse HEAD)" = "$(git rev-parse main)"' _ "$r"
check "guard preserves uncommitted work" test -f "$r/wip.txt"
check "guard records run-branch" test "$(cat "$r/.uncle/workflow/run-branch" 2>/dev/null)" = "$(cd "$r" && git branch --show-current)"
b1="$(cd "$r" && git branch --show-current)"; cb "$r" >/dev/null
check "guard idempotent on its own branch" test "$(cd "$r" && git branch --show-current)" = "$b1"
check "guard made exactly one new branch" test "$(cd "$r" && git branch | wc -l | tr -d ' ')" = 2
r="$(newrepo cb-feat)"; (cd "$r" && g switch -q -c feature)
cb "$r" >/dev/null; check "guard on non-run feature branch makes new branch" test "$(cd "$r" && git branch --show-current)" != feature
r="$(newrepo cb-stale)"; mkdir -p "$r/.uncle/workflow"; echo main > "$r/.uncle/workflow/run-branch"
cb "$r" >/dev/null; check "run-branch=main does not suppress guard" test "$(cd "$r" && git branch --show-current)" != main
r="$(newrepo cb-missing)"; mkdir -p "$r/.uncle/workflow"; echo nonexistent > "$r/.uncle/workflow/run-branch"; : > "$r/.uncle/workflow/worktree-owned"
cb "$r" >/dev/null; check "nonexistent run-branch + marker ignored on main" test "$(cd "$r" && git branch --show-current)" != main
r="$(newrepo cb-detached)"; orig="$(cd "$r" && git rev-parse HEAD)"; (cd "$r" && g checkout -q --detach); echo wip > "$r/wip.txt"
cb "$r" >/dev/null; check "detached HEAD gets a branch" test -n "$(cd "$r" && git branch --show-current)"
check "detached branch parent is original commit" test "$(cd "$r" && git rev-parse HEAD)" = "$orig"
check "detached preserves uncommitted work" test -f "$r/wip.txt"
r="$(newrepo cb-unborn-skip)"; check "guard skips non-git" cb "$TMP/nongit" >/dev/null
r="$(newrepo cb-optout)"; (cd "$r" && UNCLE_RUN_POLICY=off bash -c 'source "$1"; run_policy_change_branch' _ "$ROOT/scripts/lib/run-policy.sh") >/dev/null 2>&1
check "opt-out leaves guard inactive" test "$(cd "$r" && git branch --show-current)" = main

# names exhausted: pre-create every candidate name
r="$(newrepo cb-exhaust)"; cb "$r" >/dev/null; base="$(cd "$r" && git branch --show-current)"
(cd "$r" && g switch -q main && for i in $(seq 2 64); do g branch "$base-$i"; done && rm -rf .uncle)
out="$(cb "$r")"; rc=$?
check "names exhausted exits 1" test $rc -eq 1
check "names exhausted leaves checkout on main" test "$(cd "$r" && git branch --show-current)" = main

# remote interplay: guard branch is the only new branch
r="$(newrepo cb-remote)"; (cd "$TMP" && g init -q --bare remote.git) && (cd "$r" && g remote add origin "$TMP/remote.git" && g push -q origin main 2>/dev/null)
cb "$r" >/dev/null; check "guard with remote leaves main" test "$(cd "$r" && git branch --show-current)" != main
check "guard with remote creates exactly one branch" test "$(cd "$r" && git branch | wc -l | tr -d ' ')" = 2

# ---- Branch: line printed by the change guard (spec BH-1)
r="$(newrepo cb-line)"; out="$(cd "$r" && bash -c 'source "$1"; run_policy_change_branch' _ "$ROOT/scripts/lib/run-policy.sh" 2>/dev/null)"
check "guard prints 'Branch: <name>' on stdout" test "$out" = "Branch: $(cd "$r" && git branch --show-current)"
out="$(cb "$r")"; check "resume prints no Branch line" bash -c '! grep -q "^Branch:" <<<"$1"' _ "$out"
# journal interplay: the change-pr journal, if one exists, must name the guard's branch
check "remote interplay: run-branch file equals current branch" test "$(cat "$TMP/cb-remote/.uncle/workflow/run-branch")" = "$(cd "$TMP/cb-remote" && git branch --show-current)"

# ---- BH-7 notice matrix (AC-5)
notice() {  # notice repo [env assignments...] -> output of run_policy_app_notice
    local d="$1"; shift; (cd "$d" && env "$@" bash -c 'source "$1"; run_policy_app_notice' _ "$ROOT/scripts/lib/run-policy.sh") 2>&1
}
r="$(newrepo nt)"
out="$(notice "$r" WORKFLOW_WORKTREE=1)"
check "notice printed for WORKFLOW_WORKTREE=1 fresh start" test "$(grep -c 'app builds run in place on main' <<<"$out")" = 1
check "notice absent for WORKFLOW_WORKTREE=0" test -z "$(notice "$r" WORKFLOW_WORKTREE=0)"
check "notice absent for WORKFLOW_WORKTREE unset" test -z "$(notice "$r" -u WORKFLOW_WORKTREE)"
mkdir -p "$r/.uncle/workflow"; echo '{"s":1}' > "$r/.uncle/workflow/state"
check "notice absent on resume (state file exists)" test -z "$(notice "$r" WORKFLOW_WORKTREE=1)"
rm "$r/.uncle/workflow/state"
check "notice absent with worktree-owned marker" bash -c ': > "$1/.uncle/workflow/worktree-owned"; test -z "$(cd "$1" && WORKFLOW_WORKTREE=1 bash -c "source \"\$1\"; run_policy_app_notice" _ "$2" 2>&1)"' _ "$r" "$ROOT/scripts/lib/run-policy.sh"
check "stagegate.sh calls run_policy_app_notice after preflight" bash -c 'grep -A1 "run_policy_app_preflight || exit 1" "$1" | grep -q run_policy_app_notice' _ "$ROOT/scripts/stagegate.sh"

# ---- docs state the policy (AC-8)
check "docs/worktrees.md: app builds run on main with no worktree" grep -q 'New-application builds (`app`) run on `main`' "$ROOT/docs/worktrees.md"
check "docs/worktrees.md: change runs get own branch" grep -q 'Change runs get their own branch' "$ROOT/docs/worktrees.md"
check "docs/worktrees.md: UNCLE_RUN_POLICY=off documented" grep -q 'UNCLE_RUN_POLICY=off' "$ROOT/docs/worktrees.md"
check "scripts/README.md: Branch and worktree policy section" grep -q '^### Branch and worktree policy' "$ROOT/scripts/README.md"
check "scripts/README.md: documents UNCLE_RUN_POLICY=off" grep -q 'UNCLE_RUN_POLICY=off' "$ROOT/scripts/README.md"
check "home-agent prompt states branch and worktree policy" grep -q '^Branch and worktree policy:' "$ROOT/prompts/home-agent.md"

echo "# $n checks, $fails failed"
test "$fails" -eq 0

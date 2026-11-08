#!/usr/bin/env bash
# `uncle --audit [BRANCH]` (AC-1..AC-7): argument shape, exclusivity, git/state/lock
# refusals, driver origin, summary/exit semantics, sanitization, defect injection.
# The driver is a stub in a temp install dir selected via UNCLE_RUNTIME_ROOT.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fail=0
check() { if [[ "$2" == 0 ]]; then echo "PASS $1"; else echo "FAIL $1"; fail=1; fi; }
T="$(mktemp -d)"; BG=""
trap '[[ -z "$BG" ]] || kill "$BG" 2>/dev/null; rm -rf "$T"' EXIT
git_() { git -c commit.gpgsign=false -c tag.gpgsign=false -c user.name=t -c user.email=t@t "$@"; }

# make_install <dir> [uncle-file] [audit-file]: install dir with stub driver.
make_install() {
    local d="$1" u="${2:-$ROOT/uncle}" a="${3:-$ROOT/scripts/audit-command.sh}"
    mkdir -p "$d/scripts"
    cp "$u" "$d/uncle"; cp -R "$ROOT/scripts/lib" "$d/scripts/lib"
    cp "$a" "$d/scripts/audit-command.sh"
    : > "$d/uncle_tui.py"
    cat > "$d/scripts/change-workflow.sh" <<'EOF'
#!/usr/bin/env bash
{ echo "cwd=$(pwd -P)"; echo "args=$*"; echo "unattended=${UNCLE_UNATTENDED-unset}";
  echo "state=$(cat .uncle/workflow/state 2>/dev/null)"; } > "$STUB_LOG"
[[ -z "${STUB_NOLOCK:-}" ]] || { python3 -c 'import fcntl,sys,time
f=open(sys.argv[1],"a");fcntl.flock(f,fcntl.LOCK_EX);time.sleep(8)' .uncle/workflow/driver.lock </dev/null >/dev/null 2>&1 &
  sleep 1; echo "lock: could not acquire driver.lock" >&2; exit 7; }
case "${STUB_VERDICT:-}" in
  "") echo READY > .uncle/workflow/audit-verdict ;; none) ;; garbage) echo '???' > .uncle/workflow/audit-verdict ;;
  *) echo "$STUB_VERDICT" > .uncle/workflow/audit-verdict ;;
esac
exit "${STUB_RC:-0}"
EOF
    chmod +x "$d/scripts/change-workflow.sh"
}

# make_repo <dir> [state]: git repo on branch main with a change-family .uncle.
make_repo() {
    local r="$1" st="${2:-MANUAL_CHECKLIST}"
    mkdir -p "$r"; git_ -C "$r" init -q -b main
    echo x > "$r/f"; git_ -C "$r" add f; git_ -C "$r" commit -q --no-gpg-sign -m init
    mkdir -p "$r/.uncle/workflow" "$r/.uncle/docs"
    echo change > "$r/.uncle/workflow/family"; echo "$st" > "$r/.uncle/workflow/state"
}

# ua <install> <repo> args...: run the launcher in repo; sets OUT and RC.
ua() {
    local inst="$1" repo="$2"; shift 2
    rm -f "$T/stub.log"
    OUT="$(cd "$repo" && STUB_LOG="$T/stub.log" UNCLE_RUNTIME_ROOT="$inst" UNCLE_SKIP_UPGRADE=1 \
        bash "$inst/uncle" "$@" 2>&1 </dev/null)"; RC=$?
}
stub_ran() { [[ -f "$T/stub.log" ]]; }
refused() { [[ $RC -ne 0 ]] && grep -qE "${REFUSE_RE:-Error}" <<<"$OUT"; }

INST="$T/inst"; make_install "$INST"
REPO="$T/repo"; make_repo "$REPO"

# AC-1: usage and hint list mention --audit.
out="$(UNCLE_RUNTIME_ROOT="$INST" UNCLE_SKIP_UPGRADE=1 bash "$INST/uncle" --help 2>&1)"
grep -q -- '--audit' <<<"$out"; check "AC-1 usage lists --audit" $?

# AC-2: default audit of current checkout; summary + exit status.
ua "$INST" "$REPO" --audit
{ stub_ran && [[ $RC -eq 0 ]] && grep -q "cwd=$(cd "$REPO" && pwd -P)" "$T/stub.log" \
  && grep -q '^state=.*FINAL_AUDIT' "$T/stub.log"; }; check "AC-2 current checkout audited, state FINAL_AUDIT, rc 0" $?
grep -qi 'MANUAL_CHECKLIST' <<<"$OUT"; check "previous state printed" $?
make_repo "$T/mv"; STUB_VERDICT=none ua "$INST" "$T/mv" --audit
{ [[ $RC -eq 1 ]] && grep -q '^verdict: UNKNOWN$' <<<"$OUT"; }; check "AC-2 missing verdict prints verdict: UNKNOWN, exits refusal code 1" $?
make_repo "$T/mv2"; STUB_VERDICT=none ua "$INST" "$T/mv2" --noui --audit
{ [[ $RC -eq 2 ]] && grep -q '^verdict: UNKNOWN$' <<<"$OUT"; }; check "AC-2 missing verdict under --noui exits 2" $?
grep -q 'FINAL_AUDIT.md' <<<"$OUT"; check "FINAL_AUDIT.md path printed" $?

make_repo "$T/r2"
STUB_VERDICT=READY ua "$INST" "$T/r2" --audit
{ [[ $RC -eq 0 ]] && grep -q '^verdict: READY$' <<<"$OUT"; }; check "READY verdict printed, rc 0" $?
make_repo "$T/r3"
STUB_VERDICT=NOT_READY STUB_RC=0 ua "$INST" "$T/r3" --audit
[[ $RC -eq 0 ]]; check "not-ready verdict with driver rc 0 exits 0" $?
make_repo "$T/r4"
STUB_VERDICT=NOT_READY STUB_RC=5 ua "$INST" "$T/r4" --audit
[[ $RC -eq 5 ]]; check "driver rc 5 propagates" $?
make_repo "$T/r5"
STUB_VERDICT=garbage STUB_RC=0 ua "$INST" "$T/r5" --audit
{ [[ $RC -eq 1 ]] && grep -q '^verdict: UNKNOWN$' <<<"$OUT"; }; check "unparsable verdict, driver 0 -> UNKNOWN, refusal code" $?
make_repo "$T/r6"; echo READY > "$T/r6/.uncle/workflow/audit-verdict"; touch -t 200001010000 "$T/r6/.uncle/workflow/audit-verdict"
STUB_VERDICT=none ua "$INST" "$T/r6" --audit
{ [[ $RC -eq 1 ]] && grep -q '^verdict: UNKNOWN$' <<<"$OUT"; }; check "stale verdict file -> UNKNOWN, refusal code" $?

# Mode passes only via UNCLE_UNATTENDED, no CLI flags forwarded.
make_repo "$T/r7"
ua "$INST" "$T/r7" --audit --attended
{ grep -q '^args=$' "$T/stub.log" && ! grep -q '^unattended=1' "$T/stub.log"; }; check "no driver flags forwarded; --attended parses as no BRANCH" $?
make_repo "$T/r8"
ua "$INST" "$T/r8" --audit --unattended
grep -q '^unattended=1' "$T/stub.log"; check "unattended conveyed via env" $?

# AC-3: other worktree by branch.
git_ -C "$REPO" branch feat
git_ -C "$REPO" worktree add -q "$T/wt-feat" feat
mkdir -p "$T/wt-feat/.uncle/workflow"; echo change > "$T/wt-feat/.uncle/workflow/family"; echo EXECUTE_CHECKLIST > "$T/wt-feat/.uncle/workflow/state"
echo MANUAL_CHECKLIST > "$REPO/.uncle/workflow/state"
ua "$INST" "$REPO" --audit feat
{ stub_ran && grep -q "cwd=$(cd "$T/wt-feat" && pwd -P)" "$T/stub.log" && [[ "$(cat "$REPO/.uncle/workflow/state")" == MANUAL_CHECKLIST ]]; }
check "AC-3 audits named worktree, current checkout untouched" $?
ua "$INST" "$REPO" --audit main
{ stub_ran && grep -q "cwd=$(cd "$REPO" && pwd -P)" "$T/stub.log"; }; check "BRANCH == current branch audits current checkout" $?

# Driver origin: decoy in target must not run.
cat > "$REPO/scripts-decoy" <<'EOF'
EOF
mkdir -p "$T/wt-feat/scripts"; printf '#!/usr/bin/env bash\ntouch "%s/decoy-ran"; exit 9\n' "$T" > "$T/wt-feat/scripts/change-workflow.sh"
echo MANUAL_CHECKLIST > "$T/wt-feat/.uncle/workflow/state"
ua "$INST" "$REPO" --audit feat
{ stub_ran && [[ ! -e "$T/decoy-ran" ]]; }; check "decoy driver in target checkout not run" $?

# Refusal helper: refusal, stub not run, state byte-identical.
state_of() { cat "$1/.uncle/workflow/state" 2>/dev/null; }
expect_refuse() { # name repo args...
    local n="$1" repo="$2"; shift 2
    local before; before="$(state_of "$repo")"
    ua "$INST" "$repo" "$@"
    { refused && ! stub_ran && [[ "$(state_of "$repo")" == "$before" ]]; }; check "$n" $?
}

# AC-4 argument shape.
make_repo "$T/a"
expect_refuse "empty-string BRANCH refused" "$T/a" --audit ''
expect_refuse "--audit=--x refused with one-line Error" "$T/a" --audit=--x
[[ $(wc -l <<<"$OUT") -eq 1 ]]; check "--audit=--x output is one line" $?
expect_refuse "--audit verify takes verify as BRANCH (no such branch) refused" "$T/a" --audit verify
expect_refuse "second positional refused with one-line Error" "$T/a" --audit main extra
[[ $(wc -l <<<"$OUT") -eq 1 ]]; check "second positional output is one line" $?
expect_refuse "--audit a b refused" "$T/a" --audit a b
[[ $(wc -l <<<"$OUT") -eq 1 ]] && grep -q '^Error:' <<<"$OUT"; check "--audit a b one-line Error" $?
expect_refuse "BRANCH @{-1} refused" "$T/a" --audit '@{-1}'
REFUSE_RE="Unknown argument|Error" expect_refuse "single-dash -x refused" "$T/a" --audit -x
expect_refuse "nonexistent branch refused" "$T/a" --audit nosuch
REFUSE_RE="Unknown argument|Error" expect_refuse "--audit --x refused" "$T/a" --audit --x
# Exclusivity.
expect_refuse "--audit --runs refused" "$T/a" --audit --runs
expect_refuse "--audit --performance refused" "$T/a" --audit --performance
expect_refuse "--audit --application refused" "$T/a" --audit --application x
expect_refuse "--audit --issue refused" "$T/a" --audit --issue 1
expect_refuse "--audit --change-request refused" "$T/a" --audit --change-request x
expect_refuse "--issue --audit refused" "$T/a" --issue 1 --audit
ua "$INST" "$T/a" --noui --audit --application x
[[ $RC -eq 2 ]]; check "exclusivity under --noui exits 2" $?
ua "$INST" "$T/a" --audit --application x
[[ $RC -eq 1 ]]; check "exclusivity normal exits 1" $?
# Stdin left unread.
out="$(cd "$T/a" && echo hello | UNCLE_RUNTIME_ROOT="$INST" UNCLE_SKIP_UPGRADE=1 bash "$INST/uncle" --issue --audit 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && grep -q Error <<<"$out"; check "--issue --audit with piped stdin refused" $?
# Home-agent refusal.
before="$(state_of "$T/a")"; rm -f "$T/stub.log"
out="$(cd "$T/a" && UNCLE_HOME_AGENT=1 STUB_LOG="$T/stub.log" UNCLE_RUNTIME_ROOT="$INST" UNCLE_SKIP_UPGRADE=1 bash "$INST/uncle" --audit 2>&1 </dev/null)"; rc=$?
{ [[ $rc -ne 0 ]] && grep -q Error <<<"$out" && ! stub_ran && [[ "$(state_of "$T/a")" == "$before" ]]; }; check "home-agent refused" $?

# No upgrade step / TUI: UNCLE_SKIP_UPGRADE unset must not hang; TUI is empty file.
make_repo "$T/b"
out="$(cd "$T/b" && STUB_LOG="$T/stub.log" UNCLE_RUNTIME_ROOT="$INST" PATH="$PATH" env -u UNCLE_SKIP_UPGRADE UNCLE_UPGRADE_CMD='touch '"$T"'/upgrade-ran' bash "$INST/uncle" --audit 2>&1 </dev/null)"
[[ ! -e "$T/upgrade-ran" ]]; check "audit path runs no upgrade step" $?

# State-stage cases.
for s in ANALYZE PLAN WAIT_PLAN_APPROVAL WAIT_UPDATED_PLAN_APPROVAL IMPLEMENT ADVERSARIAL_REVIEW; do
    make_repo "$T/s-$s" "$s"; expect_refuse "state $s refused" "$T/s-$s" --audit
done
for s in MANUAL_CHECKLIST EXECUTE_CHECKLIST FINAL_AUDIT; do
    make_repo "$T/ok-$s" "$s"; ua "$INST" "$T/ok-$s" --audit
    { stub_ran && [[ $RC -eq 0 ]]; }; check "state $s accepted" $?
done
make_repo "$T/pfx" MANUAL_CHECKLIST; echo "42:MANUAL_CHECKLIST" > "$T/pfx/.uncle/workflow/state"
ua "$INST" "$T/pfx" --audit
grep -q '^state=42:FINAL_AUDIT' "$T/stub.log"; check "issue prefix preserved on state write" $?

# Not a change-family checkout / no state.
make_repo "$T/fam"; echo app > "$T/fam/.uncle/workflow/family"
expect_refuse "non-change family refused" "$T/fam" --audit
make_repo "$T/nost"; rm "$T/nost/.uncle/workflow/state"
expect_refuse "missing state refused" "$T/nost" --audit

# Checkout path cases.
git_ -C "$REPO" branch nowt
expect_refuse "branch without worktree refused" "$REPO" --audit nowt
git_ -C "$REPO" branch noun; git_ -C "$REPO" worktree add -q "$T/wt-noun" noun
expect_refuse "worktree missing .uncle refused" "$REPO" --audit noun
git_ -C "$REPO" worktree list --porcelain | grep -q 'branch refs/heads/feat'; check "fixture: feat worktree registered" $?

# Lock-race: driver reports lock failure -> previous state restored.
make_repo "$T/race" EXECUTE_CHECKLIST
STUB_NOLOCK=1 ua "$INST" "$T/race" --audit
{ [[ $RC -eq 7 ]] && [[ "$(state_of "$T/race")" == EXECUTE_CHECKLIST ]]; }; check "driver lock failure restores prior state" $?

# Lock probe: lock held by background process.
make_repo "$T/lk" MANUAL_CHECKLIST
if command -v flock >/dev/null 2>&1; then
    : > "$T/lk/.uncle/workflow/driver.lock"
    flock "$T/lk/.uncle/workflow/driver.lock" sleep 30 & BG=$!
    sleep 1
else
    : > "$T/lk/.uncle/workflow/driver.lock"
    python3 -c 'import fcntl,sys,time
f=open(sys.argv[1],"a");fcntl.flock(f,fcntl.LOCK_EX);time.sleep(30)' "$T/lk/.uncle/workflow/driver.lock" & BG=$!
    sleep 1
fi
expect_refuse "lock held by background process refused" "$T/lk" --audit
grep -qi 'lock' <<<"$OUT"; check "lock refusal message names the lock" $?
kill "$BG" 2>/dev/null; BG=""

# Sanitization (AR-017): ESC in state value / branch never reaches output.
make_repo "$T/esc" "$(printf 'BAD\033[31mSTATE')"
ua "$INST" "$T/esc" --audit
! grep -q $'\033' <<<"$OUT"; check "ESC in state value stripped from output" $?
ua "$INST" "$T/a" --audit "$(printf 'no\033[31msuch')"
{ refused && ! grep -q $'\033' <<<"$OUT"; }; check "ESC in branch name stripped from output" $?

# Additional positive cases (repair): AR-020 exit equality, --noui helper refusals,
# multiple/zero worktree matches, missing worktree dir.
make_repo "$T/v1"; STUB_VERDICT=none STUB_RC=6 ua "$INST" "$T/v1" --audit
{ [[ $RC -eq 6 ]] && grep -q '^verdict: UNKNOWN$' <<<"$OUT"; }; check "missing verdict, driver rc 6 -> UNKNOWN, rc 6" $?
make_repo "$T/v2"; STUB_VERDICT=garbage STUB_RC=4 ua "$INST" "$T/v2" --audit
{ [[ $RC -eq 4 ]] && grep -q '^verdict: UNKNOWN$' <<<"$OUT"; }; check "unparsable verdict, driver rc 4 -> UNKNOWN, rc 4" $?
make_repo "$T/v3"; STUB_VERDICT=NOT_READY STUB_RC=3 ua "$INST" "$T/v3" --audit
{ [[ $RC -eq 3 ]] && grep -q '^verdict: NOT_READY$' <<<"$OUT"; }; check "NOT_READY verdict, driver rc 3 -> rc 3" $?
ua "$INST" "$T/a" --noui --audit nosuch
{ [[ $RC -eq 2 ]] && grep -q 'no such branch' <<<"$OUT"; }; check "--noui: helper refusal (no such branch) exits 2" $?
make_repo "$T/nu" IMPLEMENT; ua "$INST" "$T/nu" --noui --audit
{ [[ $RC -eq 2 ]] && grep -q 'IMPLEMENT' <<<"$OUT"; }; check "--noui: helper state refusal exits 2" $?
ua "$INST" "$T/a" --audit nosuch
{ [[ $RC -eq 1 ]]; }; check "normal: helper refusal exits 1" $?
git_ -C "$REPO" branch dup; git_ -C "$REPO" worktree add -q "$T/wt-dup1" dup
git_ -C "$REPO" worktree add -q -f "$T/wt-dup2" dup 2>/dev/null
ua "$INST" "$REPO" --audit dup
{ refused && ! stub_ran && grep -q 'more than one worktree' <<<"$OUT"; }; check "branch in multiple worktrees refused" $?
ua "$INST" "$REPO" --audit nowt
{ refused && ! stub_ran && grep -q 'not checked out in any worktree' <<<"$OUT"; }; check "zero worktree matches refused with message" $?
ua "$INST" "$REPO" --audit noun
{ refused && ! stub_ran && grep -q 'no .uncle directory' <<<"$OUT"; }; check "missing .uncle refused with message" $?
git_ -C "$REPO" branch gone; git_ -C "$REPO" worktree add -q "$T/wt-gone" gone; rm -rf "$T/wt-gone"
ua "$INST" "$REPO" --audit gone
{ refused && ! stub_ran && grep -q 'does not exist' <<<"$OUT"; }; check "registered worktree dir missing refused" $?
mkdir -p "$T/ng"; ua "$INST" "$T/ng" --audit
{ refused && ! stub_ran && grep -q 'not inside a git repository' <<<"$OUT"; }; check "non-git directory refused with message" $?
( cd "$T/a" && UNCLE_REFUSE_CODE=1 bash "$INST/scripts/audit-command.sh" --x ) >"$T/h.out" 2>&1; hrc=$?
{ [[ $hrc -ne 0 ]] && grep -q "must not start with '-'" "$T/h.out"; }; check "helper rejects leading-dash BRANCH directly" $?

# Defect injection: one targeted mutant per refusal, applied to temp copies only.
# mutate <name> <file> <old> <new> <test-fn>: replace exactly one occurrence of the
# fixed string <old> with <new>; the matching test must then fail. A pattern that
# does not occur exactly once is itself a FAIL (no silent no-op mutants).
MUT="$T/mut"; mkdir -p "$MUT"
mutate() {
    local name="$1" file="$2" old="$3" new="$4" fn="$5"
    local base; base="$(basename "$file")"
    local mf="$MUT/$name-$base"
    if ! python3 -I - "$file" "$mf" "$old" "$new" <<'PY'
import sys
src, dst, old, new = sys.argv[1:5]
s = open(src).read()
if s.count(old) != 1:
    sys.exit(1)
open(dst, "w").write(s.replace(old, new))
PY
    then check "mutant $name: target string occurs exactly once in $base" 1; return; fi
    local mi="$MUT/inst-$name"
    if [[ "$base" == uncle ]]; then make_install "$mi" "$mf"; else make_install "$mi" "$ROOT/uncle" "$mf"; fi
    # Self-check: the unmutated test passes on a pristine install.
    if ! "$fn" >/dev/null 2>&1; then check "mutant $name: test passes on unmutated install" 1; return; fi
    local saved="$INST"; INST="$mi"
    if "$fn" >/dev/null 2>&1; then echo "FAIL mutant $name survived (test still passes)"; fail=1
    else echo "PASS mutant $name killed by its matching test"; fi
    INST="$saved"
}
mk() { rm -rf "$1"; make_repo "$@"; }
msg() { grep -q -- "$1" <<<"$OUT"; }
t_empty()  { mk "$MUT/m1"; ua "$INST" "$MUT/m1" --audit ''; refused && ! stub_ran && msg 'cannot be empty'; }
t_dash()   { local REFUSE_RE="Unknown argument|Error"; mk "$MUT/m2"; ua "$INST" "$MUT/m2" --audit --x; refused && ! stub_ran && msg "Unknown argument"; }
t_hdash()  { mk "$MUT/m2b"; ( cd "$MUT/m2b" && bash "$INST/scripts/audit-command.sh" -x ) >"$MUT/h.out" 2>&1; [[ $? -ne 0 ]] && grep -q "must not start with" "$MUT/h.out"; }
t_excl()   { mk "$MUT/m3"; local a
    for a in "--application x" "--issue 1" "--change-request x" "--runs" "--performance"; do
        # shellcheck disable=SC2086
        ua "$INST" "$MUT/m3" --audit $a; { refused && ! stub_ran && msg 'cannot be combined'; } || return 1
    done; }
t_exnoui() { mk "$MUT/m3b"; ua "$INST" "$MUT/m3b" --noui --audit --application x; [[ $RC -eq 2 ]] && msg 'cannot be combined'; }
t_home()   { mk "$MUT/m4"; rm -f "$T/stub.log"; ( cd "$MUT/m4"; UNCLE_HOME_AGENT=1 STUB_LOG="$T/stub.log" UNCLE_RUNTIME_ROOT="$INST" UNCLE_SKIP_UPGRADE=1 bash "$INST/uncle" --audit </dev/null 2>&1 ) | grep -q Error && ! stub_ran && { ua "$INST" "$MUT/m4" --audit; stub_ran; }; }
t_state()  { mk "$MUT/m5" "$MS"; ua "$INST" "$MUT/m5" --audit; refused && ! stub_ran && [[ "$(state_of "$MUT/m5")" == "$MS" ]] && msg "$MS"; }
t_branch() { mk "$MUT/m6"; ua "$INST" "$MUT/m6" --audit nosuch; refused && ! stub_ran && msg 'no such branch'; }
t_badref() { mk "$MUT/m6b"; ua "$INST" "$MUT/m6b" --audit '@{-1}'; refused && ! stub_ran && msg 'invalid branch name'; }
t_nonwt()  { mk "$MUT/m7"; git_ -C "$MUT/m7" branch nowt; ua "$INST" "$MUT/m7" --audit nowt; refused && ! stub_ran && msg 'not checked out in any worktree'; }
t_multi()  { mk "$MUT/m7b"; git_ -C "$MUT/m7b" branch d; git_ -C "$MUT/m7b" worktree add -q "$MUT/m7b-w1" d; git_ -C "$MUT/m7b" worktree add -q -f "$MUT/m7b-w2" d 2>/dev/null
    ua "$INST" "$MUT/m7b" --audit d; refused && ! stub_ran && msg 'more than one worktree'; }
t_gone()   { mk "$MUT/m7c"; git_ -C "$MUT/m7c" branch g; git_ -C "$MUT/m7c" worktree add -q "$MUT/m7c-w" g; rm -rf "$MUT/m7c-w"
    ua "$INST" "$MUT/m7c" --audit g; refused && ! stub_ran && msg 'does not exist'; }
t_nouncle(){ mk "$MUT/m7d"; git_ -C "$MUT/m7d" branch n; git_ -C "$MUT/m7d" worktree add -q "$MUT/m7d-w" n
    ua "$INST" "$MUT/m7d" --audit n; refused && ! stub_ran && msg 'no .uncle directory'; }
t_nongit() { rm -rf "$MUT/ng"; mkdir -p "$MUT/ng"; ua "$INST" "$MUT/ng" --audit; refused && ! stub_ran && msg 'not inside a git repository'; }
t_family() { mk "$MUT/m9"; echo app > "$MUT/m9/.uncle/workflow/family"; ua "$INST" "$MUT/m9" --audit; refused && ! stub_ran && msg 'workflow family'; }
t_nostate(){ mk "$MUT/m10"; rm "$MUT/m10/.uncle/workflow/state"; ua "$INST" "$MUT/m10" --audit; refused && ! stub_ran && msg 'no workflow state'; }
t_san()    { mk "$MUT/m8" "$(printf 'BAD\033[31mSTATE')"; ua "$INST" "$MUT/m8" --audit; ! grep -q $'\033' <<<"$OUT" && grep -q 'BAD.*STATE' <<<"$OUT"; }
t_lock()   {
    mk "$MUT/lk" MANUAL_CHECKLIST; : > "$MUT/lk/.uncle/workflow/driver.lock"
    python3 -c 'import fcntl,sys,time
f=open(sys.argv[1],"a");fcntl.flock(f,fcntl.LOCK_EX);time.sleep(20)' "$MUT/lk/.uncle/workflow/driver.lock" & local bg=$!
    sleep 1; ua "$INST" "$MUT/lk" --audit; local r=1
    { refused && ! stub_ran && msg 'driver.lock is held' && [[ "$(state_of "$MUT/lk")" == MANUAL_CHECKLIST ]]; } && r=0
    kill "$bg" 2>/dev/null; wait "$bg" 2>/dev/null; return $r; }
t_race()   { mk "$MUT/rc" EXECUTE_CHECKLIST; STUB_NOLOCK=1 ua "$INST" "$MUT/rc" --audit; [[ $RC -ne 0 ]] && [[ "$(state_of "$MUT/rc")" == EXECUTE_CHECKLIST ]]; }
t_origin() { mk "$MUT/or"; mkdir -p "$MUT/or/scripts"; printf '#!/usr/bin/env bash\ntouch "%s/decoy-ran2"; exit 9\n' "$T" > "$MUT/or/scripts/change-workflow.sh"
    rm -f "$T/decoy-ran2"; ua "$INST" "$MUT/or" --audit; stub_ran && [[ ! -e "$T/decoy-ran2" ]] && [[ $RC -eq 0 ]]; }
t_verdict(){ mk "$MUT/vd"; STUB_VERDICT=garbage ua "$INST" "$MUT/vd" --audit; grep -q '^verdict: UNKNOWN$' <<<"$OUT"; }
t_unkexit(){ mk "$MUT/ue"; STUB_VERDICT=none ua "$INST" "$MUT/ue" --audit; [[ $RC -eq 1 ]]; }
t_stale()  { mk "$MUT/vs"; echo READY > "$MUT/vs/.uncle/workflow/audit-verdict"; touch -t 200001010000 "$MUT/vs/.uncle/workflow/audit-verdict"; STUB_VERDICT=none ua "$INST" "$MUT/vs" --audit; grep -q '^verdict: UNKNOWN$' <<<"$OUT"; }
t_exit()   { mk "$MUT/ex"; STUB_RC=5 ua "$INST" "$MUT/ex" --audit; [[ $RC -eq 5 ]]; }
t_verdict_label() { mk "$MUT/vl"; STUB_VERDICT=none ua "$INST" "$MUT/vl" --audit; grep -q '^verdict: UNKNOWN$' <<<"$OUT"; }
t_extra()  { mk "$MUT/ex2"; ua "$INST" "$MUT/ex2" --audit main extra; refused && ! stub_ran && grep -q '^Error: --audit takes at most one BRANCH' <<<"$OUT" && [[ $(wc -l <<<"$OUT") -eq 1 ]]; }
t_eq()     { mk "$MUT/eq"; ua "$INST" "$MUT/eq" --audit=--x; refused && ! stub_ran && grep -q '^Error: --audit takes BRANCH' <<<"$OUT" && [[ $(wc -l <<<"$OUT") -eq 1 ]]; }
t_prefix() { mk "$MUT/pf" MANUAL_CHECKLIST; echo "42:MANUAL_CHECKLIST" > "$MUT/pf/.uncle/workflow/state"; ua "$INST" "$MUT/pf" --audit; grep -q '^state=42:FINAL_AUDIT' "$T/stub.log"; }
t_noui()   { mk "$MUT/nu" IMPLEMENT; ua "$INST" "$MUT/nu" --noui --audit; [[ $RC -eq 2 ]] && msg IMPLEMENT; }

U="$ROOT/uncle"; A="$ROOT/scripts/audit-command.sh"
mutate empty-branch   "$U" 'if [[ -z "$1" ]]; then
                    printf '"'"'Error: --audit BRANCH cannot be empty\n'"'"' >&2' 'if false; then
                    printf '"'"'Error: --audit BRANCH cannot be empty\n'"'"' >&2' t_empty
mutate option-like    "$U" 'if [[ $# -gt 0 && "$1" != -* ]]; then' 'if [[ $# -gt 0 ]]; then' t_dash
mutate helper-dash    "$A" '[[ "$BRANCH" != -* ]] || refuse' ': || refuse' t_hdash
mutate exclusivity    "$U" 'if [[ "$_audit_n" -gt 0 && ( "$_audit_n" -gt 1 || "$_audit_other" -gt 0 ) ]]; then' 'if false; then' t_excl
mutate exclusivity-noui "$U" 'if [[ "$_audit_n" -gt 0 && ( "$_audit_n" -gt 1 || "$_audit_other" -gt 0 ) ]]; then' 'if false; then' t_exnoui
mutate home-agent     "$U" '"${UNCLE_HOME_AGENT:-}" == 1 &&' 'false &&' t_home
for MS in ANALYZE PLAN WAIT_PLAN_APPROVAL WAIT_UPDATED_PLAN_APPROVAL IMPLEMENT ADVERSARIAL_REVIEW; do
    mutate "state-$MS" "$A" 'WAIT_IMPLEMENT_APPROVAL|MANUAL_CHECKLIST|' "$MS|WAIT_IMPLEMENT_APPROVAL|MANUAL_CHECKLIST|" t_state
done
mutate branch-exists  "$A" 'git show-ref --verify --quiet -- "refs/heads/$BRANCH" ||' 'true ||' t_branch
mutate ref-format     "$A" 'git check-ref-format "refs/heads/$BRANCH" >/dev/null 2>&1 ||' 'true ||' t_badref
mutate no-worktree    "$A" '[[ "$matches" -ge 1 ]] ||' 'true ||' t_nonwt
mutate multi-worktree "$A" '[[ "$matches" -le 1 ]] ||' 'true ||' t_multi
mutate worktree-gone  "$A" '[[ -n "$TARGET" ]] || refuse "worktree for' 'true || refuse "worktree for' t_gone
mutate uncle-missing  "$A" '[[ -d "$UNCLE_DIR" ]] ||' 'true ||' t_nouncle
mutate not-git        "$A" 'git rev-parse --is-inside-work-tree >/dev/null 2>&1 ||' 'true ||' t_nongit
mutate family         "$A" '[[ "$family" == change ]] ||' 'true ||' t_family
mutate no-state       "$A" '[[ -s "$STATE_FILE" ]] ||' 'true ||' t_nostate
mutate sanitizer      "$A" "LC_ALL=C tr -d '\\000-\\037\\177'" 'cat' t_san
mutate lock-probe     "$A" '    sys.exit(3)' '    pass' t_lock
mutate lock-race      "$A" 'printf '"'"'%s\n'"'"' "$PREV_RAW" > "$STATE_FILE"' ':' t_race
mutate driver-origin  "$A" 'bash "$ROOT/scripts/change-workflow.sh"' 'bash "$TARGET/scripts/change-workflow.sh"' t_origin
mutate verdict-parse  "$A" 'if [[ "$v" =~ ^[A-Z_]+$ ]]; then verdict="$v"; fi' 'verdict="$v"' t_verdict
mutate verdict-stale  "$A" '"$mtime" -ge "$START"' '"$mtime" -ge 0' t_stale
mutate exit-status    "$A" 'exit "$DRIVER_STATUS"' 'exit 0' t_exit
mutate unknown-exit   "$A" 'if [[ "$verdict" == UNKNOWN && "$DRIVER_STATUS" == 0 ]]; then exit "$REFUSE"; fi' ':' t_unkexit
mutate unknown-label  "$A" 'verdict="UNKNOWN"' 'verdict="unknown"' t_verdict_label
mutate extra-positional "$U" 'if [[ "$UNCLE_STARTUP_ACTION" == audit && "$1" != -* ]]; then' 'if false; then' t_extra
mutate audit-equals   "$U" "--audit=*)" "--audit-never=*)" t_eq
mutate issue-prefix   "$A" 'NEW="$ISSUE:FINAL_AUDIT"' 'NEW="FINAL_AUDIT"' t_prefix
mutate noui-export    "$U" 'export UNCLE_AUDIT_BRANCH UNCLE_REFUSE_CODE' 'export UNCLE_AUDIT_BRANCH' t_noui

exit "$fail"

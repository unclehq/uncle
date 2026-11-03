#!/usr/bin/env bash
# End-to-end tests for the "CHANGE_REQUEST.md already exists" guard in
# scripts/from-issue.sh (change mode). Every case runs the real from-issue.sh
# as a child process against a scratch git repo, with a fake `gh` and a stub
# change-workflow.sh, so the guard is exercised exactly as a user meets it.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/crep-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAIL=0
PROMPT_TEXT='Proceed with the new change request and replace it? [y/N]'
OLD_CONTENT='OLD-REQUEST-CONTENT'

ok()  { PASS=$((PASS + 1)); echo "ok   - $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; [[ -z "${2:-}" ]] || echo "       $2"; }
check() { # check <description> <command...>
    local d="$1"; shift
    if "$@"; then ok "$d"; else bad "$d"; fi
}

# --- fixtures ---------------------------------------------------------------

# Runtime copy of scripts/ whose change-workflow.sh is a stub: the guard is
# what is under test, not the driver.
RT="$TMP/runtime"
mkdir -p "$RT"
cp -R "$REPO_ROOT/scripts" "$RT/scripts"
cat > "$RT/scripts/change-workflow.sh" <<'EOF'
#!/usr/bin/env bash
echo run >> "${STUB_RAN_FILE:?}"
exit 0
EOF
chmod +x "$RT/scripts/change-workflow.sh"

# Fake gh: answers `gh issue view` with a canned issue.
BIN="$TMP/bin"
mkdir -p "$BIN"
cat > "$BIN/gh" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == issue && "${2:-}" == view ]]; then
    printf '%s' '{"title":"Add widget","body":"Widget body","url":"https://github.com/acme/widgets/issues/142","state":"OPEN","labels":[],"comments":[]}'
    exit 0
fi
exit 1
EOF
chmod +x "$BIN/gh"

# Driver: runs a command with stdin that is a pty (answer pre-typed), a
# never-written fifo, or /dev/null; stdout/stderr go to files; 124 on timeout.
cat > "$TMP/drive.py" <<'EOF'
import codecs, os, pty, signal, subprocess, sys
out, err, tmo, mode, answer = sys.argv[1:6]
cmd = sys.argv[7:]
fo, fe = open(out, "wb"), open(err, "wb")
fifo_fd = None
master = None
if mode == "tty":
    master, slave = pty.openpty()
    stdin = slave
elif mode == "fifo":
    path = out + ".fifo"
    os.mkfifo(path)
    fifo_fd = os.open(path, os.O_RDWR)   # held open, never written: a read blocks
    stdin = fifo_fd
elif mode == "pipe":
    stdin = subprocess.PIPE
else:
    stdin = os.open(os.devnull, os.O_RDONLY)
p = subprocess.Popen(cmd, stdin=stdin, stdout=fo, stderr=fe, start_new_session=True)
if mode == "pipe":
    try:
        p.stdin.write(codecs.decode(answer, "unicode_escape").encode("latin-1"))
        p.stdin.close()
    except OSError:
        pass
if mode == "tty":
    os.close(slave)
    data = codecs.decode(answer, "unicode_escape").encode("latin-1")
    if data:
        os.write(master, data)
import select, time
deadline = time.time() + float(tmo)
while p.poll() is None:
    if time.time() > deadline:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            p.kill()
        p.wait()
        sys.exit(124)
    # Keep the pty master drained (echo output) so the child can exit cleanly.
    if master is not None and select.select([master], [], [], 0.1)[0]:
        try:
            os.read(master, 4096)
        except OSError:
            pass
    else:
        time.sleep(0.05)
sys.exit(p.returncode)
EOF

# Drop every inherited UNCLE_* variable (a driver-run build sets many, e.g.
# UNCLE_UNATTENDED) so cases see only the environment they declare.
SCRUB=(env)
while IFS='=' read -r k _; do SCRUB+=(-u "$k"); done < <(env | grep '^UNCLE_')

CASE=0
PROJ=""; OUT=""; ERR=""; RC=0; RAN=""

new_case() { # new_case <request-content|none|empty|space>
    CASE=$((CASE + 1))
    PROJ="$TMP/case$CASE/proj"
    RAN="$TMP/case$CASE/ran"
    OUT="$TMP/case$CASE/out"; ERR="$TMP/case$CASE/err"
    mkdir -p "$PROJ"
    : > "$RAN"
    (
        cd "$PROJ" || exit 1
        git init -q . && git config user.email t@example.com && git config user.name t
        git remote add origin https://github.com/acme/widgets.git
        echo code > app.txt
        git add app.txt && git commit -q -m init
        mkdir -p .uncle/workflow
        echo "keep-me" > .uncle/workflow/sentinel
    ) >/dev/null 2>&1
    case "$1" in
        none) ;;
        empty) : > "$PROJ/CHANGE_REQUEST.md" ;;
        space) printf ' \n\n' > "$PROJ/CHANGE_REQUEST.md" ;;
        *) printf '%s\n' "$1" > "$PROJ/CHANGE_REQUEST.md" ;;
    esac
}

# run_issue <stdin-mode> <answer> <timeout> <extra-env KEY=VAL...> -- <from-issue args...>
run_issue() {
    local mode="$1" answer="$2" tmo="$3"; shift 3
    local envs=()
    while [[ "$1" != -- ]]; do envs+=("$1"); shift; done
    shift
    RC=0
    python3 -I "$TMP/drive.py" "$OUT" "$ERR" "$tmo" "$mode" "$answer" -- \
        "${SCRUB[@]}" PATH="$BIN:$PATH" UNCLE_RUNTIME_ROOT="$RT" UNCLE_PROJECT_ROOT="$PROJ" \
            STUB_RAN_FILE="$RAN" ${envs[@]+"${envs[@]}"} \
        bash "$RT/scripts/from-issue.sh" 142 --change --no-worktree "$@" || RC=$?
}

sha() { shasum -a 256 < "$1" | awk '{print $1}'; }
tree_sig() { # listing + content hashes of .uncle/workflow
    ( cd "$PROJ" && find .uncle/workflow | LC_ALL=C sort | while IFS= read -r f; do
        if [[ -f "$f" ]]; then printf '%s %s\n' "$f" "$(sha "$f")"; else printf '%s\n' "$f"; fi
    done )
}
prompt_shown() { grep -qF "$PROMPT_TEXT" "$ERR"; }
stub_ran() { [[ -s "$RAN" ]]; }
req_old() { grep -q "$OLD_CONTENT" "$PROJ/CHANGE_REQUEST.md" 2>/dev/null; }
req_new() { # new seed present as a line, and old content gone from the root copy
    grep -qs '^Issue 142$' "$PROJ/CHANGE_REQUEST.md" "$PROJ/.uncle/docs/CHANGE_REQUEST.md" && ! req_old
}
no_hang() { [[ "$RC" != 124 ]]; }

# --- 1. prompt shown; answer parsing ----------------------------------------

for ans in 'y\n' 'YES\n' 'yes\n' 'y\r\n' ' Yes \n' 'y\x04\x04'; do
    new_case "$OLD_CONTENT"
    run_issue tty "$ans" 20 --
    check "answer '$ans' shows prompt on stderr" prompt_shown
    check "answer '$ans' prompt names the file" grep -q 'CHANGE_REQUEST.md' "$ERR"
    check "answer '$ans' exits 0 without hanging" test "$RC" = 0
    check "answer '$ans' replaces the request" req_new
    check "answer '$ans' starts the workflow" stub_ran
    check "answer '$ans' prompt not on stdout" bash -c '! grep -qF "$1" "$2"' _ "$PROMPT_TEXT" "$OUT"
done

for ans in 'n\n' '\n' '\x04' 'maybe\n' 'y please\n' 'yy\n' 'yes!\n'; do
    new_case "$OLD_CONTENT"
    before_req="$(sha "$PROJ/CHANGE_REQUEST.md")"
    before_tree="$(tree_sig)"
    run_issue tty "$ans" 60 --
    label="decline '$ans'"
    check "$label shows prompt" prompt_shown
    check "$label exits nonzero (not hung)" bash -c '[[ "$1" != 0 && "$1" != 124 ]]' _ "$RC"
    check "$label leaves CHANGE_REQUEST.md byte-identical" test "$(sha "$PROJ/CHANGE_REQUEST.md")" = "$before_req"
    check "$label leaves .uncle/workflow byte-identical" test "$(tree_sig)" = "$before_tree"
    check "$label does not start the workflow" bash -c '! [[ -s "$1" ]]' _ "$RAN"
    check "$label says request left unchanged" grep -qi 'unchanged' "$ERR"
done

# --- 2. prompt never shown ---------------------------------------------------

# UNCLE_NEW_WORKFLOW=1 (stdin is a tty that never answers: a prompt would hang)
new_case "$OLD_CONTENT"
run_issue tty '' 60 UNCLE_NEW_WORKFLOW=1 --
check "NEW_WORKFLOW=1: no prompt" bash -c '! grep -qF "$1" "$2"' _ "$PROMPT_TEXT" "$ERR"
check "NEW_WORKFLOW=1: no hang" no_hang
check "NEW_WORKFLOW=1: exits 0" test "$RC" = 0
check "NEW_WORKFLOW=1: request replaced" req_new

# SEED_ONLY=1 with an existing request: no prompt, no overwrite (V3)
new_case "$OLD_CONTENT"
before_req="$(sha "$PROJ/CHANGE_REQUEST.md")"
run_issue tty '' 60 -- --seed-only
check "SEED_ONLY: no prompt" bash -c '! grep -qF "$1" "$2"' _ "$PROMPT_TEXT" "$ERR"
check "SEED_ONLY: no hang" no_hang
check "SEED_ONLY: existing request untouched" test "$(sha "$PROJ/CHANGE_REQUEST.md")" = "$before_req"
check "SEED_ONLY: workflow not started" bash -c '! [[ -s "$1" ]]' _ "$RAN"

# seed_is_current: in-flight run owned by this issue
new_case "$OLD_CONTENT"
printf 'IMPLEMENT\n' > "$PROJ/.uncle/workflow/state"
printf 'acme/widgets\t142\tgh\n' > "$PROJ/.uncle/workflow/origin"
before_req="$(sha "$PROJ/CHANGE_REQUEST.md")"
run_issue tty '' 60 --
check "seed_is_current: no prompt" bash -c '! grep -qF "$1" "$2"' _ "$PROMPT_TEXT" "$ERR"
check "seed_is_current: no hang" no_hang
check "seed_is_current: request not rewritten" test "$(sha "$PROJ/CHANGE_REQUEST.md")" = "$before_req"
check "seed_is_current: resumes" grep -q 'Resuming' "$OUT"

# zero-byte request: counts as absent, replaced silently
new_case empty
run_issue tty '' 60 --
check "zero-byte request: no prompt" bash -c '! grep -qF "$1" "$2"' _ "$PROMPT_TEXT" "$ERR"
check "zero-byte request: no hang" no_hang
check "zero-byte request: exits 0" test "$RC" = 0
check "zero-byte request: replaced" req_new

# no request at all: no prompt (baseline)
new_case none
run_issue tty '' 60 --
check "no request: no prompt" bash -c '! grep -qF "$1" "$2"' _ "$PROMPT_TEXT" "$ERR"
check "no request: written" req_new

# whitespace-only request counts as existing: prompts
new_case space
ws_before="$(sha "$PROJ/CHANGE_REQUEST.md")"
run_issue tty 'n\n' 60 --
check "whitespace-only request: prompts" prompt_shown
check "whitespace-only request: preserved on decline" test "$(sha "$PROJ/CHANGE_REQUEST.md")" = "$ws_before"

# --- 3. unattended: flag and env, with/without opt-in, never-written fifo ----

for how in flag env; do
    for optin in without with; do
        new_case "$OLD_CONTENT"
        before_req="$(sha "$PROJ/CHANGE_REQUEST.md")"
        before_tree="$(tree_sig)"
        envs=()
        args=()
        [[ "$how" == flag ]] && args=(--unattended) || envs=(UNCLE_UNATTENDED=1)
        [[ "$optin" == with ]] && envs+=(UNCLE_REPLACE_CHANGE_REQUEST=1)
        label="unattended($how) $optin opt-in"
        run_issue fifo '' 30 ${envs[@]+"${envs[@]}"} -- ${args[@]+"${args[@]}"}
        check "$label: no hang on never-written stdin" no_hang
        check "$label: no prompt shown" bash -c '! grep -qF "$1" "$2"' _ "$PROMPT_TEXT" "$ERR"
        if [[ "$optin" == with ]]; then
            check "$label: exits 0" test "$RC" = 0
            check "$label: request replaced" req_new
            check "$label: workflow started" stub_ran
        else
            check "$label: exits nonzero" bash -c '[[ "$1" != 0 && "$1" != 124 ]]' _ "$RC"
            check "$label: stderr names UNCLE_REPLACE_CHANGE_REQUEST=1" grep -qF 'UNCLE_REPLACE_CHANGE_REQUEST=1' "$ERR"
            check "$label: request byte-identical" test "$(sha "$PROJ/CHANGE_REQUEST.md")" = "$before_req"
            check "$label: .uncle/workflow byte-identical" test "$(tree_sig)" = "$before_tree"
            check "$label: workflow not started" bash -c '! [[ -s "$1" ]]' _ "$RAN"
        fi
    done
done

# opt-in must be exactly 1: other values refuse
for v in 0 true yes ''; do
    new_case "$OLD_CONTENT"
    run_issue fifo '' 30 UNCLE_UNATTENDED=1 "UNCLE_REPLACE_CHANGE_REQUEST=$v" --
    check "opt-in value '$v' refuses" bash -c '[[ "$1" != 0 && "$1" != 124 ]]' _ "$RC"
    check "opt-in value '$v' keeps request" req_old
done

# opt-in=1 on an interactive tty: no prompt, replaced
new_case "$OLD_CONTENT"
run_issue tty '' 60 UNCLE_REPLACE_CHANGE_REQUEST=1 --
check "opt-in on tty: no prompt" bash -c '! grep -qF "$1" "$2"' _ "$PROMPT_TEXT" "$ERR"
check "opt-in on tty: exits 0" test "$RC" = 0
check "opt-in on tty: request replaced" req_new

# piped / devnull stdin (non-tty) with an existing request: refuse, keep
new_case "$OLD_CONTENT"
before_req="$(sha "$PROJ/CHANGE_REQUEST.md")"
run_issue devnull '' 30 --
check "non-tty stdin: refuses" bash -c '[[ "$1" != 0 && "$1" != 124 ]]' _ "$RC"
check "non-tty stdin: no prompt" bash -c '! grep -qF "$1" "$2"' _ "$PROMPT_TEXT" "$ERR"
check "non-tty stdin: request byte-identical" test "$(sha "$PROJ/CHANGE_REQUEST.md")" = "$before_req"

# piped non-tty content ('y' on a pipe) with an existing request: refuse, keep
new_case "$OLD_CONTENT"
before_req="$(sha "$PROJ/CHANGE_REQUEST.md")"
run_issue pipe 'y\ny\n' 30 --
check "piped y: refuses" bash -c '[[ "$1" != 0 && "$1" != 124 ]]' _ "$RC"
check "piped y: request byte-identical" test "$(sha "$PROJ/CHANGE_REQUEST.md")" = "$before_req"
check "piped y: workflow not started" bash -c '! [[ -s "$1" ]]' _ "$RAN"

# symlinked request: decline leaves link and target; 'y' replaces the link,
# never writes through it (D-1)
new_case none
printf '%s\n' "$OLD_CONTENT" > "$PROJ/target.md"
ln -s target.md "$PROJ/CHANGE_REQUEST.md"
t_before="$(sha "$PROJ/target.md")"
run_issue tty 'n\n' 60 --
check "symlink decline: prompts" prompt_shown
check "symlink decline: still a symlink" test -L "$PROJ/CHANGE_REQUEST.md"
check "symlink decline: target unchanged" test "$(sha "$PROJ/target.md")" = "$t_before"
new_case none
printf '%s\n' "$OLD_CONTENT" > "$PROJ/target.md"
ln -s target.md "$PROJ/CHANGE_REQUEST.md"
t_before="$(sha "$PROJ/target.md")"
run_issue tty 'y\n' 60 --
check "symlink y: exits 0" test "$RC" = 0
check "symlink y: target NOT clobbered" test "$(sha "$PROJ/target.md")" = "$t_before"
check "symlink y: request replaced" req_new

# dangling symlink counts as absent: no prompt, no hang, target not created
new_case none
ln -s missing-target.md "$PROJ/CHANGE_REQUEST.md"
run_issue tty '' 60 --
check "dangling symlink: no prompt" bash -c '! grep -qF "$1" "$2"' _ "$PROMPT_TEXT" "$ERR"
check "dangling symlink: no hang" no_hang
check "dangling symlink: dangling target not created" test ! -e "$PROJ/missing-target.md"

# directory named CHANGE_REQUEST.md: decline leaves it intact
new_case none
mkdir "$PROJ/CHANGE_REQUEST.md"; echo keep > "$PROJ/CHANGE_REQUEST.md/f"
run_issue tty 'n\n' 60 --
check "directory decline: dir and contents intact" test "$(cat "$PROJ/CHANGE_REQUEST.md/f" 2>/dev/null)" = keep
check "directory decline: no hang" no_hang

# --- 4. README documents the opt-in -----------------------------------------

check "README documents UNCLE_REPLACE_CHANGE_REQUEST=1" grep -q 'UNCLE_REPLACE_CHANGE_REQUEST=1' "$REPO_ROOT/scripts/README.md"

echo
echo "passed: $PASS  failed: $FAIL"
[[ "$FAIL" == 0 ]]

#!/usr/bin/env bash
# Housekeeping driver: plan (model) -> schema -> policy -> approval -> execute
# (argv, no shell) -> verify (fixed read-only templates) -> report.
#
# Usage: housekeeping-workflow.sh [REQUEST TEXT]   (or UNCLE_STARTUP_TEXT_FILE)
# Env:   UNCLE_HOUSEKEEPING_UNATTENDED=1  run without an approval prompt (the
#                                         policy still applies; recorded)
#        HOUSEKEEPING_APPROVAL_FILE       read the approval answer from this
#                                         path instead of /dev/tty
# Exit:  0 only for DECLINED or a run whose ops are all VERIFIED; 1 otherwise.
#
# All records live in .uncle/workflow/housekeeping/. Nothing else under
# .uncle/workflow/ is read or written except the shared driver.lock flock,
# which is released by the kernel on every exit path (fd closes with us).

ROOT="${HK_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PROJECT_ROOT="${UNCLE_PROJECT_ROOT:-$PWD}"
export PROJECT_ROOT HK_ROOT_RESOLVED="$ROOT"
. "$ROOT/scripts/lib/stage-config.sh"

HK_DIR="$PROJECT_ROOT/.uncle/workflow/housekeeping"
HK_CHECKED="$HK_DIR/plan.checked.json"
HK_ALLOWED_HASH=""
HK_OUT=""
HK_RC=0
hk_argv=()

IFS= read -r -d '' HK_PY <<'PYEOF' || true
import sys, json, hashlib, os
sys.path.insert(0, os.path.join(os.environ['HK_ROOT_RESOLVED'], 'scripts', 'lib'))
OPS = ('repo-rename', 'worktree-prune', 'worktree-remove',
       'branch-delete-merged', 'label-cleanup', 'issue-triage')

def die(msg):
    print(msg)
    sys.exit(1)

def template(op, argv):
    if op == 'repo-rename':
        return ['gh', 'repo', 'view', '--json', 'name', '--jq', '.name']
    if op in ('worktree-prune', 'worktree-remove'):
        return ['git', 'worktree', 'list']
    if op == 'branch-delete-merged':
        b = argv[-1]
        if len(argv) > 1 and argv[1] == 'push':
            return ['git', 'ls-remote', '--heads', 'origin', b]
        return ['git', 'branch', '--list', b]
    if op == 'label-cleanup':
        return ['gh', 'label', 'list']
    if op == 'issue-triage':
        if len(argv) < 4:
            return None
        return ['gh', 'issue', 'view', argv[3], '--json', 'labels,state']
    return None

def strlist(x):
    return isinstance(x, list) and len(x) > 0 and all(isinstance(t, str) and t for t in x)

def esc(s):
    return s.encode('unicode_escape').decode('ascii')

def load(path):
    return json.load(open(path, encoding='utf-8'))['ops']

def cmd_validate(raw, out):
    try:
        t = open(raw, encoding='utf-8').read().strip()
    except OSError:
        die('plan unreadable')
    if t.startswith('```'):
        lines = t.split('\n')[1:]
        if lines and lines[-1].strip().startswith('```'):
            lines = lines[:-1]
        t = '\n'.join(lines).strip()
    try:
        plan = json.loads(t)
    except ValueError:
        die('plan is not valid JSON')
    ops = plan.get('ops') if isinstance(plan, dict) else None
    if not isinstance(ops, list) or not ops:
        die('plan has zero ops')
    seen, clean = set(), []
    for o in ops:
        if not isinstance(o, dict):
            die('op is not an object')
        for k in ('id', 'op', 'argv', 'expected', 'verify'):
            if k not in o:
                die('op missing field: ' + k)
        oid = o['id']
        if isinstance(oid, bool) or not isinstance(oid, (str, int)) or str(oid) == '':
            die('op id invalid')
        oid = str(oid)
        if oid in seen:
            die('duplicate op id: ' + oid)
        seen.add(oid)
        if o['op'] not in OPS:
            die('unknown op label: ' + esc(str(o['op'])))
        if not strlist(o['argv']):
            die('op argv invalid: ' + oid)
        if not isinstance(o['expected'], str):
            die('op expected invalid: ' + oid)
        v = o['verify']
        if not isinstance(v, dict) or not strlist(v.get('argv')) or not isinstance(v.get('expect'), str):
            die('op verify invalid: ' + oid)
        tpl = template(o['op'], o['argv'])
        if tpl is None or v['argv'] != tpl:
            die('verify argv differs from the fixed template for op ' + oid)
        clean.append({'id': oid, 'op': o['op'], 'argv': o['argv'],
                      'expected': o['expected'],
                      'verify': {'argv': v['argv'], 'expect': v['expect']}})
    with open(out, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'ops': clean}, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=True) + '\n')

def is_allowed(res):
    if res is True:
        return True
    if isinstance(res, dict):
        for k in ('allowed', 'allow', 'ok'):
            if k in res:
                return res[k] is True
        return False
    if isinstance(res, (tuple, list)) and res:
        return res[0] is True
    for k in ('allowed', 'allow', 'ok'):
        if hasattr(res, k):
            return getattr(res, k) is True
    return False

def load_disallow(C):
    for name in ('effective_disallow', 'load_disallow', 'load'):
        fn = getattr(C, name, None)
        if fn is None:
            continue
        for args in ((), (os.path.join(os.environ.get('PROJECT_ROOT', '.'), '.uncle', 'config'),)):
            try:
                v = fn(*args)
                if isinstance(v, (list, tuple)):
                    return list(v)
            except Exception:
                pass
    return []

def cmd_policy(path):
    try:
        import housekeeping_policy as P
        import housekeeping_config as C
    except Exception as e:
        die('policy unavailable: ' + str(e))
    plan = json.load(open(path, encoding='utf-8'))
    disallow = load_disallow(C)
    res = P.check_plan(plan, disallow)
    if not is_allowed(res):
        die('policy refused: ' + esc(str(res)))

def cmd_hash(path):
    print(hashlib.sha256(open(path, 'rb').read()).hexdigest())

def op_at(path, idx):
    return load(path)[int(idx)]

def cmd_render(path):
    for o in load(path):
        print('[%s] %s: %s' % (o['id'], o['op'], ' '.join(esc(a) for a in o['argv'])))
        print('      verify: %s' % ' '.join(esc(a) for a in o['verify']['argv']))

def main():
    c, a = sys.argv[1], sys.argv[2:]
    if c == 'validate': cmd_validate(*a)
    elif c == 'policy': cmd_policy(*a)
    elif c == 'hash': cmd_hash(*a)
    elif c == 'render': cmd_render(*a)
    elif c == 'count': print(len(load(a[0])))
    elif c == 'field':
        o = op_at(a[0], a[1]); k = a[2]
        print(o['verify']['expect'] if k == 'vexpect' else o[k])
    elif c == 'renderop':
        o = op_at(a[0], a[1])
        print(' '.join(esc(x) for x in (o['verify']['argv'] if a[2] == 'verify' else o['argv'])))
    elif c == 'argv':
        o = op_at(a[0], a[1])
        av = o['verify']['argv'] if a[2] == 'verify' else o['argv']
        sys.stdout.buffer.write(b''.join(x.encode('utf-8') + b'\0' for x in av))
    else:
        die('bad subcommand')
main()
PYEOF

hk_py() { python3 -I -c "$HK_PY" "$@"; }
hk_hash() { hk_py hash "$HK_CHECKED"; }
hk_state() { printf '%s\n' "$1" > "$HK_DIR/state"; }
hk_log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >> "$HK_DIR/run.log"; }

hk_on_exit() {
    local rc=$?
    [[ -d "$HK_DIR" ]] && hk_log "exit status $rc"
    return $rc
}
trap hk_on_exit EXIT
trap 'exit 1' INT TERM HUP

hk_refuse() {
    echo "housekeeping: REFUSED: $*" >&2
    [[ -d "$HK_DIR" ]] && { hk_state REFUSED; hk_log "REFUSED: $*"; }
    exit 1
}

# --- Request -----------------------------------------------------------------
REQUEST="${1:-}"
if [[ -z "$REQUEST" && -n "${UNCLE_STARTUP_TEXT_FILE:-}" && -r "${UNCLE_STARTUP_TEXT_FILE}" ]]; then
    REQUEST="$(cat "$UNCLE_STARTUP_TEXT_FILE")"
fi
if [[ -z "${REQUEST//[[:space:]]/}" ]]; then
    echo "housekeeping: empty request refused" >&2
    exit 1
fi

# --- Lock (flock on the shared driver.lock; held by this fd until exit) ------
mkdir -p "$PROJECT_ROOT/.uncle/workflow"
exec 9>>"$PROJECT_ROOT/.uncle/workflow/driver.lock"
if ! python3 -I -c 'import fcntl; fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)' 2>/dev/null; then
    echo "housekeeping: another workflow holds this checkout" >&2
    exit 1
fi

mkdir -p "$HK_DIR"
rm -f "$HK_DIR"/plan.* "$HK_DIR"/ops.status "$HK_DIR"/run.log "$HK_DIR"/REPORT.md "$HK_DIR"/last.err
hk_state PLANNED
hk_log "request: $(printf '%s' "$REQUEST" | head -c 500 | tr '\n\r' '  ')"

# --- The only place plan argv is executed ------------------------------------
hk_load_argv() { # kind idx
    hk_argv=()
    local a
    while IFS= read -r -d '' a; do hk_argv+=("$a"); done < <(hk_py argv "$HK_CHECKED" "$2" "$1")
}

hk_run_checked() { # kind idx
    HK_OUT=""; HK_RC=0
    if [[ -z "$HK_ALLOWED_HASH" || "$HK_ALLOWED_HASH" != "$(hk_hash)" ]]; then
        HK_RC=99; return 99
    fi
    hk_load_argv "$1" "$2"
    if [[ ${#hk_argv[@]} -eq 0 ]]; then HK_RC=98; return 98; fi
    HK_OUT="$("${hk_argv[@]}" 2>"$HK_DIR/last.err")"
    HK_RC=$?
    return $HK_RC
}

# --- Policy gate: sole route to HK_ALLOWED_HASH -------------------------------
hk_policy_gate() {
    local why
    why="$(hk_py policy "$HK_DIR/plan.candidate.json")" || { HK_WHY="$why"; return 1; }
    cp "$HK_DIR/plan.candidate.json" "$HK_CHECKED" || return 1
    HK_ALLOWED_HASH="$(hk_hash)"
}

# --- Plan stage ---------------------------------------------------------------
{ cat "$ROOT/prompts/housekeeping-plan.md"; printf '\n## Request\n\n%s\n' "$REQUEST"; } > "$HK_DIR/plan.prompt.md"
agent_cmd="$(stage_agent_cmd housekeeping-plan)" || hk_refuse "no runner for the housekeeping-plan stage"
bash -c "$agent_cmd" < "$HK_DIR/plan.prompt.md" > "$HK_DIR/plan.raw.json" 2> "$HK_DIR/plan.agent.err" \
    || hk_refuse "plan stage failed"

why="$(hk_py validate "$HK_DIR/plan.raw.json" "$HK_DIR/plan.candidate.json")" || hk_refuse "$why"
HK_WHY=""
hk_policy_gate || hk_refuse "${HK_WHY:-policy gate failed}"
HK_APPROVED_HASH=""

# --- Approval -----------------------------------------------------------------
echo "Proposed housekeeping plan (sha256 $HK_ALLOWED_HASH):"
hk_py render "$HK_CHECKED"
if [[ "${UNCLE_HOUSEKEEPING_UNATTENDED:-}" == 1 ]]; then
    mode=unattended
    echo "Unattended run: no approval prompt; policy was enforced."
    hk_log "mode unattended (no approval prompt) plan sha256 $HK_ALLOWED_HASH"
else
    mode=attended
    printf 'Run these commands? [y/N] '
    ans=""
    IFS= read -r ans < "${HOUSEKEEPING_APPROVAL_FILE:-/dev/tty}" 2>/dev/null
    echo
    if ! [[ "$ans" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        hk_state DECLINED; hk_log "DECLINED"
        echo "Declined; nothing was run."
        exit 0
    fi
    hk_log "mode attended approved plan sha256 $HK_ALLOWED_HASH"
fi
HK_APPROVED_HASH="$HK_ALLOWED_HASH"
if [[ "$(hk_hash)" != "$HK_APPROVED_HASH" ]]; then
    hk_refuse "plan.checked.json changed after approval; nothing executed"
fi
hk_state "APPROVED($mode)"

# --- Execute ------------------------------------------------------------------
hk_merged_check() { # branch: tip must be an ancestor of origin's default branch
    local def
    def="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)" || return 1
    [[ -n "$def" ]] || return 1
    git merge-base --is-ancestor "origin/$1" "$def" >/dev/null 2>&1
}

n="$(hk_py count "$HK_CHECKED")"
ST=(); IDS=()
failed=0
for ((i = 0; i < n; i++)); do
    IDS[i]="$(hk_py field "$HK_CHECKED" "$i" id)"
    if ((failed)); then ST[i]=NOT_VERIFIED; continue; fi
    hk_load_argv exec "$i"
    shown="$(hk_py renderop "$HK_CHECKED" "$i" exec)"
    if [[ "${hk_argv[0]-} ${hk_argv[1]-} ${hk_argv[2]-}" == "git push origin" ]]; then
        if ! hk_merged_check "${hk_argv[${#hk_argv[@]}-1]}"; then
            hk_log "op ${IDS[i]} FAILED merged check: $shown"
            ST[i]=FAILED; failed=1; continue
        fi
    fi
    hk_run_checked exec "$i"
    hk_log "op ${IDS[i]} exit=$HK_RC cmd: $shown"
    if ((HK_RC != 0)); then ST[i]=FAILED; failed=1; else ST[i]=EXECUTED; fi
done
if ((failed)); then hk_state FAILED; else hk_state EXECUTED; fi

# --- Verify (fixed read-only templates; exact string compare) -----------------
bad=0
for ((i = 0; i < n; i++)); do
    [[ "${ST[i]}" == NOT_VERIFIED ]] && { bad=1; continue; }
    hk_run_checked verify "$i"
    vrc=$HK_RC
    vexp="$(hk_py field "$HK_CHECKED" "$i" vexpect)"
    hk_log "op ${IDS[i]} verify exit=$vrc cmd: $(hk_py renderop "$HK_CHECKED" "$i" verify)"
    case "${ST[i]}" in
        EXECUTED)
            if ((vrc == 0)) && [[ "$HK_OUT" == "$vexp" ]]; then ST[i]=VERIFIED
            else ST[i]=VERIFY_FAILED; bad=1; fi ;;
        *) bad=1 ;;
    esac
done

# --- Report -------------------------------------------------------------------
{
    echo "# Housekeeping report"
    echo
    echo "Mode: $mode"
    echo "Plan sha256: $HK_APPROVED_HASH"
    echo
    echo "| id | status | command |"
    echo "|---|---|---|"
    for ((i = 0; i < n; i++)); do
        echo "| ${IDS[i]} | ${ST[i]} | $(hk_py renderop "$HK_CHECKED" "$i" exec) |"
        printf '%s\t%s\n' "${IDS[i]}" "${ST[i]}" >> "$HK_DIR/ops.status"
    done
} > "$HK_DIR/REPORT.md"
hk_state REPORTED
cat "$HK_DIR/REPORT.md"
exit $((bad))

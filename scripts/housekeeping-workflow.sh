#!/usr/bin/env bash
# Housekeeping driver: one free-form agent run, as if Claude did the chore.
#
# The agent gets the request and its normal tools (read, edit, shell). There is
# no fixed list of operations. What it may not do is set by the deny list: a
# locked built-in floor plus the editable `housekeeping.disallow` list in
# .uncle/config, each pattern passed to Claude as a denied Bash prefix.
# Pattern matching is by command prefix, so it is a guard rail, not a sandbox.
#
# Usage: housekeeping-workflow.sh [--attended|--unattended] [REQUEST TEXT]
#        (or UNCLE_STARTUP_TEXT_FILE). Unattended is the default: no
#        confirmation prompt. --attended asks once before the agent starts.
# Env:   UNCLE_ATTENDED=1 selects attended; UNCLE_HOUSEKEEPING_UNATTENDED=1 is
#        deprecated (unattended is the default).
#        HOUSEKEEPING_APPROVAL_FILE   read the confirmation from this path
#                                     instead of /dev/tty
# Exit:  0 when declined or the agent finished successfully; 1 otherwise.
#
# Records live in .uncle/workflow/housekeeping/. The shared driver.lock flock
# is released by the kernel on every exit path.

ROOT="${HK_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PROJECT_ROOT="${UNCLE_PROJECT_ROOT:-$PWD}"
export PROJECT_ROOT HK_ROOT_RESOLVED="$ROOT"
. "$ROOT/scripts/lib/stage-config.sh"

HK_DIR="$PROJECT_ROOT/.uncle/workflow/housekeeping"
HK_MAX_TURNS="${HOUSEKEEPING_MAX_TURNS:-60}"
HK_TOOLS="Read,Glob,Grep,Write,Edit,TodoWrite,Bash"

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
MODE_FLAGS=()
while [[ "${1:-}" == --attended || "${1:-}" == --unattended ]]; do
    MODE_FLAGS+=("$1"); shift
done
REQUEST="${1:-}"
if [[ -z "$REQUEST" && -n "${UNCLE_STARTUP_TEXT_FILE:-}" && -r "${UNCLE_STARTUP_TEXT_FILE}" ]]; then
    REQUEST="$(cat "$UNCLE_STARTUP_TEXT_FILE")"
fi
if [[ -z "${REQUEST//[[:space:]]/}" ]]; then
    echo "housekeeping: empty request refused" >&2
    exit 1
fi

# --- Mode (resolver owns precedence, notices, TTY rule; refusal exits 1 before
# any state is created) ---------------------------------------------------------
. "$ROOT/scripts/lib/mode.sh"
UNATTENDED=0
uncle_resolve_mode "${MODE_FLAGS[@]+"${MODE_FLAGS[@]}"}" || exit 1
export UNCLE_UNATTENDED="$UNATTENDED" UNCLE_MODE_RESOLVED=1

# --- Lock (flock on the shared driver.lock; held by this fd until exit) ------
mkdir -p "$PROJECT_ROOT/.uncle/workflow"
exec 9>>"$PROJECT_ROOT/.uncle/workflow/driver.lock"
if ! python3 -I -c 'import fcntl; fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)' 2>/dev/null; then
    echo "housekeeping: another workflow holds this checkout" >&2
    exit 1
fi

mkdir -p "$HK_DIR"
if [[ "$UNATTENDED" == 1 ]]; then
    printf 'unattended\n' > "$PROJECT_ROOT/.uncle/workflow/mode"
else
    printf 'attended\n' > "$PROJECT_ROOT/.uncle/workflow/mode"
fi
rm -f "$HK_DIR"/plan.* "$HK_DIR"/ops.status "$HK_DIR"/run.log "$HK_DIR"/REPORT.md \
      "$HK_DIR"/last.err "$HK_DIR"/prompt.md "$HK_DIR"/agent.out "$HK_DIR"/agent.err
hk_state STARTED
hk_log "request: $(printf '%s' "$REQUEST" | head -c 500 | tr '\n\r' '  ')"

# --- Deny list: locked floor + editable list, as Claude Bash deny rules --------
HK_DENY_PY='
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["HK_ROOT_RESOLVED"], "scripts", "lib"))
import housekeeping_config as C
EXTRA = ("git push --force", "git push -f", "git push --force-with-lease",
         "rm -rf /", "rm -rf ~", "rm -fr /", "rm -fr ~")
pats = []
for p in list(C.floor_patterns()) + list(EXTRA) + list(C.load(sys.argv[1])):
    if any(ch in p for ch in ",()"):
        sys.stderr.write("deny pattern cannot be expressed safely: %s\n" % p)
        sys.exit(1)
    rule = "Bash(%s:*)" % p
    if rule not in pats:
        pats.append(rule)
print(",".join(pats))
print(json.dumps([r[5:-3] for r in pats]), file=sys.stderr)
'
CONFIG_FILE="${UNCLE_CONFIG:-$PROJECT_ROOT/.uncle/config}"
DENY="$(python3 -I -c "$HK_DENY_PY" "$CONFIG_FILE" 2>"$HK_DIR/deny.json")" \
    || hk_refuse "deny list unusable: $(cat "$HK_DIR/deny.json")"

# --- Agent: the supervisor's runner, model and effort --------------------------
# Housekeeping runs whatever the supervisor is configured to use
# (supervision.runner / .model / .effort, defaults claude/sonnet/low).
HK_SUP="$(python3 -I -c '
import os, sys
sys.path.insert(0, os.path.join(os.environ["HK_ROOT_RESOLVED"], "scripts", "lib"))
import supervisor as S
c = S.load_config(sys.argv[1]).values
for k in ("runner", "model", "effort"):
    print(c.get(k) or S.DEFAULTS[k])
' "$CONFIG_FILE")" || hk_refuse "supervisor settings unreadable"
{ IFS= read -r HK_RUNNER; IFS= read -r HK_MODEL; IFS= read -r HK_EFFORT; } <<< "$HK_SUP"
hk_log "runner $HK_RUNNER model $HK_MODEL effort $HK_EFFORT (supervisor settings)"
if [[ "$HK_RUNNER" != claude ]] && ! stage_command_overridden AGENT housekeeping; then
    hk_refuse "supervisor runner is '$HK_RUNNER'; housekeeping needs claude because the deny list is enforced through its tool rules"
fi
if stage_command_overridden AGENT housekeeping; then
    agent_cmd="$(stage_agent_cmd housekeeping)"
else
    agent_cmd="$(uncle_runner_cmd "$HK_RUNNER" agent)" || hk_refuse "no runner for '$HK_RUNNER'"
fi

{
    cat "$ROOT/prompts/housekeeping-plan.md"
    printf '\n## Never run commands starting with\n\n'
    python3 -I -c 'import json,sys; [print("- `%s`" % p) for p in json.load(sys.stdin)]' < "$HK_DIR/deny.json"
    printf '\n## Request\n\n%s\n' "$REQUEST"
} > "$HK_DIR/prompt.md"

if [[ "$UNATTENDED" != 1 ]]; then
    echo "Housekeeping request:"; printf '%s\n' "$REQUEST"
    printf 'Let the agent carry this out? [y/N] '
    ans=""
    IFS= read -r ans < "${HOUSEKEEPING_APPROVAL_FILE:-/dev/tty}" 2>/dev/null
    echo
    if ! [[ "$ans" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        hk_state DECLINED; hk_log "DECLINED"
        echo "Declined; nothing was run."
        exit 0
    fi
    hk_log "attended: confirmed"
else
    echo "Unattended run: no confirmation prompt; the deny list applies."
    hk_log "unattended"
fi

hk_state RUNNING
bash -c "$agent_cmd \"\$@\"" housekeeping \
    -p --max-turns "$HK_MAX_TURNS" --strict-mcp-config \
    --model "$HK_MODEL" --effort "$HK_EFFORT" \
    --allowedTools "$HK_TOOLS" --disallowedTools "$DENY" \
    < "$HK_DIR/prompt.md" 2> "$HK_DIR/agent.err" | tee "$HK_DIR/agent.out"
rc=${PIPESTATUS[0]}
hk_log "agent exit=$rc"

{
    echo "# Housekeeping report"
    echo
    echo "Mode: $([[ "$UNATTENDED" == 1 ]] && echo unattended || echo attended)"
    echo "Agent exit status: $rc"
    echo
    echo "## Request"; echo; printf '%s\n' "$REQUEST"
    echo; echo "## Agent output"; echo; cat "$HK_DIR/agent.out"
} > "$HK_DIR/REPORT.md"

if ((rc != 0)); then
    hk_state FAILED
    sed -n 1,20p "$HK_DIR/agent.err" >&2
    exit 1
fi
hk_state DONE
exit 0

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Keep installed code separate from the project selected by the launcher.
PROJECT_ROOT="${UNCLE_PROJECT_ROOT:-$ROOT}"
if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "Project root does not exist: $PROJECT_ROOT" >&2
    exit 1
fi
cd "$PROJECT_ROOT"
export UNCLE_PROJECT_ROOT="$PWD"

# ---------------------------------------------------------------------------
# Change-workflow chaining
#
# These functions run after CHANGE_REQUEST.md is seeded on the --change path:
# they start the driver directly, which owns PR handoff.
# Issues stay open until PR merge. These functions read the
# globals resolved further down (OWNER, REPO, ISSUE_NUM, USED_GH) at call time.
# ---------------------------------------------------------------------------

STATE_DIR=".uncle/workflow"
STATE_FILE="$STATE_DIR/state"
ORIGIN_FILE="$STATE_DIR/origin"
VERDICT_FILE="$STATE_DIR/audit-verdict"
MARKER_FILE="$STATE_DIR/issue-closed"

# .uncle/workflow/state grammar, and the shared INV-3 close gate the driver also uses.
. "$ROOT/scripts/lib/state.sh"
. "$ROOT/scripts/lib/issue-close.sh"
. "$ROOT/scripts/lib/terminal-title.sh"

workflow_state() {
    state_read "$STATE_FILE"
}

origin_line() {
    if [[ -s "$ORIGIN_FILE" ]]; then
        head -n 1 "$ORIGIN_FILE"
    fi
}

# .uncle/workflow/origin's first two fields name this invocation's issue. The third
# field is fetch provenance and is deliberately not part of the identity.
origin_matches_this() {
    [[ "$(origin_field "$ORIGIN_FILE" 1)" == "$OWNER/$REPO" \
        && "$(origin_field "$ORIGIN_FILE" 2)" == "$ISSUE_NUM" ]]
}

# True when this checkout holds a change run that has started and not finished.
run_in_flight() {
    local state
    state="$(workflow_state)"
    [[ -n "$state" && "$state" != "COMPLETE" ]]
}

# An in-flight run this issue cannot prove it owns must not be seeded over,
# resumed, or closed against.
check_origin_or_refuse() {
    local owner

    # Mirror of the driver's preflight: a state file bound to one issue beside
    # an origin naming another is corruption, not a foreign-owner conflict.
    state_origin_agree "$STATE_FILE" "$ORIGIN_FILE" || exit 1

    if ! run_in_flight; then
        return 0
    fi

    owner="$(origin_line)"
    if origin_matches_this; then
        return 0
    fi

    echo "Refusing to seed $OWNER/$REPO#$ISSUE_NUM: this checkout has an in-flight"
    echo "change workflow (state: $(workflow_state)) that does not belong to it."
    if [[ -n "$owner" ]]; then
        echo "  $ORIGIN_FILE owner: $owner"
    else
        echo "  $ORIGIN_FILE: absent — the in-flight state has no provable owner"
    fi
    echo "Finish or reset that run before seeding a different issue."
    echo "To clear it deliberately, once you are sure no other run is active:"
    echo "  rm -f $STATE_FILE $ORIGIN_FILE"
    exit 1
}

# True when the CHANGE_REQUEST.md on disk already belongs to this issue's
# in-flight run, in which case rewriting it would discard hand edits.
seed_is_current() {
    run_in_flight && origin_matches_this
}

# .uncle/workflow/origin's third field records how this binding was fetched. Only an
# authenticated gh fetch can later authorize a close; a two-field file written
# before this field existed reads as `curl` and fails closed.
write_origin() {
    local fetch="curl"

    if [[ "${USED_GH:-0}" == "1" ]]; then
        fetch="gh"
    fi

    mkdir -p "$STATE_DIR"
    printf '%s\t%s\t%s\n' "$OWNER/$REPO" "$ISSUE_NUM" "$fetch" > "$ORIGIN_FILE"
}

run_issue_workflow() {
    local run_id status

    run_id="$$-$(date +%Y%m%d%H%M%S)"

    echo
    echo "=================================================="
    echo "CHANGE REQUEST READY TO RUN"
    echo "  CHANGE_REQUEST.md  (from $OWNER/$REPO#$ISSUE_NUM)"
    echo "=================================================="
    echo
    echo "Starting the change workflow from this issue."

    write_origin

    local state previous_state="" reentries=0
    while :; do
        status=0
        STAGEGATE_RUN_ID="$run_id" \
        STAGEGATE_ORIGIN_REPO="$OWNER/$REPO" \
        STAGEGATE_ORIGIN_ISSUE="$ISSUE_NUM" \
            uncle_run "$ROOT/scripts/change-workflow.sh" ${ISSUE_WORKFLOW_ARGS[@]+"${ISSUE_WORKFLOW_ARGS[@]}"} || status=$?

        if [[ "$status" -ne 0 ]]; then
            echo
            echo "change-workflow.sh exited $status; $OWNER/$REPO#$ISSUE_NUM remains open."
            exit "$status"
        fi
        state="$(workflow_state)"
        [[ "$state" != COMPLETE ]] || break
        # A driver that exits 0 short of COMPLETE has moved the run to a gate it
        # wants re-entered -- a reopened approval says "re-run the driver". Do
        # that here rather than call the run finished. It stops once the state
        # no longer moves, which is a gate the operator declined.
        if [[ "$state" == WAIT_* && "$state" != "$previous_state" && "$reentries" -lt 3 ]]; then
            previous_state="$state"
            reentries=$((reentries + 1))
            echo
            echo "The run is waiting at $state; opening that gate now."
            continue
        fi
        echo
        echo "The change workflow stopped at ${state:-an unrecorded state} for $OWNER/$REPO#$ISSUE_NUM; it has not finished."
        echo "Run it again to continue from there."
        return 0
    done

    echo "Change workflow finished. Issues remain open until their PR is merged."
    echo "Making PR, please wait..."
}

# Worktree creation and removal (--worktree). Sourced above the test hook so
# close-flow-test.sh's sourced copy sees the same functions.
. "$ROOT/scripts/lib/worktrees.sh"

# offer_worktree_removal <dir> — ask on stdin; `y` removes through the guarded
# worktree_remove, anything else keeps the directory. The branch survives
# either way. Steps out of <dir> first so the removal is not made from inside it.
offer_worktree_removal() {
    local dir="$1" answer=""
    printf '%s' "Remove worktree $dir? [y/N] "
    if ! read -r answer; then
        echo
    fi
    case "$answer" in
        y|Y|yes|YES)
            case "$PWD/" in
                "$dir"/*) cd "$(dirname "$dir")" ;;
            esac
            worktree_remove "$dir"
            ;;
        *)
            echo "Keeping worktree $dir; remove later with: scripts/lib/worktrees.sh remove $dir"
            ;;
    esac
}



# Test hook: sourcing this script with STAGEGATE_FROM_ISSUE_SOURCE_ONLY=1 yields
# the functions above without running the CLI, so scripts/tests/close-flow-test.sh
# can drive them hermetically. Not a command-line flag; the documented argument
# contract is unchanged.
if [[ "${STAGEGATE_FROM_ISSUE_SOURCE_ONLY:-0}" == "1" ]]; then
    return 0 2>/dev/null || exit 0
fi

usage() {
    cat <<'EOF'
Usage: from-issue.sh <issue-number | github-url> [--change | --new] [--worktree]

Fetch a GitHub issue and seed a workflow from it.

  --change   Write CHANGE_REQUEST.md for ./scripts/change-workflow.sh (default
             if CHANGE_REQUEST.md already exists or the repo is not empty).
  --seed-only  With --change, create the request without starting a workflow.
  --new      Replace the project-brief section of REQUIREMENTS.md for
             ./scripts/stagegate.sh.
  --worktree Run the change in a new git worktree beside the project
             (<project>-issue-<N>) on a new branch; implies --change.
  --worktree-dir PATH  Worktree directory (implies --worktree).
  --branch NAME        Worktree branch (default: <label prefix><issue slug>).

The issue can be:
  - a number like 123 (repo read from the current git remote)
  - a full URL like https://github.com/owner/repo/issues/123

Requires either the gh CLI (authenticated) or curl (public repos only).
EOF
}

if [[ $# -lt 1 ]] || [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    usage
    exit 0
fi

ISSUE_ARG="$1"
MODE=""
SEED_ONLY=0
ISSUE_WORKFLOW_ARGS=()
# Off by default, and it cannot simply be flipped: the worktree is created
# before the issue is classified, so requesting one forces MODE=change below.
# Turning it on by default would silently make every issue run a change run.
#
# The launcher deliberately creates no worktree for an issue run either --
# only this script knows the issue's title, and a name taken before the fetch
# describes the previous run's work. Automatic worktrees for issue runs need
# the creation moved after classification, which is a separate change.
WORKTREE=1
WORKTREE_EXPLICIT=0
WORKTREE_DIR=""
WORKTREE_BRANCH=""
UNATTENDED=0
shift || true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --change) MODE="change" ;;
        --seed-only) SEED_ONLY=1 ;;
        --new) MODE="new" ;;
        --unattended) ISSUE_WORKFLOW_ARGS+=(--unattended); UNATTENDED=1 ;;
        --worktree) WORKTREE=1; WORKTREE_EXPLICIT=1 ;;
        --no-worktree) WORKTREE=0; WORKTREE_EXPLICIT=1 ;;
        --worktree-dir)
            if [[ -z "${2:-}" ]]; then echo "--worktree-dir requires a path."; usage; exit 1; fi
            WORKTREE=1; WORKTREE_EXPLICIT=1; WORKTREE_DIR="$2"; shift ;;
        --branch)
            if [[ -z "${2:-}" ]]; then echo "--branch requires a name."; usage; exit 1; fi
            WORKTREE_BRANCH="$2"; shift ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
    shift
done

if [[ "$SEED_ONLY" == 1 && "$MODE" != change ]]; then
    echo '--seed-only requires --change.' >&2
    exit 1
fi

# An explicit --worktree with an explicit --new is a contradiction and is caught
# here, where both were stated. The default case cannot be judged yet: MODE is
# classified further down, and this once ran before it -- so requesting a
# worktree forced MODE=change and silently reclassified the run.
if [[ "$WORKTREE" == 1 && "$WORKTREE_EXPLICIT" == 1 && "$MODE" == new ]]; then
    echo '--worktree and --worktree-dir require --change; --new is not supported.'
    usage
    exit 1
fi
if [[ "$WORKTREE" == 1 ]]; then
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "Not a git repository: $PWD"
        exit 1
    fi
elif [[ -n "$WORKTREE_BRANCH" ]]; then
    echo '--branch requires --worktree.'
    usage
    exit 1
fi

# ---------------------------------------------------------------------------
# Resolve owner/repo and issue number.
# ---------------------------------------------------------------------------

OWNER=""
REPO=""
ISSUE_NUM=""

if [[ "$ISSUE_ARG" =~ ^https?://github\.com/([^/]+)/([^/]+)/issues/([0-9]+) ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
    ISSUE_NUM="${BASH_REMATCH[3]}"
elif [[ "$ISSUE_ARG" =~ ^([0-9]+)$ ]]; then
    ISSUE_NUM="${BASH_REMATCH[1]}"
    REMOTE_URL="$(git remote get-url origin 2>/dev/null || true)"
    if [[ -z "$REMOTE_URL" ]]; then
        echo "No git remote found. Provide a full GitHub URL."
        exit 1
    fi
    # Handle both https and ssh remotes. Strip any trailing slash and the
    # optional .git suffix first: bash uses POSIX ERE, which has no lazy
    # quantifier, so "([^/]+?)(\.git)?$" fails to compile on bash 3.2.
    REMOTE_URL="${REMOTE_URL%/}"
    REMOTE_URL="${REMOTE_URL%.git}"
    if [[ "$REMOTE_URL" =~ github\.com[:/]+([^/]+)/([^/]+)$ ]]; then
        OWNER="${BASH_REMATCH[1]}"
        REPO="${BASH_REMATCH[2]}"
    else
        echo "Could not parse GitHub owner/repo from remote: $REMOTE_URL"
        exit 1
    fi
else
    echo "Unrecognized issue argument: $ISSUE_ARG"
    usage
    exit 1
fi

trap 'uncle_title_end' EXIT
trap 'uncle_cancel 130' INT
trap 'uncle_cancel 143' TERM
uncle_title_begin "$ISSUE_NUM"

# ---------------------------------------------------------------------------
# Fetch issue metadata.
# ---------------------------------------------------------------------------

fetch_with_gh() {
    gh issue view "$ISSUE_NUM" --repo "$OWNER/$REPO" --json title,body,url,state,labels,comments 2>/dev/null
}

fetch_with_curl() {
    local url="https://api.github.com/repos/$OWNER/$REPO/issues/$ISSUE_NUM"
    curl -fsSL "$url" 2>/dev/null
}

ISSUE_JSON=""
# Only an authenticated gh fetch proves gh can also close the issue later; the
# curl fallback is read-only and public-repo-only.
USED_GH=0
if command -v gh >/dev/null 2>&1; then
    ISSUE_JSON="$(fetch_with_gh || true)"
    if [[ -n "$ISSUE_JSON" ]]; then
        USED_GH=1
    fi
fi
if [[ -z "$ISSUE_JSON" ]] && command -v curl >/dev/null 2>&1; then
    ISSUE_JSON="$(fetch_with_curl || true)"
fi
if [[ -z "$ISSUE_JSON" ]]; then
    echo "Failed to fetch issue $OWNER/$REPO#$ISSUE_NUM."
    echo "Install gh and authenticate, or ensure curl is available for public repos."
    exit 1
fi

# Minimal extraction using Python because jq is optional and bash JSON parsing is brittle.
if python3 -c pass >/dev/null 2>&1; then
    TITLE="$(printf '%s' "$ISSUE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("title",""))')"
    BODY="$(printf '%s' "$ISSUE_JSON" | python3 -c '
import json, sys
issue = json.load(sys.stdin)
parts = [issue.get("body") or ""]
# A clarification written in the thread is part of the request. Dropping it
# silently is how a brief ends up contradicting what the issue actually asked.
for comment in issue.get("comments") or []:
    text = (comment.get("body") or "").strip()
    if not text:
        continue
    who = ((comment.get("author") or {}).get("login")
           or (comment.get("user") or {}).get("login") or "comment")
    parts.append("\n### Comment from %s\n\n%s" % (who, text))
print("\n".join(parts))
')"
    URL="$(printf '%s' "$ISSUE_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("html_url") or d.get("url") or sys.argv[1])' "https://github.com/$OWNER/$REPO/issues/$ISSUE_NUM")"
elif command -v jq >/dev/null 2>&1; then
    TITLE="$(printf '%s' "$ISSUE_JSON" | jq -r '.title // empty')"
    BODY="$(printf '%s' "$ISSUE_JSON" | jq -r '.body // empty')"
    URL="$(printf '%s' "$ISSUE_JSON" | jq -r '.html_url // .url // empty')"
    [[ -n "$URL" ]] || URL="https://github.com/$OWNER/$REPO/issues/$ISSUE_NUM"
else
    echo "Need python3 or jq to parse the GitHub response."
    exit 1
fi

if [[ -z "$TITLE" ]]; then
    echo "Issue title was empty; response may have been rate-limited or unauthorized."
    exit 1
fi

# Classified before the worktree, not after. The worktree decision needs to know
# whether this is a change run, and deciding it the other way round -- requesting
# a worktree and letting that force MODE=change -- silently reclassified every
# run that wanted its own directory.
if [[ -z "$MODE" ]]; then
    # If CHANGE_REQUEST.md already exists, assume the user is continuing a
    # change workflow. Otherwise, if the repo contains files beyond the workflow
    # scaffolding, default to change; if it looks like a fresh template, default
    # to new.
    if [[ -s CHANGE_REQUEST.md ]]; then
        MODE="change"
    elif git ls-files 2>/dev/null | grep -q -v \
            -e '^README\.md$' \
            -e '^REQUIREMENTS\.md$' \
            -e '^CLAUDE\.md$' \
            -e '^CHANGE_REQUEST\.md$' \
            -e '^scripts/' \
            -e '^prompts/' \
            -e '^\.claude/' \
            -e '^\.github/' \
            -e '^\.gitignore$'; then
        MODE="change"
    else
        MODE="new"
    fi
fi

# Greenfield seeding writes REQUIREMENTS.md in place and has no branch to work
# on, so it takes no worktree. Now that MODE is known this is a fact, not a
# request to refuse.
if [[ "$MODE" == new ]]; then
    WORKTREE=0
fi

# ---------------------------------------------------------------------------
# Worktree: created after the fetch (the title names the branch) and before
# the freeze and the seed, which both write under UNCLE_PROJECT_ROOT.
# ---------------------------------------------------------------------------

SOURCE_PROJECT_ROOT="$PROJECT_ROOT"
if [[ "$WORKTREE" == 1 ]]; then
    if [[ -z "$WORKTREE_BRANCH" ]]; then
        # Same label_prefix/slug the PR handoff uses; label lookup failure
        # falls back to `uncle/` inside branch-name. The last line is the name.
        . "$ROOT/scripts/lib/change-pr.sh"
        fetch_kind="curl"
        [[ "$USED_GH" == 1 ]] && fetch_kind="gh"
        WORKTREE_BRANCH="$(change_pr_engine branch-name "$TITLE" "$OWNER/$REPO" "$ISSUE_NUM" "$fetch_kind" | tail -n 1)"
        if [[ -z "$WORKTREE_BRANCH" ]]; then
            echo "Could not derive a branch name for $OWNER/$REPO#$ISSUE_NUM."
            exit 1
        fi
    fi
    if [[ -z "$WORKTREE_DIR" ]]; then
        WORKTREE_DIR="$(worktree_default_dir "$PROJECT_ROOT" "$ISSUE_NUM")"
    fi
    # One issue, one worktree. worktree_default_dir is derived from the issue
    # number, so a rerun lands on the same directory -- and worktree_create
    # refuses an existing branch, which stopped every second run of an issue
    # with "Branch already exists". Reuse it when it is this repo's worktree on
    # the branch this issue derives; anything else is someone else's and is
    # reported rather than adopted.
    if [[ -d "$WORKTREE_DIR" ]] && worktree_registered "$PROJECT_ROOT" "$WORKTREE_DIR"; then
        existing_branch="$(git -C "$WORKTREE_DIR" branch --show-current 2>/dev/null)"
        if [[ "$existing_branch" != "$WORKTREE_BRANCH" ]]; then
            echo "Worktree $WORKTREE_DIR is on branch '$existing_branch', not" >&2
            echo "'$WORKTREE_BRANCH' for $OWNER/$REPO#$ISSUE_NUM." >&2
            echo "Finish or remove it first: scripts/lib/worktrees.sh remove $WORKTREE_DIR" >&2
            exit 1
        fi
        echo "Reusing worktree $WORKTREE_DIR on branch $WORKTREE_BRANCH"
    else
        worktree_create "$WORKTREE_DIR" "$WORKTREE_BRANCH" || exit 1
    fi
    cd "$WORKTREE_DIR"
    # This worktree exists for one issue -- its name and branch both derive
    # from the number -- so in-flight state with no recorded owner can only be
    # an earlier run of the same issue. Archive it and start clean rather than
    # refuse with a remedy nobody can type from the TUI. A run that is live
    # still holds the lock, and that is refused below as before.
    if run_in_flight && [[ ! -s "$ORIGIN_FILE" ]] && ! worktree_run_locked .; then
        echo "The previous run in this worktree recorded no owner; archiving it and starting $OWNER/$REPO#$ISSUE_NUM fresh."
        UNCLE_NEW_WORKFLOW=1 python3 "$ROOT/scripts/lib/workflow_family.py" change || exit 1
    fi
    PROJECT_ROOT="$PWD"
    WORKTREE_DIR="$PWD"
    export UNCLE_PROJECT_ROOT="$PWD"
    # The TUI computed its project root before this directory existed and
    # reads stage-completion records from there; tell it where the run went.
    if [[ -n "${UNCLE_STATUS_FILE:-}" ]]; then
        jq -n -c --arg path "$PWD" '{event:"project_root",path:$path}' \
            >> "$UNCLE_STATUS_FILE" 2>/dev/null || true
    fi
    echo "Created worktree $WORKTREE_DIR on branch $WORKTREE_BRANCH"
fi

# ---------------------------------------------------------------------------
# Freeze attached files.
#
# Seed time is the only point where the fetch can succeed: `gh` is
# authenticated here, and stage network access is off by default. A failure is
# reported and the remote URL is left in place -- a brief that names an
# unreachable attachment is worth more than no brief.
# ---------------------------------------------------------------------------

if [[ -n "$BODY" ]] && python3 -c pass >/dev/null 2>&1; then
    FREEZER="$ROOT/scripts/lib/freeze-issue-files.py"
    if [[ -f "$FREEZER" ]]; then
        echo "Freezing files attached to $OWNER/$REPO#$ISSUE_NUM"
        if FROZEN="$(printf '%s' "$BODY" | UNCLE_PROJECT_ROOT="$PROJECT_ROOT" \
                python3 "$FREEZER")"; then
            BODY="$FROZEN"
        else
            echo "  attachment freeze failed; leaving remote URLs in place."
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Decide mode if not supplied.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Write the seed document.
# ---------------------------------------------------------------------------

write_change_request() {
    cat > CHANGE_REQUEST.md <<EOF
# Change Request

Issue $ISSUE_NUM

Seeded from [$OWNER/$REPO#$ISSUE_NUM]($URL).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

$TITLE

## Motivation

$BODY

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
EOF
    echo "Wrote CHANGE_REQUEST.md"
}

write_new_project_brief() {
    local brief
    brief="$(cat <<EOF
# Project brief

Issue $ISSUE_NUM

> Seeded from [$OWNER/$REPO#$ISSUE_NUM]($URL).
> Replace the placeholder guidance below with specifics before running the driver.

## Summary

$TITLE

## Problem

$BODY

## Scope

What this project covers. Keep it to what must ship.

## Non-goals

What this project explicitly does not do.

## Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| R-001 | | Must |
| R-002 | | Should |
| R-003 | | Could |

## User-visible behavior

| ID | Trigger | Expected result | On failure |
|---|---|---|---|
| B-001 | | | |

## Domain rules and invariants

| ID | Invariant | Consequence if violated |
|---|---|---|
| I-001 | | |

## Data and state

What the authoritative state is, where it lives, what may hold a cached copy,
and what survives a restart.

## Interfaces

APIs, CLI surface, UI entry points, message formats, external services.

## Constraints

Language, runtime, frameworks, libraries, deployment target, budgets,
compatibility that must not break.

## Failure behavior

What must happen on invalid input, unavailable dependencies, partial writes,
concurrent access, and restart mid-operation.

## Verification

How correctness will be demonstrated: test frameworks, commands, and anything
only checkable by hand.

## Definition of done

The concrete conditions under which this is finished.

## Open questions

Anything genuinely undecided.
EOF
)"

    if [[ ! -e REQUIREMENTS.md && ! -L REQUIREMENTS.md ]]; then
        # Noclobber uses exclusive creation; a concurrent file or link must win.
        (set -o noclobber; printf '%s\n' "$brief" > REQUIREMENTS.md)
        echo "Created REQUIREMENTS.md project brief from issue $OWNER/$REPO#$ISSUE_NUM"
        return
    fi

    # Replace the project-brief section (from '# Project brief' to EOF) in REQUIREMENTS.md.
    if ! grep -q '^# Project brief$' REQUIREMENTS.md; then
        echo "REQUIREMENTS.md does not contain a '# Project brief' section; cannot seed new-app workflow."
        exit 1
    fi
    local head
    head="$(awk '/^# Project brief$/{exit} {print}' REQUIREMENTS.md)"
    printf '%s\n%s\n' "$head" "$brief" > REQUIREMENTS.md
    echo "Updated REQUIREMENTS.md project brief from issue $OWNER/$REPO#$ISSUE_NUM"
}

case "$MODE" in
    change)
        check_origin_or_refuse
        if [[ "${UNCLE_NEW_WORKFLOW:-}" == 1 && "$SEED_ONLY" != 1 ]]; then
            if worktree_run_locked .; then
                echo "Refusing to start fresh: this issue worktree has a live workflow." >&2
                exit 1
            fi
            # A normal Start is intentionally not a resume.  This matters for
            # the stable per-issue worktree: archive its workflow evidence
            # before reseeding the issue, so seed_is_current cannot retain an
            # old request.  The live-driver check above prevents moving files
            # out from under an active process.
            python3 "$ROOT/scripts/lib/workflow_family.py" change || exit 1
            # change-workflow.sh must not archive the newly written seed a
            # second time when it inherits the launch environment.
            unset UNCLE_NEW_WORKFLOW
        fi
        if [[ "$SEED_ONLY" == 1 ]]; then
            # Exclusive creation prevents chat imports from replacing a user's brief.
            (set -o noclobber; write_change_request)
            write_origin
            exit 0
        fi
        if seed_is_current; then
            echo "Resuming the existing run for $OWNER/$REPO#$ISSUE_NUM; CHANGE_REQUEST.md left as it is."
        else
            write_change_request
        fi
        run_issue_workflow
        if [[ "$WORKTREE" == 1 && "$(workflow_state)" == "COMPLETE" ]]; then
            # The TUI drives this script through a pipe and cannot answer;
            # unattended runs have nobody to ask. Both get the command instead.
            if [[ -t 0 && "$UNATTENDED" != 1 ]]; then
                cd "$SOURCE_PROJECT_ROOT"
                # A refused removal (dirty tree) keeps the worktree and its
                # reason; the run itself succeeded, so the exit status stays 0.
                offer_worktree_removal "$WORKTREE_DIR" || true
            else
                echo "Worktree $WORKTREE_DIR kept; remove with: scripts/lib/worktrees.sh remove $WORKTREE_DIR"
            fi
        fi
        ;;
    new)
        write_new_project_brief
        # Launch only after the seed succeeds; the driver owns approvals and
        # durable workflow state in the selected project, not the install dir.
        STAGEGATE_ORIGIN_REPO="$OWNER/$REPO" \
        STAGEGATE_ORIGIN_ISSUE="$ISSUE_NUM" \
            uncle_run bash "$ROOT/scripts/stagegate.sh" ${ISSUE_WORKFLOW_ARGS[@]+"${ISSUE_WORKFLOW_ARGS[@]}"}
        ;;
esac

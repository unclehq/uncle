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
# they confirm with the human and run the driver, which owns PR handoff.
# Issues stay open until PR merge. These functions read the
# globals resolved further down (OWNER, REPO, ISSUE_NUM, USED_GH) at call time.
# ---------------------------------------------------------------------------

STATE_DIR=".uncle/workflow"
STATE_FILE="$STATE_DIR/state"
ORIGIN_FILE="$STATE_DIR/origin"
VERDICT_FILE="$STATE_DIR/audit-verdict"
MARKER_FILE="$STATE_DIR/issue-closed"
CONFIRM_WORD="RUN"

# .uncle/workflow/state grammar, and the shared INV-3 close gate the driver also uses.
. "$ROOT/scripts/lib/state.sh"
. "$ROOT/scripts/lib/issue-close.sh"

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

confirm_and_run_workflow() {
    local run_id status response

    run_id="$$-$(date +%Y%m%d%H%M%S)"

    echo
    echo "=================================================="
    echo "CHANGE REQUEST READY TO RUN"
    echo "  CHANGE_REQUEST.md  (from $OWNER/$REPO#$ISSUE_NUM)"
    echo "=================================================="
    echo
    echo "Review and edit it now if it needs more than the issue text:"
    echo "  less CHANGE_REQUEST.md"
    echo "  code CHANGE_REQUEST.md"
    echo
    echo "Confirming starts ./scripts/change-workflow.sh here. That runs the"
    echo "multi-stage agent pipeline, spends real budget, and — only on a READY"
    echo "final audit — closes $OWNER/$REPO#$ISSUE_NUM."
    echo "Commit or stash unrelated work first: the driver records git diff of the"
    echo "whole working tree as the change record."
    echo

    # Printed rather than passed to `read -p`: bash suppresses a -p prompt when
    # stdin is not a terminal, and a non-interactive caller must still see what
    # it is blocking on (CHANGE_SPEC §8).
    response=""
    printf '%s' "Type $CONFIRM_WORD exactly to start the change workflow: "
    if [[ " ${ISSUE_WORKFLOW_ARGS[*]-} " == *" --unattended "* ]]; then
        response="$CONFIRM_WORD"
        echo "Unattended: starting without human review."
    else
        read -r response || true
    fi
    echo

    if [[ "$response" != "$CONFIRM_WORD" ]]; then
        echo "Not confirmed. CHANGE_REQUEST.md is written; nothing else ran."
        echo "Run: ./scripts/change-workflow.sh"
        return 0
    fi

    write_origin

    status=0
    STAGEGATE_RUN_ID="$run_id" \
    STAGEGATE_ORIGIN_REPO="$OWNER/$REPO" \
    STAGEGATE_ORIGIN_ISSUE="$ISSUE_NUM" \
        "$ROOT/scripts/change-workflow.sh" ${ISSUE_WORKFLOW_ARGS[@]+"${ISSUE_WORKFLOW_ARGS[@]}"} || status=$?

    if [[ "$status" -ne 0 ]]; then
        echo
        echo "change-workflow.sh exited $status; $OWNER/$REPO#$ISSUE_NUM remains open."
        exit "$status"
    fi

    echo "Change workflow finished. Issues remain open until their PR is merged."
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
Usage: from-issue.sh <issue-number | github-url> [--change | --new]

Fetch a GitHub issue and seed a workflow from it.

  --change   Write CHANGE_REQUEST.md for ./scripts/change-workflow.sh (default
             if CHANGE_REQUEST.md already exists or the repo is not empty).
  --new      Replace the project-brief section of REQUIREMENTS.md for
             ./scripts/stagegate.sh.

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
ISSUE_WORKFLOW_ARGS=()
shift || true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --change) MODE="change" ;;
        --new) MODE="new" ;;
        --unattended) ISSUE_WORKFLOW_ARGS+=(--unattended) ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
    shift
done

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

# ---------------------------------------------------------------------------
# Fetch issue metadata.
# ---------------------------------------------------------------------------

fetch_with_gh() {
    gh issue view "$ISSUE_NUM" --repo "$OWNER/$REPO" --json title,body,url,state,labels 2>/dev/null
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
    BODY="$(printf '%s' "$ISSUE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("body",""))')"
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

# ---------------------------------------------------------------------------
# Decide mode if not supplied.
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Write the seed document.
# ---------------------------------------------------------------------------

write_change_request() {
    cat > CHANGE_REQUEST.md <<EOF
# Change Request

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
        echo "Run: ./scripts/stagegate.sh"
        return
    fi

    # Replace the project-brief section (from '# Project brief' to EOF) in REQUIREMENTS.md.
    if ! grep -q '^# Project brief$' REQUIREMENTS.md; then
        echo "REQUIREMENTS.md does not contain a '# Project brief' section; cannot seed new-app workflow."
        exit 1
    fi
    echo "Updated REQUIREMENTS.md project brief from issue $OWNER/$REPO#$ISSUE_NUM"
    echo "Run: ./scripts/stagegate.sh"
}

case "$MODE" in
    change)
        check_origin_or_refuse
        if seed_is_current; then
            echo "Resuming the existing run for $OWNER/$REPO#$ISSUE_NUM; CHANGE_REQUEST.md left as it is."
        else
            write_change_request
        fi
        confirm_and_run_workflow
        ;;
    new) write_new_project_brief ;;
esac

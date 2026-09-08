#!/usr/bin/env bash
# Stop before a checklist the configured runner cannot execute.
#
# The reviewer declares what each check needs exclusively -- a port, a browser
# session, a human. Those tokens are also a statement of capability: a check
# that needs `port:8000` needs a process allowed to bind one, and a check that
# needs `chrome-user-profile` needs a machine with a screen.
#
# codex runs its stages in a sandbox that denies both unless told otherwise, so
# a checklist full of GUI rows handed to a sandboxed runner produces a report
# of BLOCKED rows -- every one of them correct, none of them progress, and no
# repair attempt can turn a missing socket into a pass. That is a prerequisite
# problem, and prerequisites belong before the work, not in its results.
#
# So the runner and the checklist are compared first, and a mismatch stops at
# an operator dialog instead of spending the stage.
#
# bash 3.2 compatible: no associative arrays.
CAPABILITY_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# checklist_capability_of <token> -> port | gui | human | ""  (empty: ordinary
# state, isolated by the grouping and needing nothing of the environment)
checklist_capability_of() {
    case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
        port:*|port-*|port|localhost*|server*|socket*|bind*|http*)
            printf 'port' ;;
        browser*|chrome*|safari*|firefox*|edge*|webkit*|gui*|display*|screen*|\
        clipboard*|keyboard*|print*|mail*|window*|zoom*)
            printf 'gui' ;;
        reviewer:*|reviewer|human*|sign-off*|signoff*|approval*|approver*)
            printf 'human' ;;
        *)  printf '' ;;
    esac
}

# checklist_runner_provides <capability> <runner> <network> -> 0 when it can
#
# Only codex sandboxes a stage. Its workspace-write sandbox denies network
# access -- loopback binds included -- unless <stage>.network turns it on, and
# it has no screen at all, which no setting changes.
checklist_runner_provides() {
    local capability="$1" runner="$2" network="$3"
    case "$capability" in
        port)  [[ "$runner" != codex || "$network" == true ]] ;;
        gui)   [[ "$runner" != codex ]] ;;
        human) return 1 ;;    # no runner is a person; never a gate, see below
        *)     return 0 ;;
    esac
}

# checklist_capability_gaps <resources.tsv> <runner> <network>
#   -> "<capability>\t<count>\t<tokens>\t<ids>" per unmet capability
#
# Human rows are reported separately by the caller: they are unmet by every
# runner, so gating on them would make the stage permanently unrunnable.
checklist_capability_gaps() {
    local file="$1" runner="$2" network="$3"
    [[ -s "$file" ]] || return 0
    local capability token ids
    for capability in port gui; do
        checklist_runner_provides "$capability" "$runner" "$network" && continue
        local tokens="" all="" count=0
        while IFS="$(printf '\t')" read -r token ids; do
            [[ -n "$token" ]] || continue
            [[ "$(checklist_capability_of "$token")" == "$capability" ]] || continue
            tokens="${tokens:+$tokens }$token"
            all="${all:+$all,}$ids"
            count=$((count + 1))
        done < "$file"
        [[ "$count" -gt 0 ]] || continue
        printf '%s\t%s\t%s\t%s\n' "$capability" \
            "$(printf '%s' "$all" | tr ',' '\n' | sort -u | grep -c .)" \
            "$tokens" "$(checklist_sort_ids "$all")"
    done
}

# checklist_sort_ids <comma-separated ids> -- unique, grouped by prefix, in
# numeric order. A lexical sort puts MC-10 between MC-1 and MC-2, which makes a
# list of two dozen checks unreadable exactly when the operator has to read it.
# --- what this machine can actually open ------------------------------------
# A checklist that names a browser is naming something that may not be here.
# Safari does not exist on Windows at all; Chrome is a download on every
# platform, and CDP -- the protocol every headless harness in this repo speaks
# -- only exists in Chrome, Chromium, and Edge. So "there is a browser" is not
# the question. The question is whether the browser this checklist names is on
# this machine, and it has to be asked before the stage, not discovered in its
# results.
#
# Tests override checklist_platform and checklist_app_present.

checklist_platform() {
    case "$(uname -s 2>/dev/null)" in
        Darwin)               printf 'macos' ;;
        MINGW*|MSYS*|CYGWIN*) printf 'windows' ;;
        *)                    printf 'linux' ;;
    esac
}

# The opener that follows the user's own default-browser setting, which is the
# only browser choice this workflow should be making on its own.
checklist_browser_opener() {
    case "$(checklist_platform)" in
        macos)   printf 'open' ;;
        windows) printf 'start' ;;
        *)       printf 'xdg-open' ;;
    esac
}

# checklist_browser_of <token> -> chrome | safari | firefox | edge | system | ""
checklist_browser_of() {
    case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
        *chrom*)                printf 'chrome' ;;
        *safari*|*webkit*)      printf 'safari' ;;
        *firefox*|*gecko*)      printf 'firefox' ;;
        *edge*)                 printf 'edge' ;;
        browser:system|browser|gui*|display*|screen*|window*|zoom*|print*|        clipboard*|keyboard*|mail*)
                                printf 'system' ;;
        *)                      printf '' ;;
    esac
}

checklist_app_present() {
    local candidate
    for candidate in "$@"; do
        case "$candidate" in
            /*) [[ -e "$candidate" ]] && return 0 ;;
            *)  command -v "$candidate" > /dev/null 2>&1 && return 0 ;;
        esac
    done
    return 1
}

# checklist_browser_present <browser> -> 0 when it can be launched here
checklist_browser_present() {
    local browser="$1" platform
    platform="$(checklist_platform)"
    case "$browser:$platform" in
        system:*)
            # The opener always resolves to whatever the user set as default.
            checklist_app_present "$(checklist_browser_opener)" ;;
        chrome:macos)
            checklist_app_present "/Applications/Google Chrome.app" \
                "${HOME:-/nonexistent}/Applications/Google Chrome.app" \
                "/Applications/Chromium.app" "google-chrome" "chromium" ;;
        chrome:windows)
            checklist_app_present \
                "/c/Program Files/Google/Chrome/Application/chrome.exe" \
                "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
                "${LOCALAPPDATA:-/nonexistent}/Google/Chrome/Application/chrome.exe" \
                "chrome" "chrome.exe" ;;
        chrome:*)
            checklist_app_present google-chrome google-chrome-stable chromium \
                chromium-browser ;;
        safari:macos)
            checklist_app_present "/Applications/Safari.app" ;;
        safari:*)
            return 1 ;;          # Safari has never shipped off macOS
        edge:macos)
            checklist_app_present "/Applications/Microsoft Edge.app" ;;
        edge:windows)
            checklist_app_present \
                "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
                "/c/Program Files/Microsoft/Edge/Application/msedge.exe" \
                "msedge" "msedge.exe" ;;
        edge:*)
            checklist_app_present microsoft-edge microsoft-edge-stable ;;
        firefox:macos)
            checklist_app_present "/Applications/Firefox.app" firefox ;;
        firefox:windows)
            checklist_app_present \
                "/c/Program Files/Mozilla Firefox/firefox.exe" \
                "firefox" "firefox.exe" ;;
        firefox:*)
            checklist_app_present firefox ;;
        *)  return 0 ;;
    esac
}

checklist_browser_advice() {
    case "$1:$(checklist_platform)" in
        safari:windows|safari:linux)
            printf 'Safari does not exist on this platform. Retarget the check at the system browser (browser:system) or run it on a Mac.' ;;
        chrome:*)
            printf 'Install Chrome, or retarget the check at the system browser (browser:system). Note that a CDP/headless harness needs Chrome, Chromium, or Edge; it cannot drive Safari or Firefox.' ;;
        *)  printf 'Install it, or retarget the check at the system browser (browser:system).' ;;
    esac
}

# checklist_missing_browsers <resources.tsv> -> "<browser>\t<tokens>\t<ids>"
checklist_missing_browsers() {
    local file="$1"
    [[ -s "$file" ]] || return 0
    local token ids browser seen=""
    for browser in chrome safari firefox edge system; do
        checklist_browser_present "$browser" && continue
        local tokens="" all="" found=""
        while IFS="$(printf '\t')" read -r token ids; do
            [[ -n "$token" ]] || continue
            [[ "$(checklist_browser_of "$token")" == "$browser" ]] || continue
            tokens="${tokens:+$tokens }$token"
            all="${all:+$all,}$ids"
            found=1
        done < "$file"
        [[ -n "$found" ]] || continue
        printf '%s\t%s\t%s\n' "$browser" "$tokens" "$(checklist_sort_ids "$all")"
    done
}

checklist_sort_ids() {
    printf '%s' "$1" | tr ',' '\n' | grep -v '^$' | sort -u \
        | sort -t- -k1,1 -k2,2n | tr '\n' ' '
}

checklist_capability_explain() {
    case "$1" in
        port) printf 'bind a local port. codex sandboxes its stages and its workspace-write sandbox denies network access, loopback included.' ;;
        gui)  printf 'drive a real browser or desktop. A codex stage has no screen, and no setting gives it one.' ;;
    esac
}

# ensure_checklist_runner <stage> -- the dialog. Returns 0 to run the stage,
# 1 to leave the run pending.
#
# Re-reads .uncle/config on every pass, because that is where the answer is:
# the drivers read per-stage settings at the moment a stage starts, so an
# operator who changes the runner here is changing what runs next.
ensure_checklist_runner() {
    local stage="$1"
    local file="$STATE_DIR/checklist-groups/resources.tsv"
    [[ -s "$file" ]] || return 0
    local answer runner network gaps humans capability count tokens ids

    while true; do
        runner="$(uncle_stage_runner "$stage")"
        network="$(uncle_stage_network "$stage")"
        gaps="$(checklist_capability_gaps "$file" "$runner" "$network")"

        humans="$(while IFS="$(printf '\t')" read -r capability ids; do
            [[ "$(checklist_capability_of "$capability")" == human ]] || continue
            printf '%s\n' "$ids" | tr ',' '\n'
        done < "$file" | sort -u | grep -c . || true)"

        local missing browser tokens ids
        missing="$(checklist_missing_browsers "$file")"

        if [[ -z "$gaps" ]]; then
            if [[ -n "$missing" ]]; then
                echo
                echo "Checklist runner: $runner on $(checklist_platform). Some named browsers are not installed here:"
                while IFS="$(printf '\t')" read -r browser tokens ids; do
                    [[ -n "$browser" ]] || continue
                    echo "  $browser is missing ($tokens): $ids"
                    echo "    $(checklist_browser_advice "$browser")"
                done <<< "$missing"
                echo "Those rows record BLOCKED. The system browser here is whatever"
                echo "\`$(checklist_browser_opener)\` resolves to, which is per-user and per-machine:"
                echo "record which browser a row actually used, or the result is not reproducible."
            fi
            if [[ "${humans:-0}" -gt 0 ]]; then
                echo
                echo "Checklist runner: $runner. $humans check(s) need a person and will record BLOCKED; no runner can sign for them."
            fi
            return 0
        fi

        echo
        echo "The checklist needs more than this stage's runner can do."
        echo "  stage:   $stage"
        echo "  runner:  $runner${network:+ (network: $network)}"
        while IFS="$(printf '\t')" read -r capability count tokens ids; do
            [[ -n "$capability" ]] || continue
            echo
            echo "  $count check(s) must $(checklist_capability_explain "$capability")"
            echo "    declared as: $tokens"
            echo "    checks:      $ids"
        done <<< "$gaps"
        if [[ -n "$missing" ]]; then
            while IFS="$(printf '\t')" read -r browser tokens ids; do
                [[ -n "$browser" ]] || continue
                echo
                echo "  Also: $browser is not installed on this $(checklist_platform) machine ($tokens)"
                echo "    checks:      $ids"
                echo "    $(checklist_browser_advice "$browser")"
            done <<< "$missing"
        fi
        echo
        echo "Running it anyway records those rows BLOCKED. That is an accurate"
        echo "report and no progress: a repair stage cannot grant a socket or a"
        echo "screen, so the run would return here unchanged."
        echo
        echo "Change it in .uncle/config (\`$stage.runner\`, \`$stage.network\`)"
        echo "or from \`uncle\` -> Configure. cline, claude, and kimi are not"
        echo "sandboxed; codex needs \`$stage.network true\` for a port and"
        echo "cannot do GUI work at all."

        gate_prompt "Runner cannot execute this checklist: 'r' to re-read the config after changing it, 'run' to run anyway and record BLOCKED rows, or Enter to leave this run pending: "
        if ! IFS= read -r answer; then
            echo
            echo 'Run remains pending; the runner was not changed.'
            return 1
        fi
        case "$answer" in
            r|R|reread|re-read|retry) continue ;;
            run|RUN)
                echo "Running $stage on $runner anyway; unmet rows will record BLOCKED."
                return 0 ;;
            *)
                echo 'Run remains pending; the runner was not changed.'
                return 1 ;;
        esac
    done
}

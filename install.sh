#!/usr/bin/env bash
# GitHub bootstrap. Compatible with macOS Bash 3.2 and Git Bash.
set -euo pipefail
repo=unclehq/uncle
ref=main
source_dir=""
dry_run=0
force_live=0
usage() {
    cat <<'HELP'
Usage: bash install.sh [--repo OWNER/REPO] [--ref BRANCH|TAG|COMMIT]
                       [--source-dir PATH] [--dry-run]
macOS: Homebrew; Debian/Ubuntu (including WSL): apt; Windows Git Bash: Scoop.
Refuses to install while a workflow is running; --force-live overrides.
Downloads from GitHub by default. --source-dir packages a local checkout instead.
Install Homebrew or Scoop first. Linux uses sudo when not running as root.
HELP
}
while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo|--ref|--source-dir)
            [[ $# -ge 2 && -n "$2" ]] || { echo "Missing value for $1" >&2; exit 2; }
            case "$1" in --repo) repo="$2" ;; --ref) ref="$2" ;; --source-dir) source_dir="$2" ;; esac
            shift 2 ;;
        --dry-run) dry_run=1; shift ;;
        --force-live) force_live=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done
[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ && "$repo" != *..* ]] || { echo 'Invalid GitHub repository.' >&2; exit 2; }
[[ "$ref" =~ ^[A-Za-z0-9][A-Za-z0-9_./-]*$ && "$ref" != *..* ]] || { echo 'Invalid GitHub ref.' >&2; exit 2; }
case "$(uname -s)" in
    Darwin) platform=homebrew ;;
    Linux)
        command -v apt-get >/dev/null || { echo 'This Linux distribution needs apt-get (Debian/Ubuntu/WSL).' >&2; exit 1; }
        platform=apt ;;
    MINGW*|MSYS*|CYGWIN*) platform=scoop ;;
    *) echo 'Unsupported OS. Use macOS, Debian/Ubuntu, or Windows with PowerShell/Git Bash.' >&2; exit 1 ;;
esac
if [[ -n "$source_dir" ]]; then
    source_dir="$(cd "$source_dir" && pwd)"
    [[ -f "$source_dir/uncle" && -d "$source_dir/scripts/install" ]] || { echo 'Not an Uncle source checkout.' >&2; exit 2; }
fi
printf 'Installer: %s; source: %s (%s)\n' "$platform" "$repo" "${source_dir:-$ref}"
[[ "$dry_run" == 0 ]] || exit 0
# Never swap the scripts out from under a running driver. See lib/running-workflow.sh.
if [[ "$force_live" == 0 && -n "$source_dir" && -f "$source_dir/scripts/lib/running-workflow.sh" ]]; then
    . "$source_dir/scripts/lib/running-workflow.sh"
    if running_workflow_report; then exit 1; fi
fi
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
if [[ "$platform" == scoop ]]; then
    command -v powershell.exe >/dev/null || { echo 'Run install.ps1 in PowerShell on Windows.' >&2; exit 1; }
    if [[ -n "$source_dir" ]]; then
        ps_script="$source_dir/install.ps1"
    else
        curl --fail --location --proto '=https' --tlsv1.2 \
            "https://raw.githubusercontent.com/$repo/$ref/install.ps1" -o "$work/install.ps1"
        ps_script="$work/install.ps1"
    fi
    ps_args=(-NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$ps_script")" -Repo "$repo" -Ref "$ref")
    [[ -z "$source_dir" ]] || ps_args+=(-SourceDir "$(cygpath -w "$source_dir")")
    # Paths were converted explicitly; leave owner/repo and branch names alone.
    MSYS2_ARG_CONV_EXCL='*' powershell.exe "${ps_args[@]}"
    exit $?
fi
if [[ "$platform" == apt ]]; then
    root_cmd=()
    if [[ "$(id -u)" != 0 ]]; then
        command -v sudo >/dev/null || { echo 'Install sudo or run this installer as root.' >&2; exit 1; }
        root_cmd=(sudo)
    fi
    "${root_cmd[@]+"${root_cmd[@]}"}" apt-get update
    "${root_cmd[@]+"${root_cmd[@]}"}" apt-get install -y ca-certificates curl git python3 dpkg-dev
else
    command -v brew >/dev/null || { echo 'Install Homebrew from https://brew.sh, then rerun.' >&2; exit 1; }
    [[ "$(id -u)" != 0 ]] || { echo 'Run the Homebrew installer as your normal user, not root.' >&2; exit 1; }
    brew install git python@3.13
    export PATH="$(brew --prefix python@3.13)/libexec/bin:$PATH"
fi
if [[ -z "$source_dir" ]]; then
    source_dir="$work/source"
    git init -q "$source_dir"
    git -C "$source_dir" remote add origin "https://github.com/$repo.git"
    git -C "$source_dir" -c core.autocrlf=false fetch --depth 1 origin "$ref"
    git -C "$source_dir" -c core.autocrlf=false checkout -q --detach FETCH_HEAD
    commit="$(git -C "$source_dir" rev-parse HEAD)"
else
    commit=local
fi
[[ -f "$source_dir/scripts/install/build-package.py" ]] || { echo 'Selected revision predates the package installers.' >&2; exit 1; }
if [[ "$platform" == apt ]]; then
    python3 "$source_dir/scripts/install/build-package.py" deb --source "$source_dir" --output "$work/packages"
    "${root_cmd[@]+"${root_cmd[@]}"}" apt-get install -y --reinstall "$work"/packages/uncle_*_all.deb
else
    bash "$source_dir/scripts/install/homebrew.sh" "$source_dir" "$work" "$repo" "$commit"
fi
printf '\nUncle installed. Install/authenticate your selected agent CLIs, then run uncle in your project.\n'

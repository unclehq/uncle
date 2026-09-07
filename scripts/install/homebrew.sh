#!/usr/bin/env bash
set -euo pipefail
source_dir="$1" work="$2" repo="$3" commit="$4"
if [[ "$commit" == local ]]; then
    python3 "$source_dir/scripts/install/build-package.py" archive --source "$source_dir" --output "$work/packages"
    archive="$work/packages/uncle.tar.gz"
    url="file://$archive"
else
    archive="$work/github.tar.gz"
    url="https://github.com/$repo/archive/$commit.tar.gz"
    curl --fail --location --proto '=https' --tlsv1.2 "$url" -o "$archive"
fi
# A local tap is deliberately separate from any published upstream tap. It is
# refreshed by this installer, so selecting a tag never silently follows main.
tap=unclehq/github-install
if [[ ! -d "$(brew --repository)/Library/Taps/unclehq/homebrew-github-install" ]]; then
    brew tap-new --no-git "$tap"
    : > "$(brew --repository "$tap")/.uncle-generated"
fi
tap_dir="$(brew --repository "$tap")"
[[ -f "$tap_dir/.uncle-generated" ]] || { echo 'Existing tap is not owned by this installer.' >&2; exit 1; }
if [[ "$commit" == local ]]; then
    mkdir -p "$tap_dir/archives"
    cp "$archive" "$tap_dir/archives/uncle.tar.gz"
    archive="$tap_dir/archives/uncle.tar.gz"
    url="file://$archive"
fi
python3 "$source_dir/scripts/install/build-package.py" formula --source "$source_dir" \
    --output "$work/formula" --archive "$archive" --url "$url"
mkdir -p "$tap_dir/Formula"
cp "$work/formula/uncle.rb" "$tap_dir/Formula/uncle.rb"
if brew list --versions "$tap/uncle" >/dev/null 2>&1; then
    brew reinstall "$tap/uncle"
else
    brew install "$tap/uncle"
fi
brew test "$tap/uncle"

#!/usr/bin/env bash
# preview_existing_project must ignore tracked files that were deleted from the working tree.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
git init -q . && git config user.email t@t && git config user.name t
for i in 1 2 3 4 5 6 7 8 9; do echo x > "f$i.txt"; done
git add . && git commit --no-gpg-sign -qm init
eval "$(sed -n '/^preview_existing_project()/,/^}/p' "$ROOT/scripts/lib/preview-build.sh")"
preview_existing_project || { echo "FAIL: populated repo should be an existing project"; exit 1; }
rm -f f*.txt
if preview_existing_project; then echo "FAIL: wiped working tree should not count as existing"; exit 1; fi
echo "PASS"

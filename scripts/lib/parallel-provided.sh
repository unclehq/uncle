#!/usr/bin/env bash
# A parallel implementation step whose file the driver supplies, so no model is asked to write it.
#
#   parallel-provided.sh STEP TARGET     run in the step's sandbox: write the driver's defect-injection runner at TARGET
#
# The mutation runner is the same program in every project (copy the tree, inject a defect, run the spec that must fail), and writing it
# was the longest step of the build (noinit: 190 lines, 53 s) and the one that failed, because it was written blind against files other
# steps were writing at the same moment.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="${2:?target path}"
case "$target" in /*|*..*) echo "Refusing to write outside the project: $target" >&2; exit 1 ;; esac
mkdir -p "$(dirname "$target")"
cp "$here/mutation_runner.mjs" "$target"
echo "Step ${1:-?}: wrote the driver's defect-injection runner to $target (no model call)."

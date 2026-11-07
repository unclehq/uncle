#!/usr/bin/env bash
# Dispatch for the aws-bedrock runner: existing runners and the unknown-runner
# error are byte-identical to the committed (pre-change) stage-config.sh.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/oldlib"; cp "$ROOT"/scripts/lib/*.sh "$T/oldlib/" 2>/dev/null
git -C "$ROOT" show HEAD:scripts/lib/stage-config.sh >"$T/oldlib/stage-config.sh" 2>/dev/null || { echo "SKIP: no committed baseline"; exit 0; }
fails=0
probe() { # script runner -> dispatch output, unknown-runner error, validate exit
  local script=$1 runner=$2 cfg="$T/cfg.$2"
  printf 'runner %s\n' "$runner" >"$cfg"
  env -i PATH="$PATH" HOME="$T" UNCLE_CONFIG="$cfg" PROJECT_ROOT="$T" bash -c '
    source "$0"
    printf "runner=%s\n" "$(uncle_stage_runner implementation)"
    uncle_unsupported_runner "$1" 2>&1; echo "unsupported_rc=$?"
    uncle_validate_config_runners "$2" 2>&1; echo "validate_rc=$?"
  ' "$script" "$runner" "$cfg" 2>&1
}
for r in claude codex kimi self-hosted opencode aider cline bogus; do
  old=$(probe "$T/oldlib/stage-config.sh" "$r"); new=$(probe "$ROOT/scripts/lib/stage-config.sh" "$r")
  if [ "$old" = "$new" ]; then echo "PASS existing/unknown runner '$r' output identical"
  else echo "FAIL runner '$r' changed"; diff <(echo "$old") <(echo "$new"); fails=$((fails+1)); fi
done
new=$(probe "$ROOT/scripts/lib/stage-config.sh" aws-bedrock)
case "$new" in *"runner=self-hosted"*"validate_rc=0"*) echo "PASS aws-bedrock dispatches via self-hosted and validates" ;;
  *) echo "FAIL aws-bedrock dispatch: $new"; fails=$((fails+1)) ;; esac
old=$(probe "$T/oldlib/stage-config.sh" aws-bedrock)
case "$old" in *"validate_rc=0"*) echo "FAIL baseline unexpectedly accepts aws-bedrock"; fails=$((fails+1)) ;; *) echo "PASS baseline rejects aws-bedrock (test distinguishes the change)" ;; esac
[ "$fails" -eq 0 ]

#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/gates.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
mkdir -p .uncle/workspace/logs
LOG_DIR="$PWD/.uncle/workspace/logs"
printf 'requirements' > REQUIREMENTS.md
printf 'plan' > PROJECT_PLAN.md
printf 'original review' > ADVERSARIAL_REVIEW.md
printf 'Review the plan\n# Compact output budgets (binding)\n6000 bytes\n# Reviewer output\nReturn review\n' > "$LOG_DIR/prompt"
review_key() { review_input_key ADVERSARIAL_REVIEW.md "$LOG_DIR/prompt" /bin/echo model high adversarial-review; }
key=$(review_key)
[[ ${#key} == 64 ]]
save_plan_review ADVERSARIAL_REVIEW.md "$key"
rm ADVERSARIAL_REVIEW.md
restore_plan_review ADVERSARIAL_REVIEW.md "$(review_key)"
[[ $(cat ADVERSARIAL_REVIEW.md) == 'original review' ]]
# Budget increases and workflow log/state writes do not force another review.
sed 's/6000/12000/' "$LOG_DIR/prompt" > "$LOG_DIR/next"
mv "$LOG_DIR/next" "$LOG_DIR/prompt"
printf 'WAIT_APPROVAL' > .uncle/workspace/state
printf 'log output' > "$LOG_DIR/trace"
[[ $(review_key) == "$key" ]]
# Every local source addition/edit/deletion changes the snapshot.
printf 'new code' > source.py
[[ $(review_key) != "$key" ]]
rm source.py
[[ $(review_key) == "$key" ]]
printf 'changed plan' > PROJECT_PLAN.md
[[ $(review_key) != "$key" ]]
if restore_plan_review ADVERSARIAL_REVIEW.md "$(review_key)"; then exit 1; fi
printf 'plan' > PROJECT_PLAN.md
# Runner/model/env and actual review instructions invalidate reuse.
[[ $(review_input_key ADVERSARIAL_REVIEW.md "$LOG_DIR/prompt" /bin/echo other high adversarial-review) != "$key" ]]
[[ $(WORKFLOW_KIMI_MODEL=other review_key) != "$key" ]]
printf 'More review instructions\n' >> "$LOG_DIR/prompt"
[[ $(review_key) != "$key" ]]
# Do not overwrite a human-edited review with an older cached copy.
printf 'edited' > ADVERSARIAL_REVIEW.md
if restore_plan_review ADVERSARIAL_REVIEW.md "$key"; then exit 1; fi
[[ $(cat ADVERSARIAL_REVIEW.md) == edited ]]
# Later reviews/audits require fresh evidence. Opt-out and symlinks disable cache.
[[ -z $(review_input_key FINAL_AUDIT.md "$LOG_DIR/prompt" /bin/echo model high final-audit) ]]
[[ -z $(WORKFLOW_REVIEW_CACHE=0 review_key) ]]
ln -s PROJECT_PLAN.md linked
[[ -z $(review_key) ]]
echo 'review-cache-test: passed'

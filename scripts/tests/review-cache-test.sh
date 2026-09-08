#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/gates.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
mkdir -p .uncle/workflow/logs
LOG_DIR="$PWD/.uncle/workflow/logs"
printf 'requirements' > REQUIREMENTS.md
printf 'plan' > PROJECT_PLAN.md
printf 'original review' > ADVERSARIAL_REVIEW.md
printf 'Review the plan\n# Compact output budgets (binding)\n6000 bytes\n# Reviewer output\nReturn review\n' > "$LOG_DIR/prompt"
review_key() { review_input_key ADVERSARIAL_REVIEW.md "$LOG_DIR/prompt" /bin/echo model high adversarial-review; }
key=$(review_key)
[[ ${#key} == 64 ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
save_plan_review ADVERSARIAL_REVIEW.md "$key"
rm ADVERSARIAL_REVIEW.md
restore_plan_review ADVERSARIAL_REVIEW.md "$(review_key)"
[[ $(cat ADVERSARIAL_REVIEW.md) == 'original review' ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# Budget increases and workflow log/state writes do not force another review.
sed 's/6000/12000/' "$LOG_DIR/prompt" > "$LOG_DIR/next"
mv "$LOG_DIR/next" "$LOG_DIR/prompt"
printf 'WAIT_APPROVAL' > .uncle/workflow/state
printf 'log output' > "$LOG_DIR/trace"
[[ $(review_key) == "$key" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# Every local source addition/edit/deletion changes the snapshot.
printf 'new code' > source.py
[[ $(review_key) != "$key" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
rm source.py
[[ $(review_key) == "$key" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
printf 'changed plan' > PROJECT_PLAN.md
[[ $(review_key) != "$key" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
if restore_plan_review ADVERSARIAL_REVIEW.md "$(review_key)"; then exit 1; fi
printf 'plan' > PROJECT_PLAN.md
# Runner/model/env and actual review instructions invalidate reuse.
[[ $(review_input_key ADVERSARIAL_REVIEW.md "$LOG_DIR/prompt" /bin/echo other high adversarial-review) != "$key" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ $(WORKFLOW_KIMI_MODEL=other review_key) != "$key" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
printf 'More review instructions\n' >> "$LOG_DIR/prompt"
[[ $(review_key) != "$key" ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# Do not overwrite a human-edited review with an older cached copy.
printf 'edited' > ADVERSARIAL_REVIEW.md
if restore_plan_review ADVERSARIAL_REVIEW.md "$key"; then exit 1; fi
[[ $(cat ADVERSARIAL_REVIEW.md) == edited ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
# Later reviews/audits require fresh evidence. Opt-out and symlinks disable cache.
[[ -z $(review_input_key FINAL_AUDIT.md "$LOG_DIR/prompt" /bin/echo model high final-audit) ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
[[ -z $(WORKFLOW_REVIEW_CACHE=0 review_key) ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
ln -s PROJECT_PLAN.md linked
[[ -z $(review_key) ]] || { echo "FAIL $0:$LINENO" >&2; exit 1; }
echo 'review-cache-test: passed'

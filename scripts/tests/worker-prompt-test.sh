#!/usr/bin/env bash
# Panel worker prompts share a prefix: shared inputs first, per-worker text last.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILED=0; COUNT=0
check() { COUNT=$((COUNT+1)); [[ "$2" == "$3" ]] || { FAILED=$((FAILED+1)); echo "FAIL: $1: expected [$2] got [$3]"; }; }
has() { COUNT=$((COUNT+1)); [[ "$3" == *"$2"* ]] || { FAILED=$((FAILED+1)); echo "FAIL: $1: missing [$2]"; }; }

cd "$TMP"; mkdir -p .uncle/workflow/documents logs
printf '{"b":2,"a":{"y":[1,2],"x":"é"}}' > .uncle/workflow/documents/PROJECT_PLAN.json
printf '{"findings":[{"id":"AR-001"}]}' > .uncle/workflow/documents/ADVERSARIAL_REVIEW.json
base=$'You are a read-only specialist.\nReturn one JSON object.'
for lens in scope ownership; do
    printf '%s\n\n## Assigned review lens\n\nFocus only on **%s**.\n' "$base" "$lens" > "p-$lens.md"
done
printf '%s\n\n## Canonical inputs (binding)\n\nRead only `.uncle/workflow/documents/PROJECT_PLAN.json` and `.uncle/workflow/documents/ADVERSARIAL_REVIEW.json`.\n\n## Assigned review lens\n\nFocus only on **dispositions**.\n' "$base" > p-sections.md

for lens in scope ownership; do python3 -B "$HERE/../lib/worker_prompt.py" "p-$lens.md" "o-$lens.md" \
    .uncle/workflow/documents/PROJECT_PLAN.json .uncle/workflow/documents/ADVERSARIAL_REVIEW.json; done
python3 -B "$HERE/../lib/worker_prompt.py" p-sections.md o-sections.md; rc=$?
check "inputs named in the prompt's own section are used" "0" "$rc"

a="$(cat o-scope.md)"; b="$(cat o-ownership.md)"
# the longest common prefix of two workers' prompts ends where their lenses begin
common="$(python3 - o-scope.md o-ownership.md <<'PYEND'
import sys
x,y=(open(f).read() for f in sys.argv[1:3]); n=0
while n<min(len(x),len(y)) and x[n]==y[n]: n+=1
print(x[:n])
PYEND
)"
has "the shared prefix holds the plan" '"a":{"x":"é","y":[1,2]},"b":2' "$common"
has "the shared prefix holds the review" '"id":"AR-001"' "$common"
has "the shared prefix holds the contract" 'Compact worker contract (binding)' "$common"
check "the lens is not in the shared prefix" "no" "$([[ "$common" == *'**scope**'* || "$common" == *'**ownership**'* ]] && echo yes || echo no)"
has "each worker keeps its own lens" 'Focus only on **scope**' "$a"
has "each worker keeps its own lens (2)" 'Focus only on **ownership**' "$b"
check "the canonical-inputs section is dropped once embedded" "no" "$([[ "$(cat o-sections.md)" == *'Read only `.uncle'* ]] && echo yes || echo no)"
check "output is byte-stable" "$(shasum <o-scope.md)" "$(python3 -B "$HERE/../lib/worker_prompt.py" p-scope.md o-again.md .uncle/workflow/documents/PROJECT_PLAN.json .uncle/workflow/documents/ADVERSARIAL_REVIEW.json; shasum <o-again.md)"

# fallbacks leave the prompt as it was
printf 'no lens heading here\n' > p-nolens.md
python3 -B "$HERE/../lib/worker_prompt.py" p-nolens.md o-x.md a.json >/dev/null 2>&1; check "no lens heading falls back" "3" "$?"
python3 -B "$HERE/../lib/worker_prompt.py" p-scope.md o-x.md missing.json >/dev/null 2>&1; check "a missing input falls back" "3" "$?"
python3 -B "$HERE/../lib/worker_prompt.py" p-scope.md o-x.md >/dev/null 2>&1; check "no inputs falls back" "3" "$?"
python3 -c "print('{\"x\":\"' + 'a'*200000 + '\"}')" > big.json
python3 -B "$HERE/../lib/worker_prompt.py" p-scope.md o-x.md big.json >/dev/null 2>&1; check "an oversized input falls back" "3" "$?"

# manual-checklist shape: its own "checklist lens" heading, and an inputs section that also
# carries rules the worker must keep
printf '%s\n\n## Canonical inputs (binding)\n\nRead only these canonical JSON artifacts: `.uncle/workflow/documents/PROJECT_PLAN.json`, and `.uncle/workflow/documents/ADVERSARIAL_REVIEW.json`. Do not inspect any rendered Markdown view or enumerate directories.\n\nNever require Git history, commits, or a prior revision.\n\n## Assigned checklist lens\n\nFocus only on **coverage**. Use IDs only in MC-100 through MC-199.\n' "$base" > p-mc.md
python3 -B "$HERE/../lib/worker_prompt.py" p-mc.md o-mc.md; check "a checklist-lens prompt is laid out" "0" "$?"
mc="$(cat o-mc.md)"
has "the checklist lens stays at the end" 'Focus only on **coverage**' "$mc"
has "rules in the inputs section are kept" 'Never require Git history, commits, or a prior revision.' "$mc"
check "the read-these-files sentence is gone" "no" "$([[ "$mc" == *'Read only these canonical'* ]] && echo yes || echo no)"
check "the kept rules come before the lens" "yes" "$(python3 -c "
import sys
t=open('o-mc.md').read()
print('yes' if t.index('Never require Git history') < t.index('## Assigned checklist lens') else 'no')")"
check "paths with dots in them parse as inputs" "yes" "$([[ "$mc" == *'### `.uncle/workflow/documents/ADVERSARIAL_REVIEW.json`'* ]] && echo yes || echo no)"

# test-review shape: markdown inputs passed as arguments, "acceptance-gate row" heading
printf 'requirements text\n' > REQUIREMENTS.md; printf '# Report\nrows\n' > AUTO.md
printf '%s\n\n## Assigned acceptance-gate row\n\nFocus only on **coverage**.\n' "$base" > p-tr.md
printf '%s\n\n## Assigned acceptance-gate rows\n\nFocus only on **ORACLE**.\n' "$base" > p-tr2.md
python3 -B "$HERE/../lib/worker_prompt.py" p-tr.md o-tr.md REQUIREMENTS.md AUTO.md; check "markdown inputs are embedded" "0" "$?"
python3 -B "$HERE/../lib/worker_prompt.py" p-tr2.md o-tr2.md REQUIREMENTS.md AUTO.md
has "markdown is embedded as written" 'requirements text' "$(cat o-tr.md)"
check "test-review workers share everything before their row" "yes" "$(python3 -c "
x,y=(open(f).read() for f in ('o-tr.md','o-tr2.md')); n=0
while n<min(len(x),len(y)) and x[n]==y[n]: n+=1
print('yes' if 'requirements text' in x[:n] and '# Report' in x[:n] and 'Focus only' not in x[:n] else 'no')")"


# implementation steps: implement.md first, the four input documents, then only the step's own text
printf 'You are the primary implementation agent.\n\nRead these in one parallel batch of tool calls:\n\n- REQUIREMENTS.md\n' > IMPL.md
printf 'requirements text\n' > REQUIREMENTS.md
mkdir -p .uncle/docs; printf '# Interpretation\nassumptions\n' > .uncle/docs/REQUIREMENTS_INTERPRETATION.md
printf '# Plan\n## 12. Implementation order\n1. Core. Owns: `a.js`.\n' > .uncle/docs/UPDATED_PROJECT_PLAN.md
for n in 1 2; do
    { cat IMPL.md; printf '\n## Assigned isolated implementation step %s\n\nStep %s text. Owns: `f%s.js`.\n\n## Isolated ownership boundary (binding)\n\nStay in your files.\n' "$n" "$n" "$n"; } > "step-$n.md"
    python3 -B "$HERE/../lib/worker_prompt.py" --contract implementation "step-$n.md" "step-$n.shared" REQUIREMENTS.md .uncle/docs/REQUIREMENTS_INTERPRETATION.md .uncle/docs/UPDATED_PROJECT_PLAN.md
    check "implementation step $n is laid out" "0" "$?"
done
check "steps share everything up to their own heading" "yes" "$(python3 -c "
x,y=(open('step-%d.shared'%i).read() for i in (1,2)); n=0
while n<min(len(x),len(y)) and x[n]==y[n]: n+=1
shared=x[:n]
ok=all(t in shared for t in ('primary implementation agent','requirements text','# Interpretation','## 12. Implementation order','Shared inputs are embedded')) and 'step 1' not in shared.lower().replace('implementation step','')
print('yes' if ok else 'no')")"
has "step text stays after the shared part" 'Step 1 text. Owns: `f1.js`.' "$(cat step-1.shared)"
has "the ownership boundary stays with the step" 'Stay in your files.' "$(cat step-2.shared)"
check "implementation contract lets the worker read other files" "yes" "$([[ "$(cat step-1.shared)" == *'Read any other project file your'* ]] && echo yes || echo no)"
check "implementation contract does not forbid tool use" "no" "$([[ "$(cat step-1.shared)" == *'exploratory tool calls'* ]] && echo yes || echo no)"
python3 -B "$HERE/../lib/worker_prompt.py" --contract nonsense step-1.md o.md REQUIREMENTS.md >/dev/null 2>&1; check "an unknown contract is refused" "1" "$?"


# through gated_prompt: a worker log name takes the new layout, others are untouched
export STATE_DIR="$TMP/.uncle/workflow"; LOG_DIR="$TMP/logs"; ROOT="$HERE/../.."
. "$HERE/../lib/gates.sh" 2>/dev/null
out="$(gated_prompt p-scope.md updated-plan-review-worker-scope reviewer 2>/dev/null)"
has "gated_prompt embeds the shared inputs for a worker" 'Shared inputs (read-only, embedded)' "$(cat "$out" 2>/dev/null)"

# gated_prompt supplies the evidence set for the panels whose prompts name none
mkdir -p .uncle/docs
printf '{"schema":"uncle.artifact/v1","kind":"acceptance-report","rows":[{"id":"MC-1"}]}' > .uncle/workflow/documents/VERIFICATION_REPORT.json
printf '| PASS | npm test |\n' > .uncle/workflow/green-check.md
printf 'defect list\n' > .uncle/docs/DEFECTS.md
printf '%s\n\n## Assigned audit lens\n\nFocus only on **verification**.\n' "$base" > p-fa.md
out="$(gated_prompt p-fa.md final-audit-review-worker-verification reviewer 2>/dev/null)"
has "final-audit workers get the verification report embedded" '"id":"MC-1"' "$(cat "$out")"
has "final-audit workers get the green check embedded" '| PASS | npm test |' "$(cat "$out")"
has "final-audit workers get the defects embedded" 'defect list' "$(cat "$out")"
check "final-audit worker prompts end with the lens" "yes" "$([[ "$(tail -n 3 "$out")" == *'Focus only on **verification**'* ]] && echo yes || echo no)"
printf '# plan\n' > .uncle/docs/UPDATED_PROJECT_PLAN.md
printf '%s\n\n## Assigned acceptance-gate row\n\nFocus only on **coverage**.\n' "$base" > p-tr3.md
out="$(gated_prompt p-tr3.md test-review-worker-coverage reviewer 2>/dev/null)"
has "test-review workers get requirements, plan and green check embedded" '# plan' "$(cat "$out")"
has "test-review workers get the requirements" 'requirements text' "$(cat "$out")"
# a worker with nothing to embed keeps the old layout
printf '%s\n\n## Assigned audit lens\n\nFocus only on **x**.\n' "$base" > p-none.md
( cd "$(mktemp -d)" && STATE_DIR=.uncle/workflow LOG_DIR="$TMP/logs" . "$HERE/../lib/gates.sh" 2>/dev/null; out="$(gated_prompt "$TMP/p-none.md" final-audit-review-worker-verification reviewer 2>/dev/null)"; grep -q 'Shared inputs' "$out" && echo embedded || echo old ) > "$TMP/none.txt"
check "no evidence on disk keeps the old layout" "old" "$(cat "$TMP/none.txt")"


if [[ "$FAILED" -ne 0 ]]; then echo "worker-prompt-test.sh: $FAILED of $COUNT checks failed"; exit 1; fi
echo "worker-prompt-test.sh: $COUNT checks passed"

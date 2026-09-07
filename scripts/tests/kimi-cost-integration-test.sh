#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/kimi" <<'STUB'
#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
session=Path(os.environ['WORKFLOW_KIMI_SESSIONS_DIR'])/'workspace/new-session'
wire=session/'agents/main/wire.jsonl';wire.parent.mkdir(parents=True)
(session/'state.json').write_text(json.dumps({'cwd':os.getcwd()}))
prompt=sys.argv[sys.argv.index('-p')+1]
rows=[dict(type='turn.prompt',input=[dict(type='text',text=prompt)]),
      dict(type='usage.record',usageScope='turn',model='moonshot-ai/kimi-k2.7-code-highspeed',
           usage=dict(inputOther=1000,output=10,inputCacheRead=1000,inputCacheCreation=0))]
wire.write_text('\n'.join(map(json.dumps,rows)))
print(json.dumps({'role':'assistant','content':'fixture output'}))
STUB
chmod +x "$tmp/kimi"
export WORKFLOW_KIMI_SESSIONS_DIR="$tmp/sessions"
export WORKFLOW_KIMI_CMD="$tmp/kimi"
export UNCLE_STATUS_FILE="$tmp/status.jsonl"
export UNCLE_STATUS_STAGE=implementation
printf 'unique fixture prompt' | bash "$ROOT/scripts/agent-kimi.sh" --model kimi > "$tmp/result"
jq -s -e 'last | .usage.input_tokens == 1000 and .total_cost_usd == null' "$tmp/result" > /dev/null
. "$ROOT/scripts/lib/performance.sh"
STATE_DIR="$tmp/workspace"
perf_record agent implementation 1 0 "$tmp/result" "$WORKFLOW_KIMI_CMD" kimi high
python3 - "$STATE_DIR/metrics" <<'PY'
import json,sys
from pathlib import Path
row=json.loads(next(Path(sys.argv[1]).glob('*.json')).read_text())
assert row['cost_status']=='estimated'
assert abs(row['estimated_cost_usd']-.00236)<1e-10
assert row['cache_read_tokens']==1000
assert row['usage_source'].endswith('/new-session')
PY
jq -s -e 'last | .event == "usage" and .stage == "implementation" and .total_tokens == 2010' "$UNCLE_STATUS_FILE" > /dev/null
echo 'kimi-cost-integration-test: passed'

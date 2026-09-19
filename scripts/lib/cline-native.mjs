// Native Cline session bridge. JSON lines are private to the stage adapter.
import { pathToFileURL } from 'node:url';
import { createInterface } from 'node:readline';
const { ClineCore, getClineDefaultSystemPrompt } = await import(pathToFileURL(process.argv[2]).href);
const out = value => process.stdout.write(JSON.stringify(value) + '\n');
const host = await ClineCore.create({ clientName: 'uncle', backendMode: 'local' });
let session;
let sessionConfig;
host.subscribe(e => {
  if (e.type === 'agent_event' && (!session || e.payload.sessionId === session))
    out({method:'agent_event',params:e.payload.event});
});
const transientTransportError = text =>
  /ERR_HTTP2_STREAM_ERROR|NGHTTP2_INTERNAL_ERROR|ERR_HTTP2_GOAWAY_SESSION|ECONNRESET|UND_ERR_SOCKET/i.test(text);
const iterationLimit = result =>
  /max(?:imum)?(?:Iterations| iterations)|iteration limit/i.test(String(result?.text || result?.error?.message || result?.error || ''));

async function startSession() {
  const started = await host.start({config:sessionConfig,interactive:true});
  session = started.sessionId;
  return session;
}

async function sendStage(prompt, iterationRetries = 1) {
    let result;
  for (let attempt = 0; attempt <= 2; attempt++) {
    try {
      result = await host.send({sessionId:session, prompt});
    } catch (error) {
      result = {finishReason:'error', text:String(error.message || error)};
    }
    if (!result || result.finishReason === 'completed') break;
    const detail = String(result.text || result.error?.message || result.error || '');
    if (attempt === 2 || result.finishReason !== 'error' || !transientTransportError(detail)) break;
    out({method:'agent_event',params:{type:'content_end',contentType:'text',
      text:`Cline transport disconnected. Continuing the same session (retry ${attempt + 1}/2).`}});
    // The session keeps the conversation, tool results, model and filesystem.
    // Never replay the original request as a new stage or reset its approvals.
    prompt = 'The previous response stream disconnected. Continue the current stage ' +
      'from its existing conversation and current files, honoring all user steering. ' +
      'Check completed work and tool results before proceeding; do not repeat completed ' +
      'side effects. Keep the same task, permissions, approval requirements, and output ' +
      'contract. Resume unfinished work and return the required final response.';
    }
    // Some Cline backends impose a hard per-session iteration ceiling below
    // the stage's requested maxIterations. Continue once in a fresh session:
    // the workspace retains completed edits, while the follow-up explicitly
    // forbids replaying the original request. A second limit remains a real
    // failure instead of silently allowing an unbounded loop.
    if (result && iterationRetries > 0 && iterationLimit(result)) {
      try {
        await startSession();
        out({method:'agent_event',params:{type:'content_end',contentType:'text',
          text:'Cline reached its per-session iteration limit. Continuing once in a fresh session from the files already on disk.'}});
        result = await sendStage('The previous session reached its iteration limit. Continue the current stage from the files already on disk. Read the existing handoff and completed work before acting; do not replay the original request and do not repeat completed side effects. Do not broaden the task or investigate unrelated failures. Finish only the remaining required work and return the required final response.', iterationRetries - 1);
      } catch (error) {
        result = {finishReason:'error', text:String(error.message || error)};
      }
    }
    if (result && host.getAccumulatedUsage) {
    try {
      const totals = await host.getAccumulatedUsage(session);
      if (totals?.aggregateUsage || totals?.usage) result.usage = totals.aggregateUsage || totals.usage;
    } catch (error) {
      out({method:'agent_event',params:{type:'error',message:'Cline usage totals unavailable: ' + String(error.message || error)}});
    }
  }
  return result || {finishReason:'completed'};
}

const input = createInterface({input:process.stdin});
input.on('line', async line => {
  let request;
  try {
    request = JSON.parse(line);
    const p=request.params;
    if (request.method === 'start') {
      sessionConfig={providerId:'cline',modelId:p.model,cwd:p.cwd,workspaceRoot:p.cwd,
        mode:p.mode,systemPrompt:getClineDefaultSystemPrompt({workspaceRoot:p.cwd,providerId:'cline'}),
        enableTools:true,enableSpawnAgent:true,enableAgentTeams:false,yolo:p.mode==='act',
        reasoningEffort:p.effort,maxIterations:p.turns};
      await startSession();
      out({method:'ready',params:{sessionId:session}});
      const result=await sendStage(p.prompt);
      out({id:request.id,result});
    } else if (request.method === 'steer') {
      if (!session) throw new Error('No active session');
      await host.send({sessionId:session,prompt:p.text,delivery:'steer'});
      out({id:request.id,result:{status:'steered'}});
    }
  } catch(error) {
    out({id:request?.id,error:{message:String(error.message || error)}});
  }
});
input.on('close', async () => { await host.dispose(); });

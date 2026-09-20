// Native Cline session bridge. JSON lines are private to the stage adapter.
import { pathToFileURL } from 'node:url';
import { createInterface } from 'node:readline';
const { ClineCore, getClineDefaultSystemPrompt } = await import(pathToFileURL(process.argv[2]).href);
const out = value => process.stdout.write(JSON.stringify(value) + '\n');
const host = await ClineCore.create({ clientName: 'uncle', backendMode: 'local' });
let session;
host.subscribe(e => {
  if (e.type === 'agent_event' && (!session || e.payload.sessionId === session))
    out({method:'agent_event',params:e.payload.event});
});
const transientTransportError = text =>
  /ERR_HTTP2_STREAM_ERROR|NGHTTP2_INTERNAL_ERROR|ERR_HTTP2_GOAWAY_SESSION|ECONNRESET|UND_ERR_SOCKET/i.test(text);

async function sendStage(prompt) {
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
      const config={providerId:'cline',modelId:p.model,cwd:p.cwd,workspaceRoot:p.cwd,
        mode:p.mode,systemPrompt:getClineDefaultSystemPrompt({workspaceRoot:p.cwd,providerId:'cline'}),
        enableTools:true,enableSpawnAgent:true,enableAgentTeams:false,yolo:p.mode==='act',
        reasoningEffort:p.effort,maxIterations:p.turns};
      const started=await host.start({config,interactive:true});
      session=started.sessionId;
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

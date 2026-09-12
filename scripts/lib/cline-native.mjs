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
      const result=await host.send({sessionId:session,prompt:p.prompt});
      if (result && host.getAccumulatedUsage) {
        const totals=await host.getAccumulatedUsage(session);
        if (totals?.aggregateUsage || totals?.usage) result.usage=totals.aggregateUsage || totals.usage;
      }
      out({id:request.id,result:result || {finishReason:'completed'}});
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

import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, cp, readFile, writeFile, realpath, mkdtemp } from 'node:fs/promises'
import { join } from 'node:path'
import http from 'node:http'

const staged = process.argv[2]
assert.ok(staged, 'pass the staged config directory')
const largeLiteral=process.env.LARGE_LITERAL_CASE==='1'
const root = await realpath(await mkdtemp('/Users/mymac/splash/slash/tmp/opencode/iq3-live-helper-recovery-20261030-'))
const configDir = join(root, 'config/opencode'), project = join(root, 'project')
await mkdir(join(configDir, 'plugins'), { recursive: true })
await mkdir(join(project, 'tmp/opencode'), { recursive: true })
for (const name of ['tool-failure-recovery.ts', 'lib']) await cp(join(staged, 'plugins', name), join(configDir, 'plugins', name), { recursive: true })
try { await cp(join(staged,'plugins/zzzzz-bonsai-no-thinking.ts'), join(configDir, 'plugins/zzzzz-bonsai-no-thinking.ts')) }
catch (error) { if(error.code!=='ENOENT')throw error;await cp('/Users/mymac/.config/opencode/plugins/zzzzz-bonsai-no-thinking.ts', join(configDir, 'plugins/zzzzz-bonsai-no-thinking.ts')) }
const target = join(project, 'elements.cjs')
const helper = join(project, 'tmp/opencode/add-element-data.cjs')
const baseline = 'const elements = [\n' + Array.from({ length: 118 }, (_, i) => `  { z: ${i + 1}, s: "E${i + 1}", original: "keep-${i + 1}" },`).join('\n') + '\n];\nmodule.exports = elements;\n'
await writeFile(target, baseline)
await writeFile(join(project, 'check.cjs'), `const assert=require('node:assert/strict');const data=require('./elements.cjs');assert.equal(data.length,118);data.forEach((e,i)=>{assert.equal(e.z,i+1);assert.equal(e.s,'E'+(i+1));assert.equal(e.original,'keep-'+(i+1));assert.equal(e.audit,true);assert.deepEqual(Object.keys(e).sort(),['audit','original','s','z']);});console.log('PASS all 118 elements enriched; original values preserved');\n`)
if(largeLiteral) await writeFile(join(project,'check.cjs'),String.raw`const assert=require('node:assert/strict'),fs=require('node:fs');const data=require('./elements.cjs');assert.equal(data.length,118);data.forEach((e,i)=>{const z=i+1;assert.equal(e.z,z);assert.equal(e.s,'E'+z);assert.equal(e.original,'keep-'+z);assert.equal(e.audit,true);assert.equal(e.ec,'cfg-'+z+'-aa-bb-cc-dd');assert.equal(e.en,(z%10)/10);assert.equal(e.ar,100+z);assert.equal(e.ie,z+0.5);assert.equal(e.ox,'+1,-1');assert.deepEqual(Object.keys(e).sort(),['ar','audit','ec','en','ie','original','ox','s','z']);});const helper=fs.readFileSync('tmp/opencode/add-element-data.cjs','utf8');const ids=[...helper.matchAll(/^\s*["']?(\d+)["']?\s*:\s*\{/gm)].map(m=>+m[1]);assert.deepEqual([...new Set(ids)].sort((a,b)=>a-b),Array.from({length:118},(_,i)=>i+1),'helper must contain all 118 literal data keys');console.log('PASS all 118 elements enriched; original values preserved');`+'\n')
const originalChecker=await readFile(join(project,'check.cjs'),'utf8')
const original = JSON.parse(await readFile('/Users/mymac/.config/opencode/opencode.json', 'utf8'))
const model = 'qwen3.6-35b-a3b-iq3-xxs-splash'
let count = 0, workerCalls = 0, actualCalls = 0
const requests = [], responses = []
const server = http.createServer(async (req, res) => {
  try {
    if(req.method==='GET'&&req.url==='/v1/models'){
      const upstream=await fetch('http://127.0.0.1:1235/v1/models')
      const data=await upstream.text()
      await writeFile(join(root,'serving-models.json'),data)
      res.writeHead(upstream.status,{'content-type':'application/json'});res.end(data);return
    }
    let raw = ''; for await (const part of req) raw += part
    const body = JSON.parse(raw), n = ++count
    requests.push(body)
    await writeFile(join(root, `request-${n}.json`), JSON.stringify(body, null, 2))
    const worker = body.response_format?.type === 'json_schema' || Array.isArray(body.tools) && body.tools.length > 0
    const step = worker ? ++workerCalls : 0
    if (!worker || step <= 2) {
      const tool = step === 1 ? 'read' : 'write'
      const input = step === 1 ? JSON.stringify({ path: target, offset: 1, limit: 125 }) : JSON.stringify({ path: helper, content: baseline.slice(0, 200) }).slice(0, 7732)
      const delta = worker ? { tool_calls: [{ index: 0, id: `call-injected-${n}`, type: 'function', function: { name: tool, arguments: input } }] } : {role:'assistant',content:'Recovery canary'}
      const payload = { id: `injected-${n}`, object: 'chat.completion.chunk', created: 1, model, choices: [{ index: 0, delta, finish_reason: worker ? (step === 1 ? 'tool_calls' : 'length') : 'stop' }] }
      res.writeHead(200, { 'content-type': 'text/event-stream' })
      res.end(`data: ${JSON.stringify(payload)}\n\ndata: [DONE]\n\n`)
      return
    }
    actualCalls++
    if (actualCalls > 18) { res.writeHead(429, {'content-type':'application/json'}); res.end(JSON.stringify({error:{message:'Canary exceeded 18 actual requests; stopped'}})); return }
    const abort = new AbortController()
    const timer = setTimeout(() => abort.abort(), largeLiteral?600000:90000)
    try {
      const upstream = await fetch('http://127.0.0.1:1235/v1/chat/completions', { method: 'POST', headers: {'content-type':'application/json'}, body: largeLiteral ? JSON.stringify({...JSON.parse(raw), max_tokens: 12288}) : raw, signal: abort.signal })
      const data = await upstream.text()
      await writeFile(join(root, `response-${n}.txt`), data)
      responses.push({ request: n, status: upstream.status, bytes: data.length })
      res.writeHead(upstream.status, { 'content-type': upstream.headers.get('content-type') ?? 'application/json' })
      res.end(data)
    } finally { clearTimeout(timer) }
  } catch (error) { res.writeHead(502, {'content-type':'application/json'}); res.end(JSON.stringify({error:{message:String(error)}})) }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const config = {
  model: `local-llama/${model}`, small_model: `local-llama/${model}`, default_agent: 'general_worker',
  enabled_providers: ['local-llama'], compaction: { auto: false },
  permission: { '*': 'allow', external_directory: { '*': 'deny' } },
  provider: {'local-llama': {npm:'@ai-sdk/openai-compatible',options:{baseURL:`http://127.0.0.1:${server.address().port}/v1`},models:{[model]:{name:model,limit:original.provider['local-llama'].models[model].limit}}}},
  agent: {general_worker: {...original.agent.general_worker,mode:'all',model:`local-llama/${model}`,prompt:'Complete the assigned helper creation, execution, and required check. Use actual tools. Prefer concise transformations reusing existing source over reproducing arrays. Keep original values. Honor recovery tool schemas. Preserve user-required verification commands verbatim, including arguments and working directory; do not substitute an inline check. Return DONE only after both required commands pass; otherwise PARTIAL with evidence.'}}
}
await writeFile(join(configDir, 'opencode.json'), JSON.stringify(config, null, 2))
let message = `OBJECTIVE: Add audit:true to every object in the existing 118-element array in ${target}, preserving all original fields and all 118 objects. You MUST create a JavaScript helper at ${helper}, then run it to perform the edit safely. Do not reproduce the array or edit source directly. A concise helper can require('../../elements.cjs'), add audit:true to the loaded objects, and serialize them back to elements.cjs. Create a complete tiny script, or bootstrap it then append complete small sections. Use write to create the nonexistent helper; edit requires an existing nonempty matching anchor. REQUIRED COMMANDS from ${project}: node tmp/opencode/add-element-data.cjs, then node check.cjs. Both must exit0 before DONE. OUT OF SCOPE: editing check.cjs or external paths. The first two worker responses are fixtures: a source read followed by one injected incomplete helper write. Recover and finish the task with actual tools.`
if(largeLiteral) message+=` This is a synthetic large-payload regression: also add five supplied fields to each record z: ec='cfg-'+z+'-aa-bb-cc-dd', en=(z%10)/10, ar=100+z, ie=z+0.5, ox='+1,-1'. The helper MUST contain a literal const data={1:{ec:...,en:...,ar:...,ie:...,ox:...}, ...118:{...}} with one explicit numeric-key entry per line, all 118 entries, no omitted placeholders and no runtime generation of the lookup table. Then apply that lookup to the loaded original objects and set audit:true. Preserve existing fields. The literal requirement intentionally reproduces a legitimate helper payload larger than 4096 output tokens. Write this entire complete helper in the first correction write if the recovery grants enough output headroom. Use this exact deterministic supplied data; no research or factual chemistry claims are involved.`
const child = spawn('/opt/homebrew/bin/opencode', ['run','--standalone','--format','json','--agent','general_worker', message], {
  cwd: project, env: {...process.env,PWD:project,XDG_CONFIG_HOME:join(root,'config'),XDG_DATA_HOME:join(root,'data'),XDG_STATE_HOME:join(root,'state'),XDG_CACHE_HOME:join(root,'cache'),OPENCODE_CONFIG_DIR:configDir,OPENCODE_CONFIG:join(configDir,'opencode.json'),OPENCODE_DB:join(root,'test.db'),OPENCODE_PERFORMANCE_DIAGNOSTIC:'1',OPENCODE_PROGRESS_TEST_DIR:join(root,'progress'),OPENCODE_DISABLE_MODELS_FETCH:'true'},stdio:['ignore','pipe','pipe']
})
let stdout='',stderr=''
child.stdout.on('data',x=>{stdout+=x})
child.stderr.on('data',x=>{stderr+=x})
const timer=setTimeout(()=>child.kill('SIGTERM'),largeLiteral?900000:360000)
try {
  const code=await new Promise(resolve=>child.on('exit',resolve))
  clearTimeout(timer)
  await writeFile(join(root,'stdout.jsonl'),stdout)
  await writeFile(join(root,'stderr.log'),stderr)
  let checkerOutput='',checkerCode
  const checker=spawn(process.execPath,['check.cjs'],{cwd:project,stdio:['ignore','pipe','pipe']})
  checker.stdout.on('data',x=>{checkerOutput+=x});checker.stderr.on('data',x=>{checkerOutput+=x})
  checkerCode=await new Promise(resolve=>checker.on('exit',resolve))
  const summary={root,code,count,workerCalls,actualCalls,checkerCode,checkerOutput,responses}
  await writeFile(join(root,'result.json'),JSON.stringify(summary,null,2))
  console.log(JSON.stringify(summary))
  assert.equal(code,0,stderr.slice(-1200))
  if(!largeLiteral) assert.equal(checkerCode,0,checkerOutput)
  assert.ok((await readFile(join(project,'check.cjs'),'utf8'))===originalChecker,'Worker changed the checker')
  if(!largeLiteral){assert.match(stdout,/STATUS: DONE|\bDONE\b/)}

  const events=stdout.split('\n').filter(Boolean).map(l=>JSON.parse(l))
  const succeeded=command=>events.some(e=>{
    const p=e.part,s=p?.state,input=s?.input
    const combined='node tmp/opencode/add-element-data.cjs && node check.cjs'
    return e.type==='tool_use'&&p?.tool==='shell'&&s?.status==='completed'&&s.metadata?.metadata?.exit===0&&
      (input?.command===command&&input.workdir===project||input?.command===`cd ${project} && ${command}`||input?.command===combined&&input.workdir===project||input?.command===`cd ${project} && ${combined}`)
  })
  if(!largeLiteral){
    assert.ok(succeeded('node tmp/opencode/add-element-data.cjs'),'Worker did not execute the required helper command successfully')
    assert.ok(succeeded('node check.cjs'),'Worker did not execute the required checker successfully')
  }
  assert.ok((await readFile(helper,'utf8')).length>0,'Helper was not created')
  assert.ok(!events.some(e=>e.type==='tool_use'&&e.part?.tool==='edit'&&e.part.state?.input?.oldString===''),'An empty-anchor edit escaped validation')
  assert.ok(requests.slice(2).some(p=>p.response_format?.type==='json_schema' && !p.tools && p.stream===false),'No bounded JSON response schema was sent to actual IQ3')
  assert.ok(responses.every(r=>r.status===200))
  const rawResults=await Promise.all(responses.map(async r=>JSON.parse(await readFile(join(root,`response-${r.request}.txt`),'utf8'))))
  const maximumCompletionTokens=Math.max(...rawResults.map(r=>r.usage?.completion_tokens??0))
  if(largeLiteral){
    assert.ok(maximumCompletionTokens===4096,'Large-payload case never hit the 4096-token ceiling')
    assert.ok(requests.some(r=>r.max_tokens===12288),'No guarded 12288-token grant reached the serving request')
  }
  await writeFile(join(root,'result.json'),JSON.stringify({...summary,helper,largeLiteral,maximumCompletionTokens,requiredHelperExecuted:true,requiredCheckerExecuted:true,noEmptyAnchorEdit:true},null,2))
} finally {
  clearTimeout(timer)
  if(child.exitCode==null)child.kill('SIGTERM')
  await new Promise(resolve=>server.close(resolve))
}

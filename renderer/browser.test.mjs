/** Actual browser regressions run in the trusted renderer image in CI. */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { preparePresentation, serve } from './render.mjs'
for (const allGraphs of [false,true]) test(`structured totals remain visible with ${allGraphs ? 'all' : 'first'} results diagrams`,{skip:!process.env.AUTOPOC_BROWSER_INTEGRATION},async()=>{
  const root=await mkdtemp(join(tmpdir(),'autopoc-result-graphs-'))
  let browser,server
  try {
    const data=JSON.parse(await readFile(new URL('../tests/fixtures/executive-story/complex/narrative.json',import.meta.url)))
    const plan=JSON.parse(await readFile(new URL('../tests/fixtures/executive-story/complex/scenes.json',import.meta.url)))
    const graph=JSON.parse(await readFile(new URL('../tests/fixtures/executive-story/graph.json',import.meta.url)))
    const index=data.slides.findIndex(s=>s.section==='results')
    data.slides[index].graph=graph;data.slides[index].graph_claim_ids=['claim-3']
    const extra=structuredClone(data.slides[index]);extra.id='results-more'
    if(!allGraphs){extra.graph=null;extra.graph_claim_ids=[]}
    data.slides.splice(index+1,0,extra);plan.slide_ids=data.slides.map(s=>s.id)
    await writeFile(join(root,'narrative.json'),JSON.stringify(data));await writeFile(join(root,'scenes.json'),JSON.stringify(plan));await writeFile(join(root,'versions.json'),JSON.stringify({template:3}))
    const output=join(root,'output')
    const m=await preparePresentation(root,output)
    assert.equal(m.artifacts.deck.status,'validated')
    const modules=resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || new URL('./node_modules',import.meta.url).pathname)
    const {chromium}=await import(join(modules,'playwright-chromium/index.mjs'))
    const hosted=await serve(join(output,'source/dist'));server=hosted.server
    browser=await chromium.launch({headless:true,executablePath:process.env.AUTOPOC_CHROMIUM_EXECUTABLE || undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']})
    const page=await browser.newPage({viewport:{width:1280,height:720}})
    await page.goto(`${hosted.url}/${index+1}?embedded`,{waitUntil:'networkidle'})
    const current=page.locator('.executive[data-executive-ready="true"]');await current.waitFor()
    assert.equal(await current.locator('.results').count(),1,'The first results slide must show authoritative totals even with a graph')
    for(const [status,value] of Object.entries(data.results))assert.equal(await current.locator(`.results .${status} strong`).textContent(),String(value))
    assert.equal(await current.locator('.topology-stage').count(),1)
    if(process.env.AUTOPOC_BROWSER_QA_DIR)await page.screenshot({path:join(process.env.AUTOPOC_BROWSER_QA_DIR,`results-${allGraphs?'all':'first'}-graph.png`)})
  }finally {await browser?.close();if(server)await new Promise(accept=>server.close(accept));await rm(root,{recursive:true,force:true})}
})

import { cp, mkdir, symlink } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { prepareDeck } from './render.mjs'
import { inspectScene, sceneProblems, sceneCheckTimes } from './scene-validation.mjs'
const examples=new URL('../.opencode/skills/run-poc/references/executive-story-examples/',import.meta.url)
async function stageExample(root,name){
 const path=new URL(`${name}/`,examples)
 const narrative=JSON.parse(await readFile(new URL('narrative.json',path)))
 const scenes=JSON.parse(await readFile(new URL('scenes.json',path)))
 const visuals=JSON.parse(await readFile(new URL('manifest.json',path)))
 if(name==='github-service')visuals.assets[0].caption += ' This explanatory drawing describes intended components only. It does not establish observed forwarding, health, error handling or completion of any recorded check.'
 const evidence=JSON.parse(await readFile(new URL('evidence-index.json',path)))
 const checks={schema_version:1,run_id:narrative.run_id,results:evidence.final_results.results.map(({scenario_id,scenario_name,status})=>({scenario_id,scenario_name,status}))}
 await mkdir(root,{recursive:true})
 for(const [file,value] of Object.entries({narrative,scenes,visuals,checks,versions:{template:4}}))await writeFile(join(root,`${file}.json`),JSON.stringify(value))
 if(visuals.assets.length)await cp(new URL('assets/',path),join(root,'visuals/assets'),{recursive:true})
 return {narrative,scenes,visuals,checks}
}
async function buildDeck(root, customize){
 const deck=join(root,'deck');await prepareDeck(root,deck)
 if(customize)await customize(deck)
 const modules=resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || new URL('./node_modules',import.meta.url).pathname)
 await symlink(modules,join(deck,'node_modules'),'dir')
 await new Promise((accept,reject)=>{const child=spawn(process.execPath,[join(modules,'@slidev/cli/bin/slidev.mjs'),'build','slides.md','--out','dist'],{cwd:deck});let log='';child.stdout.on('data',d=>log+=d);child.stderr.on('data',d=>log+=d);child.on('exit',code=>code?reject(new Error(log)):accept())})
 return deck
}
test('pinned source captures abbreviate Git labels without changing source metadata',{skip:!process.env.AUTOPOC_BROWSER_INTEGRATION},async()=>{
 const root=await mkdtemp(join(tmpdir(),'autopoc-source-revision-'));let browser
 try{
  const modules=resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || new URL('./node_modules',import.meta.url).pathname)
  const {chromium}=await import(join(modules,'playwright-chromium/index.mjs'))
  browser=await chromium.launch({headless:true,executablePath:process.env.AUTOPOC_CHROMIUM_EXECUTABLE || undefined})
  for(const [revision,label] of [
   ['0123456789abcdef0123456789abcdef01234567','0123456789ab…'],
   ['ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789','ABCDEF012345…'],
   ['release-2026.11-reviewed','release-2026.11-reviewed'],
  ]){
   const input=join(root,revision),data=await stageExample(input,'github-service'),asset=data.visuals.assets[0]
   // Synthetic source-capture metadata exercises layout, not real project evidence.
   Object.assign(asset,{kind:'source_capture',source_revision:revision,source_url:`https://github.com/example/parcel-relay/blob/${revision}/documentation/project-overview/README.md`,caption:'Synthetic project overview from pinned documentation.',attribution:'Synthetic fixture · example/parcel-relay'})
   data.narrative.project_context.revision=revision
   await writeFile(join(input,'visuals.json'),JSON.stringify(data.visuals))
   await writeFile(join(input,'narrative.json'),JSON.stringify(data.narrative))
   const original=await readFile(join(input,'visuals.json'),'utf8'),deck=await buildDeck(input),hosted=await serve(join(deck,'dist'))
   try{
    const page=await browser.newPage({viewport:{width:1280,height:720}})
    await page.goto(`${hosted.url}/1?embedded`,{waitUntil:'networkidle'})
    const current=page.locator('.executive[data-executive-ready="true"]');await current.waitFor()
    const heading=current.locator('.project-visual figcaption strong')
    assert.equal(await heading.innerText(),`Source context · ${label}`)
    assert.equal(await heading.getAttribute('title'),revision)
    assert.equal(await heading.evaluate(element=>{const range=document.createRange();range.selectNodeContents(element);return range.getClientRects().length}),1,'The source label must fit on one line')
    assert.deepEqual(sceneProblems(await page.evaluate(inspectScene)),[],'Pinned README metadata must fit the first slide')
    assert.equal(await current.locator('.project-visual figcaption small').last().innerText(),asset.source_url)
    assert.ok((await current.locator('.source-card').innerText()).includes(`Revision: ${revision}`))
    assert.deepEqual(JSON.parse(await readFile(join(deck,'visuals.json'),'utf8')),data.visuals)
    assert.equal(await readFile(join(input,'visuals.json'),'utf8'),original)
    await page.close()
   }finally{await new Promise(r=>hosted.server.close(r))}
  }
 }finally{await browser?.close();await rm(root,{recursive:true,force:true})}
})
test('generic layouts define projects, show provenance and all checks in browser and print',{skip:!process.env.AUTOPOC_BROWSER_INTEGRATION},async()=>{
 const root=await mkdtemp(join(tmpdir(),'autopoc-generic-'));let browser
 try{
 const modules=resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || new URL('./node_modules',import.meta.url).pathname)
 const {chromium}=await import(join(modules,'playwright-chromium/index.mjs'))
 browser=await chromium.launch({headless:true,executablePath:process.env.AUTOPOC_CHROMIUM_EXECUTABLE || undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']})
 for(const name of ['github-service','gitlab-cli','codeberg-library']){
  const input=join(root,name),data=await stageExample(input,name),deck=await buildDeck(input),hosted=await serve(join(deck,'dist'))
  try{
   const page=await browser.newPage({viewport:{width:1280,height:720}})
   for(const [i,slide] of data.narrative.slides.entries()){
    await page.goto(`${hosted.url}/${i+1}?embedded`,{waitUntil:'networkidle'})
    const current=page.locator('.executive[data-executive-ready="true"]');await current.waitFor()
    assert.deepEqual(sceneProblems(await page.evaluate(inspectScene)),[],`${name} ${slide.id}`)
    if(i===0){
     const definition=data.narrative.claims.find(c=>c.id===data.narrative.project_context.definition_claim_id).text
     assert.ok((await current.innerText()).includes(definition))
     assert.ok((await current.innerText()).includes(data.narrative.project_context.repository_url))
     if(!data.narrative.project_context.revision)assert.match(await current.innerText(),/Revision unavailable/)
     if(slide.visual_id){const asset=data.visuals.assets[0];assert.equal(await current.locator('.project-visual img').evaluate(img=>img.complete&&img.naturalWidth>0),true);for(const text of [asset.caption,asset.attribution])assert.ok((await current.innerText()).includes(text))}
     else assert.equal(await current.locator('.source-card').count(),1)
    }
    if(slide.layout==='checks'){
     for(const id of slide.bullet_claim_ids)assert.ok((await current.innerText()).includes(data.narrative.claims.find(claim=>claim.id===id).text),'Separate reviewed context must stay visible with check rows')
     assert.deepEqual(await current.locator('[data-check-id]').evaluateAll(rows=>rows.map(row=>row.dataset.checkId)),slide.checks.map(row=>row.scenario_id))
     for(const row of slide.checks){const verified=data.checks.results.find(result=>result.scenario_id===row.scenario_id),element=current.locator(`[data-check-id="${row.scenario_id}"]`);assert.equal(await element.getAttribute('title'),verified.scenario_name);assert.equal(await element.locator('.check-status').innerText(),verified.status)}
     if(!slide.checks.length)assert.match(await current.innerText(),/No checks recorded/)
     else {
      const timeline={id:slide.id,start_seconds:10,duration_seconds:30,sentence_offsets:slide.narration.map((_,j)=>({start_seconds:j*2,end_seconds:j*2+1}))}
      await page.evaluate(timeline=>window.dispatchEvent(new CustomEvent('executive-clock',{detail:{scene:timeline,elapsed_seconds:10.35}})),timeline)
      assert.equal(await current.locator('.check-active').count(),1)
      await page.emulateMedia({media:'print'})
      await page.waitForFunction(()=>!document.querySelector('.check-active'))
      await page.emulateMedia({media:'screen'})
      await page.evaluate(()=>window.dispatchEvent(new CustomEvent('executive-clock',{detail:{elapsed_seconds:0}})))
      assert.equal(await current.locator('.check-active').count(),0)
      await page.evaluate(()=>window.dispatchEvent(new CustomEvent('executive-reset')))
      await current.waitFor() // Reset settles fonts/layout asynchronously before inspection.
      assert.equal(await current.locator('.check-active').count(),0)
     }
    }
    if(slide.section==='results')for(const status of ['pass','fail','error','skip','incomplete'])assert.ok((await current.innerText()).includes(status))
    if(process.env.AUTOPOC_BROWSER_QA_DIR)await page.screenshot({path:join(process.env.AUTOPOC_BROWSER_QA_DIR,`${name}-${slide.id}.png`)})
    await page.emulateMedia({media:'print'});await page.evaluate(async()=>{for(const family of ['Display','Text','Mono'])for(const weight of [400,500,700])await document.fonts.load(`${weight} 16px \"Red Hat ${family}\"`);await document.fonts.ready});assert.equal(await current.locator('.check-active').filter({visible:true}).count(),0)
    assert.deepEqual(sceneProblems(await page.evaluate(inspectScene)),[])
    if(process.env.AUTOPOC_BROWSER_QA_DIR)await page.pdf({path:join(process.env.AUTOPOC_BROWSER_QA_DIR,`${name}-${slide.id}.pdf`),width:'1280px',height:'720px',printBackground:true})
    await page.emulateMedia({media:'screen'})
   }
   await page.goto(`${hosted.url}/print?print=true`,{waitUntil:'networkidle'})
   await page.locator('.executive[data-executive-ready="true"]').first().waitFor()
   assert.equal(await page.locator('.executive[data-executive-ready="true"]').count(),data.narrative.slides.length)
   assert.equal(await page.locator('.check-active').count(),0)
   await page.pdf({path:join(process.env.AUTOPOC_BROWSER_QA_DIR || root,`${name}.pdf`),width:'1280px',height:'720px',printBackground:true})
   await page.close()
  }finally{await new Promise(r=>hosted.server.close(r))}
 }
 }finally{await browser?.close();await rm(root,{recursive:true,force:true})}
})

test('eleven checks retain five-row pagination and readable long project names',{skip:!process.env.AUTOPOC_BROWSER_INTEGRATION},async()=>{
 const root=await mkdtemp(join(tmpdir(),'autopoc-eleven-'));let browser,server
 try{
  // Structural layout fixture only; semantic/source agreement uses the worked stories above.
  const cases=JSON.parse(await readFile(new URL('../tests/fixtures/executive-story/schema3-cases.json',import.meta.url)))
  const item=cases.find(item=>item.narrative.slides.flatMap(s=>s.checks).length===11),n=item.narrative
  const checks={schema_version:1,run_id:n.run_id,results:n.slides.flatMap(s=>s.checks).map((row,i)=>({scenario_id:row.scenario_id,scenario_name:`Synthetic layout scenario ${i+1}`,status:['pass','fail','error','skip','incomplete'][i%5]}))}
  const totals=Object.fromEntries(['pass','fail','error','skip','incomplete'].map(status=>[status,checks.results.filter(r=>r.status===status).length]));n.results=totals
  n.project_name='A long project name for a reusable command line data validation library'
  const setup=n.slides.find(slide=>slide.section==='setup')
  setup.layout='topology';setup.graph=JSON.parse(await readFile(new URL('../tests/fixtures/executive-story/graph.json',import.meta.url)));setup.graph_claim_ids=setup.bullet_claim_ids
  // This synthetic topology tests generic layout dispatch only, not project evidence.
  for(const [file,value] of Object.entries({narrative:n,scenes:item.plan,checks,visuals:{schema_version:1,run_id:n.run_id,assets:[],gaps:[]},versions:{template:4}}))await writeFile(join(root,`${file}.json`),JSON.stringify(value))
  const deck=await buildDeck(root),hosted=await serve(join(deck,'dist'));server=hosted.server
  const modules=resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || new URL('./node_modules',import.meta.url).pathname),{chromium}=await import(join(modules,'playwright-chromium/index.mjs'))
  browser=await chromium.launch({headless:true,executablePath:process.env.AUTOPOC_CHROMIUM_EXECUTABLE || undefined})
  const page=await browser.newPage({viewport:{width:1280,height:720}}),seen=[]
  for(const [i,slide] of n.slides.entries()){
   await page.goto(`${hosted.url}/${i+1}?embedded`,{waitUntil:'networkidle'});const current=page.locator('.executive[data-executive-ready="true"]');await current.waitFor()
   assert.deepEqual(sceneProblems(await page.evaluate(inspectScene)),[])
   if(slide.layout==='topology')assert.equal(await current.locator('.topology-stage .tl-root').count() || await current.locator('.topology-stage .tl-canvas').count(),1)
   seen.push(...await current.locator('[data-check-id]').evaluateAll(rows=>rows.map(row=>row.dataset.checkId)))
   for(const size of await current.locator('.check-row h2').evaluateAll(rows=>rows.map(row=>parseFloat(getComputedStyle(row).fontSize))))assert.ok(size>=22)
   if(process.env.AUTOPOC_BROWSER_QA_DIR)await page.screenshot({path:join(process.env.AUTOPOC_BROWSER_QA_DIR,`eleven-${slide.id}.png`)})
  }
  assert.equal(seen.length,11);assert.equal(new Set(seen).size,11)
 }finally{await browser?.close();if(server)await new Promise(r=>server.close(r));await rm(root,{recursive:true,force:true})}
})

test('referenced PNG that fails full browser decode invalidates preparation before speech',{skip:!process.env.AUTOPOC_BROWSER_INTEGRATION},async()=>{
 const root=await mkdtemp(join(tmpdir(),'autopoc-bad-image-'))
 try{
  const {createHash}=await import('node:crypto'),data=await stageExample(root,'github-service')
  // Valid trusted signature/dimensions/hash, but deliberately truncated image payload.
  const path=join(root,'visuals/assets/context.png'),bytes=(await readFile(path)).subarray(0,33)
  await writeFile(path,bytes);data.visuals.assets[0].sha256=createHash('sha256').update(bytes).digest('hex')
  await writeFile(join(root,'visuals.json'),JSON.stringify(data.visuals))
  const diagnostics=[],original=console.error
  let manifest
  try{console.error=(...args)=>diagnostics.push(args.join(' '));manifest=await preparePresentation(root,join(root,'output'))}finally{console.error=original}
  assert.equal(diagnostics.length,1);assert.match(diagnostics[0],/image|decode|EncodingError/i)
  assert.equal(manifest.artifacts.deck.status,'failed')
  assert.equal(manifest.artifacts.pdf,undefined)
  assert.equal(manifest.status,'partial')
 }finally{await rm(root,{recursive:true,force:true})}
})

for(const mutation of ['missing-checks','missing-visuals','wrong-id','wrong-status','wrong-hash','symlink'])test(`template4 rejects staged ${mutation} before creating browser input`,async()=>{
 const root=await mkdtemp(join(tmpdir(),'autopoc-staged-'))
 try{
  const data=await stageExample(root,'github-service')
  if(mutation==='missing-checks')await rm(join(root,'checks.json'))
  if(mutation==='missing-visuals')await rm(join(root,'visuals.json'))
  if(mutation==='wrong-id')data.checks.results[0].scenario_id='unknown'
  if(mutation==='wrong-status')data.checks.results[0].status='fail'
  if(['wrong-id','wrong-status'].includes(mutation))await writeFile(join(root,'checks.json'),JSON.stringify(data.checks))
  if(mutation==='wrong-hash')await writeFile(join(root,'visuals/assets/context.png'),'changed')
  if(mutation==='symlink'){const path=join(root,'visuals/assets/context.png');await rm(path);await symlink('/etc/passwd',path)}
  await assert.rejects(prepareDeck(root,join(root,'deck')))
 }finally{await rm(root,{recursive:true,force:true})}
})

test('actual narrated check cue aligns to measured offsets after variable-frame capture',{skip:!process.env.AUTOPOC_BROWSER_INTEGRATION},async()=>{
 const root=await mkdtemp(join(tmpdir(),'autopoc-check-capture-'));let browser,server,context
 try{
  const {playMeasuredScene}=await import('./render.mjs'),{encodeCapture}=await import('./audio.mjs'),{execFileSync}=await import('node:child_process')
  const run=async(command,args,cwd)=>execFileSync(command,args,{cwd,maxBuffer:20*1024*1024}).toString()
  const data=await stageExample(root,'github-service'),deck=await buildDeck(root),hosted=await serve(join(deck,'dist'));server=hosted.server
  const modules=resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || new URL('./node_modules',import.meta.url).pathname),{chromium}=await import(join(modules,'playwright-chromium/index.mjs'))
  browser=await chromium.launch({headless:true,executablePath:process.env.AUTOPOC_CHROMIUM_EXECUTABLE || undefined})
  context=await browser.newContext({viewport:{width:1280,height:720},recordVideo:{dir:join(root,'capture'),size:{width:1280,height:720}}})
  const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));await page.goto(`${hosted.url}/2?embedded`,{waitUntil:'networkidle'})
  await page.locator('.executive[data-executive-ready="true"]').waitFor()
  const row=await page.locator('.executive[data-executive-ready="true"] .check-row').first().boundingBox()
  const slide=data.narrative.slides[1],scene={id:slide.id,start_seconds:0,duration_seconds:181/30,frame_count:181,sentence_offsets:slide.narration.map((_,i)=>({start_seconds:i*.3,end_seconds:i*.3+.2}))}
  await playMeasuredScene(page,scene,3)
  assert.deepEqual(errors,[])
  const raw=await page.video().path();await context.close();context=null
  if(process.env.AUTOPOC_BROWSER_QA_DIR)await cp(raw,join(process.env.AUTOPOC_BROWSER_QA_DIR,'measured-check-raw.webm'))
  const output=join(root,'cue.mp4');await encodeCapture(raw,scene,output,root,run,{anchor_slate:true})
  const probe=JSON.parse(await run('ffprobe',['-v','error','-show_streams','-of','json',output],root));assert.equal(Number(probe.streams[0].nb_frames),181)
  // Sample the actual rendered row border from every encoded frame, not DOM time.
  const pixels=execFileSync('ffmpeg',['-v','error','-i',output,'-vf',`crop=2:2:${Math.round(row.x+2)}:${Math.round(row.y+10)},scale=1:1`,'-f','rawvideo','-pix_fmt','rgb24','pipe:1'],{maxBuffer:1024*1024})
  const highlighted=[];for(let i=0;i<pixels.length/3;i++)if(pixels[i*3]>150 && pixels[i*3+1]<100 && pixels[i*3+2]<100)highlighted.push(i)
  const corners=execFileSync('ffmpeg',['-v','error','-i',output,'-vf','crop=2:2:2:2,scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],{maxBuffer:1024*1024})
  for(let i=0;i<corners.length;i+=3)assert.ok(!(corners[i]>180 && corners[i+1]<80 && corners[i+2]>180),'Private pre-roll slate must never appear in the encoded scene')
  assert.ok(highlighted.length>0,'Encoded video must contain the rendered row cue')
  assert.ok(Math.abs(highlighted[0]/30-.35)<=2/30,`cue starts ${highlighted[0]/30}s; measured .35s`)
  assert.ok(Math.abs((highlighted.at(-1)+1)/30-.85)<=2/30,`cue ends ${(highlighted.at(-1)+1)/30}s; measured .85s`)
  if(process.env.AUTOPOC_BROWSER_QA_DIR){await cp(output,join(process.env.AUTOPOC_BROWSER_QA_DIR,'measured-check-cue.mp4'));await writeFile(join(process.env.AUTOPOC_BROWSER_QA_DIR,'measured-check-cue.json'),JSON.stringify({frame_count:181,first_frame:highlighted[0],end_frame:highlighted.at(-1)+1,expected_start_seconds:.35,expected_end_seconds:.85}))}
 }finally{await context?.close();await browser?.close();if(server)await new Promise(r=>server.close(r));await rm(root,{recursive:true,force:true})}
})

test('production template4 preparation exports every reviewed slide to PDF',{skip:!process.env.AUTOPOC_BROWSER_INTEGRATION},async()=>{
 const root=await mkdtemp(join(tmpdir(),'autopoc-generic-pdf-'))
 try{
  const data=await stageExample(root,'github-service'),output=join(root,'output')
  const manifest=await preparePresentation(root,output)
  assert.equal(manifest.artifacts.deck.status,'validated')
  assert.equal(manifest.artifacts.pdf.status,'validated')
  const path=join(output,'executive-summary.pdf'),bytes=await readFile(path)
  const modules=resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || new URL('./node_modules',import.meta.url).pathname)
  const {PDFDocument}=await import(join(modules,'pdf-lib/cjs/index.js'))
  assert.equal((await PDFDocument.load(bytes)).getPageCount(),data.narrative.slides.length)
  if(process.env.AUTOPOC_BROWSER_QA_DIR)await cp(path,join(process.env.AUTOPOC_BROWSER_QA_DIR,'github-service-full.pdf'))
 }finally{await rm(root,{recursive:true,force:true})}
})

test('excess check context fails actionable bounds without shrinking or omitting reviewed text',{skip:!process.env.AUTOPOC_BROWSER_INTEGRATION},async()=>{
 const root=await mkdtemp(join(tmpdir(),'autopoc-check-overflow-'));let browser,server
 try{
  const data=await stageExample(root,'github-service'),slide=data.narrative.slides[1]
  slide.bullet_claim_ids=Array.from({length:4},(_,i)=>`overflow-${i}`)
  for(const id of slide.bullet_claim_ids)data.narrative.claims.push({id,text:'This deliberately verbose context describes the synthetic layout bounds and retains all reviewed words. '.repeat(2),kind:'observed',sources:['source.md#L1-L1']})
  await writeFile(join(root,'narrative.json'),JSON.stringify(data.narrative))
  const deck=await buildDeck(root),hosted=await serve(join(deck,'dist'));server=hosted.server
  const modules=resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || new URL('./node_modules',import.meta.url).pathname),{chromium}=await import(join(modules,'playwright-chromium/index.mjs'))
  browser=await chromium.launch({headless:true,executablePath:process.env.AUTOPOC_CHROMIUM_EXECUTABLE || undefined})
  const page=await browser.newPage({viewport:{width:1280,height:720}});await page.goto(`${hosted.url}/2?embedded`,{waitUntil:'networkidle'})
  const current=page.locator('.executive[data-executive-ready="true"]');await current.waitFor()
  const problems=sceneProblems(await page.evaluate(inspectScene));assert.match(problems.join(),/Layout overflow.*shorten the reviewed text/)
  assert.equal(await current.locator('.check-context li').count(),4);assert.equal(await current.locator('.check-row').count(),5)
  assert.equal(await current.locator('.check-context li').first().evaluate(el=>parseFloat(getComputedStyle(el).fontSize)),18)
  assert.equal(await current.locator('.check-row h2').first().evaluate(el=>parseFloat(getComputedStyle(el).fontSize)),22)
 }finally{await browser?.close();if(server)await new Promise(r=>server.close(r));await rm(root,{recursive:true,force:true})}
})


test('TopoLoop repaints every inspection pose on one mount and owns one cancellable loop',{skip:!process.env.AUTOPOC_BROWSER_INTEGRATION},async()=>{
 const root=await mkdtemp(join(tmpdir(),'autopoc-freeze-'));let browser,server
 try{
  await stageExample(root,'github-service')
  const graph=JSON.parse(await readFile(new URL('../tests/fixtures/executive-story/graph.json',import.meta.url)))
  graph.nodes.forEach((n,i)=>{n.sub=`Component ${i+1}`;n.anchor=i?'down':'up';n.group='recorded'})
  graph.groups=[{id:'recorded',label:'Recorded components'}]
  graph.acts=[0,1,2].map(i=>({id:i,t0:i*4,t1:(i+1)*4,title:`Inspection act ${i+1}`,path:'request',tone:['neutral','positive','negative'][i]}))
  const deck=await buildDeck(root,async deck=>{
   await writeFile(join(deck,'components/FreezeHarness.vue'),`<script setup>
import {ref,nextTick,onMounted} from 'vue'
import TopoLoop from '../vendor/topoloop/src/TopoLoop.vue'
import {redhatTheme} from './redhat-theme.ts'
const graph=${JSON.stringify(graph)}, freeze=ref(0), mounted=ref(true)
onMounted(()=>{window.freezeHarness=async(value,show=true)=>{freeze.value=value;mounted.value=show;await nextTick()}})
</script><template><div class="executive" data-executive-ready="true" style="position:absolute;inset:0"><div class="topology-stage" style="position:absolute;inset:0"><TopoLoop v-if="mounted" :spec="graph" :freeze-at="freeze" :seed="1" :theme="redhatTheme"/></div></div></template>`)
   await writeFile(join(deck,'slides.md'),'---\nlayout: none\n---\n<FreezeHarness/>\n')
  })
  const hosted=await serve(join(deck,'dist'));server=hosted.server
  const modules=resolve(process.env.AUTOPOC_RENDER_NODE_MODULES || new URL('./node_modules',import.meta.url).pathname),{chromium}=await import(join(modules,'playwright-chromium/index.mjs'))
  browser=await chromium.launch({headless:true,executablePath:process.env.AUTOPOC_CHROMIUM_EXECUTABLE || undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']})
  const page=await browser.newPage({viewport:{width:1280,height:720}})
  await page.addInitScript(()=>{const request=window.requestAnimationFrame.bind(window),cancel=window.cancelAnimationFrame.bind(window),pending=new Set();window.requestAnimationFrame=callback=>{const id=request(t=>{pending.delete(id);callback(t)});pending.add(id);return id};window.cancelAnimationFrame=id=>{pending.delete(id);cancel(id)};window.pendingFrames=pending})
  await page.goto(`${hosted.url}/1?embedded`,{waitUntil:'networkidle'});await page.waitForFunction(()=>window.freezeHarness)
  await page.evaluate(async()=>{for(const family of ['Display','Text','Mono'])for(const weight of [400,500,700])await document.fonts.load(`${weight} 16px "Red Hat ${family}"`);await document.fonts.ready})
  const errors=[];page.on('pageerror',error=>errors.push(error.message))
  await page.evaluate(()=>{window.originalCanvas=document.querySelector('.tl-canvas canvas')})
  const poses=new Map()
  for(const t of sceneCheckTimes(graph)){
   await page.evaluate(async t=>{await window.freezeHarness(t);await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))},t)
   assert.equal(await page.locator('.tl-title').innerText(),graph.acts.find(a=>t>=a.t0&&t<a.t1).title,`act at ${t}`)
   assert.equal(await page.evaluate(()=>document.querySelector('.tl-canvas canvas')===window.originalCanvas),true,'inspection must retain one mounted canvas')
   assert.deepEqual(sceneProblems(await page.evaluate(inspectScene)),[],`pose ${t}`)
   poses.set(t,await page.locator('.tl-canvas canvas').evaluate(canvas=>canvas.toDataURL()))
   if(process.env.AUTOPOC_BROWSER_QA_DIR)await page.screenshot({path:join(process.env.AUTOPOC_BROWSER_QA_DIR,`freeze-${t}.png`)})
  }
  assert.equal(new Set(poses.values()).size,poses.size,'all requested poses repaint visible geometry')
  // Use deterministic text geometry for negative collisions without relying on a lucky camera pose.
  const fixture=JSON.parse(await readFile(new URL('../tests/fixtures/executive-story/label-collisions.json',import.meta.url)))
  const diagnostics=[]
  for(const t of sceneCheckTimes(graph)){
   await page.evaluate(async t=>{await window.freezeHarness(t);await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))},t)
   for(const item of fixture){
   await page.evaluate(item=>{const root=document.querySelector('.executive'),stage=document.createElement('div');stage.className='topology-stage collision-fixture';stage.style.cssText='position:absolute;inset:0';root.append(stage);for(const [className,text,x,y,w,h] of item.labels){const el=document.createElement('div');el.className=className;el.textContent=text;el.style.cssText=`position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;font:20px/24px sans-serif`;if(item.outside?.includes(className)){el.classList.add('external-collision-fixture');root.append(el)}else stage.append(el)}},item)
   const problems=sceneProblems(await page.evaluate(inspectScene))
   if(item.error)assert.match(problems.join(),new RegExp(item.error),item.name)
   else assert.deepEqual(problems,[],item.name)
   diagnostics.push({time:t,fixture:item.name,problems})
   if(t===3 && item.error && process.env.AUTOPOC_BROWSER_QA_DIR)await page.screenshot({path:join(process.env.AUTOPOC_BROWSER_QA_DIR,`collision-${fixture.indexOf(item)}.png`)})
   await page.locator('.collision-fixture, .external-collision-fixture').evaluateAll(elements=>elements.forEach(el=>el.remove()))
   }
  }
  if(process.env.AUTOPOC_BROWSER_QA_DIR)await writeFile(join(process.env.AUTOPOC_BROWSER_QA_DIR,'collision-diagnostics.json'),JSON.stringify(diagnostics,null,2))

  const baseline=await page.evaluate(()=>window.pendingFrames.size)
  for(let i=0;i<3;i++){
   await page.evaluate(()=>window.freezeHarness(null));await page.waitForFunction(count=>window.pendingFrames.size===count,baseline+1)
   assert.equal(await page.evaluate(()=>window.pendingFrames.size),baseline+1,'release owns one animation callback')
   const released=await page.locator('.tl-canvas canvas').evaluate(canvas=>canvas.toDataURL())
   await page.waitForFunction(image=>document.querySelector('.tl-canvas canvas').toDataURL()!==image,released)
   assert.notEqual(await page.locator('.tl-canvas canvas').evaluate(canvas=>canvas.toDataURL()),released,'release resumes visible animation')
   await page.evaluate(()=>window.freezeHarness(5));await page.waitForFunction(count=>window.pendingFrames.size===count,baseline)
   assert.equal(await page.evaluate(()=>window.pendingFrames.size),baseline,'freeze cancels animation callback')
  }
  await page.evaluate(()=>window.freezeHarness(null));await page.waitForFunction(count=>window.pendingFrames.size===count,baseline+1)
  await page.evaluate(()=>window.freezeHarness(null,false));await page.waitForFunction(count=>window.pendingFrames.size===count&&!document.querySelector('.tl-canvas canvas'),baseline)
  assert.equal(await page.evaluate(()=>window.pendingFrames.size),baseline,'unmount cancels animation callback')
  assert.equal(await page.locator('canvas').count(),0);assert.deepEqual(errors,[])
 }finally{await browser?.close();if(server)await new Promise(r=>server.close(r));await rm(root,{recursive:true,force:true})}
})

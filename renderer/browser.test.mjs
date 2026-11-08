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

import test from 'node:test'
import assert from 'node:assert/strict'
import { checkWindows, activeCheck } from './check-timing.mjs'
const slide={id:'checks',checks:[{scenario_id:'a',narration_sentence_indices:[0,1]},{scenario_id:'b',narration_sentence_indices:[2]}]}
const scene={id:'checks',start_seconds:10,duration_seconds:8,sentence_offsets:[{start_seconds:0,end_seconds:1},{start_seconds:1.2,end_seconds:2},{start_seconds:2.2,end_seconds:3}]}
test('measured check windows include lead, preserve gaps, and use half-open bounds',()=>{
  const windows=checkWindows(slide,scene)
  assert.deepEqual(windows,[{scenario_id:'a',start_seconds:10.35,end_seconds:12.35},{scenario_id:'b',start_seconds:12.55,end_seconds:13.35}])
  for(const [time,id] of [[10,null],[10.35,'a'],[11.45,'a'],[12.35,null],[12.55,'b'],[13.35,null],[10.5,'a']])assert.equal(activeCheck(windows,time),id)
  assert.deepEqual(checkWindows({...slide,id:'next',checks:[]},{...scene,id:'next'}),[])
})
for(const change of [s=>delete s.sentence_offsets,s=>s.sentence_offsets[0].end_seconds=NaN,s=>s.sentence_offsets[0].start_seconds=-1,s=>s.sentence_offsets[2].end_seconds=9,s=>s.sentence_offsets[2].start_seconds=1.5,s=>s.id='wrong'])test(`reject invalid measured offsets ${change}`,()=>{const s=structuredClone(scene);change(s);assert.throws(()=>checkWindows(slide,s))})
test('reject missing mappings and overlapping check windows',()=>{
 for(const checks of [[{scenario_id:'a',narration_sentence_indices:[8]}],[...slide.checks,{scenario_id:'c',narration_sentence_indices:[2]}]])assert.throws(()=>checkWindows({...slide,checks},scene))
})

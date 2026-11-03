<script setup>
import { ref, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import { useIsSlideActive, useNav } from '@slidev/client'
import { usePreferredReducedMotion } from '@vueuse/core'
import TopoLoop from '../vendor/topoloop/src/TopoLoop.vue'
import narrative from '../narrative.json'
import scenes from '../scenes.json'

const props = defineProps({ kind: String })
const active = useIsSlideActive()
const { isPrintMode } = useNav()
const ready = ref(false)
const reducedMotion = usePreferredReducedMotion()
const generation = ref(0)
const titles = { purpose: 'Purpose and PoC objective', testing_strategy: 'Testing strategy', topology: 'Recorded setup', test_execution: 'How we tested', results: 'Validation results', platform_suitability: 'OpenShift and Kubernetes conclusions' }
const claims = computed(() => narrative[props.kind] || [])
const graph = computed(() => props.kind === 'topology' ? narrative.topology : narrative.scenario_flow)
const rate = computed(() => graph.value ? graph.value.loop / scenes.durations[props.kind === 'topology' ? 2 : 3] : 1)
const reset = async () => {
  ready.value = false
  generation.value++
  await nextTick()
  requestAnimationFrame(() => requestAnimationFrame(() => { ready.value = true }))
}
onMounted(async () => {
  await document.fonts.ready
  await nextTick()
  requestAnimationFrame(() => requestAnimationFrame(() => { ready.value = true }))
  window.addEventListener('executive-reset', reset)
})
onBeforeUnmount(() => window.removeEventListener('executive-reset', reset))
</script>

<template>
  <section class="executive" :data-executive-ready="ready && (active || isPrintMode)">
    <p class="eyebrow">AutoPoC · {{ narrative.project_name }}</p>
    <h1>{{ titles[kind] }}</h1>
    <div v-if="kind === 'topology' || (kind === 'test_execution' && graph)" class="topology-stage" :class="{ 'scenario-stage': kind === 'test_execution' }">
      <TopoLoop v-if="graph && (active || isPrintMode)" :key="generation" :spec="graph" theme="dark" :seed="1" :rate="rate" :freeze-at="isPrintMode || reducedMotion === 'reduce' ? 3 : null" />
      <div v-else class="no-graph"><h2>Topology evidence unavailable</h2><p>See the report for the recorded setup. No infrastructure has been inferred.</p></div>
    </div>
    <div v-else-if="kind === 'results'" class="results">
      <div v-for="(value, status) in narrative.results" :key="status" :class="status"><strong>{{ value }}</strong><span>{{ status }}</span></div>
    </div>
    <ul v-else class="claims"><li v-for="(claim, i) in claims" :key="i">{{ claim.text }}<small>Evidence: {{ claim.sources.join(', ') }}</small></li></ul>
    <ul v-if="kind === 'test_execution' && graph" class="flow-claims"><li v-for="(claim, i) in claims" :key="i">{{ claim.text }}<small :title="claim.sources.join(', ')">Evidence: {{ claim.sources.map(s => s.split('/').pop().slice(0,48)).slice(0,2).join(', ') }}</small></li></ul>
    <p v-if="kind === 'topology' || (kind === 'test_execution' && graph)" class="caveat">Animation illustrates archived evidence; playback timing is illustrative.</p>
    <p v-if="kind === 'results' || kind === 'platform_suitability'" class="caveat">{{ narrative.limitations.join(' · ') }}</p>
    <footer>{{ narrative.run_id }} <span>Report-based executive summary</span></footer>
  </section>
</template>

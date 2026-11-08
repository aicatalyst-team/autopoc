<script setup>
import { ref, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import { useIsSlideActive, useNav } from '@slidev/client'
import { usePreferredReducedMotion } from '@vueuse/core'
import TopoLoop from '../vendor/topoloop/src/TopoLoop.vue'
import { redhatTheme } from './redhat-theme.ts'
import { loadSceneAssets } from '../scene-validation.mjs'
import narrative from '../narrative.json'
import scenes from '../scenes.json'

const props = defineProps({ kind: String, slideId: String })
const root = ref(null)
const active = useIsSlideActive()
const { isPrintMode } = useNav()
const ready = ref(false)
const error = ref('')
const reducedMotion = usePreferredReducedMotion()
const generation = ref(0)
const validationTime = ref(null)
const kinds = ['purpose', 'testing_strategy', 'topology', 'test_execution', 'results', 'platform_suitability']
const titles = { purpose: 'Purpose and PoC objective', testing_strategy: 'Testing strategy', topology: 'Recorded setup', test_execution: 'How we tested', results: 'Validation results', platform_suitability: 'OpenShift and Kubernetes conclusions' }
const narrated = narrative.schema_version === 2
const index = computed(() => narrated ? narrative.slides.findIndex(s => s.id === props.slideId) : kinds.indexOf(props.kind))
const slide = computed(() => narrated ? narrative.slides[index.value] : null)
const section = computed(() => slide.value?.section || props.kind)
const claims = computed(() => narrated ? slide.value.bullet_claim_ids.map(id => narrative.claims.find(c => c.id === id)) : narrative[props.kind] || [])
const graph = computed(() => narrated ? slide.value.graph : props.kind === 'topology' ? narrative.topology : narrative.scenario_flow)
const graphScene = computed(() => narrated ? !!graph.value : props.kind === 'topology' || (props.kind === 'test_execution' && graph.value))
const opening = computed(() => narrated ? index.value === 0 : props.kind === 'purpose')
const corporateMark = computed(() => opening.value || section.value === (narrated ? 'recommendation' : 'platform_suitability'))
const resultsScene = computed(() => narrated ? section.value === 'results' && narrative.slides.findIndex(s => s.section === 'results') === index.value : props.kind === 'results')
const duration = ref(null)
const setDuration = event => { duration.value = event.detail }
const rate = computed(() => !graph.value ? 1 : narrated ? (duration.value ? graph.value.loop / duration.value : 1) : graph.value.loop / scenes.durations[props.kind === 'topology' ? 2 : 3])
const settle = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
const reset = async () => { ready.value = false; validationTime.value = null; generation.value++; await nextTick(); await settle(); ready.value = true }
const still = async event => { ready.value = false; validationTime.value = event.detail; await nextTick(); await settle(); ready.value = true }
onMounted(async () => {
  try { await loadSceneAssets(root.value); await nextTick(); await settle() }
  catch (failure) { error.value = failure.message || 'Required brand assets failed to load' }
  ready.value = true
  window.addEventListener('executive-reset', reset)
  window.addEventListener('executive-still', still)
  window.addEventListener('executive-duration', setDuration)
})
onBeforeUnmount(() => { window.removeEventListener('executive-reset', reset); window.removeEventListener('executive-still', still); window.removeEventListener('executive-duration', setDuration) })
</script>

<template>
  <section ref="root" class="executive" :class="{ opening, narrated }" :data-slide-id="slide?.id || kind" :data-slide-count="narrated ? narrative.slides.length : 6" :data-slide-section="section" :data-slide-graph="!!graphScene" :data-executive-ready="ready && (active || isPrintMode)" :data-executive-error="error">
    <header class="scene-header" data-layout-region="slide heading">
      <p class="section-marker">AutoPoC<span v-if="!opening"> · {{ narrative.project_name }}</span><span v-else> executive summary</span></p>
      <h1 :data-max-lines="narrated || opening ? 2 : 1">{{ narrated ? slide.title : opening ? narrative.project_name : titles[kind] }}</h1>
      <p v-if="opening" class="subtitle">{{ narrated ? narrative.project_name : titles[kind] }}</p>
    </header>
    <main class="scene-content" :class="{ 'graph-content': graphScene, 'graph-results': graphScene && resultsScene }" data-layout-region="slide content">
      <div v-if="resultsScene" class="results">
        <div v-for="(value, status) in narrative.results" :key="status" :class="status" :data-layout-region="'result ' + status"><strong>{{ value }}</strong><span>{{ status }}</span></div>
      </div>
      <div v-if="graphScene" class="topology-stage" :class="{ 'scenario-stage': section === 'execution' || kind === 'test_execution' }">
        <TopoLoop v-if="graph && (active || isPrintMode)" :key="generation" :spec="graph" :theme="redhatTheme" :seed="1" :rate="rate" :freeze-at="validationTime ?? (isPrintMode || reducedMotion === 'reduce' ? 3 : null)" />
        <div v-else-if="!graph" class="no-graph"><h2>Topology evidence unavailable</h2><p>See the report for the recorded setup. No infrastructure has been inferred.</p></div>
      </div>
      <ul v-else-if="!resultsScene" class="claims"><li v-for="(claim, i) in claims" :key="i">{{ claim.text }}<small>Evidence: {{ claim.sources.join(', ') }}</small></li></ul>
      <ul v-if="(narrated && (graphScene || resultsScene)) || (kind === 'test_execution' && graph)" class="claims flow-claims" :class="{ 'result-claims': resultsScene }"><li v-for="(claim, i) in claims" :key="i">{{ claim.text }}<small>Evidence: {{ claim.sources.join(', ') }}</small></li></ul>
    </main>
    <p v-if="graphScene" class="caveat" data-layout-region="evidence caveat">Animation illustrates archived evidence; playback timing is illustrative.</p>
    <ul v-if="!narrated && (kind === 'results' || kind === 'platform_suitability')" class="limitations" data-layout-region="limitations"><li v-for="(text, i) in narrative.limitations" :key="i">{{ text }}</li></ul>
    <footer class="brand-footer" data-layout-region="brand footer">
      <span class="slide-number">{{ index + 1 }}</span>
      <div class="footer-meta"><span>{{ narrative.run_id }}</span><span>Report-based executive summary</span></div>
      <img v-if="corporateMark" class="corporate-logo" src="/brand/logos/redhat-logo-standard.svg" alt="Red Hat" width="150" height="36" />
      <img v-else class="hat-logo" src="/brand/logos/redhat-hat-standard.svg" alt="Red Hat" width="38" height="29" />
    </footer>
  </section>
</template>

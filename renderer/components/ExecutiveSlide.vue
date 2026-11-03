<script setup>
import { ref, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import { useIsSlideActive, useNav } from '@slidev/client'
import { usePreferredReducedMotion } from '@vueuse/core'
import TopoLoop from '../vendor/topoloop/src/TopoLoop.vue'
import { redhatTheme } from './redhat-theme.ts'
import { loadSceneAssets } from '../scene-validation.mjs'
import narrative from '../narrative.json'
import scenes from '../scenes.json'

const props = defineProps({ kind: String })
const root = ref(null)
const active = useIsSlideActive()
const { isPrintMode } = useNav()
const ready = ref(false)
const error = ref('')
const reducedMotion = usePreferredReducedMotion()
const generation = ref(0)
const kinds = ['purpose', 'testing_strategy', 'topology', 'test_execution', 'results', 'platform_suitability']
const titles = { purpose: 'Purpose and PoC objective', testing_strategy: 'Testing strategy', topology: 'Recorded setup', test_execution: 'How we tested', results: 'Validation results', platform_suitability: 'OpenShift and Kubernetes conclusions' }
const claims = computed(() => narrative[props.kind] || [])
const graph = computed(() => props.kind === 'topology' ? narrative.topology : narrative.scenario_flow)
const graphScene = computed(() => props.kind === 'topology' || (props.kind === 'test_execution' && graph.value))
const opening = computed(() => props.kind === 'purpose')
const corporateMark = computed(() => opening.value || props.kind === 'platform_suitability')
const rate = computed(() => graph.value ? graph.value.loop / scenes.durations[props.kind === 'topology' ? 2 : 3] : 1)
const settle = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
const reset = async () => { ready.value = false; generation.value++; await nextTick(); await settle(); ready.value = true }
onMounted(async () => {
  try { await loadSceneAssets(root.value); await nextTick(); await settle() }
  catch (failure) { error.value = failure.message || 'Required brand assets failed to load' }
  ready.value = true
  window.addEventListener('executive-reset', reset)
})
onBeforeUnmount(() => window.removeEventListener('executive-reset', reset))
</script>

<template>
  <section ref="root" class="executive" :class="{ opening }" :data-executive-ready="ready && (active || isPrintMode)" :data-executive-error="error">
    <header class="scene-header" data-layout-region="slide heading">
      <p class="section-marker">AutoPoC<span v-if="!opening"> · {{ narrative.project_name }}</span><span v-else> executive summary</span></p>
      <h1 :data-max-lines="opening ? 2 : 1">{{ opening ? narrative.project_name : titles[kind] }}</h1>
      <p v-if="opening" class="subtitle">{{ titles[kind] }}</p>
    </header>
    <main class="scene-content" :class="{ 'graph-content': graphScene }" data-layout-region="slide content">
      <div v-if="graphScene" class="topology-stage" :class="{ 'scenario-stage': kind === 'test_execution' }">
        <TopoLoop v-if="graph && (active || isPrintMode)" :key="generation" :spec="graph" :theme="redhatTheme" :seed="1" :rate="rate" :freeze-at="isPrintMode || reducedMotion === 'reduce' ? 3 : null" />
        <div v-else-if="!graph" class="no-graph"><h2>Topology evidence unavailable</h2><p>See the report for the recorded setup. No infrastructure has been inferred.</p></div>
      </div>
      <div v-else-if="kind === 'results'" class="results">
        <div v-for="(value, status) in narrative.results" :key="status" :class="status"><strong>{{ value }}</strong><span>{{ status }}</span></div>
      </div>
      <ul v-else class="claims"><li v-for="(claim, i) in claims" :key="i">{{ claim.text }}<small>Evidence: {{ claim.sources.join(', ') }}</small></li></ul>
      <ul v-if="kind === 'test_execution' && graph" class="claims flow-claims"><li v-for="(claim, i) in claims" :key="i">{{ claim.text }}<small>Evidence: {{ claim.sources.join(', ') }}</small></li></ul>
    </main>
    <p v-if="graphScene" class="caveat" data-layout-region="evidence caveat">Animation illustrates archived evidence; playback timing is illustrative.</p>
    <ul v-if="kind === 'results' || kind === 'platform_suitability'" class="limitations" data-layout-region="limitations"><li v-for="(text, i) in narrative.limitations" :key="i">{{ text }}</li></ul>
    <footer class="brand-footer" data-layout-region="brand footer">
      <span class="slide-number">{{ kinds.indexOf(kind) + 1 }}</span>
      <div class="footer-meta"><span>{{ narrative.run_id }}</span><span>Report-based executive summary</span></div>
      <img v-if="corporateMark" class="corporate-logo" src="/brand/logos/redhat-logo-standard.svg" alt="Red Hat" width="150" height="36" />
      <img v-else class="hat-logo" src="/brand/logos/redhat-hat-standard.svg" alt="Red Hat" width="38" height="29" />
    </footer>
  </section>
</template>

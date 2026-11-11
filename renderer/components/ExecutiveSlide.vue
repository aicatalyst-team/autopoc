<script setup>
import { ref, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import { useIsSlideActive, useNav } from '@slidev/client'
import { usePreferredReducedMotion } from '@vueuse/core'
import ExecutiveChecks from './ExecutiveChecks.vue'
import visuals from '../visuals.json'
import checks from '../checks.json'
import TopoLoop from '../vendor/topoloop/src/TopoLoop.vue'
import { redhatTheme } from './redhat-theme.ts'
import { loadSceneAssets } from '../scene-validation.mjs'
import { resultOrder } from '../storyboard.mjs'
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
const narrated = [2,3].includes(narrative.schema_version)
const generic = narrative.schema_version === 3
const asset = computed(() => visuals.assets.find(asset => asset.id === slide.value?.visual_id))
const sourceRevisionLabel = computed(() => {
  const revision = asset.value?.source_revision
  return /^(?:[a-f\d]{40}|[a-f\d]{64})$/i.test(revision) ? revision.slice(0, 12) + '…' : revision
})
const definition = computed(() => narrative.claims.find(claim => claim.id === narrative.project_context?.definition_claim_id))
const index = computed(() => narrated ? narrative.slides.findIndex(s => s.id === props.slideId) : kinds.indexOf(props.kind))
const slide = computed(() => narrated ? narrative.slides[index.value] : null)
const section = computed(() => slide.value?.section || props.kind)
const claims = computed(() => narrated ? slide.value.bullet_claim_ids.map(id => narrative.claims.find(c => c.id === id)) : narrative[props.kind] || [])
const graph = computed(() => narrated ? slide.value.graph : props.kind === 'topology' ? narrative.topology : narrative.scenario_flow)
const graphScene = computed(() => narrated ? (generic ? slide.value.layout === 'topology' : !!graph.value) : props.kind === 'topology' || (props.kind === 'test_execution' && graph.value))
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
  try { await loadSceneAssets(root.value, generic ? visuals.assets : []); await nextTick(); await settle() }
  catch (failure) { error.value = failure.message || 'Required brand assets failed to load' }
  ready.value = true
  window.addEventListener('executive-reset', reset)
  window.addEventListener('executive-still', still)
  window.addEventListener('executive-duration', setDuration)
})
onBeforeUnmount(() => { window.removeEventListener('executive-reset', reset); window.removeEventListener('executive-still', still); window.removeEventListener('executive-duration', setDuration) })
</script>

<template>
  <section ref="root" class="executive" :class="{ opening, narrated, generic }" :data-slide-id="slide?.id || kind" :data-slide-count="narrated ? narrative.slides.length : 6" :data-slide-section="section" :data-slide-graph="!!graphScene" :data-executive-ready="ready && (active || isPrintMode)" :data-executive-error="error">
    <header class="scene-header" data-layout-region="slide heading">
      <p class="section-marker">AutoPoC<span v-if="!opening"> · {{ narrative.project_name }}</span><span v-else> executive summary</span></p>
      <h1 :data-max-lines="narrated || opening ? 2 : 1">{{ narrated ? slide.title : opening ? narrative.project_name : titles[kind] }}</h1>
      <p v-if="opening" class="subtitle">{{ narrated ? narrative.project_name : titles[kind] }}</p>
    </header>
    <main class="scene-content" :class="{ 'graph-content': graphScene, 'graph-results': graphScene && resultsScene }" data-layout-region="slide content">
      <div v-if="generic && slide.layout === 'identity'" class="identity-content">
        <div class="identity-copy" data-layout-region="project definition">
          <p class="project-definition">{{ definition.text }}</p>
          <ul class="identity-notes"><li v-for="claim in claims.filter(c => c.id !== definition.id)" :key="claim.id">{{ claim.text }}</li></ul>
          <div class="source-card" data-layout-region="source card"><strong>Source repository</strong><span>{{ narrative.project_context.repository_url }}</span><span>{{ narrative.project_context.revision ? 'Revision: ' + narrative.project_context.revision : 'Revision unavailable in retained source metadata' }}</span></div>
        </div>
        <figure v-if="asset" class="project-visual" data-layout-region="project visual">
          <img :src="'/visuals/' + asset.id + '.png'" :alt="asset.alt" />
          <figcaption><strong :title="asset.source_revision">{{ asset.kind === 'concept' ? 'Conceptual illustration' : asset.source_revision ? 'Source context · ' + sourceRevisionLabel : 'Contextual current documentation' }}</strong><span>{{ asset.caption }}</span><small>{{ asset.attribution }}</small><small v-if="asset.source_url">{{ asset.source_url }}</small></figcaption>
        </figure>
      </div>
      <ExecutiveChecks v-else-if="generic && slide.layout === 'checks'" :slide="slide" :claims="narrative.claims" :checks="checks" :active="active" :print="isPrintMode" />
      <div v-if="resultsScene" class="results">
        <div v-for="status in resultOrder" :key="status" :class="status" :data-layout-region="'result ' + status"><strong>{{ narrative.results[status] }}</strong><span>{{ status }}</span></div>
      </div>
      <div v-if="graphScene" class="topology-stage" :class="{ 'scenario-stage': section === 'execution' || kind === 'test_execution' }">
        <TopoLoop v-if="graph && (active || isPrintMode)" :key="generation" :spec="graph" :theme="redhatTheme" :seed="1" :rate="rate" :freeze-at="validationTime ?? (isPrintMode || reducedMotion === 'reduce' ? 3 : null)" />
        <div v-else-if="!graph" class="no-graph"><h2>Topology evidence unavailable</h2><p>See the report for the recorded setup. No infrastructure has been inferred.</p></div>
      </div>
      <ul v-else-if="!resultsScene && !(generic && ['identity','checks'].includes(slide.layout))" class="claims"><li v-for="(claim, i) in claims" :key="i">{{ claim.text }}<small>Evidence: {{ claim.sources.join(', ') }}</small></li></ul>
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

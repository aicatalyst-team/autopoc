<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAsyncState, usePreferredReducedMotion } from '@vueuse/core'
import { useIsSlideActive, useNav } from '@slidev/client'
import TopoLoop from '../vendor/topoloop/src/TopoLoop.vue'
import { themes, type ThemeInput } from '../vendor/topoloop/src/theme.ts'
import { setup } from '../specs/omnigent-setup.ts'
import { createScenarios } from '../specs/omnigent-scenarios.ts'

const props = defineProps<{ kind: 'setup' | 'scenarios' }>()
const { isPrintMode } = useNav()
const active = useIsSlideActive()
const reducedMotion = usePreferredReducedMotion()
const paused = ref(reducedMotion.value === 'reduce')
watch(reducedMotion, value => { if (value === 'reduce') paused.value = true })
const { state: spec, error } = useAsyncState(async () => {
  if (props.kind === 'setup') return setup
  const response = await fetch('/evidence/test-results.json')
  if (!response.ok) throw new Error(`Unable to load original test evidence: HTTP ${response.status}`)
  return createScenarios(await response.json())
}, null)
const posterAt = props.kind === 'setup' ? 7 : 47
const frozen = computed(() => isPrintMode.value || paused.value)
const theme: ThemeInput = { ...themes.dark, name: 'autopoc', bg: ['#23272d', '#171a1e', '#111417'], fog: '#171a1e', neutral: '#ff7b72', textFaint: '#aeb8c5', textGhost: '#9ca8b8', labelDim: '0.8' }
</script>

<template>
  <section class="run-topoloop" :data-topoloop="kind">
    <h1>{{ kind === 'setup' ? 'AutoPoC setup topology' : 'Five original HTTP scenarios' }}</h1>
    <button v-if="!isPrintMode" class="motion-toggle" type="button" :aria-pressed="paused" @click="paused = !paused">
      {{ paused ? 'Play animation' : 'Show still frame' }}
    </button>
    <div class="run-topoloop-stage">
      <p v-if="error" class="run-topoloop-error" role="alert">Unable to render the run evidence. Reload the presentation or inspect the linked original results.</p>
      <TopoLoop v-else-if="spec && (isPrintMode || active)" :key="String(frozen)" :spec="spec" :theme="theme" :seed="1" :freeze-at="frozen ? posterAt : null" />
    </div>
    <p class="run-topoloop-note">Animated reconstruction from run evidence. Playback timing is illustrative. <span v-if="kind === 'scenarios'">HTTP checks only; no login or agent execution.</span><span v-else>SQLite storage is temporary.</span></p>
    <footer>
      <a :href="kind === 'setup' ? '/evidence/deployment.yaml' : '/evidence/test-results.json'">{{ kind === 'setup' ? 'Deployment evidence' : 'Original test JSON' }}</a>
      <span>Run autopoc-omnigent-8554</span>
      <a href="https://github.com/r-bit-rry/topoloop">Powered by TopoLoop</a>
    </footer>
  </section>
</template>

<style>
.run-topoloop { position: absolute; inset: 0; background: #171a1e; color: #fff; font-family: Arial, sans-serif; }
.run-topoloop > h1 { position: absolute; top: 27px; left: 40px; margin: 0; font-size: 38px; font-weight: 700; letter-spacing: -1px; }
.run-topoloop-stage { position: absolute; top: 92px; left: 18px; right: 18px; bottom: 87px; }
.run-topoloop-error { padding: 60px 30px; color: #ffb0a9; font-size: 24px; }
.run-topoloop .motion-toggle { position: absolute; top: 29px; right: 40px; color: #f5f6f7; border: 1px solid #909ba8; background: #23272d; border-radius: 3px; padding: 9px 16px; font-size: 17px; cursor: pointer; }
.run-topoloop .motion-toggle:focus-visible { outline: 3px solid #ff7b72; outline-offset: 3px; }
.run-topoloop-note { position: absolute; left: 40px; bottom: 40px; margin: 0; font-size: 16px; color: #d0d6de; }
.run-topoloop footer { position: absolute; left: 40px; right: 40px; bottom: 16px; display: flex; justify-content: space-between; font-size: 14px; color: #aeb8c5; }
.run-topoloop footer a { color: #ffb0a9; text-decoration: underline; }
.run-topoloop .tl-title { font-size: 29px; max-width: 720px; }
.run-topoloop .tl-hud-top { top: 0; }
.run-topoloop .tl-kicker { font-size: 14px; }
.run-topoloop .tl-node-t, .run-topoloop .tl-node.off .tl-node-t { font-size: 18px; }
.run-topoloop .tl-node-s { font-size: 14px; }
.run-topoloop .tl-ns { font-size: 14px; letter-spacing: 1px; }
.run-topoloop .tl-b-row { font-size: 16px; padding: 4px 6px; }
.run-topoloop .tl-s-l { font-size: 14px; }
.run-topoloop .tl-s-v { font-size: 22px; }
.run-topoloop .tl-line { font-size: 15px; }
.run-topoloop .tl-term-title { font-size: 12px; }
.run-topoloop .tl-term-run { font-size: 11px; }
.run-topoloop .tl-a-cell { font-size: 16px; }
.run-topoloop .tl-a-cell i { font-size: 12px; }
.run-topoloop .tl-ann { gap: 18px; }
.run-topoloop .no-mascot .tl-term { top: 56%; }
.run-topoloop .no-mascot .tl-board { top: 22%; }
/* ponytail: show labels for the active path; upgrade to a label-layout solver for larger graphs. */
.run-topoloop .tl-node.off { visibility: hidden; }
</style>

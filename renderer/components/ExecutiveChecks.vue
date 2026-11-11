<script setup>
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { checkWindows, activeCheck } from '../check-timing.mjs'
const props = defineProps({slide:Object,claims:Array,checks:Object,active:Boolean,print:Boolean})
const windows = ref([]), elapsed = ref(null), mediaPrint = ref(false)
let printMedia
const printChanged = event => { mediaPrint.value=event.matches; reset() }
const current = computed(() => props.active && !props.print && !mediaPrint.value ? activeCheck(windows.value,elapsed.value) : null)
const claim = id => props.claims.find(row => row.id === id)?.text
const original = id => props.checks.results.find(row => row.scenario_id === id)
const reset = () => { windows.value=[]; elapsed.value=null }
const clock = event => {
  if (!props.active || props.print) return reset()
  if (event.detail.scene) windows.value = checkWindows(props.slide,event.detail.scene)
  elapsed.value = event.detail.elapsed_seconds
}
watch(() => [props.active,props.print,props.slide.id], reset)
onMounted(() => { printMedia=window.matchMedia('print'); mediaPrint.value=printMedia.matches; printMedia.addEventListener('change',printChanged); window.addEventListener('executive-clock',clock); window.addEventListener('executive-reset',reset); window.addEventListener('beforeprint',reset); window.addEventListener('executive-still',reset) })
onBeforeUnmount(() => { printMedia?.removeEventListener('change',printChanged); window.removeEventListener('executive-clock',clock); window.removeEventListener('executive-reset',reset); window.removeEventListener('beforeprint',reset); window.removeEventListener('executive-still',reset) })
</script>
<template>
  <div class="check-list" data-layout-region="checks">
    <ul class="check-context" data-layout-region="check context"><li v-for="id in slide.bullet_claim_ids" :key="id">{{ claim(id) }}</li></ul>
    <p v-if="!checks.results.length" class="empty-checks">No checks recorded</p>
    <article v-for="row in slide.checks" :key="row.scenario_id" :data-check-id="row.scenario_id" :title="original(row.scenario_id).scenario_name" class="check-row" :class="{'check-active':current===row.scenario_id}" data-layout-region="check row">
      <div><h2>{{ claim(row.label_claim_id) }}</h2><p>{{ claim(row.purpose_claim_id) }}</p></div>
      <span class="check-status" :class="original(row.scenario_id).status">{{ original(row.scenario_id).status }}</span>
    </article>
  </div>
</template>

<script setup lang="ts">
/**
 * TopoLoop
 *
 * A seamless loop over a graph. Each act walks one path: a probe travels it,
 * everything it touches takes the act's tone, and optional panels show a
 * status badge, a board of every act's status, a bar of facts, and a log.
 *
 * Layout is three non-overlapping regions, no occlusion:
 *   left       - topology viewport, own camera, CSS2D label layer pinned to it
 *   top right  - optional mascot stage, own scene and camera
 *   low right  - log panel, board
 *
 * The component holds no project content. Everything is in the spec.
 */
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import * as THREE from 'three'
import { CSS2DObject, CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import { buildTopology } from './topology'
import { actAt, board, EMPTY_SPEC, MAX_LOG as SPEC_MAX_LOG, validate, type LogLine, type CheckedSpec, type Spec, type Tone } from './spec'
import { frameState, TRAIL } from './frame'
import { cssVars, resolveTheme, themes, type ThemeInput } from './theme'
import { rng } from './rng'

export interface Mascot {
  root: THREE.Object3D
  /** per-frame idle motion */
  idle?: (t: number) => void
  /** 0..1, raised while a negative act plays */
  setAlert?: (v: number) => void
}

const props = withDefaults(defineProps<{
  spec: Spec
  /** freeze at this second, for a PDF export frame */
  freezeAt?: number | null
  rate?: number
  /** show the credits block in the header band */
  credits?: boolean
  /** optional 3D figurine for the top-right stage */
  mascot?: (() => Mascot) | null
  /** effect randomness (stars, shards). null = fresh each mount, number = repeatable */
  seed?: number | null
  /** built-in theme name, or a partial deep-merged over `blueprint` */
  theme?: ThemeInput
}>(), { freezeAt: null, rate: 1, credits: false, mascot: null, seed: null, theme: 'blueprint' })

// A bad spec must print on the slide. Throwing here would unmount the whole
// component and leave a blank rectangle, the failure validate() exists to stop.
// Spec and theme are checked separately so a slide with both wrong shows both.
const errors: string[] = []
const attempt = <T>(f: () => T, fallback: T): T => {
  try { return f() }
  catch (e: any) { errors.push(e?.message ?? String(e)); return fallback }
}
// on a fatal error EMPTY_SPEC feeds the computeds; the template renders only .tl-fatal
const spec: CheckedSpec = attempt(() => validate(props.spec), EMPTY_SPEC)
const TH = attempt(() => resolveTheme(props.theme), themes.blueprint)
const fatal = ref(errors.join('\n'))
const BOARD = board(spec)
const VARS = cssVars(TH)

const host = shallowRef<HTMLDivElement | null>(null)
const clockT = ref(0)

const act = computed(() => actAt(spec, clockT.value))
const actProgress = computed(() => {
  const a = act.value
  return ((clockT.value % spec.loop) - a.t0) / (a.t1 - a.t0)
})
// without a mascot the log panel is taller, so it can hold more lines
const MAX_LOG = props.mascot ? 5 : SPEC_MAX_LOG
// validate() cannot see the mascot prop; this is where the 5-line cap is known
for (const a of spec.acts) {
  const n = a.log?.length ?? 0
  if (n > MAX_LOG) console.warn(`TopoLoop: act ${a.id} has ${n} log lines; with a mascot the log shows ${MAX_LOG}, the first ${n - MAX_LOG} scroll off`)
}
const visibleLog = computed<LogLine[]>(() => {
  const x = clockT.value % spec.loop
  return (act.value.log ?? []).filter(b => b.at <= x).slice(-MAX_LOG)
})
// a region shows only when the spec gives it something to say
const HAS_LOG = spec.acts.some(a => a.log?.length)
const LOG_TITLE = spec.logTitle ?? 'log'
const tone = computed<Tone>(() => act.value.tone ?? 'neutral')
const MARK: Record<Tone, string> = { positive: '[+] ', negative: '[x] ', neutral: '[-] ' }
const annShow = ref(false)

const logColor = (b: LogLine): Record<string, string> => ({ color: `var(--tl-log-${b.kind})` })

let raf = 0
let renderer: THREE.WebGLRenderer | null = null
let labelRenderer: CSS2DRenderer | null = null
let ro: ResizeObserver | null = null

// region geometry, fractions of the host box
const R = {
  topo: { x: 0.010, y: 0.150, w: 0.620, h: 0.640 },
  mascot: { x: 0.645, y: 0.268, w: 0.345, h: 0.230 },
}
// no mascot means the right column starts higher, so the topology gets the
// full height instead of leaving a dead band
if (!props.mascot) {
  R.topo.y = 0.118
  R.topo.h = 0.700
}

onMounted(() => {
  if (fatal.value) return
  try { boot() }
  catch (e: any) { fatal.value = e?.message ?? String(e) }
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  ro?.disconnect()
  renderer?.dispose()
  renderer?.forceContextLoss?.()
})

function boot() {
  const el = host.value!
  const W = () => el.clientWidth || 980
  const H = () => el.clientHeight || 551

  renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    // required: slidev export captures a blank canvas without it
    preserveDrawingBuffer: true,
  })
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
  renderer.setSize(W(), H())
  renderer.setScissorTest(true)
  renderer.autoClear = false
  Object.assign(renderer.domElement.style, { position: 'absolute', inset: '0' })
  el.appendChild(renderer.domElement)

  // CSS2D layer is sized and positioned to exactly cover the topology region,
  // so its projection matches the topology camera's viewport.
  labelRenderer = new CSS2DRenderer()
  const lde = labelRenderer.domElement
  Object.assign(lde.style, { position: 'absolute', pointerEvents: 'none', overflow: 'hidden' })
  el.appendChild(lde)

  // ======================= topology scene ================================
  const rand = rng(props.seed)
  const scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(new THREE.Color(TH.fog).getHex(), 0.020)

  const cam = new THREE.PerspectiveCamera(41, 1.6, 0.1, 200)

  scene.add(new THREE.AmbientLight(TH.amb, 0.42))
  const key = new THREE.DirectionalLight(TH.key, 1.6)
  key.position.set(-7, 9, 8)
  scene.add(key)
  const rim = new THREE.DirectionalLight(TH.rim, 1.3)
  rim.position.set(8, 1, -7)
  scene.add(rim)
  const pulseLight = new THREE.PointLight(TH.positive, 0, 30, 2)
  scene.add(pulseLight)

  // starfield
  {
    const n = 700
    const pos = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) {
      const r = 40 + rand() * 40
      const th = rand() * Math.PI * 2
      const ph = Math.acos(2 * rand() - 1)
      pos[i * 3] = r * Math.sin(ph) * Math.cos(th)
      pos[i * 3 + 1] = r * Math.cos(ph) * 0.5
      pos[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th)
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    scene.add(new THREE.Points(g, new THREE.PointsMaterial({
      color: TH.star, size: 0.16, transparent: true, opacity: 0.5,
    })))
  }

  const topo = buildTopology(spec, TH)
  scene.add(topo.root)

  // node labels, offset per node so they never sit on geometry
  const ANCHOR: Record<string, THREE.Vector3> = {
    up: new THREE.Vector3(0, 0.92, 0),
    down: new THREE.Vector3(0, -1.02, 0),
    left: new THREE.Vector3(-0.20, -1.02, 0),
    right: new THREE.Vector3(0.20, 0.92, 0),
  }
  const nodeLabel: Record<string, HTMLDivElement> = {}
  for (const n of spec.nodes) {
    const d = document.createElement('div')
    d.className = 'tl-node'
    const tt = document.createElement('span')
    tt.className = 'tl-node-t'
    tt.textContent = n.label
    d.appendChild(tt)
    if (n.sub) {
      const ss = document.createElement('span')
      ss.className = 'tl-node-s'
      ss.textContent = n.sub
      d.appendChild(ss)
    }
    const o = new CSS2DObject(d)
    o.position.copy(topo.pos[n.id]).add(ANCHOR[n.anchor ?? 'up'])
    scene.add(o)
    nodeLabel[n.id] = d
  }

  // group captions, anchored under their own shell so they never collide
  for (const g of spec.groups ?? []) {
    const at = topo.shellAnchor[g.id]
    if (!at) continue
    const d = document.createElement('div')
    d.className = 'tl-ns'
    d.textContent = g.label
    const o = new CSS2DObject(d)
    o.position.copy(at)
    scene.add(o)
  }

  // --- probe ---------------------------------------------------------------
  const probe = new THREE.Mesh(
    new THREE.IcosahedronGeometry(0.19, 1),
    new THREE.MeshBasicMaterial({ color: TH.negative }),
  )
  scene.add(probe)
  const probeGlow = new THREE.PointLight(TH.negative, 3, 7, 2)
  scene.add(probeGlow)

  // comet trail, as a tapered ribbon of spheres so it survives a projector
  const trailDots: THREE.Mesh[] = []
  for (let i = 0; i < TRAIL; i++) {
    const s = 0.13 * (1 - i / TRAIL)
    const m = new THREE.Mesh(
      new THREE.SphereGeometry(Math.max(s, 0.012), 6, 5),
      new THREE.MeshBasicMaterial({ color: TH.negative, transparent: true, opacity: 0 }),
    )
    scene.add(m)
    trailDots.push(m)
  }

  // --- where the walk ends or halts ---------------------------------------
  const flare = new THREE.Mesh(
    new THREE.RingGeometry(0.10, 1.9, 44),
    new THREE.MeshBasicMaterial({ color: TH.positive, transparent: true, opacity: 0, side: THREE.DoubleSide }),
  )
  scene.add(flare)

  // halted: shards reflect back along the incoming path. finished: they scatter.
  const SH = 110
  const shPos = new Float32Array(SH * 3)
  const shVel: THREE.Vector3[] = Array.from({ length: SH }, () => {
    const u = rand() * 2 - 1
    const th = rand() * Math.PI * 2
    const s = Math.sqrt(1 - u * u)
    return new THREE.Vector3(s * Math.cos(th), u, s * Math.sin(th)).multiplyScalar(0.6 + rand() * 2.6)
  })
  const shGeo = new THREE.BufferGeometry()
  shGeo.setAttribute('position', new THREE.BufferAttribute(shPos, 3))
  const shards = new THREE.Points(shGeo, new THREE.PointsMaterial({
    color: TH.positive, size: 0.13, transparent: true, opacity: 0,
  }))
  scene.add(shards)

  // explicit stop marker, so a halted walk reads from the geometry alone and
  // not only from a caption
  const stopMark = new THREE.Group()
  for (const rot of [Math.PI / 4, -Math.PI / 4]) {
    const bar = new THREE.Mesh(
      new THREE.BoxGeometry(1.30, 0.26, 0.10),
      new THREE.MeshBasicMaterial({ color: TH.positive, transparent: true, opacity: 0 }),
    )
    bar.rotation.z = rot
    stopMark.add(bar)
  }
  stopMark.add(new THREE.Mesh(
    new THREE.TorusGeometry(0.94, 0.075, 8, 30),
    new THREE.MeshBasicMaterial({ color: TH.positive, transparent: true, opacity: 0 }),
  ))
  scene.add(stopMark)

  // ======================= mascot stage ====================================
  const mascot = props.mascot ? props.mascot() : null
  const mScene = new THREE.Scene()
  const mCam = new THREE.PerspectiveCamera(38, 1, 0.1, 60)
  if (mascot) {
    mCam.position.set(3.0, 2.5, 5.2)
    mCam.lookAt(0, 0.85, 0)
    mScene.add(new THREE.AmbientLight(TH.amb, 0.5))
    const mKey = new THREE.DirectionalLight(TH.key, 2.6)
    mKey.position.set(3, 6, 6)
    mScene.add(mKey)
    const mRim = new THREE.DirectionalLight(TH.rim, 2.4)
    mRim.position.set(-5, 1, -4)
    mScene.add(mRim)
    mascot.root.position.set(-0.15, 0.10, 0)
    mScene.add(mascot.root)
  }
  const mPulse = new THREE.PointLight(TH.positive, 0, 12, 2)
  mPulse.position.set(0, 1.4, 2.4)
  mScene.add(mPulse)

  // ------------------------------------------------------------------------
  const start = performance.now()

  function layoutBox() {
    const w = W(); const h = H()
    return {
      topo: { x: R.topo.x * w, y: R.topo.y * h, w: R.topo.w * w, h: R.topo.h * h },
      mascot: { x: R.mascot.x * w, y: R.mascot.y * h, w: R.mascot.w * w, h: R.mascot.h * h },
      w,
      h,
    }
  }

  function applyLayout() {
    const L = layoutBox()
    renderer!.setSize(L.w, L.h)
    cam.aspect = L.topo.w / L.topo.h
    cam.updateProjectionMatrix()
    mCam.aspect = L.mascot.w / L.mascot.h
    mCam.updateProjectionMatrix()
    labelRenderer!.setSize(L.topo.w, L.topo.h)
    Object.assign(lde.style, {
      left: `${L.topo.x}px`,
      top: `${L.topo.y}px`,
      width: `${L.topo.w}px`,
      height: `${L.topo.h}px`,
    })
  }
  applyLayout()

  function frame() {
    const t = props.freezeAt != null
      ? props.freezeAt
      : ((performance.now() - start) / 1000) * props.rate
    clockT.value = t
    const F = frameState(spec, topo.pos, t, { fov: cam.fov, aspect: cam.aspect })
    const col = TH[F.tone]

    cam.position.copy(F.camera.pos)
    cam.lookAt(F.camera.look)

    // --- mascot ------------------------------------------------------------
    if (mascot) {
      mascot.idle?.(t)
      mascot.setAlert?.(F.mascot.alert)
      mascot.root.rotation.y = F.mascot.spin
    }
    mPulse.color.set(col)
    mPulse.intensity = F.mascot.intensity

    topo.tick(t)
    topo.reset()

    // --- probe -------------------------------------------------------------
    probe.position.copy(F.probe.at)
    probe.rotation.copy(F.probe.spin)
    probeGlow.position.copy(F.probe.at)
    ;(probe.material as THREE.MeshBasicMaterial).color.set(col)
    probeGlow.color.set(col)
    probeGlow.intensity = F.probe.glow

    trailDots.forEach((d, i) => {
      d.position.copy(F.trail[i].at)
      const m = d.material as THREE.MeshBasicMaterial
      m.color.set(col)
      m.opacity = F.trail[i].opacity
    })

    for (const e of F.edges) topo.pulseEdge(e.a, e.b, e.v, col)
    for (const n of F.nodes) topo.flashNode(n.id, n.v, col)

    // label relevance: only this act's nodes are readable. everything else
    // drops to a dim name, which is what kills the label pile-up.
    for (const n of spec.nodes) {
      nodeLabel[n.id].className = F.lit.includes(n.id) ? 'tl-node on' : 'tl-node off'
    }

    // --- where the walk ends or halts ---------------------------------------
    stopMark.position.copy(F.stopMark.at)
    stopMark.lookAt(cam.position)
    stopMark.scale.setScalar(F.stopMark.scale)
    stopMark.children.forEach((c) => {
      const m = (c as THREE.Mesh).material as THREE.MeshBasicMaterial
      m.color.set(col)
      m.opacity = F.stopMark.opacity
    })

    flare.position.copy(F.flare.at)
    flare.lookAt(cam.position)
    flare.scale.setScalar(F.flare.scale)
    const fm = flare.material as THREE.MeshBasicMaterial
    fm.color.set(col)
    fm.opacity = F.flare.opacity

    const sm = shards.material as THREE.PointsMaterial
    sm.color.set(col)
    sm.opacity = F.shards.opacity
    if (F.shards.opacity > 0) {
      const { at: o, back, spread: g } = F.shards
      for (let i = 0; i < SH; i++) {
        const v = shVel[i]
        const dvec = F.halted ? v.clone().multiplyScalar(0.45).add(back.clone().multiplyScalar(1.5)) : v
        shPos[i * 3] = o.x + dvec.x * g
        shPos[i * 3 + 1] = o.y + dvec.y * g - 0.8 * g * g
        shPos[i * 3 + 2] = o.z + dvec.z * g
      }
      shGeo.attributes.position.needsUpdate = true
    }

    pulseLight.color.set(col)
    pulseLight.intensity = F.pulse.intensity
    pulseLight.position.copy(F.pulse.at)

    // the act's own shell reacts in the act's tone: a taut pulse, or a dim
    // flicker for a negative act
    if (F.shell) topo.setShell(F.shell.id, col, F.shell.opacity, F.shell.scale)

    // annotation is a docked strip in the template, driven by annShow
    annShow.value = F.annShow

    // --- draw --------------------------------------------------------------
    const L = layoutBox()
    const r = renderer!
    // clear the FULL canvas first. with scissorTest on, clear() only clears the
    // current scissor rect, which leaves an uncleared opaque block behind.
    r.setScissorTest(false)
    r.clear()
    r.setScissorTest(true)

    r.setViewport(L.topo.x, L.h - L.topo.y - L.topo.h, L.topo.w, L.topo.h)
    r.setScissor(L.topo.x, L.h - L.topo.y - L.topo.h, L.topo.w, L.topo.h)
    r.render(scene, cam)

    if (mascot) {
      r.setViewport(L.mascot.x, L.h - L.mascot.y - L.mascot.h, L.mascot.w, L.mascot.h)
      r.setScissor(L.mascot.x, L.h - L.mascot.y - L.mascot.h, L.mascot.w, L.mascot.h)
      r.render(mScene, mCam)
    }

    labelRenderer!.render(scene, cam)

    if (props.freezeAt == null) raf = requestAnimationFrame(frame)
  }

  ro = new ResizeObserver(() => { applyLayout() })
  ro.observe(el)

  frame()
  // second pass after layout settles, so an export never captures a zero-size
  // canvas or a pre-resize viewport
  if (props.freezeAt != null) {
    requestAnimationFrame(() => { applyLayout(); frame() })
  }
}
</script>

<template>
  <div class="tl-wrap" :class="{ 'no-mascot': !mascot }" :style="VARS">
    <div ref="host" class="tl-canvas" />
    <template v-if="!fatal">

    <div class="tl-hud-top">
      <div v-if="act.kicker" class="tl-kicker">{{ act.kicker }}</div>
      <div class="tl-title">{{ act.title }}</div>
    </div>

    <div v-if="act.status" class="tl-status" :class="`t-${tone}`">
      <span class="tl-s-l">{{ act.status.label }}</span>
      <span class="tl-s-v">{{ act.status.value }}</span>
    </div>

    <div v-if="spec.mascotCaption" class="tl-stage-cap">{{ spec.mascotCaption }}</div>

    <div v-if="credits && spec.credits" class="tl-credits">
      <div class="tl-cr-q">{{ spec.credits.headline }}</div>
      <div v-for="(l, i) in spec.credits.lines" :key="i" class="tl-cr-n">{{ l }}</div>
    </div>

    <!-- board: one row per act that has a status, current row lit -->
    <div v-if="BOARD.length" class="tl-board">
      <div
        v-for="row in BOARD" :key="row.actId" class="tl-b-row"
        :class="[`t-${row.tone}`, { on: row.actId === act.id }]"
      >
        <span class="tl-b-l">{{ row.label }}</span>
        <span class="tl-b-v">{{ MARK[row.tone] }}{{ row.value }}</span>
      </div>
    </div>

    <div v-if="HAS_LOG" class="tl-term">
      <div class="tl-term-bar">
        <span class="tl-dot" /><span class="tl-dot" /><span class="tl-dot" />
        <span class="tl-term-title">{{ LOG_TITLE }}</span>
        <span v-if="act.source" class="tl-term-run">{{ act.source }}</span>
      </div>
      <div v-for="(b, i) in visibleLog" :key="i" class="tl-line" :style="logColor(b)">{{ b.line }}</div>
    </div>

    <!-- facts, docked under the topology so they occlude nothing -->
    <div v-if="act.facts?.length" class="tl-ann" :class="[`t-${tone}`, { show: annShow }]">
      <div v-for="([k, val], i) in act.facts" :key="i" class="tl-a-cell"><i>{{ k }}</i><b>{{ val }}</b></div>
    </div>

    <div class="tl-acts">
      <div
        v-for="a in spec.acts" :key="a.id" class="tl-pip"
        :class="`t-${a.tone ?? 'neutral'}`"
      >
        <i :style="{ width: a.id === act.id ? `${Math.max(0, Math.min(1, actProgress)) * 100}%` : (a.t0 < act.t0 ? '100%' : '0%') }" />
      </div>
    </div>

    </template>
    <div v-if="fatal" class="tl-fatal">TopoLoop failed: {{ fatal }}</div>
  </div>
</template>

<style>
/* Bundled, so every host renders the same glyphs and the goldens compare on
   any machine. Red Hat Mono and Red Hat Display, SIL OFL 1.1, src/fonts/OFL.txt. Own family name
   so an installed copy of a different version never wins. */
@font-face { font-family: 'TopoLoop Mono'; font-weight: 400; src: url('./fonts/RedHatMono-Regular.otf') format('opentype'); }
@font-face { font-family: 'TopoLoop Mono'; font-weight: 500; src: url('./fonts/RedHatMono-Medium.otf') format('opentype'); }
@font-face { font-family: 'TopoLoop Mono'; font-weight: 700; src: url('./fonts/RedHatMono-Bold.otf') format('opentype'); }
@font-face { font-family: 'TopoLoop Display'; font-weight: 700; src: url('./fonts/RedHatDisplay-Bold.otf') format('opentype'); }
.tl-wrap {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: var(--tl-bg);
  --mono: var(--tl-mono);
}
.tl-canvas { position: absolute; inset: 0; }

.tl-hud-top { position: absolute; top: 2.6%; left: 2.2%; z-index: 5; pointer-events: none; }
.tl-kicker {
  font-size: 0.62rem; letter-spacing: 0.30em; text-transform: uppercase;
  color: var(--tl-kicker); font-family: var(--mono);
}
.tl-title {
  font-family: 'TopoLoop Display', sans-serif;
  font-size: 1.65rem; font-weight: 700; color: var(--tl-text); line-height: 1.1; margin-top: 3px;
  text-shadow: 0 2px 20px var(--tl-labelShadow);
}

/* one class per tone sets the two colours every toned element reads */
.t-positive { --tl-tone: var(--tl-positive); --tl-tone-text: var(--tl-positive); }
.t-negative { --tl-tone: var(--tl-negative); --tl-tone-text: var(--tl-negativeSoft); }
.t-neutral { --tl-tone: var(--tl-neutral); --tl-tone-text: var(--tl-neutral); }

.tl-status {
  position: absolute; top: 2.8%; right: 2.2%; z-index: 5; text-align: right;
  font-family: var(--mono);
}
.tl-s-l {
  display: block; font-size: 0.58rem; letter-spacing: 0.16em; color: var(--tl-textMute);
  text-transform: uppercase;
}
.tl-s-v {
  display: inline-block; margin-top: 3px; font-size: 1.0rem; font-weight: 700;
  letter-spacing: 0.20em; padding: 3px 12px; border: 1px solid; border-radius: 3px;
  background: var(--tl-badge); color: var(--tl-tone-text); border-color: var(--tl-tone);
}

.tl-credits {
  position: absolute; right: 2.2%; top: 13.2%; width: 33.3%; z-index: 6;
  text-align: right; pointer-events: none; white-space: nowrap;
}
.tl-cr-q {
  font-size: 0.88rem; font-weight: 700; color: var(--tl-negative); letter-spacing: 0.02em;
  text-shadow: 0 2px 14px var(--tl-labelShadow);
}
.tl-cr-n { font-size: 0.54rem; color: var(--tl-textStrong); margin-top: 2px; }

.tl-stage-cap {
  position: absolute; left: 64.5%; top: 48.6%; z-index: 5;
  font-family: var(--mono); font-size: 0.5rem; letter-spacing: 0.24em;
  text-transform: uppercase; color: var(--tl-textFaint);
}

.tl-board {
  position: absolute; left: 64.5%; top: 53.0%; width: 34.5%; z-index: 5;
  font-family: var(--mono);
}
.no-mascot .tl-board { top: 26.0%; }
/* no mascot: the transcript becomes a tall top-and-bottom anchored panel
   instead of leaving the right column hollow */
.no-mascot .tl-term { top: 40.0%; overflow: hidden; }
.tl-b-row {
  display: flex; justify-content: space-between; align-items: baseline;
  font-size: 0.52rem; padding: 1.5px 6px; border-left: 2px solid var(--tl-panelBorder);
  color: var(--tl-textFaint); letter-spacing: 0.02em;
}
.tl-b-row.on { background: var(--tl-rowHi); border-left-width: 3px; }
.tl-b-row.on .tl-b-l::before { content: '> '; color: var(--tl-textMute); }
.tl-b-row.on .tl-b-l { color: var(--tl-textStrong); }
.tl-b-row.on { border-left-color: var(--tl-tone); }
.tl-b-v { font-weight: 700; letter-spacing: 0.10em; }
.tl-b-v { color: var(--tl-tone-text); opacity: 0.45; }
.tl-b-row.on .tl-b-v { opacity: 1; }

.tl-term {
  position: absolute; left: 64.5%; bottom: 4.5%; width: 33.5%; z-index: 5;
  background: var(--tl-panel); border: 1px solid var(--tl-panelBorder); border-radius: 4px;
  padding-bottom: 5px;
}
.tl-term-bar {
  display: flex; align-items: center; gap: 5px; padding: 4px 8px;
  border-bottom: 1px solid var(--tl-panelBorder);
}
.tl-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--tl-textGhost); }
.tl-term-title {
  margin-left: 4px; font-size: 0.44rem; letter-spacing: 0.20em; text-transform: uppercase;
  color: var(--tl-textFaint); font-family: var(--mono);
}
.tl-term-run {
  margin-left: auto; font-size: 0.40rem; color: var(--tl-textGhost); font-family: var(--mono);
}
.tl-line {
  font-family: var(--mono); font-size: 0.47rem; line-height: 1.5;
  padding: 1px 9px; white-space: pre-wrap; overflow-wrap: anywhere; word-break: normal;
}

.tl-ann {
  position: absolute; left: 2.2%; width: 60.0%; bottom: 6.6%; z-index: 6;
  display: flex; align-items: baseline; gap: 22px;
  font-family: var(--mono);
  background: var(--tl-panel); border-left: 3px solid var(--tl-tone);
  padding: 6px 12px; border-radius: 3px;
  opacity: 0; transition: opacity 0.35s ease;
  box-shadow: 0 8px 30px var(--tl-shadow);
}
.tl-ann.show { opacity: 1; }
.tl-a-cell { font-size: 0.5rem; line-height: 1.35; min-width: 0; }
.tl-a-cell i {
  font-style: normal; display: block; color: var(--tl-textSub); letter-spacing: 0.14em;
  text-transform: uppercase; font-size: 0.40rem;
}
.tl-a-cell b { color: var(--tl-textStrong); font-weight: 500; }

.tl-acts { position: absolute; left: 2.2%; bottom: 2.4%; z-index: 5; display: flex; gap: 5px; }
.tl-pip { width: 38px; height: 3px; background: var(--tl-panelBorder); border-radius: 2px; overflow: hidden; }
.tl-pip i { display: block; height: 100%; background: var(--tl-tone); }

/* --- CSS2D layer -------------------------------------------------------- */
.tl-node {
  font-family: var(--mono); text-align: center; white-space: nowrap;
  pointer-events: none; transition: opacity 0.3s ease;
}
.tl-node-t {
  display: block; font-size: 0.55rem; color: var(--tl-textBright); font-weight: 700;
  text-shadow: 0 0 8px var(--tl-labelShadow), 0 0 3px var(--tl-labelShadow), 0 1px 2px var(--tl-labelShadow);
}
.tl-node-s {
  display: block; font-size: 0.45rem; color: var(--tl-textDim);
  text-shadow: 0 0 8px var(--tl-labelShadow), 0 0 3px var(--tl-labelShadow);
}
/* only the nodes this act touches are readable. the rest stay present as
   dim names so the graph never becomes a wall of competing text. */
.tl-node.on { opacity: 1; }
.tl-node.off { opacity: var(--tl-labelDim); }
.tl-node.off .tl-node-s { display: none; }
.tl-node.off .tl-node-t { font-weight: 400; color: var(--tl-textMute); font-size: 0.48rem; }
.tl-ns {
  font-family: var(--mono); font-size: 0.48rem; letter-spacing: 0.22em;
  text-transform: uppercase; color: var(--tl-label); white-space: nowrap;
  text-shadow: 0 0 10px var(--tl-labelShadow), 0 0 4px var(--tl-labelShadow);
}

.tl-fatal {
  position: absolute; inset: auto 0 50% 0; z-index: 20; text-align: center;
  font-family: var(--mono); font-size: 0.8rem; color: var(--tl-fatal);
}
</style>

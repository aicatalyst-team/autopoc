// Everything the renderer needs for one instant, as plain data.
//
// frameState(spec, pos, t) is pure: same arguments, same output, on any host.
// It knows nothing about a renderer, the DOM, a theme, or the wall clock. The
// component applies the result to meshes; node can assert on it.
//
// Colour is deliberately absent. A frame carries the act's `tone`, the
// component picks the theme token.

import * as THREE from 'three'
import { actAt, type Act, type CheckedSpec, type Spec, type Tone } from './spec.ts'

/** camera intrinsics of the topology viewport */
export interface View { fov: number, aspect: number }

export interface Pose { pos: THREE.Vector3, look: THREE.Vector3 }

export interface FrameState {
  /** loop-local time, t % spec.loop */
  x: number
  act: Act
  /** 0..1 within the act */
  p: number
  tone: Tone
  /** the walk stops short of the end of its path (act.stopAt < 1) */
  halted: boolean
  camera: Pose
  probe: { at: THREE.Vector3, spin: THREE.Euler, glow: number }
  /** newest first, one entry per trail dot */
  trail: { at: THREE.Vector3, opacity: number }[]
  edges: { a: string, b: string, v: number }[]
  nodes: { id: string, v: number }[]
  /** node ids on this act's path, the only ones with a readable label */
  lit: string[]
  stopMark: { at: THREE.Vector3, scale: number, opacity: number }
  flare: { at: THREE.Vector3, scale: number, opacity: number }
  shards: { at: THREE.Vector3, back: THREE.Vector3, spread: number, opacity: number }
  /** light flash where the walk ends or halts */
  pulse: { at: THREE.Vector3, intensity: number }
  shell: { id: string, opacity: number, scale: number } | null
  mascot: { alert: number, spin: number, intensity: number }
  annShow: boolean
}

const MARGIN = 1.12
/** seconds an act spends easing out of the previous act's end pose */
const EASE = 1.2
export const TRAIL = 26
/** curve units between trail dots, matched to the old 60fps ring buffer */
const TRAIL_STEP = 0.004
const UP = new THREE.Vector3(0, 1, 0)

const smoothstep = (u: number) => u * u * (3 - 2 * u)

function curveFor(spec: Spec, pos: Record<string, THREE.Vector3>, key: string) {
  return new THREE.CatmullRomCurve3(spec.paths[key].via.map(id => pos[id]), false, 'catmullrom', 0.35)
}

function centerOf(spec: Spec, pos: Record<string, THREE.Vector3>) {
  const c = new THREE.Vector3()
  for (const n of spec.nodes) c.add(pos[n.id])
  return c.divideScalar(spec.nodes.length || 1)
}

// Pull the camera back until every node is inside the frustum. A hardcoded
// distance clips a spec whose extent the component has never seen.
function fitDistance(
  spec: Spec, pos: Record<string, THREE.Vector3>,
  camAt: THREE.Vector3, look: THREE.Vector3, base: number, view: View,
) {
  const fwd = new THREE.Vector3().subVectors(look, camAt).normalize()
  const right = new THREE.Vector3().crossVectors(fwd, UP).normalize()
  const up = new THREE.Vector3().crossVectors(right, fwd).normalize()
  const tanY = Math.tan(THREE.MathUtils.degToRad(view.fov / 2))
  const tanX = tanY * view.aspect
  let need = base
  for (const n of spec.nodes) {
    const d = new THREE.Vector3().subVectors(pos[n.id], look)
    const z = d.dot(fwd)
    need = Math.max(
      need,
      Math.abs(d.dot(right)) * MARGIN / tanX - z,
      Math.abs(d.dot(up)) * MARGIN / tanY - z,
    )
  }
  return need
}

/** the act's own target pose at progress p. No history, no smoothing. */
export function cameraFor(
  spec: CheckedSpec, pos: Record<string, THREE.Vector3>, a: Act, p: number, t: number, view: View,
): Pose {
  const via = spec.paths[a.path].via
  const focus = pos[via[via.length - 1]].clone()
    .lerp(pos[via[0]], 0.45)
    .lerp(centerOf(spec, pos), 0.45)
  // play-order rank, 1-based: act ids are labels, renumbering must not move the camera
  const n = spec.acts.filter(u => u.t0 < a.t0).length + 1
  const ang = -0.7 + n * 0.55 + p * 0.34 + Math.sin(t * 0.09) * 0.04
  const height = 3.2 + Math.sin(n * 1.4) * 1.4
  const look = focus.add(new THREE.Vector3(0, 0.3, 0))
  const at = (d: number) =>
    new THREE.Vector3(look.x + Math.sin(ang) * d, height, look.z + Math.cos(ang) * d)
  // one refinement pass: the fit depends on the direction, which depends on
  // the distance only weakly, so two evaluations converge
  let dist = 15.0 - Math.sin(p * Math.PI) * 1.6
  dist = fitDistance(spec, pos, at(dist), look, dist, view)
  dist = fitDistance(spec, pos, at(dist), look, dist, view)
  return { pos: at(dist), look }
}

export function frameState(
  spec: CheckedSpec,
  pos: Record<string, THREE.Vector3>,
  t: number,
  view: View = { fov: 41, aspect: 1.6 },
): FrameState {
  const x = ((t % spec.loop) + spec.loop) % spec.loop
  const a = actAt(spec, t)
  const p = (x - a.t0) / (a.t1 - a.t0)
  const tone = a.tone ?? 'neutral'
  const negative = tone === 'negative'

  // --- camera: the act's target, eased out of the previous act's end pose ---
  const camera = cameraFor(spec, pos, a, p, t, view)
  const into = x - a.t0
  if (into < EASE) {
    const order = [...spec.acts].sort((u, v) => u.t0 - v.t0)
    const prev = order[(order.findIndex(u => u.id === a.id) + order.length - 1) % order.length]
    const at0 = t - into
    const from = cameraFor(spec, pos, prev, 1, at0, view)
    const e = smoothstep(THREE.MathUtils.clamp(into / EASE, 0, 1))
    camera.pos.copy(from.pos.lerp(camera.pos, e))
    camera.look.copy(from.look.lerp(camera.look, e))
  }

  // --- probe walk ----------------------------------------------------------
  const spath = spec.paths[a.path]
  const stop = a.stopAt ?? 1
  const u = THREE.MathUtils.clamp((p - 0.10) / 0.60, 0, 1)
  const travelled = Math.min(smoothstep(u), stop)
  const curve = curveFor(spec, pos, a.path)
  const at = curve.getPoint(travelled)

  // trail: sampled behind the probe along the curve, no ring buffer, so the
  // same t gives the same tail at any frame rate
  const trail = Array.from({ length: TRAIL }, (_, i) => ({
    at: curve.getPoint(Math.max(travelled - i * TRAIL_STEP, 0)),
    opacity: u > 0 ? (1 - i / TRAIL) * 0.7 * Math.sin(Math.PI * Math.min(u * 1.6, 1)) : 0,
  }))

  const hops = spath.via.length - 1
  const edges = Array.from({ length: hops }, (_, i) => ({
    a: spath.via[i],
    b: spath.via[i + 1],
    v: THREE.MathUtils.clamp(travelled * hops - i, 0, 1),
  }))
  const nodes = spath.via.map((id, i) => ({
    id,
    v: Math.max(0, 1 - Math.min(1, Math.abs(travelled * hops - i) * 1.8)),
  }))

  // --- the decision moment -------------------------------------------------
  const decidedAt = 0.10 + 0.60 * stop
  const since = p - decidedAt
  const origin = curve.getPoint(stop)

  // the marker shows only when the walk halts, i.e. the probe stopped
  // short of the end of its path
  const early = stop < 0.999
  const sm = early && since >= -0.04
    ? 1 - Math.pow(1 - THREE.MathUtils.clamp((since + 0.04) / 0.20, 0, 1), 3)
    : 0
  const f = THREE.MathUtils.clamp(since / 0.24, 0, 1)
  const after = since >= 0

  return {
    x,
    act: a,
    p,
    tone,
    halted: early,
    camera,
    probe: { at, spin: new THREE.Euler(t * 3, t * 2.2, 0), glow: u > 0 && u < 1 ? 4 : 0.8 },
    trail,
    edges,
    nodes,
    lit: spath.via,
    stopMark: { at: origin.clone(), scale: 0.5 + sm * 0.75, opacity: sm ? 0.95 * sm : 0 },
    flare: { at: origin.clone(), scale: 0.25 + f * 1.6, opacity: after ? (1 - f) * 0.5 : 0 },
    shards: {
      at: origin.clone(),
      // a halted walk sprays back along the incoming direction, a finished one scatters
      back: curve.getTangent(Math.max(stop - 0.02, 0.01)).multiplyScalar(-1),
      spread: Math.max(since, 0) * 2.2,
      opacity: after ? Math.max(0, 1 - (since * 2.2) / 1.5) * 0.65 : 0,
    },
    pulse: { at: origin.clone(), intensity: after ? 16 * Math.exp(-since * 5) : 0 },
    shell: a.shell
      ? {
          id: a.shell,
          opacity: negative
            ? 0.055 + 0.02 * Math.sin(t * 4)
            : 0.075 + (after ? 0.34 * Math.exp(-since * 6) : 0.02 * Math.sin(t * 3)),
          scale: !negative && after ? 1 + 0.045 * Math.exp(-since * 5) : 1,
        }
      : null,
    mascot: {
      alert: negative ? 0.5 + 0.5 * Math.sin(x * 7) : 0,
      spin: -0.30 + Math.sin(t * 0.30) * 0.42,
      intensity: negative ? 7 + 5 * Math.sin(x * 7) : 5,
    },
    annShow: p > 0.38,
  }
}

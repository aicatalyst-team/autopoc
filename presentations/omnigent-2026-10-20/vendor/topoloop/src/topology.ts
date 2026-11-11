// Spec-driven 3D graph. Same rendering decisions as the OpenClaw deck it came
// from, generalized over an arbitrary node/edge/group set.
//
// Edges are tube meshes, not THREE.Line. WebGL ignores linewidth on every
// desktop driver, so lines render 1px and vanish on a projector.

import * as THREE from 'three'
import type { GroupSpec, NodeKind, Spec } from './spec.ts'
import { groupBounds, layout } from './layout.ts'
import type { Theme } from './theme.ts'

const BLACK = 0x000000

/** one entry per node kind. Colour comes from theme.node[kind]. */
export const NODE_KINDS: Record<NodeKind, { geometry: () => THREE.BufferGeometry }> = {
  pod: { geometry: () => new THREE.BoxGeometry(0.74, 0.52, 0.74) },
  store: { geometry: () => new THREE.CylinderGeometry(0.34, 0.34, 0.46, 14) },
  external: { geometry: () => new THREE.OctahedronGeometry(0.42, 0) },
  control: { geometry: () => new THREE.BoxGeometry(0.74, 0.52, 0.74) },
}

export interface Topology {
  root: THREE.Group
  pos: Record<string, THREE.Vector3>
  center: THREE.Vector3
  /** shell mesh per group id, empty when the spec declares no groups */
  shells: Record<string, THREE.Mesh>
  shellAnchor: Record<string, THREE.Vector3>
  /** call once per frame before pulsing */
  reset: () => void
  pulseEdge: (a: string, b: string, v: number, color: THREE.ColorRepresentation) => void
  flashNode: (id: string, v: number, color: THREE.ColorRepresentation) => void
  setShell: (id: string, color: THREE.ColorRepresentation, opacity: number, scale: number) => void
  tick: (t: number) => void
}

export function buildTopology(spec: Spec, theme: Theme): Topology {
  const root = new THREE.Group()
  const pos = layout(spec)
  const halos: Record<string, THREE.Mesh> = {}
  const bodies: Record<string, THREE.Mesh> = {}

  for (const n of spec.nodes) {
    const g = new THREE.Group()
    g.position.copy(pos[n.id])

    const geo = NODE_KINDS[n.kind ?? 'pod'].geometry()
    const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
      color: theme.node[n.kind ?? 'pod'],
      emissive: BLACK,
      roughness: 0.62,
      metalness: 0.3,
      flatShading: true,
    }))
    g.add(m)
    bodies[n.id] = m

    // high-contrast outline, keeps the node readable on a washed-out projector
    g.add(new THREE.LineSegments(
      new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({ color: theme.outline, transparent: true, opacity: 0.8 }),
    ))

    const halo = new THREE.Mesh(
      new THREE.SphereGeometry(0.72, 16, 12),
      new THREE.MeshBasicMaterial({ color: theme.halo, transparent: true, opacity: 0, side: THREE.BackSide }),
    )
    g.add(halo)
    halos[n.id] = halo

    root.add(g)
  }

  const edgeMesh: Record<string, THREE.Mesh> = {}
  const arrowMesh: Record<string, THREE.Mesh> = {}
  for (const [a, b] of spec.edges) {
    const pa = pos[a]
    const pb = pos[b]
    const dir = new THREE.Vector3().subVectors(pb, pa)
    const len = dir.length()

    const tube = new THREE.Mesh(
      new THREE.CylinderGeometry(0.026, 0.026, len, 6),
      new THREE.MeshBasicMaterial({ color: theme.edge, transparent: true, opacity: 0.5 }),
    )
    tube.position.copy(pa).addScaledVector(dir, 0.5)
    tube.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize())
    root.add(tube)

    const head = new THREE.Mesh(
      new THREE.ConeGeometry(0.17, 0.44, 8),
      new THREE.MeshBasicMaterial({ color: theme.arrow, transparent: true, opacity: 0.9 }),
    )
    // stop short of the target so the cone is not swallowed by the node mesh
    head.position.copy(pa).addScaledVector(dir, 1 - 0.68 / len)
    head.quaternion.copy(tube.quaternion)
    root.add(head)

    for (const key of [`${a}>${b}`, `${b}>${a}`]) {
      edgeMesh[key] = tube
      arrowMesh[key] = head
    }
  }

  // --- group shells ---------------------------------------------------------
  const shells: Record<string, THREE.Mesh> = {}
  const shellAnchor: Record<string, THREE.Vector3> = {}
  const rest: Record<string, { color: THREE.ColorRepresentation, opacity: number }> = {}
  for (const g of spec.groups ?? []) {
    const ids = spec.nodes.filter(n => n.group === g.id).map(n => n.id)
    if (!ids.length) continue
    const { center, radius } = groupBounds(pos, ids)
    const color = g.color ?? theme.shell
    const opacity = g.opacity ?? 0.06
    const s = new THREE.Mesh(
      new THREE.IcosahedronGeometry(radius, 2),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity, wireframe: true }),
    )
    s.position.copy(center)
    root.add(s)
    shells[g.id] = s
    rest[g.id] = { color, opacity }
    shellAnchor[g.id] = center.clone().setY(center.y - radius - 0.55)
  }

  const center = new THREE.Vector3()
  for (const n of spec.nodes) center.add(pos[n.id])
  center.divideScalar(spec.nodes.length || 1)

  return {
    root,
    pos,
    center,
    shells,
    shellAnchor,
    reset() {
      for (const k of Object.keys(edgeMesh)) {
        const m = edgeMesh[k].material as THREE.MeshBasicMaterial
        m.color.set(theme.edge)
        m.opacity = 0.5
        edgeMesh[k].scale.set(1, 1, 1)
        const h = arrowMesh[k].material as THREE.MeshBasicMaterial
        h.color.set(theme.arrow)
        h.opacity = 0.9
        arrowMesh[k].scale.setScalar(1)
      }
      for (const id of Object.keys(halos)) {
        ;(halos[id].material as THREE.MeshBasicMaterial).opacity = 0
        halos[id].scale.setScalar(1)
        ;(bodies[id].material as THREE.MeshStandardMaterial).emissive.set(BLACK)
      }
      for (const id of Object.keys(shells)) {
        const m = shells[id].material as THREE.MeshBasicMaterial
        m.color.set(rest[id].color)
        m.opacity = rest[id].opacity
        shells[id].scale.setScalar(1)
      }
    },
    pulseEdge(a, b, v, color) {
      const e = edgeMesh[`${a}>${b}`]
      if (!e) return
      const m = e.material as THREE.MeshBasicMaterial
      m.opacity = 0.5 + v * 0.5
      if (v > 0.02) m.color.set(color)
      e.scale.set(1 + v * 2.4, 1, 1 + v * 2.4)
      const h = arrowMesh[`${a}>${b}`].material as THREE.MeshBasicMaterial
      h.opacity = 0.9 + v * 0.1
      if (v > 0.02) h.color.set(color)
      arrowMesh[`${a}>${b}`].scale.setScalar(1 + v * 0.7)
    },
    flashNode(id, v, color) {
      const h = halos[id]
      if (!h) return
      const hm = h.material as THREE.MeshBasicMaterial
      hm.color.set(color)
      hm.opacity = v * 0.34
      h.scale.setScalar(1 + v * 0.18)
      const bm = bodies[id].material as THREE.MeshStandardMaterial
      bm.emissive.set(color)
      bm.emissiveIntensity = v * 0.55
    },
    setShell(id, color, opacity, scale) {
      const s = shells[id]
      if (!s) return
      const m = s.material as THREE.MeshBasicMaterial
      m.color.set(color)
      m.opacity = opacity
      s.scale.setScalar(scale)
    },
    tick(t) {
      const keys = Object.keys(shells)
      keys.forEach((id, i) => {
        shells[id].rotation.y = t * (i % 2 ? -0.05 : 0.07)
        shells[id].rotation.x = Math.sin(t * 0.19 + i) * 0.06
      })
    },
  }
}

export type { GroupSpec }

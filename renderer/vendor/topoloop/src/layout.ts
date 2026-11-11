import * as THREE from 'three'
import type { NodeSpec, Spec } from './spec'

/**
 * Positions for nodes that did not declare one.
 *
 * Groups are laid out left to right, each group's members on a circle around
 * its centre, ungrouped nodes on an outer ring. Deterministic, so a deck
 * renders the same on every machine and in the PDF export.
 *
 * ponytail: static placement, no force sim. A graph big enough to need one
 * is too big to read from the back of a room.
 */
export function layout(spec: Spec): Record<string, THREE.Vector3> {
  const out: Record<string, THREE.Vector3> = {}
  const placed = spec.nodes.filter(n => n.pos)
  for (const n of placed) out[n.id] = new THREE.Vector3(...n.pos!)

  const auto = spec.nodes.filter(n => !n.pos)
  if (!auto.length) return out

  const byGroup = new Map<string, NodeSpec[]>()
  for (const n of auto) {
    const k = n.group ?? ''
    if (!byGroup.has(k)) byGroup.set(k, [])
    byGroup.get(k)!.push(n)
  }

  const groupKeys = [...byGroup.keys()].filter(k => k).sort()
  const span = 4.9
  const x0 = -((groupKeys.length - 1) * span) / 2

  groupKeys.forEach((k, gi) => {
    const members = byGroup.get(k)!
    const cx = x0 + gi * span
    const r = 1.5 + members.length * 0.28
    members.forEach((n, i) => {
      const a = (i / members.length) * Math.PI * 2 - Math.PI / 2
      out[n.id] = new THREE.Vector3(cx + Math.cos(a) * r, Math.sin(a) * r, Math.sin(a * 2) * 0.9)
    })
  })

  const loose = byGroup.get('') ?? []
  const outerR = 3.0 + groupKeys.length * 2.6
  loose.forEach((n, i) => {
    const a = (i / Math.max(loose.length, 1)) * Math.PI * 1.1 - Math.PI * 0.15
    out[n.id] = new THREE.Vector3(Math.cos(a) * outerR, Math.sin(a) * (outerR * 0.42), Math.sin(a * 3) * 1.1)
  })

  return out
}

/** Centre and radius of a group's members, for its shell. */
export function groupBounds(pos: Record<string, THREE.Vector3>, ids: string[]) {
  const c = new THREE.Vector3()
  for (const id of ids) c.add(pos[id])
  c.divideScalar(ids.length || 1)
  let r = 0
  for (const id of ids) r = Math.max(r, pos[id].distanceTo(c))
  return { center: c, radius: r + 1.15 }
}

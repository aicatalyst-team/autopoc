// A TopoLoop spec is the whole animation: a graph, some groups drawn as
// shells around it, named paths through the graph, and acts that each walk
// one path. What a walk stands for (a request, a record, a deploy, an attack)
// is the author's; the spec only knows graph, time, tone and text.
//
// Everything a deck author edits lives in a spec file. Nothing in this
// package hardcodes a project.

export type NodeKind = 'pod' | 'store' | 'external' | 'control'
export type Anchor = 'up' | 'down' | 'left' | 'right'

export interface NodeSpec {
  id: string
  label: string
  sub?: string
  kind?: NodeKind
  /** omit to let layout() place it */
  pos?: [number, number, number]
  /** label side, keeps the CSS label off the geometry */
  anchor?: Anchor
  /** group id, drives the shell it sits inside and auto-layout clustering */
  group?: string
}

export interface GroupSpec {
  id: string
  label: string
  /** shell wireframe colour, hex number or CSS string. default: theme.shell */
  color?: number | string
  /** shell opacity at rest. default 0.06 */
  opacity?: number
}

export interface PathSpec {
  via: string[]
}

export type LogKind = 'input' | 'output' | 'positive' | 'negative' | 'warn' | 'note'

export interface LogLine {
  /** seconds from loop start, absolute */
  at: number
  line: string
  kind: LogKind
}

/** Colour of everything an act touches. What positive or negative means is
 *  the author's: a check that held, a deploy that went out, a step that
 *  succeeded. */
export type Tone = 'positive' | 'negative' | 'neutral'
export const TONES: readonly Tone[] = ['positive', 'negative', 'neutral']

export interface Act {
  id: number
  t0: number
  t1: number
  /** small caps line above the title */
  kicker?: string
  title: string
  path: string
  /** 0..1 along the path where the walk halts: stop marker, shards thrown
   *  back. omit = the walk runs to the end of the path */
  stopAt?: number
  /** default 'neutral' */
  tone?: Tone
  /** badge top right; when any act has one, also a row on the board */
  status?: { label: string, value: string }
  /** label/value cells in the bar under the graph, at most 3 */
  facts?: [string, string][]
  /** group whose shell reacts in the act's tone */
  shell?: string
  /** lines typed into the log panel. omit on every act = no panel */
  log?: LogLine[]
  /** right side of the log panel title bar: a run id, a file, a source */
  source?: string
}

export interface Spec {
  title: string
  /** loop length in seconds. must equal the last act's t1 */
  loop: number
  nodes: NodeSpec[]
  edges: [string, string][]
  groups?: GroupSpec[]
  paths: Record<string, PathSpec>
  acts: Act[]
  /** log panel title. default 'log' */
  logTitle?: string
  credits?: { headline: string, lines: string[] }
  /** caption under the mascot stage. omit to hide the mascot region */
  mascotCaption?: string
}

/** A spec that passed validate(): acts sorted by t0. The order-sensitive
 *  functions take this type, so passing the raw spec is a type error. */
declare const checked: unique symbol
export type CheckedSpec = Spec & { readonly [checked]: true }

/** transcript lines the panel holds without a mascot (TopoLoop.vue) */
export const MAX_LOG = 8
/** cells the facts bar fits at 1280x720 */
export const MAX_FACTS = 3

const LOG_KINDS = new Set<string>(['input', 'output', 'positive', 'negative', 'warn', 'note'])

/** Throws on the mistakes that otherwise show up as a blank slide on stage. */
export function validate(s: Spec): CheckedSpec {
  const err: string[] = []
  const ids = new Set<string>()
  for (const n of s.nodes) {
    if (ids.has(n.id)) err.push(`duplicate node id ${n.id}`)
    ids.add(n.id)
  }
  const groups = new Set((s.groups ?? []).map(g => g.id))
  for (const g of groups) {
    // topology.ts sizes a shell to its members; with none it draws nothing
    if (!s.nodes.some(n => n.group === g)) err.push(`group ${g} has no member nodes, so no shell is drawn`)
  }
  for (const n of s.nodes) {
    if (n.group && !groups.has(n.group)) err.push(`node ${n.id} in unknown group ${n.group}`)
  }
  const edgeKey = (a: string, b: string) => [a, b].sort().join('>')
  const known = new Set<string>()
  for (const [a, b] of s.edges) {
    for (const id of [a, b]) if (!ids.has(id)) err.push(`edge ${a}-${b} references unknown node ${id}`)
    known.add(edgeKey(a, b))
  }
  for (const [name, p] of Object.entries(s.paths)) {
    if (p.via.length < 2) err.push(`path ${name} needs at least two nodes`)
    for (const id of p.via) if (!ids.has(id)) err.push(`path ${name} references unknown node ${id}`)
    for (let i = 0; i < p.via.length - 1; i++) {
      if (!known.has(edgeKey(p.via[i], p.via[i + 1]))) {
        err.push(`path ${name} hops ${p.via[i]}->${p.via[i + 1]} with no such edge`)
      }
    }
  }
  const acts = [...s.acts].sort((a, b) => a.t0 - b.t0)
  if (!acts.length) err.push('spec has no acts')
  const actIds = new Set<number>()
  acts.forEach((a, i) => {
    if (actIds.has(a.id)) err.push(`duplicate act id ${a.id}`)
    actIds.add(a.id)
    if (a.t1 <= a.t0) err.push(`act ${a.id} ends before it starts`)
    if (!s.paths[a.path]) err.push(`act ${a.id} uses unknown path ${a.path}`)
    if (a.stopAt != null && !(a.stopAt > 0 && a.stopAt <= 1)) err.push(`act ${a.id} stopAt must be in (0,1]`)
    if (a.tone != null && !TONES.includes(a.tone)) err.push(`act ${a.id} tone "${a.tone}" is not one of ${TONES.join(', ')}`)
    if (a.status && (typeof a.status.label !== 'string' || typeof a.status.value !== 'string')) {
      err.push(`act ${a.id} status needs a string label and value`)
    }
    if (a.facts) {
      if (a.facts.length > MAX_FACTS) err.push(`act ${a.id} has ${a.facts.length} facts; the bar shows ${MAX_FACTS}`)
      if (!a.facts.every(f => Array.isArray(f) && f.length === 2)) err.push(`act ${a.id} facts must be [label, value] pairs`)
    }
    const log = a.log ?? []
    if (log.length > MAX_LOG) err.push(`act ${a.id} has ${log.length} log lines; the panel shows ${MAX_LOG} (5 with a mascot)`)
    if (a.shell && !groups.has(a.shell)) err.push(`act ${a.id} reacts to unknown group ${a.shell}`)
    if (i > 0 && a.t0 !== acts[i - 1].t1) err.push(`gap or overlap between act ${acts[i - 1].id} and act ${a.id}`)
    for (const b of log) {
      if (b.at < a.t0 || b.at >= a.t1) err.push(`act ${a.id} log line at ${b.at}s falls outside [${a.t0},${a.t1})`)
      if (!LOG_KINDS.has(b.kind)) err.push(`act ${a.id} log kind "${b.kind}" is not one of ${[...LOG_KINDS].join(', ')}`)
    }
  })
  if (acts.length && acts[0].t0 !== 0) err.push('first act must start at 0')
  if (acts.length && acts[acts.length - 1].t1 !== s.loop) err.push(`loop is ${s.loop}s but acts end at ${acts[acts.length - 1].t1}s`)
  if (err.length) throw new Error(`invalid TopoLoop spec:\n  ${err.join('\n  ')}`)
  // acts in play order, so the scoreboard, pips and camera never depend on
  // the order they were written in
  return { ...s, acts } as CheckedSpec
}

/** Stands in for a spec that failed validate(), so a component can keep its
 *  computeds alive while it prints the error. Validated at import: a stricter
 *  validate() that rejects it fails every test, never the fatal path on stage. */
export const EMPTY_SPEC: CheckedSpec = validate({
  title: '', loop: 1, nodes: [{ id: 'a', label: '' }, { id: 'b', label: '' }], edges: [['a', 'b']],
  paths: { p: { via: ['a', 'b'] } },
  acts: [{ id: 0, t0: 0, t1: 1, title: '', path: 'p' }],
})

export function actAt(s: CheckedSpec, t: number): Act {
  const x = ((t % s.loop) + s.loop) % s.loop
  return s.acts.find(a => x >= a.t0 && x < a.t1) ?? s.acts[0]
}

/** Board rows, derived: one per act that has a status, in play order. */
export function board(s: CheckedSpec) {
  return s.acts.flatMap(a => a.status ? [{ actId: a.id, label: a.status.label, value: a.status.value, tone: a.tone ?? 'neutral' }] : [])
}

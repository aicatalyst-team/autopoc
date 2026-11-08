// Every colour in the component, in one object.
//
// Tokens are CSS colour strings, so the same value serves `var(--tl-*)` in CSS
// and `new THREE.Color(str)` in WebGL. A theme is never named by a spec:
// content and presentation stay in separate files.
//
// A custom theme is one object:
//   import { themes, type Theme } from 'topoloop'
//   export const brand: Theme = { ...themes.blueprint, name: 'brand', positive: '#3fb950' }
// or a partial passed to the `theme` prop, deep-merged over `blueprint`.

import type { LogKind, NodeKind } from './spec.ts'

export interface Theme {
  name: string
  /** radial gradient stops, centre to corner */
  bg: [string, string, string]
  /** drafting grid ruled over the ground, 'transparent' for none */
  grid: string
  /** headline */
  text: string
  /** node label, first line */
  textBright: string
  /** node sub-label */
  textDim: string
  /** dimmed node label, status caption */
  textMute: string
  /** facts caption, board left rule */
  textSub: string
  /** facts value, active board row */
  textStrong: string
  /** resting board row, panel title */
  textFaint: string
  /** window dots, log source */
  textGhost: string
  /** act kicker */
  kicker: string
  /** group caption in the graph */
  label: string
  /** halo behind every in-graph label */
  labelShadow: string
  /** opacity of a label not on this act's path. a light ground needs more */
  labelDim: string
  /** tone: 'positive' acts */
  positive: string
  /** tone: 'negative' acts */
  negative: string
  /** lighter negative, for text on a dark ground */
  negativeSoft: string
  /** tone: 'neutral' acts, and any act with no tone */
  neutral: string
  edge: string
  arrow: string
  outline: string
  halo: string
  /** default group shell colour, overridden per group by GroupSpec.color */
  shell: string
  fog: string
  star: string
  /** rim light */
  rim: string
  /** key light */
  key: string
  /** ambient light */
  amb: string
  panel: string
  /** status badge ground, darker than the panels */
  badge: string
  panelBorder: string
  /** active board row wash */
  rowHi: string
  /** panel drop shadow */
  shadow: string
  fatal: string
  node: Record<NodeKind, string>
  log: Record<LogKind, string>
  font: { mono: string }
}

export const themes: Record<'blueprint' | 'dark' | 'light', Theme> = {
  // The default. A drafting sheet: blueprint-blue ground under a ruled grid,
  // lines in blueprint white, and Red Hat red kept for the walk and for
  // negative acts, so the one moving thing on screen is the one red thing.
  blueprint: {
    name: 'blueprint',
    bg: ['#133563', '#0a1f3c', '#06152b'],
    grid: 'rgba(120, 165, 225, 0.15)',
    text: '#f4f8fd',
    textBright: '#eef4fb',
    textDim: '#c3d4e8',
    textMute: '#a9c0dc',
    textSub: '#b0c6e0',
    textStrong: '#e3ecf8',
    textFaint: '#98b1d0',
    textGhost: '#a9c0dc',
    kicker: '#98b1d0',
    label: '#bcd0e8',
    labelShadow: '#041022',
    labelDim: '0.72',
    positive: '#3ddc97',
    negative: '#ee0000',
    negativeSoft: '#ff7a7a',
    neutral: '#73bcf7',
    edge: '#5b82b5',
    arrow: '#9ab8dc',
    outline: '#cfe0f5',
    halo: '#73bcf7',
    shell: '#6f93c2',
    fog: '#0a1f3c',
    star: '#6f8db3',
    rim: '#9cc3ee',
    key: '#ffffff',
    amb: '#ffffff',
    panel: 'rgba(6, 21, 43, 0.92)',
    badge: 'rgba(4, 14, 30, 0.82)',
    panelBorder: '#3a64a0',
    rowHi: 'rgba(207, 224, 245, 0.08)',
    shadow: 'rgba(0, 0, 0, 0.6)',
    fatal: '#ff5c5c',
    node: { pod: '#1f4170', store: '#2c3a5e', external: '#3b4466', control: '#1c4b63' },
    log: {
      input: '#e6eef8',
      output: '#73bcf7',
      warn: '#f5c542',
      negative: '#ff5c5c',
      positive: '#3ddc97',
      note: '#a9c0dc',
    },
    font: { mono: "'TopoLoop Mono', ui-monospace, 'Red Hat Mono', 'JetBrains Mono', 'Fira Code', monospace" },
  },
  dark: {
    name: 'dark',
    bg: ['#101728', '#060a14', '#020308'],
    grid: 'transparent',
    text: '#ffffff',
    textBright: '#f1f5f9',
    textDim: '#b6c2d1',
    textMute: '#94a3b8',
    textSub: '#64748b',
    textStrong: '#e5e7eb',
    textFaint: '#4b5563',
    textGhost: '#374151',
    kicker: '#7c8798',
    label: '#8b97a8',
    labelShadow: '#000000',
    labelDim: '0.42',
    positive: '#10b981',
    negative: '#ee0000',
    negativeSoft: '#ff5f5f',
    neutral: '#7dd3fc',
    edge: '#55606e',
    arrow: '#93a3b8',
    outline: '#9aa7b8',
    halo: '#00e5cc',
    shell: '#64748b',
    fog: '#050810',
    star: '#93a6bd',
    rim: '#00e5cc',
    key: '#ffe6de',
    amb: '#ffffff',
    panel: 'rgba(2, 4, 9, 0.92)',
    badge: 'rgba(0, 0, 0, 0.65)',
    panelBorder: '#1f2937',
    rowHi: 'rgba(255, 255, 255, 0.07)',
    shadow: 'rgba(0, 0, 0, 0.8)',
    fatal: '#ef4444',
    node: { pod: '#323947', store: '#3d2626', external: '#4a3a1c', control: '#24303f' },
    log: {
      input: '#d1d5db',
      output: '#7dd3fc',
      warn: '#fbbf24',
      negative: '#ff5f5f',
      positive: '#34d399',
      note: '#6b7280',
    },
    font: { mono: "'TopoLoop Mono', ui-monospace, 'Red Hat Mono', 'JetBrains Mono', 'Fira Code', monospace" },
  },
  // Washed-out projectors, printed PDFs, README light mode. The case the dark
  // theme fails. Node bodies stay light so the dark outline carries the shape,
  // and the starfield is a pale grey that reads as texture, not noise.
  light: {
    name: 'light',
    bg: ['#ffffff', '#eef2f7', '#dde4ee'],
    grid: 'transparent',
    text: '#0f172a',
    textBright: '#0f172a',
    textDim: '#1e293b',
    textMute: '#1e293b',
    textSub: '#334155',
    textStrong: '#0f172a',
    textFaint: '#334155',
    textGhost: '#475569',
    kicker: '#334155',
    label: '#1e293b',
    labelShadow: '#ffffff',
    labelDim: '0.70',
    positive: '#047857',
    negative: '#b91c1c',
    negativeSoft: '#b91c1c',
    neutral: '#0369a1',
    edge: '#334155',
    arrow: '#0f172a',
    outline: '#1e293b',
    halo: '#0e7490',
    shell: '#334155',
    fog: '#e2e8f0',
    star: '#64748b',
    rim: '#7dd3fc',
    key: '#fff4ec',
    amb: '#ffffff',
    panel: 'rgba(241, 245, 249, 0.97)',
    badge: 'rgba(255, 255, 255, 0.85)',
    panelBorder: '#475569',
    rowHi: 'rgba(15, 23, 42, 0.14)',
    shadow: 'rgba(15, 23, 42, 0.18)',
    fatal: '#b91c1c',
    node: { pod: '#cbd5e1', store: '#e7cfcf', external: '#efdcb4', control: '#b9c6d6' },
    log: {
      input: '#0f172a',
      output: '#0369a1',
      warn: '#b45309',
      negative: '#b91c1c',
      positive: '#047857',
      note: '#64748b',
    },
    font: { mono: "'TopoLoop Mono', ui-monospace, 'Red Hat Mono', 'JetBrains Mono', 'Fira Code', monospace" },
  },
}

/** a partial may override single node kinds or log kinds */
export type PartialTheme = Omit<Partial<Theme>, 'node' | 'log' | 'font'> & {
  node?: Partial<Record<NodeKind, string>>
  log?: Partial<Record<LogKind, string>>
  font?: Partial<Theme['font']>
}
export type ThemeInput = keyof typeof themes | PartialTheme

/** A name, or a partial deep-merged over `blueprint`. Throws on an unknown name. */
export function resolveTheme(t: ThemeInput = 'blueprint'): Theme {
  if (typeof t === 'string') {
    if (!Object.hasOwn(themes, t)) throw new Error(`unknown theme "${t}". known: ${Object.keys(themes).join(', ')}`)
    return themes[t]
  }
  const b = themes.blueprint
  return {
    ...b,
    ...t,
    node: { ...b.node, ...t.node },
    log: { ...b.log, ...t.log },
    font: { ...b.font, ...t.font },
  }
}

/** `--tl-*` custom properties for the wrapper element. */
export function cssVars(t: Theme): Record<string, string> {
  const v: Record<string, string> = {
    '--tl-bg': [
      `linear-gradient(${t.grid} 1px, transparent 1px) 0 0 / 40px 40px`,
      `linear-gradient(90deg, ${t.grid} 1px, transparent 1px) 0 0 / 40px 40px`,
      `radial-gradient(ellipse at 28% 22%, ${t.bg[0]} 0%, ${t.bg[1]} 52%, ${t.bg[2]} 100%)`,
    ].join(', '),
    '--tl-mono': t.font.mono,
  }
  for (const [k, val] of Object.entries(t)) {
    if (typeof val === 'string') v[`--tl-${k}`] = val
  }
  for (const [k, val] of Object.entries(t.log)) v[`--tl-log-${k}`] = val
  return v
}

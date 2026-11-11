import { themes, type Theme } from '../vendor/topoloop/src/theme.ts'

// Red Hat's information palette: danger-orange is failure, red is branding.
export const redhatTheme: Theme = {
  ...themes.light, name: 'redhat', bg: ['#ffffff', '#f2f2f2', '#f2f2f2'], grid: 'transparent',
  text: '#151515', textBright: '#151515', textDim: '#383838', textMute: '#4d4d4d', textSub: '#4d4d4d',
  textStrong: '#151515', textFaint: '#4d4d4d', textGhost: '#707070', kicker: '#4d4d4d',
  label: '#383838', labelShadow: '#ffffff', labelDim: '1', positive: '#3d7317',
  negative: '#b1380b', negativeSoft: '#b1380b', fatal: '#b1380b', neutral: '#4d4d4d',
  edge: '#707070', arrow: '#383838', outline: '#4d4d4d', halo: '#c7c7c7', shell: '#707070',
  fog: '#f2f2f2', star: '#c7c7c7', rim: '#e0e0e0', key: '#ffffff', amb: '#ffffff',
  panel: 'rgba(255,255,255,.98)', panelBorder: '#c7c7c7', badge: '#ffffff', rowHi: '#f2f2f2', shadow: 'rgba(0,0,0,.12)',
  node: { pod: '#e0e0e0', store: '#e0e0e0', external: '#f2f2f2', control: '#e0e0e0' },
  log: { input: '#383838', output: '#0066cc', warn: '#9e4a06', negative: '#b1380b', positive: '#3d7317', note: '#4d4d4d' },
  font: { mono: '"Red Hat Mono", monospace' },
}

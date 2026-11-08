import type { Spec } from '../vendor/topoloop/src/spec.ts'

// Animated reconstruction of archived resources, not a captured network trace.
export const setup: Spec = {
  title: 'Omnigent setup topology',
  loop: 30,
  logTitle: 'original run excerpts',
  nodes: [
    { id: 'github', label: 'GitHub', sub: 'source + artifacts', kind: 'external', pos: [-5, 4, -2], anchor: 'up' },
    { id: 'runner', label: 'AutoPoC job', sub: 'autopoc-test', kind: 'control', pos: [-5, 1.3, 2], anchor: 'up' },
    { id: 'build', label: 'Build pod', sub: 'autopoc-test-builds', pos: [-1, -1.3, -1], anchor: 'up' },
    { id: 'quay', label: 'Quay', sub: 'image registry', kind: 'external', pos: [4, -4, 1], anchor: 'up' },
    { id: 'route', label: 'HTTPS Route', sub: 'edge TLS', kind: 'control', pos: [-5, 4, 2], anchor: 'up' },
    { id: 'service', label: 'Service', sub: '80 to 8000', kind: 'control', pos: [-1, -1.3, 0], anchor: 'up' },
    { id: 'server', label: 'Omnigent pod', sub: 'poc-omnigent', pos: [3, 1.3, -2], anchor: 'up' },
    { id: 'data', label: 'SQLite', sub: 'emptyDir /data', kind: 'store', pos: [6, -1.3, 2], anchor: 'up' },
  ],
  edges: [
    ['github', 'runner'], ['runner', 'build'], ['build', 'quay'],
    ['quay', 'server'], ['server', 'data'],
    ['route', 'service'], ['service', 'server'],
  ],
  paths: {
    build: { via: ['github', 'runner', 'build', 'quay'] },
    deploy: { via: ['quay', 'server', 'data'] },
    access: { via: ['route', 'service', 'server'] },
  },
  acts: [
    {
      id: 1, t0: 0, t1: 10,
      kicker: 'Setup 1 of 3', title: 'Build and publish', path: 'build', tone: 'positive',
      status: { label: 'image build', value: 'COMPLETE' },
      facts: [['build attempts', '2'], ['successful build', '8m 57s'], ['base', 'UBI 9']],
      source: 'build-1/2 logs',
      log: [
        { at: 1, kind: 'note', line: '# GitHub source to on-cluster build' },
        { at: 4, kind: 'negative', line: 'Error: Unable to find a match: tmux' },
        { at: 7, kind: 'positive', line: 'Push successful' },
      ],
    },
    {
      id: 2, t0: 10, t1: 20,
      kicker: 'Setup 2 of 3', title: 'Deploy the server', path: 'deploy', tone: 'positive',
      status: { label: 'rollout', value: 'READY 1/1' },
      facts: [['replicas', '1'], ['storage', 'temporary'], ['GPU', 'not required']],
      source: 'runner log',
      log: [
        { at: 11, kind: 'note', line: '# Quay image to Omnigent server pod' },
        { at: 14, kind: 'positive', line: 'deployment "omnigent" successfully rolled out' },
        { at: 17, kind: 'note', line: '# SQLite data is lost on pod replacement' },
      ],
    },
    {
      id: 3, t0: 20, t1: 30,
      kicker: 'Setup 3 of 3', title: 'Expose the app', path: 'access', tone: 'positive',
      status: { label: 'control plane', value: 'REACHABLE' },
      facts: [['entry', 'HTTPS Route'], ['server port', '8000'], ['checks', '5 passed']],
      source: 'runner log',
      log: [
        { at: 21, kind: 'note', line: '# Route to Service to server' },
        { at: 24, kind: 'output', line: 'HTTP 200' },
        { at: 27, kind: 'positive', line: '{"status":"ok"}' },
      ],
    },
  ],
}

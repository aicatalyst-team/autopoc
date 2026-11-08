import type { Act, Spec } from '../vendor/topoloop/src/spec.ts'

export interface ArchivedResults {
  results: { scenario_name: string, status: string, duration_seconds: number }[]
}

// The animation uses the original outcomes, never a later test replay.
const endpoints: Record<string, [string, string]> = {
  'health-check': ['/health', 'ok'],
  'version-info': ['/api/version', 'version'],
  'server-info': ['/v1/info', 'server_version'],
  'web-ui': ['/', 'html'],
  'login-page': ['/login', 'html'],
}

export function createScenarios(results: ArchivedResults): Spec {
  return {
  title: 'Original HTTP scenario flow',
  loop: results.results.length * 10,
  logTitle: 'original result JSON',
  nodes: [
    { id: 'test', label: 'Test runner', sub: 'poc_test.py', kind: 'control', pos: [-4.5, 3.5, 0], anchor: 'up' },
    { id: 'route', label: 'HTTPS Route', sub: 'edge TLS', kind: 'control', pos: [-1.5, 1.2, 1], anchor: 'up' },
    { id: 'service', label: 'Service', sub: '80 to 8000', kind: 'control', pos: [1.5, -1.2, -1], anchor: 'up' },
    { id: 'server', label: 'Omnigent', sub: 'HTTP endpoint', pos: [4.5, -3.5, 0], anchor: 'up' },
  ],
  edges: [['test', 'route'], ['route', 'service'], ['service', 'server']],
  paths: { request: { via: ['test', 'route', 'service', 'server'] } },
  acts: results.results.map<Act>((result, index) => {
    const [endpoint, expected] = endpoints[result.scenario_name]
    const t0 = index * 10
    return {
      id: index + 1, t0, t1: t0 + 10,
      kicker: `Original check ${index + 1} of ${results.results.length}`,
      title: `GET ${endpoint}`,
      path: 'request', tone: result.status === 'pass' ? 'positive' : 'negative',
      status: { label: result.scenario_name, value: result.status.toUpperCase() },
      facts: [['expected', `200 + ${expected}`], ['observed time', `${result.duration_seconds.toFixed(2)} s`], ['scope', 'pre-auth HTTP']],
      source: 'test-results.json',
      log: [
        { at: t0 + 1, kind: 'note', line: `# Original run: GET ${endpoint}` },
        { at: t0 + 3, kind: 'output', line: `"scenario_name": "${result.scenario_name}",` },
        { at: t0 + 5, kind: 'positive', line: `"status": "${result.status}",` },
        { at: t0 + 7, kind: 'output', line: `"duration_seconds": ${result.duration_seconds}` },
      ],
    }
  }),
  }
}

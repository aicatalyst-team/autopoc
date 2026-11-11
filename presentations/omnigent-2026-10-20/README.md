# Omnigent AutoPoC run review

A stakeholder presentation of run `autopoc-omnigent-8554` on 20 October 2026.
Fourteen main slides, including two animated TopoLoop walkthroughs, followed
by four evidence slides.

## Present or edit

Requires Node.js 22.18 or newer. From this directory:

```bash
npm ci
npm run dev
```

Open <http://localhost:3030/>. Edit `slides.md` and `style.css` to revise the
deck. Speaker notes include evidence references, precise scope and caveats.
The setup topology is slide 7 and the five-check scenario flow is slide 8.
Use the arrow keys to navigate, or open `/presenter/` for presenter mode.

## Build and export

```bash
npm run build
npm run preview
npm run export
```

The browser build is in `dist/`; preview it at <http://localhost:4173/>.
The PDF is `output/omnigent-autopoc.pdf`. Slidev's PDF exporter uses Chromium.
If browser download is unavailable, use an installed compatible browser:

```bash
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm ci
npm run export -- --executable-path /usr/bin/google-chrome
```

`output/omnigent-presentation.zip`, when supplied, contains editable sources,
the lock file, evidence, the PDF and the built static website. Extract it and
serve `dist/` from a static server with SPA fallback, or use the commands above.
Opening `dist/index.html` directly as a `file:` URL is not supported.

## Topology and scenario animations

TopoLoop's unmodified runtime is vendored under `vendor/topoloop/`, pinned to
commit `8631cf7955ebf40a579aab4ce3d0cca50d215c21`. Its MIT license and bundled
font OFL are preserved there and included in the browser build's assets.

- `specs/omnigent-setup.ts` defines eight resources and three acts: build/push,
  deployment/storage and HTTPS access. Namespace names appear in node labels.
- `specs/omnigent-scenarios.ts` builds five acts from the original archived
  test results. Each request follows runner, Route, Service and server.
- `components/RunTopoLoop.vue` integrates Slidev, the common red/charcoal theme,
  inactive-slide cleanup, reduced-motion preference and still-frame/play control.
- Browser loops are 30 and 50 seconds. Playback timing is illustrative, and
  displayed HTTP durations come from the original results. No deployed test
  endpoint is called by these animations.
- Node labels follow the active path for readability. The existing static
  architecture slide retains the full serving/storage diagram.
- PDF/print export freezes setup at 7 seconds and scenarios at 47 seconds.
  The scenario status board retains all five original outcomes.
- Log lines prefixed with `#` explain the reconstruction. Other excerpts quote
  original logs or the original result JSON.

These are animated explanations of the saved evidence, not original traces,
packet captures, scenario recordings or new test runs. To edit the graphs,
change the specs rather than the vendored library.

## Evidence and interpretation

`public/evidence/index.json` maps slide claims to sources. Generated reports
and manifests are preserved from commit
`f2d3c4d8183de4d67f5a2cb3135c3b653211f6e6` of
`aicatalyst-team/omnigent`. Their SHA-256 hashes are in the index.

- Test JSON was extracted from the original runner log. Tests were not replayed.
- The archived test script uses `.py.txt` to preserve exact source bytes and
  avoid modifying historical evidence through automatic Python formatting.
  The index links to the executable original on GitHub.
- Runner and both build logs are provided as sanitized `.log.gz` files. Sensitive
  lines and opaque values have been removed. Raw logs, Secret resources and
  full cluster objects are excluded from the presentation package.
- `execution-events.json` selects timestamped activity from the sanitized
  runner log. It is execution history, not a distributed trace export.
- No run-specific Playwright trace, distributed trace export or original UI
  recording was found in the archived outputs. The original five tests used
  HTTP requests and did not capture browser interactions.
- The screenshot in `public/assets/` is a later unauthenticated observation.
  Capture time and URL are in `capture.json`. No account was created.
- Job/build times describe the original run. The live-object checks and UI
  screenshot are separately labeled later observations.
- Local evidence links require the browser deck's server. The PDF also retains
  external GitHub links; use the browser deck or bundled index for local files.

## Material limitations

The five checks establish control-plane reachability and expected response
text. They do not validate login, agent execution, inference, persistence,
load, failover or production readiness. Request durations are individual
observations, not performance benchmarks. The 94m31s job duration includes
report/blog work and artifact finalization. No labor/cost baseline was measured.

The actual deployment uses temporary `emptyDir` storage. The run ended with a
stale `autopoc` source branch while the corrected manifest was archived on
`autopoc-artifacts`. Google Docs publication failed.

The report claims `restricted-v3` compliance. A later read-only check verified
the running pod's `openshift.io/scc` annotation is `restricted-v2`. The archived
manifest also puts `hostUsers` under `securityContext`; Kubernetes defines
that field directly on PodSpec, and it is absent from the live object. The
deck records this discrepancy rather than silently altering the source.
Review the manifest before reuse. See the [Kubernetes field reference](https://kubernetes.io/docs/concepts/workloads/pods/user-namespaces/).

This directory is a presentation of one completed run. Automatic pipeline
integration, narration and video composition remain separate work.

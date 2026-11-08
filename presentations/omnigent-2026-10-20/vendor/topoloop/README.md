<p align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="docs/brand/logo-light.png">
    <img alt="TopoLoop: walk any system, one path at a time" src="docs/brand/logo-dark.png" width="560">
  </picture>
</p>

<p align="center">
  <a href="https://github.com/r-bit-rry/topoloop/actions/workflows/check.yml"><img alt="check" src="https://github.com/r-bit-rry/topoloop/actions/workflows/check.yml/badge.svg"></a>
  <a href="https://github.com/r-bit-rry/topoloop/releases/tag/v0.1.0"><img alt="release v0.1.0" src="https://img.shields.io/badge/release-v0.1.0-0a1f3c"></a>
  <a href="LICENSE"><img alt="license MIT" src="https://img.shields.io/badge/license-MIT-0a1f3c"></a>
  <a href="https://nodejs.org"><img alt="node 22.18+" src="https://img.shields.io/badge/node-22.18%2B-0a1f3c?logo=nodedotjs&logoColor=white"></a>
  <br>
  <a href="https://vuejs.org"><img alt="Vue 3" src="https://img.shields.io/badge/Vue-3-0a1f3c?logo=vuedotjs&logoColor=white"></a>
  <a href="https://threejs.org"><img alt="three.js" src="https://img.shields.io/badge/three.js-WebGL-0a1f3c?logo=threedotjs&logoColor=white"></a>
  <a href="https://sli.dev"><img alt="Slidev" src="https://img.shields.io/badge/Slidev-ready-0a1f3c?logo=slidev&logoColor=white"></a>
  <a href="https://ffmpeg.org"><img alt="exports mp4, webm, gif, png" src="https://img.shields.io/badge/export-mp4%20%C2%B7%20webm%20%C2%B7%20gif%20%C2%B7%20png-ee0000"></a>
</p>

Animated, looping graph walkthroughs for slides. You describe a graph and a
few acts in one TypeScript file; TopoLoop renders it as a 3D loop that plays
while you talk, on a [Slidev](https://sli.dev) slide, in any web page, or
exported to mp4 or gif.

Each act walks one path through the graph. The walk, the nodes it touches and
the group around them take the act's tone (positive, negative or neutral), and
optional panels show a status badge, a board of every act's status, a row of
facts and a log that types itself in. What a walk means is yours: a request
through a service mesh, a batch through a data pipeline, a user through
onboarding, an attacker against a boundary.

<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/demo-light.gif">
  <img alt="TopoLoop playing act 1 of specs/checkout-demo.ts" src="docs/demo.gif" width="100%">
</picture>

<p align="center"><sub>Act 1 of <a href="specs/checkout-demo.ts"><code>specs/checkout-demo.ts</code></a>, 10 s of a 40 s loop. Below, <a href="specs/pipeline-demo.ts"><code>specs/pipeline-demo.ts</code></a> at t=15 s.</sub></p>

![A data pipeline spec: a renamed column stops one batch at the transform stage](docs/pipeline.png)

## Get started

Needs Node 22.18 or newer (it runs the `.ts` sources directly). Video export
also needs ffmpeg (`brew install ffmpeg`, `apt install ffmpeg`).

```sh
git clone https://github.com/r-bit-rry/topoloop && cd topoloop
npm install
npm run dev:standalone
```

Open `http://localhost:5199/?spec=pipeline-demo`. Three specs ship in
`specs/`:

| spec | what it shows |
|---|---|
| `minimal` | three nodes, one act: the smallest spec that renders |
| `pipeline-demo` | a nightly data load; one batch is rejected at transform |
| `checkout-demo` | four security checks against a checkout service |

Page options go in the query string: `theme=dark` or `theme=light`, `t=15` (freeze at second
15), `seed=1` (repeatable effects), `w=1280&h=720` (fixed stage size),
`credits`.

## Write your own

Copy the minimal spec and open it in the browser:

```sh
cp specs/minimal.ts specs/my-system.ts
# then open http://localhost:5199/?spec=my-system
```

```ts
import type { Spec } from '../src/spec.ts'

export const spec: Spec = {
  title: 'Minimal',
  loop: 10,
  groups: [{ id: 'app', label: 'app' }],
  nodes: [
    { id: 'web', label: 'web', group: 'app' },
    { id: 'api', label: 'api', group: 'app' },
    { id: 'db', label: 'db', kind: 'store' },
  ],
  edges: [['web', 'api'], ['api', 'db']],
  paths: { read: { via: ['web', 'api', 'db'] } },
  acts: [{
    id: 1, t0: 0, t1: 10, path: 'read',
    title: 'A read reaches the database',
  }],
}
```

Then add what you need to each act. Every panel appears only when a field
feeds it:

```ts
tone: 'negative',                                  // colour of the walk and its panels
status: { label: 'schema check', value: 'REJECTED' }, // badge, and a row on the board
facts: [['batch', '0412'], ['cause', 'renamed column']], // up to 3 cells under the graph
log: [{ at: 2, kind: 'negative', line: 'SchemaError: missing column "total"' }], // log lines
stopAt: 0.6,                                       // the walk halts 60% along the path
```

A mistake (a path through two nodes with no edge, a log line outside its act, a
gap between acts) prints on the page in place of the animation, naming the
field. [docs/AUTHORING.md](docs/AUTHORING.md) lists every field, where it
shows on screen, what is checked, and what makes an act read well.

## Show it

**Export a video or image**

```sh
npm run export -- --spec pipeline-demo --format mp4 --out out/pipeline.mp4
npm run export -- --spec pipeline-demo --format gif --from 0 --to 10
npm run export -- --spec pipeline-demo --format png --from 15
```

`mp4` (default), `gif`, `webm`, `png`. WebGL renders on the GPU when there is
one and falls back to the CPU; the first line of output names the renderer.
Every flag is in [AUTHORING.md](docs/AUTHORING.md#6-export-a-file).

**In a Slidev deck**

`npm run dev` opens `deck/slides.md`, where slide 2 plays a spec through
`deck/components/TopoLoopSlide.vue`. Point that file's import at your spec,
or add a component like it to your own deck:

```vue
<script setup lang="ts">
import TopoLoop from '../../src/TopoLoop.vue'   // path from your deck to this repo
import { spec } from '../../specs/pipeline-demo'
</script>

<template>
  <TopoLoop :spec="spec" />
</template>
```

```md
---
layout: none
---

<TopoLoopSlide />
```

**In any web page**

```ts
import { mount } from './topoloop/src/index.ts'
import { spec } from './topoloop/specs/pipeline-demo.ts'

mount(document.getElementById('stage')!, spec, { theme: 'light', seed: 1 })
```

Both need a bundler that compiles `.vue` files, such as Vite. TopoLoop is not
on npm; copy the repo or add it as a git submodule.

Component props. `mount()` takes the same options except `mascot`:

| prop | default | what |
|---|---|---|
| `spec` | required | the animation |
| `theme` | `'blueprint'` | `'blueprint'`, `'dark'`, `'light'`, or a partial theme merged over blueprint |
| `seed` | `null` | effect randomness; a number repeats exactly |
| `freezeAt` | `null` | hold one second, for a PDF or poster frame |
| `rate` | `1` | clock multiplier, `0.5` to rehearse |
| `credits` | `false` | show `spec.credits` in the header |
| `mascot` | `null` | `() => { root, idle?, setAlert? }`, a THREE object for the top right |

## Extend it

- **Colours:** a theme is one object of colour tokens. Start from
  `themes.blueprint` or pass a partial to the `theme` prop.
  [AUTHORING.md section 5](docs/AUTHORING.md#5-write-a-custom-theme).
- **Node shapes:** add the name to `NodeKind` in `src/spec.ts`, a mesh to
  `NODE_KINDS` in `src/topology.ts`, and a colour to each built-in theme. The
  compiler points at every theme that lacks it.
- **Log kinds and tones** are closed unions in `src/spec.ts` with a colour
  token each in `src/theme.ts`. Extend both together.
- **Motion:** `src/frame.ts` turns a moment into a plain state object (camera,
  where the walk is, what glows). It has no THREE scene and no DOM, so a new
  effect can be unit tested before it is drawn.

## Layout

```
specs/             one file per animation
src/spec.ts        the Spec type, validate(), actAt(), board()
src/layout.ts      positions for nodes that do not set one
src/topology.ts    THREE meshes: nodes, edges, group shells
src/frame.ts       time -> camera, walk position and effect state
src/theme.ts       colour tokens: blueprint (default), dark, light
src/TopoLoop.vue   the component: scene, panels, labels
src/mount.ts       mount() for pages that are not Vue apps
scripts/export.mjs mp4 / gif / webm / png export
scripts/check-render.mjs  headless render and screenshot compare
deck/              a Slidev deck that plays a spec
docs/AUTHORING.md  every spec field, themes, export flags
docs/LESSONS.md    why the rendering works the way it does
docs/BRAND.md      logo, icon, palette, motto, vocabulary
```

## Contribute

```sh
npm run check     # typecheck, unit tests, headless render of both demos
```

`npm run check` must pass before a pull request, and CI runs the same command
on every push. The render step fails on a blank canvas, a page error, a spec
error, or text drawn in a font TopoLoop does not bundle. On Linux it also
compares each frame to a stored screenshot in `test/golden/`.

A change to how things look will fail that screenshot compare. Chrome draws
text slightly differently on macOS, so the screenshots are recorded in the
same Linux container CI uses. With docker or podman installed:

```sh
npm run render:ci    # compare in the CI container
npm run golden:ci    # re-record, then look at test/golden/*.png before committing
```

Guidelines:

- A new spec field needs a row in the table in `docs/AUTHORING.md`, a check in
  `validate()` if a wrong value would render as a blank or misleading slide,
  and a test in `test/spec.test.ts`.
- Keep specs free of colour. Colour belongs to themes.
- One change per pull request, with a still or a short export when it changes
  what is on screen.

## Scope

TopoLoop has no force-directed layout, no interaction and no data import. A
graph too large to place by group or by hand is too large to read from the
back of a room. An importer that turns Prometheus or `kubectl` output into a
spec is a reasonable separate tool; the acts still have to be written by
someone who knows the story.

Built for the AGNTCon 2026 OpenClaw isolation talk, where it closed the Q&A.

## License

MIT, see [LICENSE](LICENSE). The bundled Red Hat Display and Red Hat Mono
fonts are under the SIL Open Font License 1.1
([src/fonts/OFL.txt](src/fonts/OFL.txt)).

// Embed TopoLoop in a page that is not a Vue app.
//
//   import { mount } from 'topoloop'
//   import { spec } from './my-spec'
//   mount(document.getElementById('stage')!, spec, { theme: 'light', seed: 1 })

import { createApp, h, type App } from 'vue'
import TopoLoop from './TopoLoop.vue'
import type { Spec } from './spec.ts'
import type { ThemeInput } from './theme.ts'

export interface MountOptions {
  theme?: ThemeInput
  /** effect randomness. null = fresh each mount, number = repeatable */
  seed?: number | null
  /** freeze at this second, for a poster frame */
  freezeAt?: number | null
  rate?: number
  credits?: boolean
}

/** Returns the Vue app, so the caller can `.unmount()`. */
export function mount(el: Element, spec: Spec, opts: MountOptions = {}): App {
  const app = createApp({ render: () => h(TopoLoop, { spec, ...opts }) })
  app.mount(el)
  return app
}

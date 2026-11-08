// Randomness for visual effects only (starfield, shard spray). Topology never
// takes randomness. seed null means a fresh look each mount; a number repeats.
export type Rng = () => number

export function rng(seed: number | null = null): Rng {
  if (seed == null) return Math.random
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

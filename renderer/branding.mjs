/** Verify committed brand assets before generating output. */
import { readFile, lstat } from 'node:fs/promises'
import { join } from 'node:path'
import { createHash } from 'node:crypto'

export async function verifyBrandAssets(root) {
  const manifest = JSON.parse(await readFile(join(root, 'manifest.json'), 'utf8'))
  const expected = ['licenses/OFL.txt', 'licenses/AUTHORS.txt', 'logos/redhat-logo-standard.svg', 'logos/redhat-hat-standard.svg',
    ...['Display', 'Text', 'Mono'].flatMap(family => ['Regular', 'Medium', 'Bold'].map(weight => `fonts/RedHat${family}-${weight}.woff2`))].sort()
  if (manifest.schema_version !== 1 || !Array.isArray(manifest.files)
      || JSON.stringify(manifest.files.map(f => f.path).sort()) !== JSON.stringify(expected))
    throw new Error('Required brand asset inventory is incomplete')
  for (const entry of manifest.files) {
    const path = join(root, entry.path)
    const stat = await lstat(path).catch(() => null)
    if (!stat?.isFile() || stat.isSymbolicLink()) throw new Error(`Required brand asset missing: ${entry.path}`)
    const data = await readFile(path)
    if (data.length !== entry.size || createHash('sha256').update(data).digest('hex') !== entry.sha256)
      throw new Error(`Brand asset integrity failed: ${entry.path}`)
  }
  return manifest
}

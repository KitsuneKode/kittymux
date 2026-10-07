// Rewrites ^ and ~ ranges in package.json to the exact installed version, so a rebuild next year is the build of today.
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'

const root = new URL('..', import.meta.url).pathname
const pkgPath = join(root, 'package.json')
const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'))
let changed = 0
for (const section of ['dependencies', 'devDependencies']) {
  for (const [name, range] of Object.entries(pkg[section] ?? {})) {
    if (!/^[\^~]/.test(range)) continue
    const manifest = join(root, 'node_modules', name, 'package.json')
    if (!existsSync(manifest)) throw new Error(`pin-exact: ${name} is not installed; run bun install first`)
    const { version } = JSON.parse(readFileSync(manifest, 'utf8'))
    pkg[section][name] = version
    changed++
  }
}
writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n')
console.log(`pinned ${changed} dependencies to exact versions`)

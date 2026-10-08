// bun scripts/patch-routes.mjs <build dir>: narrows the "immutable for a year" cache rule that the Nitro Vercel preset puts on EVERYTHING under /assets/.
// Only files whose names carry a content hash (index-CPW22bKk.js) can be immutable; the screenshots and docs images under /assets/ keep the same name when they change,
// and a year of caching would hide every update from returning visitors. The build directory is .vercel/output/static; the config is one level up.
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const IMMUTABLE = 'public, max-age=31536000, immutable'
const SHORT = 'public, max-age=86400, stale-while-revalidate=604800'
// a Vite content hash: "-" + 8 URL-safe characters right before the extension, with at least one capital or digit ("this-tab" in where-is-this-tab.png is not a hash).
// A real hash that happens to have neither gets the short rule: the safe direction.
const BODY = '(?:.*/)?[^/]*-(?=[A-Za-z0-9_-]{8}\\.)(?=[a-z_-]*[A-Z0-9])[A-Za-z0-9_-]{8}\\.[a-z0-9]+'
export const HASHED = `/assets/${BODY}`
// every other file under /assets/: a lookahead keeps hashed files out, so no later rule can overwrite their immutable header
export const UNHASHED = `/assets/(?!${BODY}$)(.*)`

export function patchRoutes(config) {
  const out = structuredClone(config)
  // a rule that only sets headers must not end route matching (so the security headers and the cache rule both apply, and the file or page is still served)
  for (const r of out.routes) if (r.headers && !r.dest && !r.handle && !r.status) r.continue = true
  const i = out.routes.findIndex((r) => r.src === '/assets/(.*)' && r.headers?.['cache-control'] === IMMUTABLE)
  if (i === -1) return { config: out, changed: false }
  out.routes[i] = { ...out.routes[i], src: HASHED }
  // the rest of /assets/ (unhashed images) gets the short rule, after the immutable one so a hashed file never matches it
  out.routes.splice(i + 1, 0, { src: UNHASHED, headers: { 'cache-control': SHORT }, continue: true })
  // the short rules nitro wrote for /assets/shots and /og.png are now redundant for /assets/shots; keep them (they are exact)
  return { config: out, changed: true }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dir = process.argv[2]
  const file = join(dir, '..', 'config.json')
  if (!dir || !existsSync(file)) { console.error('usage: bun scripts/patch-routes.mjs <build dir> (config.json must be next to it)'); process.exit(2) }
  const { config, changed } = patchRoutes(JSON.parse(readFileSync(file, 'utf8')))
  if (!changed) { console.error('patch-routes: no "/assets/(.*)" immutable rule found: the Nitro preset changed, so check the cache rules by hand'); process.exit(1) }
  writeFileSync(file, JSON.stringify(config, null, 2) + '\n')
  console.log('routes: immutable caching now only for content-hashed files')
}

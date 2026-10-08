// bun scripts/gen-github.mjs: the repository's star count, read once at build time into src/generated/github.json. The page never calls GitHub from the visitor's browser.
// A failure (offline, rate limit) is not a build failure: the count is then null and the pages show the button without a number.
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const REPO = 'KitsuneKode/kittymux'
const out = join(fileURLToPath(new URL('..', import.meta.url)), 'src/generated/github.json')

export function parseStars(body) {
  const n = body?.stargazers_count
  return Number.isInteger(n) && n >= 0 ? n : null
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  let stars = null
  try {
    const headers = { accept: 'application/vnd.github+json', 'user-agent': 'kittymux-site-build' }
    if (process.env.GITHUB_TOKEN) headers.authorization = `Bearer ${process.env.GITHUB_TOKEN}`
    const res = await fetch(`https://api.github.com/repos/${REPO}`, { headers, signal: AbortSignal.timeout(6000) })
    if (res.ok) stars = parseStars(await res.json())
    else console.warn(`github: ${res.status} ${res.statusText}; the star count will be left out`)
  } catch (e) {
    console.warn(`github: ${e.message}; the star count will be left out`)
  }
  mkdirSync(join(out, '..'), { recursive: true })
  writeFileSync(out, JSON.stringify({ repo: REPO, stars }) + '\n')
  console.log(`github: ${stars === null ? 'no star count' : `${stars} stars`}`)
}

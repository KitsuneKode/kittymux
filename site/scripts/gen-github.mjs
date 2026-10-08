// bun scripts/gen-github.mjs: what GitHub knows about the repository (stars, forks, open issues, last push) and about each project in the footer (stars), read once at build time into
// src/generated/github.json. The page never calls GitHub from the visitor's browser. A failure (offline, rate limit) is not a build failure: those numbers are then null and the pages leave them out.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const REPO = 'KitsuneKode/kittymux'
const root = fileURLToPath(new URL('..', import.meta.url))
const out = join(root, 'src/generated/github.json')

const count = (n) => (Number.isInteger(n) && n >= 0 ? n : null)

/** The few fields of a repository the site shows. Anything that is not a plain number or a date string is null. */
export function parseRepo(body) {
  const pushed = typeof body?.pushed_at === 'string' && !Number.isNaN(Date.parse(body.pushed_at)) ? body.pushed_at : null
  return { stars: count(body?.stargazers_count), forks: count(body?.forks_count), issues: count(body?.open_issues_count), pushed }
}
export const parseStars = (body) => parseRepo(body).stars

/** The footer's repository names, read from src/lib/projects.ts (one list, not two). */
export function projectRepos(source) {
  return [...source.matchAll(/repo:\s*'([A-Za-z0-9._-]+)'/g)].map((m) => m[1])
}

async function get(path) {
  const headers = { accept: 'application/vnd.github+json', 'user-agent': 'kittymux-site-build' }
  if (process.env.GITHUB_TOKEN) headers.authorization = `Bearer ${process.env.GITHUB_TOKEN}`
  try {
    const res = await fetch(`https://api.github.com/repos/${path}`, { headers, signal: AbortSignal.timeout(6000) })
    if (res.ok) return await res.json()
    console.warn(`github: ${path}: ${res.status} ${res.statusText}`)
  } catch (e) {
    console.warn(`github: ${path}: ${e.message}`)
  }
  return null
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const main = parseRepo(await get(REPO))
  const projects = {}
  const owner = REPO.split('/')[0]
  const names = projectRepos(readFileSync(join(root, 'src/lib/projects.ts'), 'utf8'))
  for (const [name, body] of await Promise.all(names.map(async (n) => [n, await get(`${owner}/${n}`)]))) projects[name] = parseRepo(body).stars
  mkdirSync(join(out, '..'), { recursive: true })
  writeFileSync(out, JSON.stringify({ repo: REPO, ...main, projects }) + '\n')
  console.log(`github: ${main.stars === null ? 'no numbers' : `${main.stars} stars, ${main.forks} forks, ${main.issues} open issues`}; ${Object.values(projects).filter((v) => v !== null).length}/${names.length} projects`)
}

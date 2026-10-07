// docs/ is the only place prose lives. This validates it for the site and copies it into content/docs.
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const walk = (dir) =>
  readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    return statSync(p).isDirectory() ? walk(p) : [p]
  })

/** The site URL of a docs file: docs/index.mdx -> /docs, docs/users/index.mdx -> /docs/users, docs/users/a.mdx -> /docs/users/a */
export function urlOf(docsDir, file) {
  const rel = relative(docsDir, file).replace(/\\/g, '/').replace(/\.mdx?$/, '')
  const parts = rel.split('/').filter((p) => p !== 'index')
  return '/' + ['docs', ...parts].join('/')
}

function frontmatter(text) {
  const m = /^---\n([\s\S]*?)\n---\n/.exec(text)
  const out = {}
  if (m) for (const line of m[1].split('\n')) {
    const kv = /^([A-Za-z_-]+):\s*(.*)$/.exec(line)
    if (kv) out[kv[1]] = kv[2].trim()
  }
  return { fields: out, hasBlock: Boolean(m) }
}

export function validateDocs(docsDir, assetsDir) {
  const errors = []
  const assets = new Set()
  const files = walk(docsDir).filter((f) => /\.mdx?$/.test(f))
  const pages = new Set(files.map((f) => urlOf(docsDir, f)))
  const shown = (f) => join('docs', relative(docsDir, f)).replace(/\\/g, '/')

  for (const file of files) {
    const text = readFileSync(file, 'utf8')
    const { fields, hasBlock } = frontmatter(text)
    if (!hasBlock) errors.push(`${shown(file)}: no frontmatter block`)
    for (const key of ['title', 'description']) if (!fields[key]) errors.push(`${shown(file)}: frontmatter is missing "${key}"`)

    let fenced = false
    text.split('\n').forEach((line, i) => {
      if (/^\s*```/.test(line)) { fenced = !fenced; return }
      if (fenced) return
      line = line.replace(/`[^`]*`/g, '')                              // an inline-code example is not a link
      for (const m of line.matchAll(/\]\((\/docs[^)\s]*)\)/g)) {
        const target = m[1].split('#')[0].replace(/\/$/, '') || '/docs'
        if (!pages.has(target)) errors.push(`${shown(file)}:${i + 1}: link to ${m[1]} but there is no such page`)
      }
      for (const m of line.matchAll(/\]\((\/assets\/[^)\s]+)\)/g)) {
        const rel = m[1].replace('/assets/', '')
        if (existsSync(join(assetsDir, rel))) assets.add(rel)
        else errors.push(`${shown(file)}:${i + 1}: image ${m[1]} does not exist in assets/`)
      }
    })
  }

  for (const meta of walk(docsDir).filter((f) => f.endsWith('meta.json'))) {
    let data
    try { data = JSON.parse(readFileSync(meta, 'utf8')) } catch (e) { errors.push(`${shown(meta)}: not valid JSON (${e.message})`); continue }
    const dir = dirname(meta)
    for (const entry of data.pages ?? []) {
      if (/^(---|\.\.\.|\[|!)/.test(entry)) continue                 // separators, rest and links are Fumadocs syntax, not pages
      const ok = [`${entry}.mdx`, `${entry}.md`, join(entry, 'index.mdx'), join(entry, 'meta.json')].some((p) => existsSync(join(dir, p)))
      if (!ok) errors.push(`${shown(meta)}: lists "${entry}" but no such page or folder exists`)
    }
  }
  return { errors, pages: [...pages], assets: [...assets] }
}

export function syncDocs({ docsDir, assetsDir, outDir, publicDir }) {
  const { errors, pages, assets } = validateDocs(docsDir, assetsDir)
  if (errors.length) throw new Error(`docs sync failed:\n  ${errors.join('\n  ')}`)
  rmSync(outDir, { recursive: true, force: true })
  mkdirSync(outDir, { recursive: true })
  for (const file of walk(docsDir)) {
    if (!/\.(mdx?|json)$/.test(file)) continue
    const dest = join(outDir, relative(docsDir, file))
    mkdirSync(dirname(dest), { recursive: true })
    cpSync(file, dest)
  }
  for (const rel of assets) {                                         // only what the pages show: the notification icons and templates stay out
    const dest = join(publicDir, 'assets', rel)
    mkdirSync(dirname(dest), { recursive: true })
    cpSync(join(assetsDir, rel), dest)
  }
  return { pages }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const repo = fileURLToPath(new URL('../..', import.meta.url))
  const site = join(repo, 'site')
  // Only the published tree: index, users/, developer/. The flat notes in docs/ (audits, checklists) are not site pages.
  const stage = mkdtempSync(join(tmpdir(), 'kmx-stage-'))
  for (const entry of ['index.mdx', 'meta.json', 'users', 'developer']) cpSync(join(repo, 'docs', entry), join(stage, entry), { recursive: true })
  try {
    const { pages } = syncDocs({ docsDir: stage, assetsDir: join(repo, 'assets'), outDir: join(site, 'content/docs'), publicDir: join(site, 'public') })
    console.log(`synced ${pages.length} pages`)
  } catch (e) {
    console.error(String(e.message ?? e).replaceAll(stage, 'docs'))
    process.exit(1)
  } finally {
    rmSync(stage, { recursive: true, force: true })
  }
}

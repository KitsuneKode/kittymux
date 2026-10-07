// CHANGELOG.md -> src/generated/CHANGELOG.md (read raw by the /changelog route). Refuses an empty or release-less file.
import { copyFileSync, mkdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = fileURLToPath(new URL('../..', import.meta.url))
const src = join(repo, 'CHANGELOG.md')
if (!/^## /m.test(readFileSync(src, 'utf8'))) { console.error('gen-changelog: CHANGELOG.md has no "## " release heading'); process.exit(1) }
const out = join(repo, 'site/src/generated/CHANGELOG.md')
mkdirSync(join(out, '..'), { recursive: true })
copyFileSync(src, out)
console.log('changelog: copied')

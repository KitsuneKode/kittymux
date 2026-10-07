import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const repo = fileURLToPath(new URL('../..', import.meta.url))
const out = join(repo, 'site/src/generated/facts.json')
const run = spawnSync('python3', [join(repo, 'tools/export_facts.py')], { encoding: 'utf8' })
if (run.status !== 0) {
  console.error(`gen-facts: tools/export_facts.py failed\n${run.stderr}`)
  process.exit(1)
}
let facts
try { facts = JSON.parse(run.stdout) } catch (e) { console.error(`gen-facts: output is not JSON (${e.message})`); process.exit(1) }
if (!facts.chords || !facts.agents?.length || !facts.states?.length) {
  console.error('gen-facts: facts are empty; refusing to build a site with an empty Keys page')
  process.exit(1)
}
mkdirSync(join(out, '..'), { recursive: true })
writeFileSync(out, JSON.stringify(facts, null, 2) + '\n')
console.log(`facts: ${facts.chords} chords, ${facts.agents.length} agents, ${facts.states.length} states`)

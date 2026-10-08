import { expect, test } from 'bun:test';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { ICONS } from './icons';

function metas(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? metas(p) : n === 'meta.json' ? [p] : [];
  });
}

test('every icon a meta.json names is one the site ships', () => {
  const used = metas(join(import.meta.dir, '../../content/docs')).map((f) => JSON.parse(readFileSync(f, 'utf8')).icon).filter(Boolean);
  expect(used.length).toBeGreaterThan(0);
  for (const name of used) expect(Object.keys(ICONS)).toContain(name);
});

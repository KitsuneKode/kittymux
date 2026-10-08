import { expect, test } from 'bun:test'
import { parseRepo, parseStars, projectRepos } from './gen-github.mjs'

test('a repository is reduced to plain counts and a date, and anything odd is null', () => {
  expect(parseRepo({ stargazers_count: 41, forks_count: 3, open_issues_count: 2, pushed_at: '2026-10-08T07:00:00Z' })).toEqual({ stars: 41, forks: 3, issues: 2, pushed: '2026-10-08T07:00:00Z' })
  expect(parseRepo({ stargazers_count: 0 }).stars).toBe(0)
  for (const bad of [undefined, null, {}, { stargazers_count: '41', pushed_at: 'yesterday' }, { stargazers_count: -1 }, { stargazers_count: 1.5 }]) {
    const r = parseRepo(bad)
    expect([r.stars, r.pushed]).toEqual([null, null])
  }
  expect(parseStars({ stargazers_count: 7 })).toBe(7)
})

test('the footer projects are read from the one list in src/lib/projects.ts', () => {
  expect(projectRepos("{ repo: 'kunai' }, { repo: 'Kitsu-Lab' }, { name: 'x' }")).toEqual(['kunai', 'Kitsu-Lab'])
})

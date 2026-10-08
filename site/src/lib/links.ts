import { gitConfig } from './shared'
import data from '../generated/github.json'

export const REPO = `${gitConfig.user}/${gitConfig.repo}`
export const REPO_URL = `https://github.com/${REPO}`
export const ISSUES_URL = `${REPO_URL}/issues/new`
export const SPONSOR_URL = `https://github.com/sponsors/${gitConfig.user}`
export const AUTHOR_URL = `https://github.com/${gitConfig.user}`
export const ALL_PROJECTS_URL = `${AUTHOR_URL}?tab=repositories`

type Count = number | null
/** What GitHub said when the site was built (scripts/gen-github.mjs). Null means GitHub could not be reached: the pages then leave the number out rather than guess. */
export const github: { stars: Count; forks: Count; issues: Count; pushed: string | null; projects: Record<string, Count> } = {
  stars: data.stars ?? null,
  forks: data.forks ?? null,
  issues: data.issues ?? null,
  pushed: data.pushed ?? null,
  projects: (data.projects ?? {}) as Record<string, Count>,
}
/** The star count, zero included: an honest 0 beats a button that hides it. */
export const stars: Count = github.stars

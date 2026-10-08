import { gitConfig } from './shared'
import github from '../generated/github.json'

export const REPO = `${gitConfig.user}/${gitConfig.repo}`
export const REPO_URL = `https://github.com/${REPO}`
export const ISSUES_URL = `${REPO_URL}/issues/new`
export const SPONSOR_URL = `https://github.com/sponsors/${gitConfig.user}`
export const AUTHOR_URL = `https://github.com/${gitConfig.user}`
export const ALL_PROJECTS_URL = `${AUTHOR_URL}?tab=repositories`

/** Stars read at build time (scripts/gen-github.mjs); null when GitHub could not be reached. A count of 0 is not shown: an empty counter asks nobody to join. */
export const stars: number | null = typeof github.stars === 'number' && github.stars > 0 ? github.stars : null

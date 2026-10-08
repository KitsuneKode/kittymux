import { FAQ } from '@/components/landing/faq'
import { PROJECTS } from '@/lib/projects'
import { parseChangelog, parseInline } from '@/lib/inline'
import type { Facts } from '@/lib/facts'

/** What the search needs from a page that is not an MDX doc: the same shape Fumadocs' own pages produce, so the dialog treats every result alike. */
export type SiteIndex = {
  id: string
  title: string
  url: string
  description?: string
  breadcrumbs?: string[]
  structuredData: { headings: { id: string; content: string }[]; contents: { heading: string | undefined; content: string }[] }
}

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
const plain = (md: string) => parseInline(md).map((p) => p.v).join('')

/** /keys: one hit per chord, landing on its section. The ids are the ones KeyTable gives its section headings. */
export function keysIndex(keys: Facts['keys']): SiteIndex {
  return {
    id: '/keys',
    url: '/keys',
    title: 'Keys',
    description: 'Every key kittymux binds, grouped by what it does.',
    breadcrumbs: ['Reference'],
    structuredData: {
      headings: keys.map((s) => ({ id: `k-${slug(s.section)}`, content: s.section })),
      contents: keys.flatMap((s) => s.rows.map((r) => ({ heading: `k-${slug(s.section)}`, content: `${r.key}: ${plain(r.desc)}` }))),
    },
  }
}

/** /changelog: one hit per entry, landing on its release. The ids are the ones the changelog page gives its release headings. */
export function changelogIndex(md: string): SiteIndex {
  const releases = parseChangelog(md)
  return {
    id: '/changelog',
    url: '/changelog',
    title: 'Changelog',
    description: 'What changed in kittymux, newest first.',
    breadcrumbs: ['Reference'],
    structuredData: {
      headings: releases.map((r) => ({ id: `r-${slug(r.heading)}`, content: r.heading })),
      contents: releases.flatMap((r) => r.groups.flatMap((g) => g.items.map((item) => ({ heading: `r-${slug(r.heading)}`, content: `${g.name}: ${plain(item)}` })))),
    },
  }
}

/** The front page's questions and the other projects, so “does it send my data”, “sponsor” or “kunai” finds something. */
export function pageIndexes(): SiteIndex[] {
  return [
    {
      id: '/#faq',
      url: '/#faq',
      title: 'Questions people ask first',
      description: 'Privacy, typing into agents, supported agents, tmux, Wayland.',
      breadcrumbs: ['Home'],
      structuredData: { headings: [], contents: FAQ.map(([q, a]) => ({ heading: undefined, content: `${q} ${a}` })) },
    },
    {
      id: '/#support',
      url: '/#support',
      title: 'Sponsor and star',
      description: 'How to keep kittymux going: star it, sponsor it, open an issue.',
      breadcrumbs: ['Home'],
      structuredData: {
        headings: [],
        contents: [{ heading: undefined, content: 'Star kittymux on GitHub, sponsor the work on GitHub Sponsors, or open an issue with what broke or what is missing. kittymux is MIT licensed.' }],
      },
    },
    {
      id: '/#more-projects',
      url: '/#more-projects',
      title: 'More from KitsuneKode',
      description: 'Other projects by the same author.',
      breadcrumbs: ['Home'],
      structuredData: { headings: [], contents: PROJECTS.map((p) => ({ heading: undefined, content: `${p.name} (${p.kind}): ${p.blurb}` })) },
    },
  ]
}

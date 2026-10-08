import { gitConfig } from './shared'

export const SITE_NAME = 'kittymux'
export const REPO_URL = `https://github.com/${gitConfig.user}/${gitConfig.repo}`
/** Social preview, 1200x630 (scripts/og.mjs draws it from the site's own screenshots). */
export const OG_IMAGE = { path: '/og.png', width: 1200, height: 630, alt: 'kittymux: know which agent needs you. The docked panel lists tabs, one marked as needing you.' }

/**
 * The public address of the site, from VITE_SITE_URL at build time (for example https://example.org). Unset means "not deployed yet": the pages then carry no canonical URL,
 * no absolute image URL and no sitemap, rather than a made-up address that search engines would trust.
 */
export function siteUrl(env: string | undefined = import.meta.env?.VITE_SITE_URL): string {
  if (!env) return ''
  try {
    const u = new URL(env)
    if (u.protocol !== 'https:' && u.hostname !== 'localhost') return ''
    return u.origin + u.pathname.replace(/\/+$/, '')
  } catch {
    return ''
  }
}

export function absolute(path: string, base: string = siteUrl()): string {
  if (!base) return ''
  return base + (path === '/' ? '/' : path.replace(/\/+$/, ''))
}

type Meta = Record<string, string>
export type Head = { meta: Meta[]; links: Record<string, string>[]; scripts: { type: string; children: string }[] }

export type PageHeadInput = { title: string; description: string; path: string; type?: 'website' | 'article'; base?: string; ldJson?: object[] }

/** Everything a page says about itself to a search engine or a link preview. `title` is the full title as shown. */
export function pageHead({ title, description, path, type = 'website', base = siteUrl(), ldJson = [] }: PageHeadInput): Head {
  const url = absolute(path, base)
  const image = absolute(OG_IMAGE.path, base)
  const meta: Meta[] = [
    { title },
    { name: 'description', content: description },
    { property: 'og:site_name', content: SITE_NAME },
    { property: 'og:locale', content: 'en' },
    { property: 'og:type', content: type },
    { property: 'og:title', content: title },
    { property: 'og:description', content: description },
    { name: 'twitter:card', content: image ? 'summary_large_image' : 'summary' },
    { name: 'twitter:title', content: title },
    { name: 'twitter:description', content: description },
  ]
  if (url) meta.push({ property: 'og:url', content: url })
  if (image) meta.push({ property: 'og:image', content: image }, { property: 'og:image:width', content: String(OG_IMAGE.width) }, { property: 'og:image:height', content: String(OG_IMAGE.height) }, { property: 'og:image:alt', content: OG_IMAGE.alt }, { name: 'twitter:image', content: image })
  const links = url ? [{ rel: 'canonical', href: url }] : []
  // "<" is escaped so no string in the data can close the script element
  const scripts = ldJson.map((o) => ({ type: 'application/ld+json', children: JSON.stringify(o).replace(/</g, '\\u003c') }))
  return { meta, links, scripts }
}

export function softwareLd(base: string = siteUrl()) {
  return {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: SITE_NAME,
    description: 'A configuration pack that turns the kitty terminal into a multiplexer for AI coding agents: tabs, panes, session restore and a tab bar that shows which agent is working, waiting or done.',
    applicationCategory: 'DeveloperApplication',
    operatingSystem: 'Linux',
    license: 'https://opensource.org/license/mit',
    isAccessibleForFree: true,
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    codeRepository: REPO_URL,
    ...(base ? { url: base + '/' } : {}),
  }
}

export function faqLd(items: readonly (readonly [string, string])[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: items.map(([q, a]) => ({ '@type': 'Question', name: q, acceptedAnswer: { '@type': 'Answer', text: a } })),
  }
}

/** Breadcrumbs for a docs page: Docs > Section > Page. Absolute URLs are required, so none are made without a site URL. */
export function breadcrumbLd(trail: { name: string; path: string }[], base: string = siteUrl()) {
  if (!base) return null
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((t, i) => ({ '@type': 'ListItem', position: i + 1, name: t.name, item: absolute(t.path, base) })),
  }
}

import { gitConfig } from './shared'

export const SITE_NAME = 'kittymux'
export const REPO_URL = `https://github.com/${gitConfig.user}/${gitConfig.repo}`
/** Social preview, 1200x630 (scripts/gen-og.mjs renders it from the site's own fonts, mascot, cosmos backdrop, and live workspace capture). */
export const OG_IMAGE = {
  path: '/og.png',
  width: 1200,
  height: 630,
  alt: 'kittymux: Know which agent needs you — pixel tab bar, multi-account usage, inbox, and live workspace inside kitty.',
}

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

export function pageHead({ title, description, path, type = 'website', base = siteUrl(), ldJson = [] }: PageHeadInput): Head {
  const url = absolute(path, base)
  const image = absolute(OG_IMAGE.path, base)
  const meta: Meta[] = [
    { title },
    { name: 'description', content: description },
    { property: 'og:site_name', content: SITE_NAME },
    { property: 'og:locale', content: 'en_US' },
    { property: 'og:type', content: type },
    { property: 'og:title', content: title },
    { property: 'og:description', content: description },
    { name: 'twitter:card', content: image ? 'summary_large_image' : 'summary' },
    { name: 'twitter:title', content: title },
    { name: 'twitter:description', content: description },
  ]
  if (url) meta.push({ property: 'og:url', content: url })
  if (image) {
    meta.push(
      { property: 'og:image', content: image },
      { property: 'og:image:type', content: 'image/png' },
      { property: 'og:image:width', content: String(OG_IMAGE.width) },
      { property: 'og:image:height', content: String(OG_IMAGE.height) },
      { property: 'og:image:alt', content: OG_IMAGE.alt },
      { name: 'twitter:image', content: image },
      { name: 'twitter:image:alt', content: OG_IMAGE.alt },
    )
  }
  const links = url ? [{ rel: 'canonical', href: url }] : []
  const scripts = ldJson.map((o) => ({ type: 'application/ld+json', children: JSON.stringify(o).replace(/</g, '\\u003c') }))
  return { meta, links, scripts }
}

export function softwareLd(base: string = siteUrl()) {
  const shot = absolute('/assets/shots/workspace-dark.png', base)
  return {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: SITE_NAME,
    description: 'A configuration pack that turns the kitty terminal into a native workspace for AI coding agents: pixel tab bar, multi-account usage, inbox, Kitty 0.50 pane controls, Quickshell client, and session restore.',
    applicationCategory: 'DeveloperApplication',
    operatingSystem: 'Linux',
    license: 'https://opensource.org/license/mit',
    isAccessibleForFree: true,
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    author: { '@type': 'Person', name: 'KitsuneKode', url: `https://github.com/${gitConfig.user}` },
    codeRepository: REPO_URL,
    featureList: [
      'Cairo and Slang pixel tab bar inside kitty',
      'Graphical Agents, multi-account Usage, and Inbox panel',
      'Direct Claude Code, Codex, OpenCode, and OSC 7501 status hooks',
      'Kitty 0.50 scoped pane controls and attention dividers',
      'Quickshell native Wayland sidebar client',
      'Session save and conversation-aware restore',
    ],
    ...(shot ? { screenshot: shot } : {}),
    ...(base ? { url: base + '/' } : {}),
  }
}

export function websiteLd(base: string = siteUrl()) {
  if (!base) return null
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: SITE_NAME,
    url: base + '/',
    description: 'Documentation, keymap, changelog, and setup guide for kittymux.',
    publisher: { '@type': 'Person', name: 'KitsuneKode', url: `https://github.com/${gitConfig.user}` },
    sameAs: [REPO_URL],
  }
}

export function faqLd(items: readonly (readonly [string, string])[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: items.map(([q, a]) => ({ '@type': 'Question', name: q, acceptedAnswer: { '@type': 'Answer', text: a } })),
  }
}

export function techArticleLd({ title, description, path }: { title: string; description: string; path: string }, base: string = siteUrl()) {
  const url = absolute(path, base)
  if (!url) return null
  return {
    '@context': 'https://schema.org',
    '@type': 'TechArticle',
    headline: title,
    description,
    url,
    author: { '@type': 'Person', name: 'KitsuneKode', url: `https://github.com/${gitConfig.user}` },
    isPartOf: { '@type': 'WebSite', name: SITE_NAME, url: base + '/' },
  }
}

export function breadcrumbLd(trail: { name: string; path: string }[], base: string = siteUrl()) {
  if (!base) return null
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((t, i) => ({ '@type': 'ListItem', position: i + 1, name: t.name, item: absolute(t.path, base) })),
  }
}

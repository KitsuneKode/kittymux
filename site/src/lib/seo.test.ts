import { expect, test } from 'bun:test'
import { absolute, breadcrumbLd, faqLd, pageHead, siteUrl, softwareLd } from './seo'

test('the site URL is read strictly: https only, no trailing slash, nothing when unset or garbage', () => {
  expect(siteUrl(undefined)).toBe('')
  expect(siteUrl('')).toBe('')
  expect(siteUrl('not a url')).toBe('')
  expect(siteUrl('http://example.org')).toBe('')
  expect(siteUrl('https://example.org/')).toBe('https://example.org')
  expect(siteUrl('https://example.org/kittymux///')).toBe('https://example.org/kittymux')
  expect(siteUrl('http://localhost:3000')).toBe('http://localhost:3000')
})

test('absolute URLs have no trailing slash except the root, and are empty without a base', () => {
  expect(absolute('/docs/', 'https://a.test')).toBe('https://a.test/docs')
  expect(absolute('/', 'https://a.test')).toBe('https://a.test/')
  expect(absolute('/docs', '')).toBe('')
})

test('a page without a site URL claims no canonical address and no absolute image', () => {
  const h = pageHead({ title: 'T — kittymux', description: 'd', path: '/x', base: '' })
  expect(h.links).toEqual([])
  expect(JSON.stringify(h.meta)).not.toContain('og:image')
  expect(h.meta.find((m) => m.name === 'twitter:card')?.content).toBe('summary')
})

test('a page with a site URL says where it lives and what its preview looks like', () => {
  const h = pageHead({ title: 'T — kittymux', description: 'd', path: '/docs/users/shortcuts/', base: 'https://a.test' })
  expect(h.links).toEqual([{ rel: 'canonical', href: 'https://a.test/docs/users/shortcuts' }])
  const by = (k: string) => h.meta.find((m) => m.property === k || m.name === k)?.content
  expect(by('og:url')).toBe('https://a.test/docs/users/shortcuts')
  expect(by('og:image')).toBe('https://a.test/og.png')
  expect(by('twitter:card')).toBe('summary_large_image')
  expect(by('og:title')).toBe('T — kittymux')
})

test('structured data cannot close its own script element', () => {
  const h = pageHead({ title: 't', description: 'd', path: '/', base: '', ldJson: [{ name: '</script><script>alert(1)</script>' }] })
  expect(h.scripts[0].children).not.toContain('</script>')
  expect(JSON.parse(h.scripts[0].children).name).toBe('</script><script>alert(1)</script>')
})

test('the structured data is what schema.org expects', () => {
  expect(softwareLd('').url).toBeUndefined()
  expect(softwareLd('https://a.test').url).toBe('https://a.test/')
  const faq = faqLd([['Q1?', 'A1.']])
  expect(faq.mainEntity[0].acceptedAnswer.text).toBe('A1.')
  expect(breadcrumbLd([{ name: 'Docs', path: '/docs' }], '')).toBeNull()
  expect(breadcrumbLd([{ name: 'Docs', path: '/docs' }, { name: 'X', path: '/docs/x' }], 'https://a.test')?.itemListElement[1].item).toBe('https://a.test/docs/x')
})

import react from '@vitejs/plugin-react';
import { tanstackStart } from '@tanstack/react-start/plugin/vite';
import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { fumadocsMdx } from 'fumadocs-mdx/vite';
import { nitro } from 'nitro/vite';
import { readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

// every docs page also has a Markdown twin (/docs/x.md: the "Copy Markdown" and "View as Markdown" buttons, and what an LLM is sent). Nothing links to them, so the crawler would never find them.
function markdownPages(root = 'content/docs'): { path: string }[] {
  const walk = (d: string): string[] => readdirSync(d).flatMap((n) => (statSync(join(d, n)).isDirectory() ? walk(join(d, n)) : n.endsWith('.mdx') ? [join(d, n)] : []));
  return walk(root).map((f) => {
    const slug = relative(root, f).replace(/\.mdx$/, '').replace(/\/index$/, '');   // a folder's index page is /docs/folder.md; the root index is /docs/index.md
    return { path: `/docs/${slug}.md` };
  });
}

/**
 * Response headers for every page and file. The CSP allows inline scripts because the theme script and TanStack Start's page data are inline (a hash per page would be
 * needed to drop that); everything else is same-origin only, which is also what keeps the site free of third-party requests.
 */
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' data:",   // Vite inlines the smallest font files as data: URIs
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  'upgrade-insecure-requests',
].join('; ');

const ROUTE_RULES = {
  '/**': {
    headers: {
      'content-security-policy': CSP,
      'x-content-type-options': 'nosniff',
      'referrer-policy': 'strict-origin-when-cross-origin',
      'permissions-policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()',
      'cross-origin-opener-policy': 'same-origin',
      'strict-transport-security': 'max-age=63072000; includeSubDomains; preload',
    },
  },
  // not content-hashed, so not immutable: a day in caches, and a stale copy is served while a fresh one is fetched
  '/assets/shots/**': { headers: { 'cache-control': 'public, max-age=86400, stale-while-revalidate=604800' } },
  '/og.png': { headers: { 'cache-control': 'public, max-age=86400, stale-while-revalidate=604800' } },
};

export default defineConfig({
  server: {
    port: 3000,
  },
  plugins: [
    fumadocsMdx(),
    tailwindcss(),
    tanstackStart({
      prerender: {
        enabled: true,
        crawlLinks: true,
        failOnError: true,
        // the crawler follows #anchor links as if they were pages: it then writes the SAME file from several tasks at once and can leave it empty (it did)
        filter: (page: { path: string }) => !page.path.includes('#'),
      },
      // not linked from any page, so the crawler would never find them: the search index and the llms.txt files are static assets
      pages: [{ path: '/api/search' }, { path: '/llms.txt' }, { path: '/llms-full.txt' }, ...markdownPages()],
    }),
    react(),
    // please see https://tanstack.com/start/latest/docs/framework/react/guide/hosting#nitro for guides on hosting
    nitro({
      preset: 'vercel',
      routeRules: ROUTE_RULES,
    }),
  ],
  resolve: {
    tsconfigPaths: true,
    alias: {
      tslib: 'tslib/tslib.es6.js',
    },
  },
});

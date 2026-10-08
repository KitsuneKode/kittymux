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
    }),
  ],
  resolve: {
    tsconfigPaths: true,
    alias: {
      tslib: 'tslib/tslib.es6.js',
    },
  },
});

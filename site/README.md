# kittymux documentation site

TanStack Start + Fumadocs + Tailwind v4 + shadcn (Base UI), prerendered to static HTML. **Not deployed**: building it needs no account and publishing it needs the owner's go.

## Where things come from

| What | Source of truth | How it gets here |
|---|---|---|
| Every docs page | `../docs/` (`index.mdx`, `users/`, `developer/`) | `scripts/sync-docs.mjs` validates (links, images, `meta.json`, frontmatter) and copies to `content/docs/` |
| Keys, agents, states, features | the product's own parsers | `../tools/export_facts.py` → `src/generated/facts.json` |
| Changelog | `../CHANGELOG.md` | copied to `src/generated/` |
| Screenshots | the repository's rigs, on made-up data | `bash ../tools/build-site-assets.sh` → `public/assets/shots/` (committed) |

`content/`, `src/generated/` and `public/assets/*` (except `shots/`) are generated and git-ignored. **Edit `../docs/`, never `content/`.**

## Commands (in `site/`, with bun)

```bash
bun install
bun run dev          # sync, then the dev server
bun run check        # sync + unit tests + typecheck + build + crawl the built site
bun run axe          # axe-core (light and dark) on key pages, overflow at 320/390/768/1440, search finds a page
bun run budget       # what a first visit downloads (gzip) and that nothing leaves the site
bun run shoot        # screenshots of key pages, 3 widths x 2 themes, into .shots/
```

The built site is in `.vercel/output/static` (named in `BUILD_DIR`).

## Look

Tokens are in `src/styles/tokens.css` (cream, red, ink; a dark theme that is not an inversion); `src/lib/contrast.test.ts` asserts every text pair of both themes is at least 4.5:1. Theme: System by default, Light and Dark. One easing everywhere (`cubic-bezier(0.23, 1, 0.32, 1)`), press scale 0.96, all motion off under `prefers-reduced-motion`.

## Measured (2026-10-08)

axe: no violations on 8 pages in both themes; no horizontal overflow at 320, 390, 768 or 1440 px; search finds a page. Lighthouse (gzip, local): accessibility 100, SEO 100, best practices 96-100; performance 98 with the desktop preset and 73 with the default mobile throttling (simulated slow 4G, 4x CPU). The landing page ships about 504 KB of gzip JavaScript (React, TanStack Start, Fumadocs' shell, Base UI): the original 120 KB target was **not** met. Splitting the docs shell away from the landing page is the way to get there.

## Deploying

A static host serving `.vercel/output/static` works (the build also emits a Vercel function directory that nothing needs). Do not deploy from CI without the owner's go.

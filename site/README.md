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
bun run og           # redraw public/og.png and the touch icon
bun run tour         # full-page screenshots of one page, light and dark (bun scripts/tour.mjs DIR OUT [path] [width])
```

The built site is in `.vercel/output/static` (named in `BUILD_DIR`).

## Look

Tokens are in `src/styles/tokens.css` (cream, red, ink; a dark theme that is not an inversion); `src/lib/contrast.test.ts` asserts every text pair of both themes is at least 4.5:1. Theme: System by default, Light and Dark. One easing everywhere (`cubic-bezier(0.23, 1, 0.32, 1)`), press scale 0.96, all motion off under `prefers-reduced-motion`.

## Measured (2026-10-08)

axe: no violations on 8 pages in both themes (two Fumadocs-owned rules are filtered by place, see `scripts/axe.mjs`); no horizontal overflow at 320, 390, 768 or 1440 px; search finds a page from the docs and from the landing page's own field; a click on a docs link changes the page on a host with no server. Lighthouse (gzip, local server): accessibility, best practices and SEO 100 on `/` and a docs page; performance on `/` is 100 with the desktop preset and **87** with the default mobile throttling (simulated slow 4G, 4x CPU; LCP 3.3 s); a docs page 99 and 84.

JavaScript on a first visit: **150 KB gzip on the landing page** (React 19 and TanStack Start's router are most of it; `bun scripts/chunks.mjs "$(cat BUILD_DIR)" /` lists every script) and 363 KB on a docs page. The first plan's 120 KB target for the landing page was **not** met; it was 504 KB before the Fumadocs provider moved to the docs routes and a two-icon set replaced Lucide's whole set. The rest is the framework: going lower means not hydrating the landing page at all.

## Search engines and link previews

Each page carries a title (at most 60 characters), a description (70 to 160), Open Graph and Twitter tags, and a `/og.png` preview (`bun run og` redraws it and `public/apple-touch-icon.png`). The landing page also has `SoftwareApplication` and `FAQPage` structured data; docs pages have `BreadcrumbList`. `scripts/check-site.mjs` fails the build if a title or description is shared, too long, or missing, if the structured data is not JSON, or if a page asks not to be indexed.

The **public address is a build-time setting**: `VITE_SITE_URL=https://your.domain bun run build`. With it, every page gets a canonical URL and an absolute `og:image`, and the build writes `sitemap.xml` and a `robots.txt` that points to it. Without it the pages carry no canonical URL and there is no sitemap, on purpose: an address that was made up would be trusted by search engines. `llms.txt` and `llms-full.txt` are also published, and every docs page has a Markdown twin at `/docs/<page>.md`.

## Deploying (needs the owner's go; nothing here deploys)

The build is a Vercel *Build Output* (`.vercel/output`: `static/` plus one function for any address that is not a prerendered page, such as the 404). Two ways:

1. **Vercel's Git integration** (recommended: previews for every pull request). Import the repository; set *Root Directory* to `site`, *Install Command* to `bun install --frozen-lockfile`, *Build Command* to `bun run build`; leave the output directory alone; add the environment variable `VITE_SITE_URL` (set it for Production only: Vercel marks preview deployments `noindex` itself, and without the variable their pages carry no canonical URL pointing at the real site). Then add the domain, and in the registrar point it as Vercel says.
2. **From a machine**: `cd site && VITE_SITE_URL=https://your.domain bun run build && npx vercel deploy --prebuilt` (add `--prod` for production). `vercel link` once before.

A host that serves files only (any CDN, GitHub Pages) also works for every page, because docs navigation reads prerendered JSON, but unknown addresses then need the host's own 404 page. After the first deploy: open the site in a private window, check `view-source:` for the canonical URL, request `/sitemap.xml`, add the property in Google Search Console and Bing Webmaster Tools, submit the sitemap, and paste a link into a chat to see the preview card.

## What is left

- **Owner decisions:** the domain (it sets `VITE_SITE_URL`), whether previews are public, and the go to deploy.
- **Search index:** about 400 KB gzip, fetched on the first search. Not in the budget yet; a smaller index (titles and headings only) is possible.
- **Mobile Lighthouse** is 87, not 95: hydration cost of the framework (see above).
- **`.github/workflows/site.yml`** has not run on GitHub yet; it needs one push to show whether the runner's Chrome path and the Bun version hold.
- **Screenshots** come from the repository's rigs; rerun `bash ../tools/build-site-assets.sh` after the panel or bar changes look.

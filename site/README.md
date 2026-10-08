# kittymux documentation site

TanStack Start + Fumadocs + Tailwind v4 + shadcn (Base UI), prerendered to static HTML. Live at **https://kittymux.kitsunekode.in** (Vercel project `kittymux-docs`, team `kitsunekode`).

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

The **public address is a build-time setting**: `VITE_SITE_URL=https://kittymux.kitsunekode.in bun run build`. With it, every page gets a canonical URL and an absolute `og:image`, and the build writes `sitemap.xml` and a `robots.txt` that points to it. Without it the pages carry no canonical URL and there is no sitemap, on purpose: an address that was made up would be trusted by search engines. `llms.txt` and `llms-full.txt` are also published, and every docs page has a Markdown twin at `/docs/<page>.md`.

## Deploying

Production is a **prebuilt deploy from a clean checkout of `main`** (the build needs Python for `tools/export_facts.py`, so it runs here and not on Vercel's builders):

```bash
cd site
bun install --frozen-lockfile
VITE_SITE_URL=https://kittymux.kitsunekode.in bun run build     # also writes robots.txt and sitemap.xml
bun run check:crawl && bun run axe && bun run budget            # the same gates CI runs
vercel deploy --prebuilt --prod                                  # .vercel/ (project link) is git-ignored; `vercel link --project kittymux-docs` once
```

- **Previews are private.** The project's protection is `all_except_custom_domains`: every preview deployment and the `*.vercel.app` addresses ask for a Vercel login; only `kittymux.kitsunekode.in` is public. A preview is `vercel deploy --prebuilt` without `--prod`; read it with `vercel curl <path> --deployment <url>`.
- **DNS** (Cloudflare, `kitsunekode.in`): one record, `kittymux  CNAME  0bf5b3e5f1d7d49a.vercel-dns-017.com`, DNS only (grey cloud). It is the same target the other `*.kitsunekode.in` sites use; `vercel domains inspect kittymux.kitsunekode.in` says when it verifies. (Vercel's other suggestion, `A kittymux 76.76.21.21`, works too.)
- The build is a Vercel *Build Output*: `static/` plus one function for any address that is not a prerendered page (the 404). A plain static host also serves every page, because docs navigation reads prerendered JSON.
- **After a deploy:** view-source for the canonical URL, open `/sitemap.xml`, add the property in Google Search Console and Bing Webmaster Tools and submit the sitemap, and paste the link into a chat to see the preview card.

## What is left

- **Git integration** (a deploy per push, private previews per pull request) is not set up: the build needs Python, so it would need a custom install step. Until then, deploys are by hand as above.
- **Star count** is read once per build (`scripts/gen-github.mjs`); it is 0 today and the buttons then say "Star" without a number. Rebuild after it grows.
- **Search index:** about 400 KB gzip, fetched on the first search. Not in the budget yet; a smaller index (titles and headings only) is possible.
- **Mobile Lighthouse** is 87, not 95: hydration cost of the framework (see above).
- **`.github/workflows/site.yml`** has not run on GitHub yet; it needs one push to show whether the runner's Chrome path and the Bun version hold.
- **Screenshots** come from the repository's rigs; rerun `bash ../tools/build-site-assets.sh` after the panel or bar changes look.

# kittymux documentation site

TanStack Start + Fumadocs + Tailwind v4 + shadcn (Base UI), prerendered to static HTML. Live at **https://kittymux.kitsunekode.in** (Vercel project `kittymux`, team `kitsunekode`, connected to this repository).

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
bun run cls          # layout shift on every page, theme and width, slow first visit included (must stay 0)
bun run tour         # full-page screenshots of one page, light and dark (bun scripts/tour.mjs DIR OUT [path] [width])
```

The built site is in `.vercel/output/static` (named in `BUILD_DIR`).

## Look

Tokens are in `src/styles/tokens.css` (cream, red, ink; a dark theme that is not an inversion); `src/lib/contrast.test.ts` asserts every text pair of both themes is at least 4.5:1. Theme: System by default, Light and Dark. One easing everywhere (`cubic-bezier(0.23, 1, 0.32, 1)`), press scale 0.96, all motion off under `prefers-reduced-motion`.

## Measured (2026-10-08)

axe: no violations on 8 pages in both themes (two Fumadocs-owned rules are filtered by place, see `scripts/axe.mjs`); no horizontal overflow at 320, 390, 768 or 1440 px; search finds a page from the docs and from the landing page's own field; a click on a docs link changes the page on a host with no server. Lighthouse (gzip, local server): accessibility, best practices and SEO 100 on `/` and a docs page; performance on `/` is 100 with the desktop preset and **87** with the default mobile throttling (simulated slow 4G, 4x CPU; LCP 3.3 s); a docs page 99 and 84.

JavaScript on a first visit: **150 KB gzip on the landing page** (React 19 and TanStack Start's router are most of it; `bun scripts/chunks.mjs "$(cat BUILD_DIR)" /` lists every script) and 363 KB on a docs page. The first plan's 120 KB target for the landing page was **not** met; it was 504 KB before the Fumadocs provider moved to the docs routes and a two-icon set replaced Lucide's whole set. The rest is the framework: going lower means not hydrating the landing page at all.

## Search engines and link previews

Each page carries a title (at most 60 characters), a description (70 to 160), Open Graph and Twitter tags, and a `/og.png` preview. The preview card, the favicons and the mascot cutout are all derived from the one master image by `python3 tools/build-site-brand.py` (the brand's own social card, cropped; never edit the PNGs). The landing page also has `SoftwareApplication` and `FAQPage` structured data; docs pages have `BreadcrumbList`. `scripts/check-site.mjs` fails the build if a title or description is shared, too long, or missing, if the structured data is not JSON, or if a page asks not to be indexed.

The **public address is a build-time setting**: `VITE_SITE_URL=https://kittymux.kitsunekode.in bun run build`. With it, every page gets a canonical URL and an absolute `og:image`, and the build writes `sitemap.xml` and a `robots.txt` that points to it. Without it the pages carry no canonical URL and there is no sitemap, on purpose: an address that was made up would be trusted by search engines. `llms.txt` and `llms-full.txt` are also published, and every docs page has a Markdown twin at `/docs/<page>.md`.

## Deploying

**A push to `main` deploys production**; every other branch and pull request gets a private preview. The Vercel project is connected to `KitsuneKode/kittymux` with Root Directory `site` and "include source files outside the Root Directory" on (the build reads `../docs`, `../tools`, `../bin/mux-keys.py`, the key template, `CHANGELOG.md` and `../assets`). `site/vercel.json` holds the rest, so nothing depends on dashboard settings except the root directory and the domain:

- install `bun install --frozen-lockfile`, build `bun run build` (which first runs `sync`: docs → `content/`, facts from Python, the changelog, the GitHub star count);
- `VITE_SITE_URL=https://kittymux.kitsunekode.in`, which turns on canonical URLs and the sitemap;
- an **ignore step**: a push that changes nothing under `site/`, `docs/`, `tools/`, `python/`, `assets/`, `bin/mux-keys.py`, the key template or the changelog does not rebuild the site.

What the build produces, and checks:

- Security headers on every response (CSP with same-origin everything, HSTS, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, COOP), set in `vite.config.ts` and applied by Nitro; `scripts/axe.mjs` loads the pages under them and fails on a console error.
- Cache rules: files whose names carry a content hash are immutable for a year; everything else under `/assets/` revalidates daily (`scripts/patch-routes.mjs` narrows Nitro's "immutable for all of /assets/").
- **Analytics**: `@vercel/analytics` and `@vercel/speed-insights`, loaded from this site's own `/_vercel/...`, no cookies, skipped for Do Not Track and Global Privacy Control. They only collect once **Web Analytics and Speed Insights are enabled for the project** (done), and the first deployment *after* enabling is the first that serves the scripts: if `/_vercel/insights/script.js` is a 404, redeploy (`vercel redeploy <url> --target production`).

By hand, from a clean checkout of `main` (the same thing Vercel runs): `cd site && bun install --frozen-lockfile && VITE_SITE_URL=https://kittymux.kitsunekode.in bun run build && bun run check:crawl && bun run axe && bun run budget && bun run cls`.

- **Previews are private.** Protection is `all_except_custom_domains`: every preview deployment asks for a Vercel login, and only `kittymux.kitsunekode.in` (and the project's production alias) is public. Read a preview with `vercel curl <path> --deployment <url>`.
- **DNS** (Cloudflare, `kitsunekode.in`): one record, `kittymux  CNAME  0bf5b3e5f1d7d49a.vercel-dns-017.com`, DNS only (grey cloud), the same target the other `*.kitsunekode.in` sites use.
- After a deploy: view-source for the canonical URL, open `/sitemap.xml`, add the property in Google Search Console and Bing Webmaster Tools and submit the sitemap, and paste the link into a chat to see the preview card.

## What is left

- **GitHub numbers** (stars, forks, open issues, last push, and each other project's stars in the footer) are read once per build by `scripts/gen-github.mjs` into `src/generated/github.json`. A number GitHub cannot give is left out, never guessed; a count of 0 is left out too (the star button then says only "Star"). The site does not rebuild when the numbers change: they refresh on the next push to `main`, or with `vercel redeploy`.
- **Search index** (`/api/search`, prerendered; built in `src/routes/api/search.ts` from every docs page plus `src/lib/search-index.ts`: the keys, the changelog, the front page's questions, the other projects): about 2 MB, about 450 KB gzip. It is fetched when someone reaches for search (pointer, focus, touch or Ctrl K), not on page load. Results whose page title matches the query move first (`src/lib/search-rank.ts`). A smaller index (titles and headings only) is possible; not in the budget yet.
- **Mobile Lighthouse** is 87, not 95: hydration cost of the framework (see above).
- **`.github/workflows/site.yml`** has not run on GitHub yet; it needs one push to show whether the runner's Chrome path and the Bun version hold.
- **Screenshots** come from the repository's rigs; rerun `bash ../tools/build-site-assets.sh` after the panel or bar changes look.

## Missing pages and errors

`src/components/status-page.tsx` is both the 404 (`not-found-full.tsx`, inside Fumadocs' top bar, with a search button) and the error page (`route-error.tsx`, its own small top bar and no Fumadocs imports, so it cannot fail for the same reason the page it replaces did). Both are `noindex`. Only the 404 can be seen in `bun run dev`; a static host with no server answers a missing address with its own plain 404, so check the real thing after a deploy (`curl -i https://kittymux.kitsunekode.in/no/such/page`).

## Brand and layout stability

The mascot (`assets/brand/mascot.png`) is the brand: the logo tile in every header and the footer, the favicon and touch icon, the link-preview card, and the kitten that sits on the hero window and on the closing band. The palette comes from it (slate-blue field, cream, pink; `src/styles/tokens.css`). Type: Bricolage Grotesque for headings (a soft, slightly quirky grotesque that rhymes with the mascot), Geist for text and interface, JetBrains Mono for anything you type and for the wordmark, all latin subsets from `@fontsource-variable`. The scale is a handful of roles in `src/styles/app.css` (`t-display`, `t-h2`, `t-h3`, `t-lead`, `t-body`, `t-small`, `t-caption`, `t-mono`): sizes are `clamp(rem + vw)`, tracking is in `em`, leading is unitless, and components name a role instead of repeating numbers. Headings load with `font-display: swap`, text and mono with `optional`, all preloaded, each with a fallback cut to the same metrics (`tools/font_fallback.py`), so no font landing late moves the text. `bun run cls` loads every page at two widths and both themes, a slow first visit included, and moves between pages; any shift above 0.02 fails.

## What the front page deliberately does not do

No numbered section labels, no row of three identical cards, no em dashes, no decorative dots, and no more than two sections in a row with the same text-and-image split. The agent row is logos only. Sections use different shapes on purpose: a split, a logo row, two unequal columns over a wide band, a list of commands, three key groups, a list of links, plain prose, native `<details>`. A new section should not repeat the shape above it.

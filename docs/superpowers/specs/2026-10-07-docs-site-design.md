# kittymux documentation site: design

Status: **approved with answers (2026-10-07).** Decisions from review are marked **DECIDED**. Implementation starts from the plan, not from this file.

## What this is for

A public site that makes kittymux easy to understand, try and trust: a front page that says what it does in ten seconds, and
documentation that someone with a broken install or a missing key can navigate. The look is taken from the "gamusa" prototype
(`impact-coaching-center` client-preview, `app/prototypes/gamusa`). The docs themselves already exist as 29 MDX pages in
`docs/` (about 30,000 words), written for TanStack Start + Fumadocs, using only Fumadocs components (`Cards`, `Steps`, `Callout`).

**What matters most, in order:** (1) a stranger can install it and see it working; (2) a user can find the key, command or
fix they are looking for in two moves; (3) it is honest about what is verified and what is not; (4) it looks like someone cared.

## Said by you / assumed by me

| You said | I assumed (correct me) |
| --- | --- |
| Use TanStack Start for a docs site | Fumadocs on TanStack Start (what the docs were already written for); static output, no server needed |
| Use the gamusa theme and its styles | **DECIDED: everything in the reference is yours, so the palette, type, woven band and motion are used as they are.** The ICT logo, photos and copy stay out only because they are about something else |
| Better use of shadcn, typography, better-ui, frontend-design, make-interfaces-feel-better | shadcn components for the landing page and chrome; Fumadocs UI for the reading experience, restyled by tokens |
| "typeset" | Read as typography: a real type scale and prose styles, not a plugin by that name |
| "system as default, and a darker version of it with the best support of things" | **DECIDED:** three states: System (default, follows the OS), Light (cream) and Dark (ink). Dark is a full second theme, not an inversion: code colours, callouts, search, tables, focus rings and screenshots each have a dark counterpart |
| (not said) | The site lives in `site/` in this repo; `docs/` stays the single source of content |
| "a screenshot and a tagline… a marketing genius… the home page is a marketing page as well, and the docs are there as well" | **DECIDED:** the home page sells first and is also the docs hub: a search box, the four things people look for, and the popular pages sit on it. Tagline and copy below |
| (not said) | Nothing is deployed or published without your explicit go |

## Approaches considered

1. **Fumadocs UI, recoloured by tokens only.** Fastest. The site looks like every Fumadocs site with a red accent. Rejected: it throws away the reason for choosing this theme.
2. **Fumadocs for structure, custom shell and landing in shadcn (recommended).** Keep Fumadocs' loader, page tree, search, TOC, prev/next and accessible reading layout; replace header, footer, cards, callouts, code blocks and the whole landing page with our own components on the gamusa tokens. Bespoke where it is seen, standard where it is hard to get right.
3. **Custom MDX site without Fumadocs.** Total control, but rebuilds search, sidebar tree, TOC and heading anchors for no visible gain. Rejected.

## Design

### Stack

TanStack Start (Vite, React 19) + `fumadocs-core` / `fumadocs-ui` / `fumadocs-mdx` + Tailwind v4 + shadcn/ui (Tabler icons, as the reference). **bun** as package manager (installed here; the reference uses it). All routes prerendered to static HTML; search is Orama's static index, so there is no server to run. Versions pinned exactly. Fonts self-hosted through Fontsource (no request to Google at runtime): Epilogue variable for everything and JetBrains Mono for code.

### Content pipeline: one source, no drift

- `docs/` is the only place prose lives. `site/scripts/sync-docs.mjs` copies `docs/index.mdx`, `docs/users`, `docs/developer` and `meta.json` files into `site/content/docs` (git-ignored) and `assets/` into `site/public/assets`. It fails the build on a missing frontmatter field, a broken `/docs/...` link or a missing image.
- `site/scripts/gen-facts.mjs` reads the repo and writes `site/src/generated/facts.json`: the key table (parsed from `kittymux-keys.conf.tpl`, the same parser the `ctrl+alt+/` overlay uses), the supported-agent list (`assets/resume-agents.json`), the state table and the feature switches. The front page's numbers and the Keys page come from it, so they cannot be stale.
- `tests/test_docs.py` stays the gate for the content. The site adds a build-time gate for the presentation.

### Pages

| Route | What it is |
| --- | --- |
| `/` | Landing: hero, three ideas, "how it knows" table, install in three steps, keys at a glance, honest limits, footer |
| `/docs/...` | Users and Developers as two top-level tabs; sidebar tree, TOC, prev/next, "edit on GitHub", copy-as-Markdown |
| `/keys` | Every chord, generated, filterable by typing, grouped as in the overlay |
| `/changelog` | `CHANGELOG.md` rendered, newest first |
| `/llms.txt`, `/llms-full.txt` | The docs for agents to read (this tool's users run agents all day) |
| `/api/search` | Static search index; `⌘K` / `/` opens it everywhere |

### Voice and copy (DECIDED direction; final wording is yours to veto)

The promise is one thing: **you always know which agent needs you.** Everything else (panes, sessions, the palette) is how.

- **Headline:** *Know which agent needs you.*
- **Subhead:** *kittymux turns kitty into a multiplexer for AI coding agents. One glance at the tab bar says who is working, who is waiting for you and who has finished, and one click takes you there.*
- **Primary action:** `Try the demo`, with the line *Opens its own window. Your config is never touched.* **Secondary:** `Read the docs`.
- **Proof line under the hero**, every item true and checkable: *Eight agents recognised · Local only, no daemon · Never types into an agent · Silence is never "waiting"*.
- **Alternatives kept in reserve** for the share image and the repository description: *Eight agents running. One glance tells you who's waiting.* and *Stop hunting through tabs.*
- **Rules for all copy:** no "blazing", "seamless", "revolutionary"; verbs and numbers instead of adjectives; every number is generated from the repository (agents, chords, features) or omitted; the honest-limits section stays on the front page because it is the strongest trust signal the product has.

### Landing page, section by section

1. **Hero (red field).** The headline and subhead above, a docs search field styled as part of the hero (`⌘K`), the two actions, and on the right a real screenshot of the bar and panel in a terminal window. The proof line sits under it.
1b. **The problem, in one screen.** A crowded tab strip with an "Is it done? Is it stuck? Is it asking me?" caption, then the same strip as kittymux draws it. Before and after, both real screenshots.
2. **Three ideas**, each with a real screenshot: **See** (the tab bar says what every agent is doing), **Act** (the panel, the palette, one click to answer), **Come back** (sessions restore and ask before resuming).
3. **How it knows.** The state table (`limited`, `waiting`, `working`, `done`, `idle`) with the rule that silence is never "waiting". This is the trust section.
4. **Install in three steps** with copy buttons and the `doctor` output people should expect.
5. **Keys at a glance:** the twelve chords people use most, then a link to `/keys`.
5b. **The docs hub.** Because this page is also the way into the docs: four large entries (*Getting started*, *Shortcuts*, *Troubleshooting*, *CLI reference*), a row of the most-read pages, and the search field repeated. A visitor who came for a fix must not have to scroll past a pitch to find it, so a `Docs` link stays in the header and the hub is reachable by one anchor.
5c. **Questions people ask first** as an accordion: *Does it send my data anywhere? Will it type into my agents? Which agents? Do I have to leave tmux? Does it need Wayland?*
6b. **Final call to action** on a red field: the install command and the demo command.
6. **What it does not do.** Platform support and the "not verified" list, taken from `platforms.mdx`.
7. **Footer:** repository, changelog, licence, version (from `git describe` at build).

### Visual system (from the reference)

- **Colour, committed.** Cream `#F7F3EA`, red `#B3261E`, ink `#141414`, soft red `#F5D6D2`, muted `#6B655C`, hairline ink at 12%. Red carries about 40% of the landing page (hero, install band, borders, primary action); docs pages are mostly cream with red used for links, the active nav item and one accent per page. **Dark:** ink ground, cream text, the red lifted to keep 4.5:1 on ink, the red field kept for the hero and the final call to action only, surfaces a step lighter than the ground, hairlines cream at 14%. **System** is the default: the first paint follows `prefers-color-scheme` through an inline script, and the toggle cycles System, Light, Dark and remembers the choice. Every foreground/background pair of both themes is contrast-checked in a test.
- **Type.** Epilogue 700 for display at `-0.03em`, balanced; 400/500 for body at 16–17 px with `text-wrap: pretty`; a 60–72 character measure for prose; `tabular-nums` on numbers; real quotes, dashes and ellipses; JetBrains Mono for code and keys.
- **Shape.** Pills for actions, one radius family with concentric inner radii, layered transparent shadows for lift, 1 px ink-12% hairlines for structure, image outlines in pure black or white at 10%.
- **Motion.** One easing, `cubic-bezier(0.23, 1, 0.32, 1)`. Hero entrance staggered 80 ms; the primary action's clip-path wipe; press scale `0.96`; nothing animates on high-frequency actions (search open, sidebar toggle); everything is gated by `prefers-reduced-motion`, with an opacity cross-fade as the fallback.
- **Motif.** The diamond band between two threads, as one reusable SVG pattern, used as the divider under the header and above the footer. Decorative only (`aria-hidden`).
- **Screenshots.** Generated, not hand-made: a script runs the repository's own rigs (`tests/shot_panel.sh`, `shot_bar.sh`, `shot_agents.sh`) in dark and light on the synthetic world, then writes 2x PNGs with width and height into `site/public/assets/shots/`. Shown in a window frame; light mode gets the light terminal, dark mode the dark one. Every screenshot is captioned "synthetic data".

### Components

shadcn: `Button`, `Badge`, `Card`, `Tabs`, `Accordion` (FAQ), `Tooltip`, `Separator`, `Kbd`, `Command` (search), `Sheet` (mobile nav), `Empty`. Fumadocs UI supplies the docs layout, tree, TOC and search dialog, mapped onto our tokens through its `--color-fd-*` variables. Custom: the hero, the weave band, the terminal window frame, the key table, the copy button (with a visible confirmation, not motion alone) and replacements for `Callout`, `Cards` and `Steps` that match the system.

### Accessibility and performance

Skip link; one `h1` per page; visible `:focus-visible` rings; hit areas of at least 44 px for touch; sidebars and the search reachable by keyboard; reduced motion; `lang`; no layout shift (images carry dimensions); dark-mode flash avoided with an inline theme script. Budgets: Lighthouse performance ≥ 95 and accessibility 100 on `/` and one docs page, JS under 120 KB gzip on the landing page.

### Verification (how I will prove it, not just say it)

1. `bun run build` prerenders every route; the count equals pages in `docs/` plus the fixed routes.
2. A crawler over the built HTML: every internal link and anchor resolves; every image exists; every page has one `h1`.
3. Contrast test on both themes for every foreground/background pair in the token file.
4. axe-core over `/`, three docs pages, `/keys` and `/changelog`, in light and dark, in headless Chrome.
5. Screenshots at 1440, 768 and 390 px in both themes, read by me and shown to you before anything is merged.
6. Existing gates unchanged: the unit suite and `tests/test_docs.py` stay green.

### Risks

- **Version churn** (TanStack Start and Fumadocs move fast): exact pins, a lockfile, and a CI job that builds the site on every change to `docs/` or `site/`.
- **The reference is a client's visual identity.** Tokens and motifs only; no logos, photographs, copy or names. Please confirm this is the line you want.
- **Screenshots go stale** as the UI changes: they are generated by one command and the build fails if the files are missing, but it does not check they look current. Re-run the script when the UI changes.
- **Hosted assets of the reference** (Epilogue via Google Fonts there) are replaced by self-hosted files here.

### Out of scope (for now)

Deploying or choosing a domain, analytics, i18n, versioned docs, a blog, a newsletter form. A deployment configuration is prepared but nothing is published.

## Plan shape (to be written after approval)

0. Scaffold `site/` (TanStack Start + Fumadocs + shadcn), pinned, building an empty docs page.
1. Tokens, fonts, theme switch, contrast test.
2. Content pipeline and the generated facts.
3. Docs shell: layout, sidebar, TOC, search, MDX component replacements.
4. Landing page and screenshot generator.
5. `/keys`, `/changelog`, `llms.txt`.
6. Polish pass (typography, surfaces, motion), then accessibility and performance checks.
7. CI job and deployment config, not deployed.

## Decided in review

1. Everything in the reference is the owner's: its tokens, woven band and motion are used as they are.
2. System is the default theme, with a full dark version and a three-way toggle.
3. The front page is a marketing page and the docs hub at once; headline, subhead and proof line are as written above.

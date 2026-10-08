import { IconArrowRight, IconBrandGithub, IconRefresh } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { Mascot } from '@/components/logo';
import { ISSUES_URL, REPO_URL } from '@/lib/links';
import { SUGGESTIONS } from '@/lib/suggestions';

const secondary = 'inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-onbrand px-6 text-base font-semibold hover:bg-onbrand hover:text-brand';

/** A path for display: bounded, and with anything that is not printable text taken out (it comes from the address bar). */
export function showPath(path: string, max = 64): string {
  const clean = path.replace(/[^\x20-\x7e]/g, '?');
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean;
}

export function issueUrl(path: string, what: 'error' | 'missing'): string {
  const title = what === 'error' ? `Site error on ${showPath(path, 48)}` : `Broken link: ${showPath(path, 48)}`;
  return `${REPO_URL}/issues/new?title=${encodeURIComponent(title)}`;
}

type Props = {
  kind: '404' | 'error';
  path: string;
  /** What the error said, for people who report it. Shown folded away, never as the headline. */
  detail?: string;
  /** Slot for the first action: search on the 404 (needs the search provider), a retry on the error page. */
  primary: ReactNode;
};

/**
 * The page for a missing address and for a page that threw. The kitten sits on the lower edge of a blue band with a terminal line that says what happened,
 * then the way back: the pages people come for. No Fumadocs imports, so the error page cannot fail for the same reason the page it replaces did.
 */
export function StatusPage({ kind, path, detail, primary }: Props) {
  const missing = kind === '404';
  return (
    <main id="main" className="flex-1">
      <title>{missing ? 'Page not found | kittymux' : 'Something went wrong | kittymux'}</title>
      <meta name="robots" content="noindex" />
      <section data-brand="" aria-labelledby="status-title" className="relative overflow-clip bg-brand text-onbrand">
        <div className="mx-auto flex w-full max-w-[1100px] flex-col px-5 pt-14 md:px-8 md:pt-20 lg:pt-24">
          <p className="t-mono w-fit max-w-full rounded-lg bg-[var(--code-bg)] px-3.5 py-2.5 text-sm text-[var(--code-fg)] [overflow-wrap:anywhere]">
            <span className="text-pink" aria-hidden="true">$ </span>
            {missing ? <>kittymux open <span>{showPath(path)}</span></> : <>kittymux render <span>{showPath(path)}</span></>}
            <br />
            <span className="text-pink" aria-hidden="true">✗ </span>
            {missing ? 'no such pane' : 'the pane crashed'}
          </p>
          <h1 id="status-title" className="t-display mt-8 max-w-[16ch]">{missing ? 'That pane isn’t here.' : 'Something broke on this page.'}</h1>
          <p className="t-lead mt-4 max-w-[44ch] text-onbrand-soft">
            {missing
              ? 'The link may be old, or mistyped. Search the docs, or pick up from one of the pages below.'
              : 'Nothing was sent anywhere. Reloading usually fixes it; if it does not, tell us which page it was and we will look.'}
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
            {primary}
            <a href="/" data-press="" className={secondary}>Back to the front page</a>
            {!missing && (
              <a href={issueUrl(path, 'error')} target="_blank" rel="noopener" data-press="" className={secondary}>
                <IconBrandGithub aria-hidden="true" className="size-5" stroke={1.75} />
                Report it
              </a>
            )}
          </div>
          {detail && !missing && (
            <details className="mt-6 max-w-full md:max-w-[60%]">
              <summary className="min-h-11 cursor-pointer py-2 text-sm text-onbrand-soft">What the page reported</summary>
              <pre className="t-mono mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-[var(--code-bg)] p-3 text-xs text-[var(--code-fg)] [overflow-wrap:anywhere]">{detail}</pre>
            </details>
          )}
          {/* the kitten grows out of the band's lower edge: its cropped bottom is the band's bottom */}
          <Mascot width={220} priority className="mt-10 ms-auto block !w-[150px] sm:!w-[200px] md:absolute md:mt-0 md:inset-be-0 md:inset-e-[max(2rem,calc((100%-1100px)/2+2rem))] md:!w-[280px]" />
        </div>
      </section>

      <section aria-labelledby="where" className="mx-auto w-full max-w-[1100px] px-5 py-14 md:px-8">
        <h2 id="where" className="t-h3">Where people usually go</h2>
        <ul className="mt-5 grid gap-x-8 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
          {SUGGESTIONS.map((s) => (
            <li key={s.url}>
              <a href={s.url} className="group flex min-h-14 items-center justify-between gap-3 border-b border-line py-2 hover:text-link">
                <span className="flex flex-col">
                  <span className="font-semibold">{s.label}</span>
                  <span className="text-sm text-mute">{s.hint}</span>
                </span>
                <IconArrowRight aria-hidden="true" className="size-4 shrink-0 text-mute transition-transform duration-150 motion-reduce:transition-none [@media(hover:hover)_and_(pointer:fine)]:group-hover:translate-x-0.5" stroke={1.75} />
              </a>
            </li>
          ))}
        </ul>
        <p className="mt-8 text-sm text-mute">
          Still lost? <a className="underline underline-offset-2 hover:text-ink" href={ISSUES_URL} target="_blank" rel="noopener">Open an issue</a> with the address you tried.
        </p>
      </section>
    </main>
  );
}

export function RetryButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} data-cta="" data-press="" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-6 text-base font-semibold">
      <IconRefresh aria-hidden="true" className="size-5" stroke={1.75} />
      Try again
    </button>
  );
}

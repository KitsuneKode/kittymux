import * as React from 'react';
import { prefetchSearchIndex } from '@/lib/search-prefetch';

const Opener = React.lazy(() => import('./search-opener'));

/** The docs search field. The search code arrives on the first click, then the dialog opens; Ctrl K works on every docs page. */
export function SearchLauncher({ tone = 'page' }: { tone?: 'page' | 'brand' }) {
  const [opened, setOpened] = React.useState(0);
  return (
    <>
      <button
        type="button"
        data-press=""
        onClick={() => setOpened((n) => n + 1)}
        onPointerEnter={prefetchSearchIndex}
        onFocus={prefetchSearchIndex}
        className={tone === 'brand' ? 'mt-8 flex min-h-11 w-full max-w-md items-center gap-3 rounded-full border border-onbrand/40 px-4 text-start text-sm text-onbrand-soft hover:border-onbrand' : 'well flex min-h-12 w-full max-w-md items-center gap-3 rounded-full px-4 text-start text-sm text-mute'}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" className="size-4">
          <circle cx="10" cy="10" r="7" />
          <path d="m21 21-6-6" />
        </svg>
        Search the docs
        <kbd className="raised t-mono ms-auto rounded px-1.5 py-0.5 text-xs">Ctrl K</kbd>
      </button>
      {opened > 0 && (
        <React.Suspense fallback={null}>
          <Opener key={opened} />
        </React.Suspense>
      )}
    </>
  );
}

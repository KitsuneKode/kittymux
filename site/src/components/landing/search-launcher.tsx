import { IconSearch } from '@tabler/icons-react';
import * as React from 'react';
import { prefetchSearchIndex } from '@/lib/search-prefetch';

const Opener = React.lazy(() => import('./search-opener'));

/** The hero's search field. The search code arrives on the first click, then the dialog opens; Ctrl K works on every docs page. */
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
        className={tone === 'brand' ? 'mt-8 flex min-h-11 w-full max-w-md items-center gap-3 rounded-full border border-onbrand/40 px-4 text-start text-sm text-onbrand-soft hover:border-onbrand' : 'flex min-h-12 w-full max-w-md items-center gap-3 rounded-full border border-line bg-card px-4 text-start text-sm text-mute hover:border-ink'}
      >
        <IconSearch aria-hidden="true" className="size-4" stroke={1.75} />
        Search the docs
        <kbd className="t-mono ms-auto rounded bg-card-hi px-1.5 py-0.5 text-xs">Ctrl K</kbd>
      </button>
      {opened > 0 && (
        <React.Suspense fallback={null}>
          <Opener key={opened} />
        </React.Suspense>
      )}
    </>
  );
}

import { RootProvider } from 'fumadocs-ui/provider/tanstack';
import * as React from 'react';
import { THEME_PROPS } from '@/lib/theme-props';
import { prefetchSearchIndex } from '@/lib/search-prefetch';

const StaticSearchDialog = React.lazy(() => import('@/components/search'));   // the search index client and its parser load when search is first opened, not on every page

/** The Fumadocs context (search dialog, sidebar state, theme) for the pages that use its layouts: /docs, /keys, /changelog and the 404. The landing page does not load it. */
export function DocsProvider({ children }: { children: React.ReactNode }) {
  React.useEffect(() => {   // the index is ~2 MB (about 400 KB on the wire): fetch it when someone reaches for search (pointer, focus, touch, or Ctrl K), not on every page view
    const near = (e: Event) => { if ((e.target as Element | null)?.closest?.('[data-search], [data-search-full]')) prefetchSearchIndex(); };
    const key = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') prefetchSearchIndex(); };
    const opts = { passive: true, capture: true } as const;
    document.addEventListener('pointerover', near, opts);
    document.addEventListener('focusin', near, opts);
    document.addEventListener('touchstart', near, opts);
    document.addEventListener('keydown', key, opts);
    return () => {
      document.removeEventListener('pointerover', near, opts);
      document.removeEventListener('focusin', near, opts);
      document.removeEventListener('touchstart', near, opts);
      document.removeEventListener('keydown', key, opts);
    };
  }, []);
  return (
    <RootProvider search={{ SearchDialog: StaticSearchDialog }} theme={THEME_PROPS}>
      {children}
    </RootProvider>
  );
}

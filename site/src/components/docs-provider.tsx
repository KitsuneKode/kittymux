import { RootProvider } from 'fumadocs-ui/provider/tanstack';
import * as React from 'react';
import { THEME_PROPS } from '@/lib/theme-props';

const StaticSearchDialog = React.lazy(() => import('@/components/search'));   // the search index client and its parser load when search is first opened, not on every page

/** The Fumadocs context (search dialog, sidebar state, theme) for the pages that use its layouts: /docs, /keys, /changelog and the 404. The landing page does not load it. */
export function DocsProvider({ children }: { children: React.ReactNode }) {
  return (
    <RootProvider search={{ SearchDialog: StaticSearchDialog }} theme={THEME_PROPS}>
      {children}
    </RootProvider>
  );
}

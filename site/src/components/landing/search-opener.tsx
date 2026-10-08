import { useSearchContext } from 'fumadocs-ui/contexts/search';
import { useEffect } from 'react';
import { DocsProvider } from '@/components/docs-provider';

function Open() {
  const { setOpenSearch } = useSearchContext();
  useEffect(() => setOpenSearch(true), [setOpenSearch]);
  return null;
}

/** Loaded on the first click of the landing page's search button: the docs provider (and with it the search dialog) is not part of the landing page's JavaScript. */
export default function SearchOpener() {
  return (
    <DocsProvider>
      <Open />
    </DocsProvider>
  );
}

import { IconSearch } from '@tabler/icons-react';
import { useRouterState } from '@tanstack/react-router';
import { HomeLayout } from 'fumadocs-ui/layouts/home';
import { useSearchContext } from 'fumadocs-ui/contexts/search';
import { DocsProvider } from '@/components/docs-provider';
import { SiteFooter } from '@/components/site-footer';
import { StatusPage } from '@/components/status-page';
import { baseOptions } from '@/lib/layout.shared';

function SearchButton() {
  const { setOpenSearch } = useSearchContext();
  return (
    <button type="button" data-cta="" data-press="" onClick={() => setOpenSearch(true)} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-6 text-base font-semibold">
      <IconSearch aria-hidden="true" className="size-5" stroke={1.75} />
      Search the docs
    </button>
  );
}

/** The 404: Fumadocs' top bar (with its search and theme switch) around the status page. Loaded only for an address that does not exist. */
export default function NotFoundFull() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  return (
    <DocsProvider>
      <HomeLayout {...baseOptions(true)}>
        <StatusPage kind="404" path={path} primary={<SearchButton />} />
        <SiteFooter />
      </HomeLayout>
    </DocsProvider>
  );
}

import {
  SearchDialog,
  SearchDialogClose,
  SearchDialogContent,
  SearchDialogHeader,
  SearchDialogIcon,
  SearchDialogInput,
  SearchDialogList,
  SearchDialogOverlay,
  type SearchItemType,
  type SharedProps,
} from 'fumadocs-ui/components/dialog/search';
import { useDocsSearch } from 'fumadocs-core/search/client';
import { staticClient } from 'fumadocs-core/search/client/orama-static';
import { useRouter } from '@tanstack/react-router';
import { useMemo } from 'react';
import { SUGGESTIONS } from '@/lib/suggestions';
import { promoteTitles } from '@/lib/search-rank';

const TRY = ['install', 'waiting', 'sessions', 'tmux', 'privacy'];

/** Search that works on a static host: the browser downloads the prebuilt index once (/api/search is prerendered) and searches locally, across the docs, the keys, the changelog and the front page's questions. */
export default function StaticSearchDialog(props: SharedProps) {
  const { search, setSearch, query } = useDocsSearch({ client: staticClient() });
  const router = useRouter();
  const typed = search.trim().length > 0;

  const suggestions = useMemo<SearchItemType[]>(
    () =>
      SUGGESTIONS.map((s) => ({
        id: `go:${s.url}`,
        type: 'action',
        onSelect: () => {
          props.onOpenChange(false);
          router.history.push(s.url);
        },
        node: (
          <div className="flex min-w-0 flex-col">
            <span className="font-medium">{s.label}</span>
            <span className="text-sm text-fd-muted-foreground">{s.hint}</span>
          </div>
        ),
      })),
    [props, router],
  );

  // While the first results of a new query are loading, show nothing rather than the previous query's list: a stale result under a new word is worse than a short wait.
  const results = typed ? (query.isLoading ? null : query.data !== 'empty' ? promoteTitles(query.data ?? [], search) : null) : suggestions;

  return (
    <SearchDialog search={search} onSearchChange={setSearch} isLoading={query.isLoading} {...props}>
      <SearchDialogOverlay />
      <SearchDialogContent>
        <SearchDialogHeader>
          <SearchDialogIcon />
          <SearchDialogInput placeholder="Search docs, keys, changelog…" />
          <SearchDialogClose />
        </SearchDialogHeader>
        <SearchDialogList
          items={results}
          Empty={() =>
            typed && !query.isLoading ? (
              <div className="px-4 py-10 text-center text-sm text-fd-muted-foreground">
                <p>
                  Nothing for <strong className="text-fd-foreground">“{search.trim()}”</strong>.
                </p>
                <p className="mt-2">
                  Try{' '}
                  {TRY.map((w, i) => (
                    <span key={w}>
                      {i > 0 && ', '}
                      <button type="button" className="underline underline-offset-2 hover:text-fd-foreground" onClick={() => setSearch(w)}>
                        {w}
                      </button>
                    </span>
                  ))}
                  .
                </p>
              </div>
            ) : (
              <div className="px-4 py-10 text-center text-sm text-fd-muted-foreground">Searching…</div>
            )
          }
        />
      </SearchDialogContent>
    </SearchDialog>
  );
}

import { IconSearch } from '@tabler/icons-react';
import * as React from 'react';

const Opener = React.lazy(() => import('./search-opener'));

/** The hero's search field. The search code arrives on the first click, then the dialog opens; Ctrl K works on every docs page. */
export function SearchLauncher() {
  const [opened, setOpened] = React.useState(0);
  return (
    <>
      <button
        type="button"
        data-press=""
        onClick={() => setOpened((n) => n + 1)}
        className="mt-8 hidden min-h-11 w-full max-w-md items-center gap-3 rounded-full border border-onred/40 px-4 text-start text-sm text-onred-soft hover:border-onred sm:flex"
      >
        <IconSearch aria-hidden="true" className="size-4" stroke={1.75} />
        Search the docs
        <kbd className="ms-auto rounded border border-onred/40 px-1.5 py-0.5 font-mono text-xs">Ctrl K</kbd>
      </button>
      {opened > 0 && (
        <React.Suspense fallback={null}>
          <Opener key={opened} />
        </React.Suspense>
      )}
    </>
  );
}

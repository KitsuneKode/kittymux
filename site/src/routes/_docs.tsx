import { createFileRoute, Outlet } from '@tanstack/react-router';
import { DocsProvider } from '@/components/docs-provider';

/** A pathless layout: everything under it (docs, keys, changelog) gets the Fumadocs provider; the landing page does not, which keeps its JavaScript small. */
export const Route = createFileRoute('/_docs')({
  component: () => (
    <DocsProvider>
      <Outlet />
    </DocsProvider>
  ),
});

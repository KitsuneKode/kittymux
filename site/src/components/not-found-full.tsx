import { baseOptions } from '@/lib/layout.shared';
import { HomeLayout } from 'fumadocs-ui/layouts/home';
import { DefaultNotFound } from 'fumadocs-ui/layouts/home/not-found';
import { DocsProvider } from '@/components/docs-provider';

export default function NotFoundFull() {
  return (
    <DocsProvider>
      <HomeLayout {...baseOptions()}>
        <DefaultNotFound />
      </HomeLayout>
    </DocsProvider>
  );
}

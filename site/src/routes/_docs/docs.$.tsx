import { createFileRoute, notFound } from '@tanstack/react-router';
import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import { createServerFn } from '@tanstack/react-start';
import { staticFunctionMiddleware } from '@tanstack/start-static-server-functions';
import { docs, source } from '@/lib/source';
import {
  DocsBody,
  DocsDescription,
  DocsPage,
  DocsTitle,
  MarkdownCopyButton,
  ViewOptionsPopover,
} from 'fumadocs-ui/layouts/docs/page';
import { baseOptions } from '@/lib/layout.shared';
import { getPageMarkdownUrl, gitConfig } from '@/lib/shared';
import { useFumadocsLoader } from 'fumadocs-core/source/client';
import { Suspense, use } from 'react';
import { useMDXComponents } from '@/components/mdx';
import { breadcrumbLd, pageHead } from '@/lib/seo';
import { DocsEnd, DocsTopRight } from '@/components/docs-extras';

// staticFunctionMiddleware: prerender writes each page's data as a JSON file, and a client-side navigation fetches that file. Without it a click on a docs link
// calls a server endpoint that a static host does not have ("Something went wrong").
const serverLoader = createServerFn({
  method: 'GET',
})
  .middleware([staticFunctionMiddleware])
  .validator((slugs: string[]) => slugs)
  .handler(async ({ data: slugs }) => {
    const page = source.getPage(slugs);
    if (!page) throw notFound();

    return {
      path: page.path,
      title: page.data.title,
      description: page.data.description ?? '',
      markdownUrl: getPageMarkdownUrl(page).url,
      pageTree: await source.serializePageTree(source.getPageTree()),
    };
  });

export const Route = createFileRoute('/_docs/docs/$')({
  component: Page,
  head: ({ loaderData, params }: { loaderData?: { title?: string; description?: string }; params: { _splat?: string } }) => {
    const path = params._splat ? `/docs/${params._splat}` : '/docs';
    const title = loaderData?.title ?? 'Documentation';
    return pageHead({
      title: `${title} | kittymux`,
      description: loaderData?.description || 'kittymux documentation',
      path,
      type: 'article',
      ldJson: [breadcrumbLd([{ name: 'Docs', path: '/docs' }, ...(path === '/docs' ? [] : [{ name: title, path }])])].filter((x): x is NonNullable<typeof x> => x !== null),
    });
  },
  loader: async ({ params }) => {
    const slugs = params._splat?.split('/') ?? [];
    const data = await serverLoader({ data: slugs });
    await docs.getPage(data.path)?.preload();
    return data;
  },
});

function Content({ path, markdownUrl }: { path: string; markdownUrl: string }) {
  const page = docs.getPage(path);
  if (!page) throw new Error(`unknown page: ${path}`);

  const { toc } = use(page.load());
  const MDX = page.body;

  return (
    <DocsPage toc={toc}>
      <DocsTitle>{page.title}</DocsTitle>
      <DocsDescription>{page.description}</DocsDescription>
      <div className="flex flex-row gap-2 items-center border-b -mt-4 pb-6">
        <MarkdownCopyButton markdownUrl={markdownUrl} />
        <ViewOptionsPopover
          markdownUrl={markdownUrl}
          githubUrl={`https://github.com/${gitConfig.user}/${gitConfig.repo}/blob/${gitConfig.branch}/docs/${path}`}
        />
      </div>
      <DocsBody>
        <MDX components={useMDXComponents()} />
      </DocsBody>
      <DocsEnd />
    </DocsPage>
  );
}

function Page() {
  const { path, pageTree, markdownUrl } = useFumadocsLoader(Route.useLoaderData());

  return (
    <DocsLayout {...baseOptions()} tree={pageTree}>
      <DocsTopRight />
      <Suspense>
        <Content path={path} markdownUrl={markdownUrl} />
      </Suspense>
    </DocsLayout>
  );
}

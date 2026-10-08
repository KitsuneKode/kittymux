import { createFileRoute } from '@tanstack/react-router';
import { source } from '@/lib/source';
import { createSearchAPI } from 'fumadocs-core/search/server';
import { facts } from '@/lib/facts';
import { changelogIndex, keysIndex, pageIndexes, type SiteIndex } from '@/lib/search-index';
import changelog from '@/generated/CHANGELOG.md?raw';

/** A docs section's name, from the page tree (“Guides”, “Developers”), so a result says where it lives. */
function sectionOf(url: string): string[] {
  const tree = source.getPageTree();
  const walk = (nodes: typeof tree.children, trail: string[]): string[] | null => {
    for (const n of nodes) {
      if (n.type === 'page' && n.url === url) return trail;
      if (n.type === 'folder') {
        const hit = walk(n.children, typeof n.name === 'string' ? [...trail, n.name] : trail);
        if (hit) return hit;
      }
    }
    return null;
  };
  return ['Docs', ...(walk(tree.children, []) ?? [])];
}

/** One index for the whole site: every docs page (headings and paragraphs), the keys, the changelog, the questions and the other projects. Prerendered; the browser downloads it once and searches locally. */
async function indexes(): Promise<SiteIndex[]> {
  const docs = await Promise.all(
    source.getPages().map(async (page): Promise<SiteIndex> => {
      const { structuredData } = await (page.data as unknown as { load(): Promise<{ structuredData: SiteIndex['structuredData'] }> }).load();
      return { id: page.url, url: page.url, title: page.data.title, description: page.data.description, breadcrumbs: sectionOf(page.url), structuredData };
    }),
  );
  return [...docs, keysIndex(facts.keys), changelogIndex(changelog), ...pageIndexes()];
}

const server = createSearchAPI('advanced', { language: 'english', indexes });

export const Route = createFileRoute('/api/search')({
  server: {
    handlers: {
      GET: async () => server.staticGET(),
    },
  },
});

import { llms, loader } from 'fumadocs-core/source';
import { defineDocs } from 'fumadocs-mdx/macro';
import { applyMdxPreset } from 'fumadocs-mdx/config';
import { iconsPlugin } from './icons';
import { docsRoute } from './shared';

export const docs = defineDocs({
  dir: 'content/docs',
  docs: {
    async: true,
    // Code blocks are dark in both site themes (see app.css), so one dark, high-contrast Shiki theme serves both.
    mdxOptions: applyMdxPreset({ rehypeCodeOptions: { themes: { light: 'github-dark-high-contrast', dark: 'github-dark-high-contrast' } } }),
    postprocess: {
      includeProcessedMarkdown: true,
    },
  },
});

export const source = loader({
  source: docs.toFumadocsSource(),
  baseUrl: docsRoute,
  plugins: [iconsPlugin()],
});

export const docsLlms = llms(source, {
  renderPage: async (page) => `# ${page.data.title} (${page.url})

${await page.data.getText('processed')}`,
});

import { IconArrowRight } from '@tabler/icons-react';
import { DocLink } from '../doc-link';
import { SearchLauncher } from './search-launcher';

const HUB = [
  { slug: 'users/getting-started', title: 'Getting started', text: 'Try the demo, install, check, add hooks.' },
  { slug: 'users/shortcuts', title: 'Shortcuts', text: 'Every key, grouped by what it does.' },
  { slug: 'users/troubleshooting', title: 'Troubleshooting', text: 'A key does nothing? A tab says the wrong thing? Start here.' },
  { slug: 'users/cli-reference', title: 'CLI reference', text: 'Every kittymux command and its options.' },
] as const;

/** Heading and search on the left, the four most-wanted pages as plain large links on the right: no boxes. */
export function DocsHub() {
  return (
    <section id="docs" aria-labelledby="docs-title" className="border-y border-line bg-card py-16 lg:py-24">
      <div className="mx-auto grid w-full max-w-[1280px] gap-12 px-5 md:px-8 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <h2 id="docs-title" className="t-h2">Looking for something?</h2>
          <p className="t-body mt-4 max-w-[36ch] text-mute">Search every page from here, or start with one of these.</p>
          <div className="mt-6"><SearchLauncher tone="page" /></div>
        </div>
        <ul className="flex flex-col gap-7 lg:col-span-6 lg:col-start-7">
          {HUB.map(({ slug, title, text }) => (
            <li key={slug} className="group relative rounded-md has-[a:focus-visible]:outline has-[a:focus-visible]:outline-2 has-[a:focus-visible]:outline-offset-8 has-[a:focus-visible]:outline-ink">
              <DocLink slug={slug} className="t-h3 inline-flex items-center gap-2 underline-offset-4 outline-2 outline-transparent after:absolute after:inset-0 group-hover:underline focus-visible:outline-transparent">
                {title}
                <IconArrowRight aria-hidden="true" className="size-5 text-link motion-safe:transition-transform motion-safe:duration-150 group-hover:translate-x-1" stroke={1.75} />
              </DocLink>
              <span className="t-body mt-1 block max-w-[46ch] text-mute">{text}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

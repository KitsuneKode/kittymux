import { IconBook2, IconKeyboard, IconTerminal2, IconTool } from '@tabler/icons-react';
import { DocLink } from '../doc-link';

const HUB = [
  { slug: 'users/getting-started', title: 'Getting started', text: 'Try the demo, install, check, add hooks.', Icon: IconBook2 },
  { slug: 'users/shortcuts', title: 'Shortcuts', text: 'Every key, grouped by what it does.', Icon: IconKeyboard },
  { slug: 'users/troubleshooting', title: 'Troubleshooting', text: 'A key does nothing? A tab says the wrong thing? Start here.', Icon: IconTool },
  { slug: 'users/cli-reference', title: 'CLI reference', text: 'Every kittymux command and its options.', Icon: IconTerminal2 },
] as const;

export function DocsHub() {
  return (
    <section id="docs" aria-labelledby="docs-title" className="border-y border-line bg-card py-16 lg:py-24">
      <div className="mx-auto w-full max-w-[1280px] px-5 md:px-8">
        <h2 id="docs-title" className="text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-4xl lg:text-5xl">Looking for something?</h2>
        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {HUB.map(({ slug, title, text, Icon }) => (
            <li key={slug}>
              <DocLink slug={slug} data-press="" className="flex h-full flex-col gap-3 rounded-2xl border border-line bg-page p-6 hover:border-brand">
                <Icon aria-hidden="true" className="size-7 text-link" stroke={1.5} />
                <span className="text-lg font-semibold">{title}</span>
                <span className="text-pretty text-mute">{text}</span>
              </DocLink>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

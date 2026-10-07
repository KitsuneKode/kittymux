import { createFileRoute } from '@tanstack/react-router';
import { HomeLayout } from 'fumadocs-ui/layouts/home';
import { KeyTable } from '@/components/key-table';
import { SiteFooter } from '@/components/site-footer';
import { facts } from '@/lib/facts';
import { baseOptions } from '@/lib/layout.shared';

export const Route = createFileRoute('/keys')({
  head: () => ({
    meta: [
      { title: 'Keys — kittymux' },
      { name: 'description', content: `Every key kittymux binds (${facts.chords}), grouped by what it does and generated from the key template.` },
    ],
  }),
  component: Keys,
});

function Keys() {
  return (
    <HomeLayout {...baseOptions()}>
      <div className="mx-auto w-full max-w-[1000px] px-5 py-12 md:px-8">
        <h1 className="text-balance text-4xl font-bold tracking-[-0.03em] sm:text-5xl">Keys</h1>
        <p className="mt-4 max-w-[60ch] text-pretty text-lg text-mute">
          All <span className="tabular">{facts.chords}</span> chords, read from the same file kittymux installs, so this page cannot be out of date. <code>ctrl+alt+/</code> shows the same list inside kitty.
        </p>
        <div className="mt-10">
          <KeyTable keys={facts.keys} />
        </div>
      </div>
      <SiteFooter />
    </HomeLayout>
  );
}

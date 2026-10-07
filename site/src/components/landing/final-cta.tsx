import { CopyButton } from '../copy-button';
import { DocLink } from '../doc-link';

export function FinalCta() {
  return (
    <section data-red="" aria-labelledby="final" className="bg-brand text-onred">
      <div className="mx-auto flex w-full max-w-[1280px] flex-col items-start gap-6 px-5 py-16 md:px-8 lg:flex-row lg:items-center lg:justify-between lg:py-20">
        <div>
          <h2 id="final" className="max-w-[16ch] text-balance text-4xl font-bold tracking-[-0.03em] sm:text-5xl">Stop hunting through tabs.</h2>
          <p className="mt-3 max-w-[44ch] text-pretty text-lg text-onred-soft">Run the demo first. It opens its own window and leaves your setup alone.</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <CopyButton text="kittymux demo" label="Copy: kittymux demo" className="bg-onred text-brand" />
          <DocLink slug="users/getting-started" data-press="" className="inline-flex min-h-12 items-center rounded-full border border-onred px-6 font-semibold hover:bg-onred hover:text-brand">Getting started</DocLink>
        </div>
      </div>
    </section>
  );
}

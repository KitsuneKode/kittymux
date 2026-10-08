import { CopyButton } from '../copy-button';
import { DocLink } from '../doc-link';
import { DEMO_CMD } from './install';
import { Mascot } from '../logo';

export function FinalCta() {
  return (
    <section data-brand="" aria-labelledby="final" className="relative overflow-hidden bg-brand text-onbrand">
      {/* the kitten grows out of the lower-right corner of the band, as it does out of the lower-left of the social card */}
      <Mascot width={230} className="absolute -bottom-6 right-[max(1rem,calc((100%-1280px)/2+2rem))] hidden md:block" />
      <div className="relative mx-auto flex w-full max-w-[1280px] flex-col items-start gap-6 px-5 py-16 md:px-8 lg:py-20 lg:pe-72">
        <div>
          <h2 id="final" className="max-w-[16ch] text-balance text-4xl font-bold tracking-[-0.03em] sm:text-5xl">Stop hunting through tabs.</h2>
          <p className="mt-3 max-w-[44ch] text-pretty text-lg text-onbrand-soft">Run the demo first. It opens its own window and leaves your setup alone.</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <CopyButton text={DEMO_CMD} label="Copy the demo command" className="bg-onbrand text-brand" />
          <DocLink slug="users/getting-started" data-press="" className="inline-flex min-h-12 items-center rounded-full border border-onbrand px-6 font-semibold hover:bg-onbrand hover:text-brand">Getting started</DocLink>
        </div>
      </div>
    </section>
  );
}

import { CopyButton } from '../copy-button';
import { DEMO_CMD } from './install';
import { Mascot } from '../logo';

export function FinalCta() {
  return (
    <section data-brand="" aria-labelledby="final" className="relative overflow-clip bg-brand text-onbrand">
      {/* the kitten grows out of the lower-right corner of the band, as it does out of the lower-left of the social card */}
      <Mascot width={230} className="absolute -inset-be-6 inset-e-[max(1rem,calc((100%-1280px)/2+2rem))] hidden md:block" />
      <div className="relative mx-auto flex w-full max-w-[1280px] flex-col items-start gap-6 px-5 py-16 md:px-8 lg:py-20 lg:pe-72">
        <div>
          <h2 id="final" className="t-display max-w-[14ch]">Stop hunting through tabs.</h2>
          <p className="t-lead mt-3 max-w-[40ch] text-onbrand-soft">Run the demo first. It opens its own window and leaves your setup alone.</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <CopyButton text={DEMO_CMD} label="Copy the demo command" className="bg-onbrand text-brand" />
        </div>
      </div>
    </section>
  );
}

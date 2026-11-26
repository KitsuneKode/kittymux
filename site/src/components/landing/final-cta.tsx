import { CopyButton } from '../copy-button';
import { Mascot } from '../logo';
import { DEMO_CMD } from './install';

/** Closing full-bleed cobalt poster backed by vivid cosmos artwork from imageory.in, anchored by a giant clipped wordmark. */
export function FinalCta() {
  return (
    <section data-brand="" aria-labelledby="final" className="relative isolate overflow-clip bg-brand text-onbrand">
      <img
        src="/brand/art/cosmos-rays.webp"
        width={1672}
        height={941}
        alt=""
        aria-hidden="true"
        loading="lazy"
        decoding="async"
        className="pointer-events-none absolute inset-0 -z-20 h-full w-full object-cover object-center opacity-78"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 bg-[linear-gradient(100deg,color-mix(in_oklch,var(--brand)_88%,transparent)_0%,color-mix(in_oklch,var(--brand)_58%,transparent)_52%,color-mix(in_oklch,var(--brand)_26%,transparent)_100%)]"
      />
      <Mascot width={220} className="absolute -inset-be-6 inset-e-[max(1rem,calc((100%-1220px)/2+2rem))] z-10 hidden md:block" />
      <div className="relative z-10 mx-auto flex w-full max-w-[1220px] flex-col items-start gap-6 px-5 pb-14 pt-20 md:px-8 lg:pb-16 lg:pe-72 lg:pt-24">
        <div>
          <h2 id="final" className="t-display max-w-[14ch]">Stop hunting through tabs.</h2>
          <p className="t-body mt-4 max-w-[44ch] text-onbrand-soft">
            Run the isolated demo window first. It leaves your kitty configuration untouched.
          </p>
        </div>
        <CopyButton text={DEMO_CMD} label="Copy the demo command" className="bg-signal text-onsignal shadow-lg hover:bg-onbrand hover:text-brand" />
      </div>
      {/* Clipped monumental mono wordmark anchoring the poster edge */}
      <div
        aria-hidden="true"
        className="pointer-events-none relative -mb-[0.22em] select-none overflow-clip px-4 text-center font-mono text-[clamp(4.5rem,14vw,12rem)] font-extrabold leading-[0.82] tracking-[-0.05em] text-onbrand/12"
      >
        kittymux
      </div>
    </section>
  );
}

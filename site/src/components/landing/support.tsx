import { IconBug, IconHeart, IconStar } from '@tabler/icons-react';
import { GitHubStars } from '../github-stars';
import { buttonVariants } from '../ui/button';
import { cn } from '@/lib/utils';
import { ISSUES_URL, REPO, SPONSOR_URL, stars } from '@/lib/links';

/** Three ways to help, as three actions with a line each: buttons that are real links to GitHub, no cards. Nothing here collects or sends anything. */
export function Support() {
  return (
    <section aria-labelledby="support" className="mx-auto w-full max-w-[1280px] px-5 py-16 md:px-8 lg:py-24">
      <h2 id="support" className="t-h2 max-w-[18ch]">Keep kittymux going</h2>
      <p className="t-lead mt-4 max-w-[54ch] text-mute">
        kittymux is free and MIT-licensed, built and tested on one person’s daily setup. Every star, sponsor and bug report decides what gets fixed next.
      </p>
      <ul className="mt-12 grid gap-10 md:grid-cols-3 md:gap-8">
        <li className="flex flex-col items-start gap-3">
          <IconStar aria-hidden="true" className="size-6 text-link" stroke={1.75} />
          <p className="t-small max-w-[34ch] text-mute">A star is the quickest way to say it helped, and it helps other kitty users find it.</p>
          <GitHubStars repo={REPO} stargazersCount={stars} className="h-10 border border-line bg-card px-4 text-ink hover:bg-card-hi" />
        </li>
        <li className="flex flex-col items-start gap-3">
          <IconHeart aria-hidden="true" className="size-6 text-link" stroke={1.75} />
          <p className="t-small max-w-[34ch] text-mute">Sponsorship pays for the slow parts: checking each new agent CLI against real sessions and keeping the docs true.</p>
          <a href={SPONSOR_URL} target="_blank" rel="noopener" className={cn(buttonVariants({ size: 'lg' }), 'min-h-11 bg-pink px-4 font-semibold text-onpink hover:bg-pink/90 sm:min-h-10')}>
            <IconHeart aria-hidden="true" data-icon="inline-start" stroke={2} />
            Sponsor on GitHub
          </a>
        </li>
        <li className="flex flex-col items-start gap-3">
          <IconBug aria-hidden="true" className="size-6 text-link" stroke={1.75} />
          <p className="t-small max-w-[34ch] text-mute">If an agent shows the wrong state, open an issue with what was on its screen. That is how the markers get verified.</p>
          <a href={ISSUES_URL} target="_blank" rel="noopener" className={cn(buttonVariants({ variant: 'outline', size: 'lg' }), 'min-h-11 border-line px-4 sm:min-h-10')}>
            Open an issue
          </a>
        </li>
      </ul>
    </section>
  );
}

import { IconBug } from '@tabler/icons-react';
import { GitHubStars } from '../github-stars';
import { SponsorButton } from '../sponsor-button';
import { buttonVariants } from '../ui/button';
import { cn } from '@/lib/utils';
import { github, ISSUES_URL, REPO, stars } from '@/lib/links';

/** "3 days ago", "today": relative to the day the site was built, which is the day of the last push to main (every push rebuilds it). */
export function sinceLabel(iso: string | null, now = Date.now()): string | null {
  if (!iso) return null;
  const days = Math.floor((now - Date.parse(iso)) / 86_400_000);
  if (Number.isNaN(days) || days < 0) return null;
  return days === 0 ? 'today' : days === 1 ? 'yesterday' : `${days} days ago`;
}

/** What GitHub says about the project, as plain numbers (read at build time; any number GitHub could not give is left out, never guessed). */
function Facts() {
  const n = (v: number | null, one: string, many: string) => (!v ? null : `${v.toLocaleString('en-US')} ${v === 1 ? one : many}`);
  const items = [n(github.stars, 'star', 'stars'), n(github.forks, 'fork', 'forks'), (github.issues === 0 ? 'no open issues' : n(github.issues, 'open issue', 'open issues')), github.pushed ? `last commit ${sinceLabel(github.pushed)}` : null, 'MIT license'].filter(Boolean) as string[];
  return (
    <ul aria-label="The project on GitHub" className="t-small mt-8 flex flex-wrap gap-x-6 gap-y-1 text-mute">
      {items.map((t) => (
        <li key={t} className="tabular">{t}</li>
      ))}
    </ul>
  );
}

/** Three ways to help, in order of effort, with real numbers under the heading. The buttons are real links to GitHub; nothing here collects or sends anything. */
export function Support() {
  return (
    <section id="support" aria-labelledby="support-title" className="mx-auto w-full max-w-[1280px] px-5 py-16 md:px-8 lg:py-24">
      <h2 id="support-title" className="t-h2 max-w-[18ch]">Keep kittymux going</h2>
      <p className="t-lead mt-4 max-w-[54ch] text-mute">
        kittymux is free and MIT-licensed, built and tested on one person’s daily setup. Every star, sponsor and bug report decides what gets fixed next.
      </p>
      <Facts />
      <ul className="mt-10 grid gap-10 md:grid-cols-3 md:gap-8">
        <li className="flex flex-col items-start gap-4">
          <p className="t-small max-w-[34ch] text-mute">A star is the quickest way to say it helped, and it helps other kitty users find it.</p>
          <GitHubStars repo={REPO} stargazersCount={stars} />
        </li>
        <li className="flex flex-col items-start gap-4">
          <p className="t-small max-w-[34ch] text-mute">Sponsorship pays for the slow parts: checking each new agent CLI against real sessions and keeping the docs true.</p>
          <SponsorButton label="Sponsor on GitHub" />
        </li>
        <li className="flex flex-col items-start gap-4">
          <p className="t-small max-w-[34ch] text-mute">If an agent shows the wrong state, open an issue with what was on its screen. That is how the markers get verified.</p>
          <a href={ISSUES_URL} target="_blank" rel="noopener" className={cn(buttonVariants({ variant: 'outline', size: 'lg' }), 'min-h-11 gap-2 rounded-full border-line px-4 sm:min-h-10')}>
            <IconBug aria-hidden="true" data-icon="inline-start" stroke={1.9} />
            Open an issue
          </a>
        </li>
      </ul>
    </section>
  );
}

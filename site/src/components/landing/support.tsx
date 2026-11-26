import { GitHubStars } from '../github-stars';
import { SponsorButton } from '../sponsor-button';
import { github, ISSUES_URL, REPO, stars } from '@/lib/links';

/** "3 days ago", "today": relative to the day the site was built, which is the day of the last push to main. */
export function sinceLabel(iso: string | null, now = Date.now()): string | null {
  if (!iso) return null;
  const days = Math.floor((now - Date.parse(iso)) / 86_400_000);
  if (Number.isNaN(days) || days < 0) return null;
  return days === 0 ? 'today' : days === 1 ? 'yesterday' : `${days} days ago`;
}

function Facts() {
  const n = (v: number | null, one: string, many: string) => (!v ? null : `${v.toLocaleString('en-US')} ${v === 1 ? one : many}`);
  const items = [
    n(github.stars, 'star', 'stars'),
    n(github.forks, 'fork', 'forks'),
    github.issues === 0 ? 'no open issues' : n(github.issues, 'open issue', 'open issues'),
    github.pushed ? `last commit ${sinceLabel(github.pushed)}` : null,
    'MIT license',
  ].filter(Boolean) as string[];
  return (
    <ul aria-label="The project on GitHub" className="t-caption mt-6 flex flex-wrap gap-x-6 gap-y-1 text-mute">
      {items.map((t) => (
        <li key={t} className="tabular">{t}</li>
      ))}
    </ul>
  );
}

export function Support() {
  return (
    <section id="support" aria-labelledby="support-title" className="border-t border-line bg-card py-20 lg:py-28">
      <div className="mx-auto w-full max-w-[1220px] px-5 md:px-8">
        <div className="max-w-[54ch]">
          <h2 id="support-title" className="t-h2">Keep kittymux going</h2>
          <p className="t-body mt-4 text-mute">
            kittymux is free and MIT-licensed, built and tested on a real daily kitty setup. Every star, sponsor, and bug report shapes what gets verified next.
          </p>
          <Facts />
        </div>
        <ul className="mt-12 grid gap-10 border-t border-line pt-10 md:grid-cols-3 md:gap-8">
          <li className="flex flex-col items-start gap-4">
            <p className="t-body max-w-[34ch] text-mute">A star is the quickest way to say it helped and helps other kitty users find it.</p>
            <GitHubStars repo={REPO} stargazersCount={stars} />
          </li>
          <li className="flex flex-col items-start gap-4">
            <p className="t-body max-w-[34ch] text-mute">Sponsorship funds the slow work: checking new agent CLIs against live sessions and keeping every guide accurate.</p>
            <SponsorButton label="Sponsor on GitHub" />
          </li>
          <li className="flex flex-col items-start gap-4">
            <p className="t-body max-w-[34ch] text-mute">If an agent reports the wrong state, open an issue with what appeared on screen so its markers get verified.</p>
            <a href={ISSUES_URL} target="_blank" rel="noopener" data-press="" className="raised inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold text-ink sm:min-h-10">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" className="size-4 shrink-0"><path d="M9 9V8a3 3 0 0 1 6 0v1m-7 0h8a6 6 0 0 1 1 3v3a5 5 0 0 1-10 0v-3a6 6 0 0 1 1-3M3 13h4m10 0h4M12 20v-6M4 19l3.35-2M20 19l-3.35-2M4 7l3.75 2.4M20 7l-3.75 2.4" /></svg>
              Open an issue
            </a>
          </li>
        </ul>
      </div>
    </section>
  );
}

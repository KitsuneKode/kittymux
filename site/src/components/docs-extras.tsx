import { GitHubStars } from './github-stars';
import { SponsorButton } from './sponsor-button';
import { REPO, stars } from '@/lib/links';

/** The docs have no top bar on a wide screen (the sidebar is the chrome), so Sponsor is pinned to the top right where a bar would have it. */
export function DocsTopRight() {
  return (
    <aside aria-label="Sponsor kittymux" className="fixed end-5 top-3 z-30 hidden lg:block">
      <SponsorButton className="shadow-[0_6px_18px_-8px_rgb(0_0_0/0.45)]" />
    </aside>
  );
}

/** The end of every docs page: the one moment a reader has just been helped, and the right place to say a star or a sponsor keeps it going. */
export function DocsEnd() {
  return (
    <aside aria-label="Support kittymux" className="mt-16 flex flex-col gap-4 border-t border-line pt-8 sm:flex-row sm:items-center sm:justify-between">
      <p className="t-small max-w-[44ch] text-mute">If this saved you a minute, a star helps other kitty users find kittymux. Sponsoring keeps the docs true.</p>
      <div className="flex flex-wrap items-center gap-2">
        <GitHubStars repo={REPO} stargazersCount={stars} />
        <SponsorButton />
      </div>
    </aside>
  );
}

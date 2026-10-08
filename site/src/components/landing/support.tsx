import { IconBug, IconHeart, IconStar } from '@tabler/icons-react';
import { GitHubStars } from '../github-stars';
import { buttonVariants } from '../ui/button';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '../ui/card';
import { ISSUES_URL, REPO, SPONSOR_URL, stars } from '@/lib/links';

/** Three ways to help, in order of effort. The buttons are real links to GitHub; nothing here collects or sends anything. */
export function Support() {
  return (
    <section aria-labelledby="support" className="mx-auto w-full max-w-[1280px] px-5 py-16 md:px-8 lg:py-24">
      <h2 id="support" className="text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-4xl lg:text-5xl">Keep kittymux going</h2>
      <p className="mt-4 max-w-[60ch] text-pretty text-lg text-mute">
        kittymux is free and MIT-licensed. It is built and tested on one person’s daily setup, so every star, sponsor and bug report decides what gets fixed next.
      </p>
      <div className="mt-10 grid gap-6 md:grid-cols-3">
        <Card className="bg-card">
          <CardHeader>
            <IconStar aria-hidden="true" className="size-7 text-link" stroke={1.75} />
            <CardTitle className="text-xl">Star it on GitHub</CardTitle>
            <CardDescription className="text-base text-mute">A star is the quickest way to say it helped, and it helps other kitty users find it.</CardDescription>
          </CardHeader>
          <CardFooter className="mt-auto">
            <GitHubStars repo={REPO} stargazersCount={stars} className="h-10 border border-line bg-page px-4 text-ink hover:bg-card-hi" />
          </CardFooter>
        </Card>
        <Card className="bg-card">
          <CardHeader>
            <IconHeart aria-hidden="true" className="size-7 text-link" stroke={1.75} />
            <CardTitle className="text-xl">Sponsor the work</CardTitle>
            <CardDescription className="text-base text-mute">Sponsorship pays for the slow parts: checking each new agent CLI against real sessions and keeping the docs true.</CardDescription>
          </CardHeader>
          <CardFooter className="mt-auto">
            <a href={SPONSOR_URL} target="_blank" rel="noopener" className={cn(buttonVariants({ size: 'lg' }), 'min-h-11 bg-pink px-4 font-semibold text-onpink hover:bg-pink/90 sm:min-h-9')}>
              <IconHeart aria-hidden="true" data-icon="inline-start" stroke={2} />
              Sponsor on GitHub
            </a>
          </CardFooter>
        </Card>
        <Card className="bg-card">
          <CardHeader>
            <IconBug aria-hidden="true" className="size-7 text-link" stroke={1.75} />
            <CardTitle className="text-xl">Report what looks wrong</CardTitle>
            <CardDescription className="text-base text-mute">If an agent shows the wrong state, open an issue with what was on its screen. That is how the markers get verified.</CardDescription>
          </CardHeader>
          <CardFooter className="mt-auto">
            <a href={ISSUES_URL} target="_blank" rel="noopener" className={cn(buttonVariants({ variant: 'outline', size: 'lg' }), 'min-h-11 border-line px-4 sm:min-h-9')}>
              Open an issue
            </a>
          </CardFooter>
        </Card>
      </div>
    </section>
  );
}

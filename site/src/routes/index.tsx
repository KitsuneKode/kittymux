import { createFileRoute } from '@tanstack/react-router';
import { ThemeProvider } from 'next-themes';
import { AgentRow } from '@/components/landing/agent-row';
import { DocsHub } from '@/components/landing/docs-hub';
import { FAQ, Faq } from '@/components/landing/faq';
import { FinalCta } from '@/components/landing/final-cta';
import { Hero, LandingHeader } from '@/components/landing/hero';
import { HowItKnows } from '@/components/landing/how-it-knows';
import { Ideas } from '@/components/landing/ideas';
import { Install } from '@/components/landing/install';
import { KeysGlance } from '@/components/landing/keys-glance';
import { Limits } from '@/components/landing/limits';
import { Problem } from '@/components/landing/problem';
import { Roadmap } from '@/components/landing/roadmap';
import { Support } from '@/components/landing/support';
import { SiteFooter } from '@/components/site-footer';
import { faqLd, pageHead, softwareLd, websiteLd } from '@/lib/seo';
import { THEME_PROPS } from '@/lib/theme-props';

const TITLE = 'kittymux: know which agent needs you';
const DESCRIPTION = 'One glance at the bar tells you which coding agent needs you. Native agent cockpit for kitty on Linux: pixel bar, inbox, quotas, zero daemon.';

export const Route = createFileRoute('/')({
  head: () => pageHead({
    title: TITLE,
    description: DESCRIPTION,
    path: '/',
    ldJson: [softwareLd(), websiteLd(), faqLd(FAQ)].filter((x): x is NonNullable<typeof x> => x !== null),
  }),
  component: Home,
});

function Home() {
  return (
    <ThemeProvider {...THEME_PROPS}>
      <div className="min-h-[100dvh] bg-page text-ink">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-ink focus:px-4 focus:py-2 focus:text-page"
        >
          Skip to content
        </a>
        <LandingHeader />
        <main id="main">
          <Hero />
          <AgentRow />
          <Problem />
          <Ideas />
          <HowItKnows />
          <Install />
          <KeysGlance />
          <Roadmap />
          <DocsHub />
          <Limits />
          <Faq />
          <Support />
          <FinalCta />
        </main>
        <SiteFooter themeToggle flush />
      </div>
    </ThemeProvider>
  );
}

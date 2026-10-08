import { createFileRoute } from '@tanstack/react-router';
import { ThemeProvider } from 'next-themes';
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
import { ProofLine } from '@/components/landing/proof-line';
import { SiteFooter } from '@/components/site-footer';
import { THEME_PROPS } from '@/lib/theme-props';
import { faqLd, pageHead, softwareLd } from '@/lib/seo';

const TITLE = 'kittymux — know which agent needs you';
const DESCRIPTION = 'kittymux turns kitty into a multiplexer for AI coding agents: one glance at the tab bar says who is working, who is waiting for you and who has finished.';

export const Route = createFileRoute('/')({
  head: () => pageHead({ title: TITLE, description: DESCRIPTION, path: '/', ldJson: [softwareLd(), faqLd(FAQ)] }),
  component: Home,
});

function Home() {
  return (
    <ThemeProvider {...THEME_PROPS}>
    <div className="min-h-[100dvh] bg-page text-ink">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-ink focus:px-4 focus:py-2 focus:text-page">Skip to content</a>
      <LandingHeader />
      <main id="main">
      <Hero />
      <ProofLine />
      <Problem />
      <Ideas />
      <HowItKnows />
      <Install />
      <KeysGlance />
      <DocsHub />
      <Limits />
      <Faq />
      <FinalCta />
      </main>
      <SiteFooter themeToggle />
    </div>
    </ThemeProvider>
  );
}

import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { SponsorButton } from '@/components/sponsor-button';
import { Logo } from '@/components/logo';
import { ThemeToggle } from '@/components/theme-toggle';

/**
 * `inList`: the home layout puts secondary links in a <ul> (each needs its <li>); the docs layout does not.
 * Sponsor is a pink pill at the top right of every page. On the docs layout a fixed pill (DocsTopRight) does that on wide screens, so the one in the sidebar list only shows below `lg`.
 */
export function baseOptions(inList = false): BaseLayoutProps {
  return {
    nav: {
      title: <Logo size={30} textClassName="text-base" />,
      url: '/',
    },
    links: [
      { text: 'Docs', url: '/docs', active: 'url' },   // exact: inside the docs the sidebar below already marks the page, and two highlighted rows read as a mistake
      { text: 'Keys', url: '/keys' },
      { text: 'Changelog', url: '/changelog' },
      { type: 'custom', secondary: true, children: inList ? <li className="list-none"><SponsorButton collapse /></li> : <SponsorButton collapse className="lg:hidden" /> },
    ],
    slots: { themeSwitch: () => <ThemeToggle /> },
  };
}

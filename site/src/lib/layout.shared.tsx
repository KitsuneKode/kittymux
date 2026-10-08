import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { IconHeart } from '@tabler/icons-react';
import { GitHubStars } from '@/components/github-stars';
import { Logo } from '@/components/logo';
import { ThemeToggle } from '@/components/theme-toggle';
import { REPO, SPONSOR_URL, stars } from './links';

/** `inList`: the home layout puts secondary links in a <ul> (each needs its <li>); the docs layout does not. */
export function baseOptions(inList = false): BaseLayoutProps {
  const stars_ = <GitHubStars repo={REPO} stargazersCount={stars} />;
  return {
    nav: {
      title: <Logo size={30} textClassName="text-base" />,
      url: '/',
    },
    links: [
      { text: 'Docs', url: '/docs', active: 'nested-url' },
      { text: 'Keys', url: '/keys' },
      { text: 'Changelog', url: '/changelog' },
      { type: 'icon', text: 'Sponsor', label: 'Sponsor kittymux on GitHub', url: SPONSOR_URL, icon: <IconHeart aria-hidden="true" />, external: true },
      { type: 'custom', secondary: true, children: inList ? <li className="list-none">{stars_}</li> : stars_ },
    ],
    slots: { themeSwitch: () => <ThemeToggle /> },
  };
}

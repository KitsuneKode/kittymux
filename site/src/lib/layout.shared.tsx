import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { IconBrandGithub } from '@tabler/icons-react';
import { ThemeToggle } from '@/components/theme-toggle';
import { appName, gitConfig } from './shared';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <span className="flex items-center gap-2 font-semibold tracking-tight">
          <span aria-hidden="true" className="grid size-7 place-items-center rounded-md bg-brand text-sm font-bold text-onred">
            k
          </span>
          {appName}
        </span>
      ),
      url: '/',
    },
    links: [
      { text: 'Docs', url: '/docs', active: 'nested-url' },
      { text: 'Keys', url: '/keys' },
      { text: 'Changelog', url: '/changelog' },
      { type: 'icon', text: 'GitHub', label: 'kittymux on GitHub', url: `https://github.com/${gitConfig.user}/${gitConfig.repo}`, icon: <IconBrandGithub aria-hidden="true" />, external: true },
    ],
    slots: { themeSwitch: () => <ThemeToggle /> },
  };
}

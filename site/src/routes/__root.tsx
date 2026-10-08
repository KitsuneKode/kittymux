import { createRootRoute, HeadContent, Outlet, Scripts } from '@tanstack/react-router';
import appCss from '@/styles/app.css?url';
import { Telemetry } from '@/components/telemetry';
// the two files every page's first paint needs (latin subsets), fetched alongside the CSS instead of after it: the text is set in the right font from the first frame
import displayLatin from '../../node_modules/@fontsource-variable/bricolage-grotesque/files/bricolage-grotesque-latin-wght-normal.woff2?url';
import textLatin from '../../node_modules/@fontsource-variable/geist/files/geist-latin-wght-normal.woff2?url';
import monoLatin from '../../node_modules/@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2?url';

export const Route = createRootRoute({
  head: () => ({
    meta: [
      {
        charSet: 'utf-8',
      },
      {
        name: 'viewport',
        content: 'width=device-width, initial-scale=1',
      },
      { name: 'theme-color', content: '#3F5B86' },   // the brand blue: the top of the page is blue in both themes (two media-specific entries are merged into one by name)
      { name: 'color-scheme', content: 'light dark' },
    ],
    links: [
      { rel: 'preload', href: displayLatin, as: 'font', type: 'font/woff2', crossOrigin: 'anonymous' },
      { rel: 'preload', href: textLatin, as: 'font', type: 'font/woff2', crossOrigin: 'anonymous' },
      { rel: 'preload', href: monoLatin, as: 'font', type: 'font/woff2', crossOrigin: 'anonymous' },
      { rel: 'stylesheet', href: appCss },
      { rel: 'icon', href: '/favicon-32.png', sizes: '32x32', type: 'image/png' },
      { rel: 'icon', href: '/favicon-64.png', sizes: '64x64', type: 'image/png' },
      { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' },
      { rel: 'manifest', href: '/site.webmanifest' },
    ],
  }),
  component: RootComponent,
});

function RootComponent() {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <HeadContent />
      </head>
      <body className="flex flex-col min-h-screen">
        <Outlet />
        <Telemetry />
        <Scripts />
      </body>
    </html>
  );
}

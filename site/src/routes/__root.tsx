import { createRootRoute, HeadContent, Outlet, Scripts } from '@tanstack/react-router';
import appCss from '@/styles/app.css?url';

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
      {
        title: 'kittymux',
      },
    ],
    links: [{ rel: 'stylesheet', href: appCss }, { rel: 'icon', href: '/favicon.svg', type: 'image/svg+xml' }],
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
        <Scripts />
      </body>
    </html>
  );
}

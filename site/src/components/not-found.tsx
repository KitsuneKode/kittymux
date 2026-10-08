import * as React from 'react';

const Full = React.lazy(() => import('@/components/not-found-full'));   // Fumadocs' layout and provider load only for a page that does not exist

export function NotFound() {
  return (
    <React.Suspense fallback={null}>
      <Full />
    </React.Suspense>
  );
}

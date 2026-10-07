import { Link } from '@tanstack/react-router';
import type { ComponentProps, ReactNode } from 'react';

/** A link to a docs page by its slug ("users/getting-started"), typed against the route tree. */
export function DocLink({ slug = '', children, ...rest }: { slug?: string; children: ReactNode } & Omit<ComponentProps<'a'>, 'href'>) {
  return (
    <Link to="/docs/$" params={{ _splat: slug }} {...rest}>
      {children}
    </Link>
  );
}

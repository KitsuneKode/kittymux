import defaultMdxComponents from 'fumadocs-ui/mdx';
import { Step, Steps } from 'fumadocs-ui/components/steps';
import type { MDXComponents } from 'mdx/types';
import type { ComponentProps } from 'react';

/** A table wider than the column scrolls inside this box; the page itself never scrolls sideways. tabindex lets keyboard users scroll it. */
function Table(props: ComponentProps<'table'>) {
  return (
    <div tabIndex={0} className="my-6 w-full overflow-x-auto rounded-lg border border-line [overscroll-behavior-x:contain]">
      <table {...props} className="m-0 w-full min-w-max border-collapse text-sm [&_td]:px-3 [&_td]:py-2 [&_td]:align-top [&_th]:px-3 [&_th]:py-2 [&_th]:text-start" />
    </div>
  );
}

export function getMDXComponents(components?: MDXComponents) {
  return {
    ...defaultMdxComponents,
    Step,
    Steps,
    table: Table,
    ...components,
  } satisfies MDXComponents;
}

export const useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}

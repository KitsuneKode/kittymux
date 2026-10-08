import { BookOpen, Wrench } from 'lucide-react';
import { createElement, type ComponentType } from 'react';

/**
 * The sidebar icons the docs name in a meta.json `icon`. Fumadocs' own `lucideIconsPlugin` looks names up in lucide's whole set, which put
 * ~1,850 icon modules (178 KB gzip) into every page, the landing page included. A name that is not listed here is a build-time warning, and
 * `icons.test.ts` fails the tests, so a new `icon` in docs/ cannot silently lose its icon.
 */
export const ICONS: Record<string, ComponentType> = { BookOpen, Wrench };

function resolve(icon: unknown) {
  if (typeof icon !== 'string') return icon;
  const Icon = ICONS[icon];
  if (!Icon) {
    console.warn(`[icons] unknown sidebar icon "${icon}": add it to src/lib/icons.ts`);
    return undefined;
  }
  return createElement(Icon);
}

type IconNode = { icon?: unknown };
const replace = <T extends IconNode>(node: T): T => {
  if (node.icon === undefined || typeof node.icon === 'string') node.icon = resolve(node.icon);
  return node;
};

/** A Fumadocs source plugin that turns the icon names into elements. */
export const iconsPlugin = () => ({
  name: 'kittymux:icons',
  transformPageTree: { file: replace, folder: replace, separator: replace },
});

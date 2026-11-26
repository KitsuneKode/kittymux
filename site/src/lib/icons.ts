import { IconBook, IconTool } from '@tabler/icons-react';
import { createElement, type ComponentType } from 'react';

/**
 * The sidebar icons the docs name in a meta.json `icon`. Using Tabler icons (already loaded elsewhere) keeps lucide-react off the landing page.
 */
export const ICONS: Record<string, ComponentType> = { BookOpen: IconBook, Wrench: IconTool };

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

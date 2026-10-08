import { useRouter } from '@tanstack/react-router';
import { useEffect, useLayoutEffect, useRef } from 'react';

/** The `$` part of /docs/$ for a docs address ("/docs/users/shortcuts" → "users/shortcuts"); null for /docs itself or anything else. */
export function splatOf(url: string): string | null {
  const m = /^\/docs\/(.+?)\/?$/.exec(url);
  return m ? m[1] : null;
}

type Node = { type?: string; url?: string; index?: { url?: string }; children?: Node[] };

/** Every page address in sidebar order: a folder's own page first (if it has one), then its children. Separators and anything without an address are skipped. */
export function pageUrls(node: Node, out: string[] = []): string[] {
  if (node.type === 'page' && node.url) out.push(node.url);
  if (node.type === 'folder' && node.index?.url) out.push(node.index.url);
  for (const child of node.children ?? []) pageUrls(child, out);
  return out;
}

/** The docs addresses the pager links to from `url`: the page before and the page after it, in the order of the sidebar. (A small walker, not Fumadocs' own
 * `findNeighbour`: importing that for two addresses added 8 KB to every docs page.) */
export function neighbourUrls(tree: unknown, url: string): string[] {
  try {
    const all = pageUrls(tree as Node);
    const i = all.indexOf(url);
    if (i < 0) return [];
    return [all[i - 1], all[i + 1]].filter((u): u is string => typeof u === 'string');
  } catch {
    return [];
  }
}

let byHistory = 0;
if (typeof window !== 'undefined') window.addEventListener('popstate', () => { byHistory = Date.now(); });
/** Back and forward restore the old position; a click does not. The flag expires, so a back-step that never rendered a docs page cannot swallow a later click. */
export function arrivedByHistory(now = Date.now()): boolean {
  const was = byHistory !== 0 && now - byHistory < 3000;
  byHistory = 0;
  return was;
}

/**
 * Put the reader at the top of a docs page once ITS CONTENT is on screen. The router resets the scroll when the address changes, but a docs page's content
 * arrives a moment later (its code is loaded behind a Suspense boundary): on a slow load the address and the scroll position had already changed while the old
 * page was still drawn, and the new page then appeared wherever the browser's clamped position left it. Doing it after the content commits cannot be early.
 * Not on the first render (a reload keeps the browser's position), not for back/forward, and a `#anchor` goes to its heading instead.
 */
export function useArriveAtTop(key: string) {
  const first = useRef(true);
  useLayoutEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (arrivedByHistory()) return;
    const id = decodeURIComponent(window.location.hash.slice(1));
    const heading = id ? document.getElementById(id) : null;
    if (heading) heading.scrollIntoView();
    else if (!id) window.scrollTo({ top: 0, left: 0, behavior: 'instant' as ScrollBehavior });
  }, [key]);
}

/** Load the previous and next pages' data and code while the browser is idle, so the pager's "Next" is instant. Not on a data-saver connection. */
export function usePreloadNeighbours(tree: unknown, url: string) {
  const router = useRouter();
  useEffect(() => {
    const nav = navigator as Navigator & { connection?: { saveData?: boolean } };
    if (nav.connection?.saveData) return;
    const run = () => {
      for (const u of neighbourUrls(tree, url)) {
        const splat = splatOf(u);
        if (splat) router.preloadRoute({ to: '/docs/$', params: { _splat: splat } }).catch(() => undefined);
      }
    };
    const w = window as Window & { requestIdleCallback?: (f: () => void, o?: { timeout: number }) => number; cancelIdleCallback?: (n: number) => void };
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(run, { timeout: 3000 });
      return () => w.cancelIdleCallback?.(id);
    }
    const t = setTimeout(run, 1500);
    return () => clearTimeout(t);
  }, [router, tree, url]);
}

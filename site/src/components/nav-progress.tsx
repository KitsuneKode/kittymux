import { useRouterState } from '@tanstack/react-router';
import { useEffect, useState } from 'react';

/**
 * A slim bar at the top of the window while a page is loading. A docs page is its data plus its code (two files, one after the other), and on a cold cache the old
 * page used to stay on screen, unchanged, for a second or more after a click: it looked as if the click had done nothing. The bar appears only after 150 ms, so a
 * preloaded page (the usual case) never shows it, and it is a fixed 3 px strip, so it moves nothing.
 */
export function NavProgress() {
  const pending = useRouterState({ select: (s) => s.status === 'pending' });
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!pending) {
      setShow(false);
      return;
    }
    const t = setTimeout(() => setShow(true), 150);
    return () => clearTimeout(t);
  }, [pending]);
  return show ? <div role="progressbar" aria-label="Loading the page" aria-busy="true" className="nav-progress" /> : null;
}

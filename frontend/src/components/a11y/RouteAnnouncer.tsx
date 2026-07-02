import { useEffect, useRef, useState } from 'react';

interface RouteAnnouncerProps {
  /** The resolved, human-readable name of the page currently in view. */
  title: string;
}

/**
 * SPA route announcer (#226 · WCAG 2.4.x — screen-reader pass).
 *
 * A single-page app swaps the <main> content on navigation without a full page
 * load, so a screen reader gets no signal that the destination changed — focus
 * stays put and nothing is spoken. This renders a persistent polite live region
 * (kept mounted by the surrounding layout across every in-app route change) and
 * updates its text with the new page's name whenever the title changes, so the
 * navigation is narrated.
 *
 * The very first mount is intentionally silent: live regions only announce
 * *updates*, and speaking on first paint would double up with the browser's own
 * page-load context. We only narrate subsequent client-side navigations.
 */
export default function RouteAnnouncer({ title }: RouteAnnouncerProps) {
  const [message, setMessage] = useState('');
  const mounted = useRef(false);

  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    setMessage(title);
  }, [title]);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className="sr-only"
      data-testid="route-announcer"
    >
      {message}
    </div>
  );
}

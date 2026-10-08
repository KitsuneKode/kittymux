/**
 * The site counts visits with Vercel Web Analytics and Speed Insights: no cookies, no personal data, and the scripts are served from this site's own
 * address (/_vercel/...), not a third party's. A visitor who sends "Do Not Track" or Global Privacy Control is not counted at all.
 */
export function wantsNoTracking(nav: { doNotTrack?: string | null; globalPrivacyControl?: boolean } | undefined = typeof navigator === 'undefined' ? undefined : navigator): boolean {
  if (!nav) return false
  return nav.doNotTrack === '1' || nav.doNotTrack === 'yes' || nav.globalPrivacyControl === true
}

/** Used as `beforeSend`: returning null drops the event. */
export function beforeSend<T>(event: T): T | null {
  return wantsNoTracking() ? null : event
}

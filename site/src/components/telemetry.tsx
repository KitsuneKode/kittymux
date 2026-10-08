import { Analytics } from '@vercel/analytics/react';
import { SpeedInsights } from '@vercel/speed-insights/react';
import { beforeSend } from '@/lib/telemetry';

/** Visit counts and real-user speed, from Vercel, first-party and cookie-less. A development server only logs to the console. */
export function Telemetry() {
  return (
    <>
      <Analytics beforeSend={beforeSend} />
      <SpeedInsights beforeSend={beforeSend} />
    </>
  );
}

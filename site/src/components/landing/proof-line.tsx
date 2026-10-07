import { facts } from '@/lib/facts';

export function ProofLine() {
  const items = [
    `${facts.agents.length} agents recognised`,
    'Local only: no server, no daemon',
    'Silence is never “waiting”',
    'Asks before resuming a conversation',
  ];
  return (
    <section aria-label="What you can rely on"><ul className="mx-auto flex w-full max-w-[1280px] flex-wrap gap-x-8 gap-y-2 px-5 py-6 text-sm font-medium md:px-8">
      {items.map((t) => (
        <li key={t} className="before:me-2 before:text-brand before:content-['◆']">
          {t}
        </li>
      ))}
    </ul></section>
  );
}

import { facts } from '@/lib/facts';

/** Real notification icons kittymux ships for recognised agent CLIs. */
const AGENTS = [
  ['claude', 'Claude Code'], ['codex', 'Codex'], ['devin', 'Devin'], ['cursor', 'Cursor Agent'],
  ['opencode', 'OpenCode'], ['gemini', 'Gemini CLI'], ['amp', 'Amp'], ['antigravity', 'Antigravity'],
  ['droid', 'Factory Droid'], ['goose', 'Goose'], ['grok', 'Grok'], ['qwen', 'Qwen Code'],
] as const;

export function AgentRow() {
  return (
    <section aria-label="Agents kittymux recognises" className="border-y border-line bg-card/65 py-10">
      <div className="mx-auto flex w-full max-w-[1220px] flex-col items-start justify-between gap-6 px-5 md:px-8 lg:flex-row lg:items-center">
        <p className="t-small max-w-[30ch] text-mute">
          Recognises <strong className="font-semibold text-ink">{facts.agents.length} agent CLIs</strong> plus T3 Code, with brand tiles and state hooks.
        </p>
        <ul className="flex flex-wrap items-center gap-3 sm:gap-3.5">
          {AGENTS.map(([id, name]) => (
            <li key={id}>
              <img
                src={`/brand/agents/${id}.png`}
                width={52}
                height={52}
                alt={name}
                title={name}
                loading="lazy"
                decoding="async"
                className="agent-tile size-11 rounded-[22%] shadow-sm ring-1 ring-black/8 dark:ring-white/10 sm:size-12"
              />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

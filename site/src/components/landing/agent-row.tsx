/** The agents kittymux recognises, as logos and nothing else (no labels under them). Each tile is the notification icon kittymux itself uses: the agent's mark with the mascot as a badge. */
const AGENTS = [
  ['claude', 'Claude Code'], ['codex', 'Codex'], ['devin', 'Devin'], ['cursor', 'Cursor'], ['opencode', 'OpenCode'], ['gemini', 'Gemini CLI'],
  ['amp', 'Amp'], ['antigravity', 'Antigravity'], ['droid', 'Factory Droid'], ['goose', 'Goose'], ['grok', 'Grok'], ['qwen', 'Qwen Code'],
] as const;

export function AgentRow() {
  return (
    <section aria-label="Agents kittymux recognises" className="mx-auto w-full max-w-[1280px] px-5 py-10 md:px-8">
      <ul className="flex flex-wrap items-center gap-3 sm:gap-4">
        {AGENTS.map(([id, name]) => (
          <li key={id}>
            <img src={`/brand/agents/${id}.png`} width={56} height={56} alt={name} loading="lazy" decoding="async" className="size-12 rounded-[22%] sm:size-14" />
          </li>
        ))}
      </ul>
    </section>
  );
}

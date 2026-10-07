import { Link } from '@tanstack/react-router';
import { facts } from '@/lib/facts';
import { gitConfig } from '@/lib/shared';
import { WeaveBand } from './weave-band';

export function SiteFooter() {
  return (
    <footer className="mt-24">
      <WeaveBand id="foot" />
      <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-6 px-5 py-10 text-sm text-mute md:flex-row md:items-center md:justify-between md:px-8">
        <p>
          kittymux <span className="tabular">{facts.version}</span> · kitty as a multiplexer for AI coding agents
        </p>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2">
          <Link to="/docs/$" params={{ _splat: '' }} className="py-2 hover:text-ink">Docs</Link>
          <Link to="/keys" className="py-2 hover:text-ink">Keys</Link>
          <Link to="/changelog" className="py-2 hover:text-ink">Changelog</Link>
          <a href={`https://github.com/${gitConfig.user}/${gitConfig.repo}`} className="py-2 hover:text-ink">GitHub</a>
        </nav>
      </div>
    </footer>
  );
}

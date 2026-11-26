import { docsLlms } from '@/lib/source';
import { createFileRoute } from '@tanstack/react-router';

const SUMMARY = 'kittymux turns kitty into a native workspace for AI coding agents: Cairo/Slang pixel tab bar (pxbar), graphical multi-account Usage and expandable Inbox panel (deckpx), direct hooks (Claude Code, Codex, OpenCode, OSC 7501 mux-pty), Kitty 0.50 scoped pane controls, Quickshell sidebar client, command palette, and session restore. Local only; Linux; verified on kitty 0.49.1, 0.49.2, and 0.50.0.';

const EXTRA = `## Feeds and reference

- [All key chords](/keys): every bound shortcut read from kittymux-keys.conf.tpl
- [Changelog](/changelog): latest upgrades, fixes, and releases
- [RSS feed](/rss.xml): changelog updates in RSS 2.0 format
- [Full documentation corpus](/llms-full.txt): concatenated Markdown of every guide
`;

export const Route = createFileRoute('/llms.txt')({
  server: {
    handlers: {
      GET: async () => {
        const index = await docsLlms.index();
        const body = index.replace(/^# [^\n]*\n+/, '');
        return new Response(`# kittymux\n\n> ${SUMMARY}\n\n${body}\n${EXTRA}`, { headers: { 'content-type': 'text/plain; charset=utf-8' } });
      },
    },
  },
});

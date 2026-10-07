import { docsLlms } from '@/lib/source';
import { createFileRoute } from '@tanstack/react-router';

const SUMMARY = 'kittymux turns kitty into a multiplexer for AI coding agents: a tab bar that shows which agent is working, which is waiting for you and which has finished, plus a docked panel, an inbox, a command palette and session restore. Local only; Linux; tested on kitty 0.49.1 and 0.49.2.';

export const Route = createFileRoute('/llms.txt')({
  server: {
    handlers: {
      GET: async () => {
        const index = await docsLlms.index();
        const body = index.replace(/^# [^\n]*\n+/, '');                    // the generated heading says "Documentation": the file is about the product
        return new Response(`# kittymux\n\n> ${SUMMARY}\n\n${body}`, { headers: { 'content-type': 'text/plain; charset=utf-8' } });
      },
    },
  },
});

/** Where to start when nothing is typed yet, and where a lost visitor goes: the pages people come for. Chosen by hand; the search-index test checks that each docs one exists. */
export const SUGGESTIONS: { label: string; hint: string; url: string }[] = [
  { label: 'Get started', hint: 'Install and first run', url: '/docs/users/getting-started' },
  { label: 'Keys', hint: 'Every chord, searchable', url: '/keys' },
  { label: 'Agent status', hint: 'What waiting, working and done mean', url: '/docs/users/agent-status' },
  { label: 'Troubleshooting', hint: 'When something looks wrong', url: '/docs/users/troubleshooting' },
  { label: 'Privacy and security', hint: 'What it reads and what it never sends', url: '/docs/users/privacy-and-security' },
  { label: 'Changelog', hint: 'What changed, newest first', url: '/changelog' },
]

/** Other projects by KitsuneKode, for the footer. Wording is ours (short, plain); names and addresses are the ones on each repository's GitHub page. */
export type Project = { name: string; blurb: string; url: string; repo: string; kind: string }

export const PROJECTS: Project[] = [
  { name: 'Kunai', kind: 'CLI', blurb: 'A terminal-first streaming shell for anime, series and movies that plays in mpv.', url: 'https://kunai.kitsunekode.in', repo: 'kunai' },
  { name: 'Sweep', kind: 'CLI', blurb: 'Safe, fast cleanup of node_modules, dist, .next, target and other build leftovers.', url: 'https://www.npmjs.com/package/@kitsunekode/sweep', repo: 'sweep' },
  { name: 'Arche', kind: 'CLI', blurb: 'A preset-led scaffold CLI for full-stack TypeScript monorepos.', url: 'https://arche.kitsunekode.in', repo: 'arche' },
  { name: 'Kyma', kind: 'Web app', blurb: 'Voice-first AI screening for tutor and communication-heavy hiring.', url: 'https://kyma.kitsunekode.in', repo: 'kyma' },
  { name: 'JS Questions Lab', kind: 'Web app', blurb: 'Interactive JavaScript interview practice with runnable snippets and an event-loop view.', url: 'https://jsquestionslab.kitsunekode.in', repo: 'js-questions-lab' },
  { name: 'Kitsu Lab', kind: 'Playground', blurb: 'A playground for unusual UI components.', url: 'https://kitsulab.kitsunekode.in', repo: 'Kitsu-Lab' },
  { name: 'Hyprland Caffeine Mode', kind: 'Utility', blurb: 'Manual idle inhibition for Hyprland, Hypridle and Waybar that survives restarts.', url: 'https://hyprland-caffeine-mode.kitsunekode.in', repo: 'hyprland-caffeine-mode' },
  { name: 'YT Playlist Dedupe', kind: 'CLI', blurb: 'Find and remove duplicate videos in one YouTube playlist, from the terminal.', url: 'https://yt-ddp.kitsunekode.in', repo: 'yt-playlist-dedupe' },
]

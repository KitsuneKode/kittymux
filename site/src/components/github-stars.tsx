import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export type GitHubStarsProps = {
  /** GitHub repository in `owner/repo` format. */
  repo: string
  /** Number of stars to display; null shows the word "Star" instead (no count yet, or GitHub could not be reached at build time). */
  stargazersCount: number | null
  /** Extra classes for the link (colour on a red header, for example). */
  className?: string
  /**
   * Optional locales for number formatting.
   * See [MDN - Intl - locales argument](https://developer.mozilla.org/docs/Web/JavaScript/Reference/Global_Objects/Intl#locales_argument).
   * @defaultValue "en-US"
   */
  locales?: Intl.LocalesArgument
}

/**
 * Based on @ncdai/github-stars (https://chanhdai.com/components/github-stars). Two changes for this site: it is a real link (the original gave a link the
 * role "button"), and the tooltip is the browser's own `title`, because Base UI's tooltip added about 45 KB of JavaScript to every page for one sentence.
 */
export function GitHubStars({ repo, stargazersCount, className, locales = "en-US" }: GitHubStarsProps) {
  const full = stargazersCount === null ? "Star kittymux on GitHub" : `${new Intl.NumberFormat(locales).format(stargazersCount)} stars on GitHub`
  return (
    <a
      href={`https://github.com/${repo}`}
      target="_blank"
      rel="noopener"
      title={full}
      aria-label={stargazersCount === null ? "Star kittymux on GitHub" : `Star kittymux on GitHub, ${stargazersCount} stars`}
      className={cn(buttonVariants({ variant: "ghost" }), "min-h-11 gap-1.5 px-2.5 sm:min-h-8", className)}
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-[1.25cap] w-auto shrink-0">
        <path
          d="M12 0C5.37 0 0 5.372 0 11.997 0 17.3 3.438 21.795 8.205 23.38c.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.725-4.042-1.609-4.042-1.609C4.422 17.77 3.633 17.4 3.633 17.4c-1.087-.744.084-.73.084-.73 1.205.085 1.838 1.237 1.838 1.237 1.07 1.834 2.809 1.304 3.495.997.108-.775.417-1.304.76-1.604-2.665-.3-5.466-1.332-5.466-5.929 0-1.31.465-2.38 1.235-3.219-.135-.303-.54-1.523.105-3.175 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.4 3-.405 1.02.006 2.04.138 3 .404 2.28-1.551 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.608-2.805 5.623-5.475 5.918.42.36.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.284 0 .315.21.69.825.57C20.565 21.79 24 17.291 24 11.997 24 5.372 18.627 0 12 0"
          fill="currentColor"
        />
      </svg>
      <span className="text-[0.8125rem]/none tabular-nums" style={{ textBox: "trim-end cap alphabetic" }}>
        {stargazersCount === null ? "Star" : new Intl.NumberFormat(locales, { notation: "compact", compactDisplay: "short" }).format(stargazersCount).toLowerCase()}
      </span>
    </a>
  )
}

import { cn } from "@/lib/utils"

export type GitHubStarsProps = {
  /** GitHub repository in `owner/repo` format. */
  repo: string
  /** Stars to show next to the label; null leaves the number out (GitHub could not be reached when the site was built). */
  stargazersCount: number | null
  /** `brand` sits on the blue field, `page` on paper. */
  tone?: "brand" | "page"
  className?: string
  /** See https://developer.mozilla.org/docs/Web/JavaScript/Reference/Global_Objects/Intl#locales_argument */
  locales?: Intl.LocalesArgument
}

const TONES = {
  brand: "border-onbrand/55 text-onbrand hover:bg-onbrand/12",
  page: "border-line bg-card text-ink hover:bg-card-hi",
} as const

/**
 * A split button like GitHub's own: the label (with the mark) and, divided from it, the count. Based on @ncdai/github-stars
 * (https://chanhdai.com/components/github-stars); changed for this site: a real link (the original gave a link the role "button"), the tooltip is the browser's
 * own `title` (Base UI's tooltip cost about 45 KB of JavaScript on every page), and a count of 0 is left out (a zero beside the button is not a reason to click it; the tooltip still says "be the first").
 */
export function GitHubStars({ repo, stargazersCount, tone = "page", className, locales = "en-US" }: GitHubStarsProps) {
  const known = stargazersCount !== null
  const full = known ? `${new Intl.NumberFormat(locales).format(stargazersCount)} ${stargazersCount === 1 ? "star" : "stars"} on GitHub${stargazersCount === 0 ? ": be the first" : ""}` : "Star kittymux on GitHub"
  return (
    <a
      href={`https://github.com/${repo}`}
      target="_blank"
      rel="noopener"
      title={full}
      aria-label={known ? `Star kittymux on GitHub (${stargazersCount} ${stargazersCount === 1 ? "star" : "stars"})` : "Star kittymux on GitHub"}
      data-press=""
      className={cn("inline-flex min-h-11 items-stretch overflow-clip rounded-full border text-sm font-semibold sm:min-h-10", TONES[tone], className)}
    >
      <span className="inline-flex items-center gap-2 px-3.5">
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-[1.3cap] w-auto shrink-0">
          <path
            d="M12 0C5.37 0 0 5.372 0 11.997 0 17.3 3.438 21.795 8.205 23.38c.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.725-4.042-1.609-4.042-1.609C4.422 17.77 3.633 17.4 3.633 17.4c-1.087-.744.084-.73.084-.73 1.205.085 1.838 1.237 1.838 1.237 1.07 1.834 2.809 1.304 3.495.997.108-.775.417-1.304.76-1.604-2.665-.3-5.466-1.332-5.466-5.929 0-1.31.465-2.38 1.235-3.219-.135-.303-.54-1.523.105-3.175 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.4 3-.405 1.02.006 2.04.138 3 .404 2.28-1.551 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.608-2.805 5.623-5.475 5.918.42.36.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.284 0 .315.21.69.825.57C20.565 21.79 24 17.291 24 11.997 24 5.372 18.627 0 12 0"
            fill="currentColor"
          />
        </svg>
        Star
      </span>
      {known && stargazersCount > 0 && (
        <span className="inline-flex items-center border-s border-current/30 px-3 tabular-nums">
          {new Intl.NumberFormat(locales, { notation: "compact", compactDisplay: "short" }).format(stargazersCount)}
        </span>
      )}
    </a>
  )
}

import { useRouter, useRouterState, type ErrorComponentProps } from '@tanstack/react-router';
import { Logo } from '@/components/logo';
import { RetryButton, StatusPage } from '@/components/status-page';

/** Any page that throws. Its own small top bar and no Fumadocs: the error may have come from there. */
export function RouteError({ error, reset }: ErrorComponentProps) {
  const router = useRouter();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const text = error instanceof Error ? error.message : String(error);
  return (
    <>
      <header className="border-b border-line">
        <div className="mx-auto flex h-14 w-full max-w-[1100px] items-center px-5 md:px-8">
          <a href="/" aria-label="kittymux, front page" className="inline-flex min-h-11 items-center">
            <Logo size={32} />
          </a>
        </div>
      </header>
      <StatusPage
        kind="error"
        path={path}
        detail={text.slice(0, 600)}
        primary={<RetryButton onClick={() => { reset(); void router.invalidate(); }} />}
      />
    </>
  );
}

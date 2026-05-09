import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRight, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { CreateSessionDialog } from "@/components/LensSessions/CreateSessionDialog"
import { useLensSessions } from "@/hooks/useLensSessions"

export const Route = createFileRoute("/_layout/lens-sessions")({
  component: LensSessionsIndex,
  head: () => ({
    meta: [{ title: "LENS · Sessions" }],
  }),
})

function LensSessionsIndex() {
  const { sessions, loading, error, create, remove } = useLensSessions()

  return (
    <div className="space-y-4">
      <header className="flex items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sessions</h1>
          <p className="text-sm text-muted-foreground">
            Each session is a series of operator-triggered runs. Ideas evolve
            with every run; click into any candidate to see what changed.
          </p>
        </div>
        <CreateSessionDialog onCreate={create} loading={loading} />
      </header>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
          {error}
        </div>
      )}

      {loading && sessions.length === 0 && (
        <div className="space-y-2">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      )}

      {!loading && sessions.length === 0 && !error && (
        <div className="rounded-xl border border-dashed bg-muted/20 p-12 text-center">
          <p className="font-medium text-foreground/80">No sessions yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Create one to begin investigating an opportunity area.
          </p>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {sessions.map((s) => (
          <article
            key={s.id}
            className="rounded-xl border bg-card/60 p-4 shadow-sm transition-colors hover:border-primary/40"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <h2 className="truncate text-base font-semibold">{s.title}</h2>
                {s.goal_query && (
                  <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                    goal: {s.goal_query}
                  </p>
                )}
                {s.description && (
                  <p className="mt-1 line-clamp-2 text-sm text-muted-foreground/80">
                    {s.description}
                  </p>
                )}
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground hover:text-destructive"
                onClick={() => {
                  if (confirm(`Delete session "${s.title}"? This removes all candidates and runs.`)) {
                    void remove(s.id)
                  }
                }}
                title="Delete session"
              >
                <Trash2 className="size-3.5" />
              </Button>
            </div>
            <div className="mt-3 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
              <span className="font-mono">
                {new Date(s.updated_at).toLocaleString()}
              </span>
              <Button asChild size="sm" variant="outline" className="h-7 gap-1">
                <Link
                  to="/lens-sessions/$sessionId"
                  params={{ sessionId: s.id }}
                >
                  Open
                  <ArrowRight className="size-3" />
                </Link>
              </Button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

export default LensSessionsIndex

import { createFileRoute, Link, useRouter } from "@tanstack/react-router"
import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, History, Wifi, WifiOff } from "lucide-react"

import { Button } from "@/components/ui/button"
import { PredictionCard } from "@/components/Board/PredictionCard"
import type { Candidate } from "@/components/Board/types"
import { CandidateHistoryDrawer } from "@/components/LensSessions/CandidateHistoryDrawer"
import { RunTimeline } from "@/components/LensSessions/RunTimeline"
import { RunTriggerPanel } from "@/components/LensSessions/RunTriggerPanel"
import { getLensSession } from "@/components/LensSessions/api"
import type { LensSessionRow } from "@/components/LensSessions/types"
import { useSessionRuns } from "@/hooks/useSessionRuns"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/_layout/lens-sessions/$sessionId")({
  component: LensSessionDetail,
  head: () => ({
    meta: [{ title: "LENS · Session" }],
  }),
})

function LensSessionDetail() {
  const { sessionId } = Route.useParams()
  const router = useRouter()
  const [meta, setMeta] = useState<LensSessionRow | null>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [historyId, setHistoryId] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  const {
    runs,
    candidates,
    running,
    error,
    connected,
    trigger,
  } = useSessionRuns(sessionId)

  useEffect(() => {
    let cancelled = false
    getLensSession(sessionId)
      .then((s) => {
        if (!cancelled) setMeta(s)
      })
      .catch((e) => {
        if (!cancelled) setMetaError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [sessionId])

  const sortedCandidates = useMemo(
    () =>
      [...candidates]
        .filter((c) => c.status !== "merged_into")
        .sort((a, b) => {
          const aDead = a.status === "killed" ? 1 : 0
          const bDead = b.status === "killed" ? 1 : 0
          if (aDead !== bDead) return aDead - bDead
          return b.v_hat * b.c_hat - a.v_hat * a.c_hat
        }),
    [candidates],
  )

  const onShowHistory = (cand: Candidate) => {
    setHistoryId(cand.id)
    setHistoryOpen(true)
  }

  const drawerCandidate =
    historyId !== null
      ? candidates.find((c) => c.id === historyId) ?? null
      : null

  if (metaError) {
    return (
      <div className="space-y-3">
        <Button variant="ghost" size="sm" onClick={() => router.history.back()}>
          <ArrowLeft className="size-3.5" /> Back
        </Button>
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          Could not load session: {metaError}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <Button variant="ghost" size="sm" asChild className="-ml-2 h-7 gap-1">
          <Link to="/lens-sessions">
            <ArrowLeft className="size-3.5" /> All sessions
          </Link>
        </Button>
        <div className="flex items-baseline justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight">
              {meta?.title ?? "…"}
            </h1>
            {meta?.goal_query && (
              <p className="mt-0.5 text-sm text-muted-foreground">
                goal: <span className="font-mono">{meta.goal_query}</span>
              </p>
            )}
          </div>
          <ConnectedBadge connected={connected} />
        </div>
      </header>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
          {error}
        </div>
      )}

      <RunTriggerPanel
        onTrigger={trigger}
        running={running}
        hasCandidates={candidates.length > 0}
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-3">
          {sortedCandidates.length === 0 ? (
            <div className="rounded-xl border border-dashed bg-muted/30 p-12 text-center text-sm text-muted-foreground">
              <p className="mb-2 font-medium text-foreground/80">No candidates yet</p>
              <p>
                Trigger a <span className="font-mono">Seed ideas</span> run above
                to populate this session.
              </p>
            </div>
          ) : (
            sortedCandidates.map((c, i) => (
              <div
                key={c.id}
                className={cn(
                  "group relative cursor-pointer rounded-xl transition-shadow hover:shadow-md",
                )}
                onClick={() => onShowHistory(c)}
              >
                <PredictionCard candidate={c} rank={i + 1} />
                <div className="pointer-events-none absolute right-2 top-2 flex items-center gap-1 rounded-md border bg-card/80 px-2 py-1 text-[10px] text-muted-foreground opacity-0 shadow-sm transition-opacity group-hover:opacity-100">
                  <History className="size-3" />
                  history
                </div>
              </div>
            ))
          )}
        </div>

        <aside className="space-y-3">
          <RunTimeline runs={runs} />
        </aside>
      </div>

      <CandidateHistoryDrawer
        sessionId={sessionId}
        candidate={drawerCandidate}
        open={historyOpen}
        onOpenChange={setHistoryOpen}
      />
    </div>
  )
}

function ConnectedBadge({ connected }: { connected: boolean }) {
  return (
    <div className="flex items-center gap-1.5 rounded-md border bg-card/60 px-2.5 py-1 text-[11px] font-mono">
      {connected ? (
        <>
          <Wifi className="size-3 text-emerald-400" />
          <span className="text-emerald-400">live</span>
        </>
      ) : (
        <>
          <WifiOff className="size-3 text-destructive" />
          <span className="text-destructive">offline</span>
        </>
      )}
    </div>
  )
}

export default LensSessionDetail

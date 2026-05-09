import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useMemo, useRef, useState } from "react"
import { Activity, Wifi, WifiOff } from "lucide-react"
import { cn } from "@/lib/utils"

import { BenchmarkWidget } from "@/components/Board/BenchmarkWidget"
import { CarSidePanel } from "@/components/Board/CarSidePanel"
import { DemoController } from "@/components/Board/DemoController"
import { DiffFeed } from "@/components/Board/DiffFeed"
import { OpportunityBriefDialog } from "@/components/Board/OpportunityBriefDialog"
import { PredictionCard } from "@/components/Board/PredictionCard"
import { RankingHeader } from "@/components/Board/RankingHeader"
import type { Candidate } from "@/components/Board/types"
import { useBoardSimulation } from "@/hooks/useBoardSimulation"
import { useLiveBoard } from "@/hooks/useLiveBoard"

export const Route = createFileRoute("/_layout/board/$sessionId")({
  component: PredictionBoard,
  head: () => ({
    meta: [{ title: "LENS · Prediction Board" }],
  }),
})

type Mode = "mock" | "live"

function PredictionBoard() {
  const { sessionId } = Route.useParams()
  const [mode, setMode] = useState<Mode>("mock")

  const sim = useBoardSimulation()
  const live = useLiveBoard(sessionId)

  const isLive = mode === "live"
  const state = isLive ? live.state : sim.state
  const stageIndex = isLive ? live.stageIndex : sim.stageIndex
  const totalStages = isLive ? live.totalStages : sim.stages.length
  const currentStage = isLive
    ? live.currentStage
    : sim.currentStage
      ? {
          key: sim.currentStage.key,
          label: sim.currentStage.label,
          narration: sim.currentStage.narration,
        }
      : null

  const onNext = isLive ? live.next : sim.next
  const onPrev = isLive ? live.prev : sim.prev
  const onReset = isLive ? live.reset : sim.reset
  const onJumpTo = isLive ? live.jumpTo : sim.jumpTo
  const setBriefCandidate = isLive ? live.setBriefCandidate : sim.setBriefCandidate
  const setFullReeval = isLive ? live.setFullReeval : sim.setFullReeval

  const [briefOpen, setBriefOpen] = useState(false)
  const [briefCandidateId, setBriefCandidateIdLocal] = useState<string | null>(
    null,
  )
  const lastStageKey = useRef<string | null>(null)

  // Auto-open brief when the demo stage flips it on
  useEffect(() => {
    if (state.briefCandidateId && state.briefCandidateId !== briefCandidateId) {
      setBriefCandidateIdLocal(state.briefCandidateId)
      setBriefOpen(true)
    }
  }, [state.briefCandidateId, briefCandidateId])

  // In live mode, auto-open brief when a ready_to_validate candidate has the enriched fields
  useEffect(() => {
    if (!isLive || briefOpen) return
    const target = state.candidates.find(
      (c) =>
        c.status === "ready_to_validate" &&
        c.dossier_grounded &&
        (c.pain_owner || c.why_now),
    )
    if (target && !briefCandidateId) {
      setBriefCandidateIdLocal(target.id)
      setBriefOpen(true)
    }
  }, [isLive, state.candidates, briefOpen, briefCandidateId])

  const justAddedIds = useMemo(() => {
    const stage = currentStage?.key ?? null
    if (stage === lastStageKey.current) return new Set<string>()
    lastStageKey.current = stage
    return new Set(
      state.events
        .filter(
          (e) =>
            e.kind === "candidate_added" ||
            e.kind === "candidate_v_hat_updated" ||
            e.kind === "dossier_complete",
        )
        .slice(0, 6)
        .map((e) => e.candidate_id)
        .filter((x): x is string => Boolean(x)),
    )
  }, [currentStage?.key, state.events])

  const liveCandidates = useMemo(() => {
    return [...state.candidates]
      .filter((c) => c.status !== "merged_into")
      .sort((a, b) => {
        const aDead = a.status === "killed" ? 1 : 0
        const bDead = b.status === "killed" ? 1 : 0
        if (aDead !== bDead) return aDead - bDead
        return b.v_hat * b.c_hat - a.v_hat * a.c_hat
      })
  }, [state.candidates])

  const briefCandidate: Candidate | null = useMemo(
    () => state.candidates.find((c) => c.id === briefCandidateId) ?? null,
    [briefCandidateId, state.candidates],
  )

  const ycMatch = (id: string) =>
    state.ycScore.matches.find((m) => m.prediction_id === id)

  const handleReveal = async () => {
    if (state.ycRevealed) return
    if (isLive) {
      await live.jumpTo(Math.max(stageIndex, 9))
    } else {
      sim.jumpTo(Math.max(stageIndex, 9))
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Prediction board</h1>
          <p className="text-sm text-muted-foreground">
            session{" "}
            <span className="font-mono text-foreground/80">
              {sessionId.slice(0, 8)}…
            </span>{" "}
            · watch it get smarter
          </p>
        </div>
        <ModeToggle
          mode={mode}
          onModeChange={setMode}
          connected={live.connected}
          loading={live.loading}
        />
      </header>

      <DemoController
        stages={
          isLive
            ? Array.from({ length: live.totalStages }, (_, i) => ({
                key: `live-${i}`,
                label: live.currentStage?.label ?? `Stage ${i + 1}`,
                narration: live.currentStage?.narration ?? "",
                apply: () => ({} as never),
              }))
            : sim.stages
        }
        stageIndex={stageIndex}
        currentStage={currentStage as any}
        onNext={onNext}
        onPrev={onPrev}
        onReset={onReset}
        onJumpTo={onJumpTo}
      />

      <RankingHeader
        candidates={state.candidates}
        ycScore={state.ycScore}
        fullReeval={state.fullReeval}
        onToggleFullReeval={setFullReeval}
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-3">
          {liveCandidates.map((c, i) => {
            const m = ycMatch(c.id)
            return (
              <div key={c.id} className={cn("board-card-enter")}>
                <PredictionCard
                  candidate={c}
                  rank={i + 1}
                  pulseLens={justAddedIds.has(c.id)}
                  matchKind={m?.match_kind}
                  ycMatchTitle={m?.rationale}
                  onOpenBrief={(id) => {
                    setBriefCandidateIdLocal(id)
                    setBriefOpen(true)
                  }}
                />
              </div>
            )
          })}
          {liveCandidates.length === 0 && (
            <div className="rounded-xl border border-dashed bg-muted/30 p-12 text-center text-sm text-muted-foreground">
              <p className="mb-2 font-medium text-foreground/80">Cold start</p>
              <p>
                Drop a corpus to begin. Press <span className="font-mono">Next</span> to
                advance the demo arc stage by stage.
              </p>
              {isLive && live.error && (
                <p className="mt-3 text-destructive">{live.error}</p>
              )}
            </div>
          )}
        </div>

        <aside className="space-y-3">
          <BenchmarkWidget
            candidates={state.candidates}
            ycScore={state.ycScore}
            revealed={state.ycRevealed}
            onReveal={handleReveal}
          />
          <CarSidePanel tickets={state.dossierTickets} />
          <div className="rounded-xl border bg-card/60 p-3 shadow-sm">
            <h3 className="mb-2 text-sm font-semibold">Diff feed</h3>
            <DiffFeed events={state.events.slice(0, 14)} />
          </div>
        </aside>
      </div>

      <OpportunityBriefDialog
        candidate={briefCandidate}
        open={briefOpen}
        onOpenChange={(open) => {
          setBriefOpen(open)
          if (!open) {
            setBriefCandidate(null)
            setBriefCandidateIdLocal(null)
          }
        }}
        onVerdict={async (verdict) => {
          if (isLive && briefCandidate) {
            try {
              await fetch(
                `${(import.meta.env.VITE_API_URL as string | undefined) ?? ""}/api/v1/sessions/${sessionId}/candidates/${briefCandidate.id}/verdict`,
                {
                  method: "PATCH",
                  headers: {
                    Authorization: `Bearer ${localStorage.getItem("access_token") ?? ""}`,
                    "Content-Type": "application/json",
                  },
                  body: JSON.stringify({ verdict }),
                },
              )
            } catch {
              // ignore — demo path
            }
          }
          setBriefOpen(false)
        }}
      />
    </div>
  )
}

function ModeToggle({
  mode,
  onModeChange,
  connected,
  loading,
}: {
  mode: Mode
  onModeChange: (m: Mode) => void
  connected: boolean
  loading: boolean
}) {
  return (
    <div className="flex items-center gap-2 rounded-md border bg-card/60 p-1 text-xs">
      <button
        type="button"
        onClick={() => onModeChange("mock")}
        className={cn(
          "rounded px-2.5 py-1 transition-colors",
          mode === "mock"
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        Mock
      </button>
      <button
        type="button"
        onClick={() => onModeChange("live")}
        className={cn(
          "flex items-center gap-1.5 rounded px-2.5 py-1 transition-colors",
          mode === "live"
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        <Activity className="size-3" />
        Live
        {mode === "live" &&
          (connected ? (
            <Wifi className="size-3 text-emerald-400" />
          ) : (
            <WifiOff className="size-3 text-destructive" />
          ))}
        {loading && (
          <span className="ml-1 size-1.5 animate-pulse rounded-full bg-amber-400" />
        )}
      </button>
    </div>
  )
}

export default PredictionBoard

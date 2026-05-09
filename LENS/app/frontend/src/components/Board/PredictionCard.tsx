import { ArrowUpRight, Skull } from "lucide-react"
import { cn } from "@/lib/utils"

import { Button } from "@/components/ui/button"
import { CandidateBadges } from "./CandidateBadges"
import { ConfidenceBar } from "./ConfidenceBar"
import { LensChip } from "./LensChip"
import type { Candidate } from "./types"

interface PredictionCardProps {
  candidate: Candidate
  rank: number
  pulseLens?: boolean
  onOpenBrief?: (id: string) => void
  matchKind?: "direct" | "adjacent" | "none"
  ycMatchTitle?: string
}

export function PredictionCard({
  candidate,
  rank,
  pulseLens,
  onOpenBrief,
  matchKind,
  ycMatchTitle,
}: PredictionCardProps) {
  const killed = candidate.status === "killed"
  const merged = candidate.status === "merged_into"
  const ready = candidate.status === "ready_to_validate"
  const composite = candidate.v_hat * candidate.c_hat

  return (
    <div
      className={cn(
        "group relative rounded-xl border bg-card text-card-foreground p-4 shadow-sm transition-all duration-500 ease-out",
        ready && "border-emerald-500/40 ring-1 ring-emerald-500/10",
        killed &&
          "opacity-50 border-destructive/40 ring-1 ring-destructive/20",
        merged && "opacity-30 scale-[0.98]",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border bg-muted text-xs font-mono text-muted-foreground">
          {rank}
        </div>
        <div className="flex-1 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1.5">
              <p
                className={cn(
                  "text-sm font-medium leading-snug",
                  killed && "line-through decoration-destructive/70",
                )}
              >
                {candidate.statement}
              </p>
              <div className="flex flex-wrap items-center gap-1.5">
                <LensChip lens={candidate.lens} pulse={pulseLens} />
                {matchKind === "direct" && (
                  <span className="inline-flex items-center rounded-md border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300" title={ycMatchTitle}>
                    ▣ YC direct
                  </span>
                )}
                {matchKind === "adjacent" && (
                  <span className="inline-flex items-center rounded-md border border-sky-500/40 bg-sky-500/10 px-1.5 py-0.5 text-[10px] font-medium text-sky-300" title={ycMatchTitle}>
                    ◆ YC adjacent
                  </span>
                )}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {killed && (
                <span className="inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-destructive">
                  <Skull className="size-3" /> killed
                </span>
              )}
              {ready && onOpenBrief && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10 hover:text-emerald-200"
                  onClick={() => onOpenBrief(candidate.id)}
                >
                  Open brief
                  <ArrowUpRight className="size-3.5" />
                </Button>
              )}
            </div>
          </div>

          <CandidateBadges candidate={candidate} />

          <div className="space-y-1">
            <ConfidenceBar label="V̂" value={candidate.v_hat} tone="primary" />
            <ConfidenceBar label="Ĉ" value={candidate.c_hat} tone="warm" />
          </div>

          <div className="flex items-center justify-between text-[10px] text-muted-foreground">
            <span className="font-mono">composite {composite.toFixed(2)}</span>
            <span className="truncate">
              {candidate.evidence_chunk_ids.length} chunks ·{" "}
              {candidate.source_count} sources
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

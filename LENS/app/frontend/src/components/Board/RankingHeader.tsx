import { Activity, FlaskConical, Skull, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"

import type { Candidate, YcScore } from "./types"

interface RankingHeaderProps {
  candidates: Candidate[]
  ycScore: YcScore
  fullReeval: boolean
  onToggleFullReeval: (v: boolean) => void
  className?: string
}

export function RankingHeader({
  candidates,
  ycScore,
  fullReeval,
  onToggleFullReeval,
  className,
}: RankingHeaderProps) {
  const live = candidates.filter(
    (c) => c.status !== "killed" && c.status !== "merged_into",
  )
  const killed = candidates.filter((c) => c.status === "killed").length
  const dossiered = live.filter((c) => c.dossier_grounded).length
  const ready = live.filter((c) => c.status === "ready_to_validate").length

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-xl border bg-card/60 p-3",
        className,
      )}
    >
      <Stat icon={<Activity className="size-3.5" />} label="live" value={live.length} />
      <Stat
        icon={<FlaskConical className="size-3.5" />}
        label="dossiered"
        value={dossiered}
        tone="amber"
      />
      <Stat
        icon={<Sparkles className="size-3.5" />}
        label="ready"
        value={ready}
        tone="emerald"
      />
      <Stat
        icon={<Skull className="size-3.5" />}
        label="killed"
        value={killed}
        tone="destructive"
      />
      <span className="mx-1 h-6 w-px bg-border" />
      <Stat
        label="precision"
        value={ycScore.revealed ? `${(ycScore.precision * 100).toFixed(0)}%` : "–"}
        tone="rose"
      />
      <Stat
        label="recall"
        value={ycScore.revealed ? `${(ycScore.recall * 100).toFixed(0)}%` : "–"}
        tone="rose"
      />
      <div className="ml-auto flex items-center gap-2 text-[11px]">
        <button
          type="button"
          onClick={() => onToggleFullReeval(!fullReeval)}
          className={cn(
            "rounded-md border px-2 py-1 font-mono transition-colors",
            fullReeval
              ? "border-amber-500/60 bg-amber-500/10 text-amber-200"
              : "border-border bg-muted/30 text-muted-foreground hover:bg-muted/60",
          )}
          title="Toggle full pipeline re-eval (fallback for dirty-set bugs)"
        >
          full re-eval: {fullReeval ? "ON" : "off"}
        </button>
      </div>
    </div>
  )
}

interface StatProps {
  icon?: React.ReactNode
  label: string
  value: number | string
  tone?: "amber" | "emerald" | "destructive" | "rose"
}

function Stat({ icon, label, value, tone }: StatProps) {
  return (
    <div className="flex items-center gap-1.5 rounded-md border bg-muted/30 px-2 py-1 text-xs">
      {icon}
      <span className="text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-mono font-medium tabular-nums",
          tone === "amber" && "text-amber-300",
          tone === "emerald" && "text-emerald-300",
          tone === "destructive" && "text-destructive",
          tone === "rose" && "text-rose-300",
        )}
      >
        {value}
      </span>
    </div>
  )
}

import { cn } from "@/lib/utils"
import type { DiffEvent } from "./types"

interface DiffFeedProps {
  events: DiffEvent[]
  className?: string
}

const KIND_TONE: Record<DiffEvent["kind"], string> = {
  candidate_added: "border-l-primary/60 text-primary",
  candidate_v_hat_updated: "border-l-amber-500/70 text-amber-300",
  candidate_killed: "border-l-destructive/70 text-destructive",
  candidate_merged: "border-l-sky-500/70 text-sky-300",
  dossier_queued: "border-l-violet-500/70 text-violet-300",
  dossier_running: "border-l-violet-500/70 text-violet-300",
  dossier_complete: "border-l-emerald-500/70 text-emerald-300",
  candidate_challenged_held: "border-l-emerald-500/70 text-emerald-300",
  candidate_red_struck: "border-l-destructive/70 text-destructive",
  yc_revealed: "border-l-rose-500/70 text-rose-300",
  ahead_of_yc: "border-l-rose-500/70 text-rose-300",
}

const fmtTime = (ts: number) =>
  new Date(ts).toLocaleTimeString(undefined, {
    hour12: false,
    minute: "2-digit",
    second: "2-digit",
  })

export function DiffFeed({ events, className }: DiffFeedProps) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {events.length === 0 && (
        <div className="rounded-lg border border-dashed bg-muted/30 p-3 text-xs text-muted-foreground">
          Waiting for events… Drop a corpus to begin.
        </div>
      )}
      {events.map((event) => (
        <div
          key={event.id}
          className={cn(
            "animate-in slide-in-from-right-2 fade-in-50 rounded-md border-l-2 bg-card/60 px-3 py-1.5 text-xs",
            KIND_TONE[event.kind],
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-mono text-foreground/90">
              {event.message}
            </span>
            <span className="shrink-0 text-[10px] text-muted-foreground/80">
              {fmtTime(event.ts)}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

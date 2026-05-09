import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react"
import { cn } from "@/lib/utils"

import { RUN_KIND_META, type RunRow } from "./types"

interface RunTimelineProps {
  runs: RunRow[]
  className?: string
}

const STATUS_ICON = {
  pending: <Circle className="size-3.5 text-muted-foreground" />,
  running: <Loader2 className="size-3.5 animate-spin text-amber-400" />,
  complete: <CheckCircle2 className="size-3.5 text-emerald-400" />,
  failed: <XCircle className="size-3.5 text-destructive" />,
}

export function RunTimeline({ runs, className }: RunTimelineProps) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-card/60 p-3 shadow-sm",
        className,
      )}
    >
      <h3 className="mb-2 text-sm font-semibold">Run history</h3>
      {runs.length === 0 ? (
        <p className="rounded-md border border-dashed bg-muted/30 p-4 text-center text-xs text-muted-foreground">
          No runs yet. Start with{" "}
          <span className="font-mono text-foreground/80">Seed ideas</span>.
        </p>
      ) : (
        <ol className="relative space-y-2 border-l border-muted pl-4">
          {runs.map((r) => {
            const meta = RUN_KIND_META[r.kind]
            const elapsed = r.finished_at
              ? formatElapsed(r.started_at, r.finished_at)
              : null
            const sum = r.summary
            const stats: string[] = []
            if (sum.candidates_added) stats.push(`+${sum.candidates_added}`)
            if (sum.candidates_updated) stats.push(`~${sum.candidates_updated}`)
            if (sum.candidates_killed) stats.push(`✗${sum.candidates_killed}`)
            if (sum.candidates_merged) stats.push(`⤲${sum.candidates_merged}`)
            return (
              <li key={r.id} className="relative">
                <span className="absolute -left-[1.30rem] top-1 flex h-4 w-4 items-center justify-center rounded-full border bg-background">
                  {STATUS_ICON[r.status]}
                </span>
                <div className="rounded-md border bg-muted/30 px-3 py-2">
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-1.5 font-medium text-foreground/90">
                      <span>{meta?.icon}</span>
                      <span>{meta?.label ?? r.kind}</span>
                      <span
                        className={cn(
                          "ml-1 rounded px-1.5 py-px text-[10px] font-mono",
                          r.mode === "real"
                            ? "bg-emerald-400/10 text-emerald-300"
                            : "bg-muted text-muted-foreground",
                        )}
                      >
                        {r.mode}
                      </span>
                    </div>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {new Date(r.started_at).toLocaleTimeString()}
                      {elapsed && ` · ${elapsed}`}
                    </span>
                  </div>
                  {stats.length > 0 && (
                    <div className="mt-1 font-mono text-[11px] text-muted-foreground">
                      {stats.join("  ")}
                    </div>
                  )}
                  {r.summary?.notes && r.summary.notes.length > 0 && (
                    <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                      {r.summary.notes.join(" · ")}
                    </p>
                  )}
                  {r.error && (
                    <p className="mt-1 text-[11px] leading-relaxed text-destructive">
                      {r.error}
                    </p>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

function formatElapsed(started: string, finished: string): string {
  const ms = new Date(finished).getTime() - new Date(started).getTime()
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms / 1000)}s`
}

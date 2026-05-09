import { useEffect, useState } from "react"
import { CheckCircle2, FileSearch, Loader2, Timer } from "lucide-react"
import { cn } from "@/lib/utils"

import type { DossierTicket } from "./types"

interface CarSidePanelProps {
  tickets: DossierTicket[]
  className?: string
}

export function CarSidePanel({ tickets, className }: CarSidePanelProps) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-card/60 p-3 shadow-sm",
        className,
      )}
    >
      <div className="mb-3 flex items-center gap-2">
        <FileSearch className="size-4 text-violet-300" />
        <h3 className="text-sm font-semibold">CAR · Evidence dossiers</h3>
        <span className="ml-auto text-[10px] text-muted-foreground">
          .codex-autorunner/tickets/
        </span>
      </div>

      <div className="space-y-2">
        {tickets.length === 0 && (
          <div className="rounded-lg border border-dashed bg-muted/30 p-3 text-xs text-muted-foreground">
            No dossiers queued yet.
          </div>
        )}
        {tickets.map((t) => (
          <TicketRow key={t.ticket_id} ticket={t} />
        ))}
      </div>
    </div>
  )
}

function TicketRow({ ticket }: { ticket: DossierTicket }) {
  const elapsed = useTickingElapsed(ticket)
  const tone =
    ticket.status === "complete"
      ? "border-emerald-500/40 bg-emerald-500/5"
      : ticket.status === "running"
        ? "border-violet-500/40 bg-violet-500/10"
        : ticket.status === "failed"
          ? "border-destructive/50 bg-destructive/10"
          : "border-border/60 bg-muted/30"

  return (
    <div
      className={cn(
        "rounded-lg border p-2 text-xs transition-colors",
        tone,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] text-muted-foreground">
            {ticket.ticket_number}
          </span>
          <StatusPill status={ticket.status} />
        </div>
        <span className="flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
          <Timer className="size-3" />
          {elapsed}
        </span>
      </div>
      <p className="mt-1 line-clamp-2 text-foreground/90">
        {ticket.claim_summary}
      </p>
    </div>
  )
}

function StatusPill({ status }: { status: DossierTicket["status"] }) {
  if (status === "running") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-violet-500/40 bg-violet-500/15 px-1.5 py-0.5 text-[10px] font-medium text-violet-300">
        <Loader2 className="size-3 animate-spin" />
        running
      </span>
    )
  }
  if (status === "complete") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300">
        <CheckCircle2 className="size-3" />
        complete
      </span>
    )
  }
  if (status === "failed") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-destructive/50 bg-destructive/20 px-1.5 py-0.5 text-[10px] font-medium text-destructive">
        ✗ failed
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/40 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
      <span className="size-1.5 rounded-full bg-muted-foreground/70" />
      queued
    </span>
  )
}

function useTickingElapsed(ticket: DossierTicket): string {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (ticket.status !== "running") return
    const id = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(id)
  }, [ticket.status])

  const start = ticket.started_at ?? ticket.queued_at
  const end = ticket.completed_at ?? now
  const ms = Math.max(0, end - start)
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  return `${m}m ${s.toString().padStart(2, "0")}s`
}

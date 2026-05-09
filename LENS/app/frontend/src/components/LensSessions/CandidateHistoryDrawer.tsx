import { Skeleton } from "@/components/ui/skeleton"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { cn } from "@/lib/utils"

import { useCandidateHistory } from "@/hooks/useCandidateHistory"
import type { Candidate } from "@/components/Board/types"

import {
  RUN_KIND_META,
  type CandidateChangeRow,
  type FieldDiff,
  type RunRow,
} from "./types"

interface CandidateHistoryDrawerProps {
  sessionId: string
  candidate: Candidate | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CandidateHistoryDrawer({
  sessionId,
  candidate,
  open,
  onOpenChange,
}: CandidateHistoryDrawerProps) {
  const { history, loading, error } = useCandidateHistory(
    sessionId,
    open && candidate ? candidate.id : null,
  )

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="text-sm font-semibold">
            Idea history
          </SheetTitle>
          <SheetDescription className="text-xs">
            Every run that touched this candidate, with field-level diffs.
          </SheetDescription>
        </SheetHeader>

        {candidate && (
          <div className="mt-3 space-y-3 px-4 pb-6">
            <div className="rounded-lg border bg-muted/30 p-3">
              <div className="text-[11px] font-mono text-muted-foreground">
                {candidate.lens} · {candidate.status}
              </div>
              <p className="mt-1 text-sm font-medium leading-snug">
                {candidate.statement}
              </p>
              <div className="mt-2 flex items-center gap-3 text-[11px] font-mono text-muted-foreground">
                <span>V̂ {candidate.v_hat.toFixed(2)}</span>
                <span>Ĉ {candidate.c_hat.toFixed(2)}</span>
                <span>{candidate.source_count} sources</span>
              </div>
            </div>

            {loading && (
              <div className="space-y-2">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            )}
            {error && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
                {error}
              </div>
            )}

            {history && history.changes.length === 0 && !loading && (
              <p className="rounded-md border border-dashed bg-muted/30 p-4 text-center text-xs text-muted-foreground">
                No recorded changes for this candidate.
              </p>
            )}

            {history && history.changes.length > 0 && (
              <ol className="relative space-y-2 border-l border-muted pl-4">
                {history.changes.map((change) => (
                  <ChangeEntry
                    key={change.id}
                    change={change}
                    run={history.runs[change.run_id]}
                  />
                ))}
              </ol>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

function ChangeEntry({
  change,
  run,
}: {
  change: CandidateChangeRow
  run?: RunRow
}) {
  const meta = run ? RUN_KIND_META[run.kind] : null
  const dotColor = changeDotColor(change.change_kind)
  const interestingDiffs = filterInterestingDiffs(change.field_diffs)

  return (
    <li className="relative">
      <span
        className={cn(
          "absolute -left-[1.30rem] top-1.5 flex h-3 w-3 items-center justify-center rounded-full border bg-background",
        )}
      >
        <span className={cn("h-1.5 w-1.5 rounded-full", dotColor)} />
      </span>
      <div className="rounded-md border bg-muted/30 px-3 py-2">
        <div className="flex items-center justify-between gap-2 text-xs">
          <div className="flex items-center gap-1.5">
            {meta && <span>{meta.icon}</span>}
            <span className="font-medium">{meta?.label ?? run?.kind ?? "(run)"}</span>
            <span className="ml-1 rounded bg-background px-1.5 py-px text-[10px] font-mono text-muted-foreground">
              {change.change_kind}
            </span>
          </div>
          <span className="font-mono text-[10px] text-muted-foreground">
            {new Date(change.created_at).toLocaleTimeString()}
          </span>
        </div>
        {change.reason && (
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
            {change.reason}
          </p>
        )}
        {interestingDiffs.length > 0 && (
          <ul className="mt-2 space-y-0.5 font-mono text-[11px]">
            {interestingDiffs.map(({ field, diff }) => (
              <li key={field} className="flex items-start gap-1.5">
                <span className="text-muted-foreground min-w-[100px]">
                  {field}:
                </span>
                <span>
                  <FormatValue value={diff.from} muted />
                  <span className="mx-1 text-muted-foreground">→</span>
                  <FormatValue value={diff.to} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  )
}

function FormatValue({
  value,
  muted = false,
}: {
  value: unknown
  muted?: boolean
}) {
  const cls = muted ? "text-muted-foreground/70" : "text-foreground"
  if (value === null || value === undefined) {
    return <span className={cn(cls, "italic")}>∅</span>
  }
  if (typeof value === "number") {
    return <span className={cls}>{Number.isInteger(value) ? value : value.toFixed(2)}</span>
  }
  if (typeof value === "boolean") {
    return <span className={cls}>{String(value)}</span>
  }
  if (typeof value === "string") {
    if (value.length > 60) {
      return (
        <span className={cls} title={value}>
          {value.slice(0, 60)}…
        </span>
      )
    }
    return <span className={cls}>{value || "∅"}</span>
  }
  if (Array.isArray(value)) {
    return <span className={cls}>[{value.length}]</span>
  }
  return <span className={cls}>{JSON.stringify(value).slice(0, 60)}</span>
}

const HIDDEN_FIELDS = new Set(["evidence_chunk_ids"])

function filterInterestingDiffs(
  diffs: Record<string, FieldDiff>,
): { field: string; diff: FieldDiff }[] {
  const out: { field: string; diff: FieldDiff }[] = []
  // Render a deterministic order: scalars first, then arrays
  const priority = [
    "v_hat",
    "c_hat",
    "status",
    "challenger_verdict",
    "lens",
    "statement",
    "source_count",
    "dossier_grounded",
    "provenance_audited",
    "ahead_of_yc",
  ]
  const seen = new Set<string>()
  for (const f of priority) {
    if (HIDDEN_FIELDS.has(f)) continue
    if (diffs[f] !== undefined) {
      out.push({ field: f, diff: diffs[f] })
      seen.add(f)
    }
  }
  for (const [f, d] of Object.entries(diffs)) {
    if (HIDDEN_FIELDS.has(f) || seen.has(f)) continue
    out.push({ field: f, diff: d })
  }
  return out
}

function changeDotColor(kind: CandidateChangeRow["change_kind"]): string {
  switch (kind) {
    case "created":
      return "bg-emerald-400"
    case "reinforced":
    case "updated":
      return "bg-sky-400"
    case "killed":
    case "red_struck":
      return "bg-destructive"
    case "merged":
      return "bg-amber-400"
    case "restored":
      return "bg-violet-400"
    default:
      return "bg-muted-foreground"
  }
}

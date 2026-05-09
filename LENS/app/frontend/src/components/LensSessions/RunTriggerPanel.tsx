import { useState } from "react"
import { Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

import { RUN_KIND_META, type RunKind, type RunMode } from "./types"

interface RunTriggerPanelProps {
  onTrigger: (
    kind: RunKind,
    opts?: { mode?: RunMode; input?: Record<string, unknown> },
  ) => Promise<unknown> | void
  running: RunKind | null
  hasCandidates: boolean
  className?: string
}

const KIND_ORDER: RunKind[] = [
  "seed_ideas",
  "document_upload",
  "hn_search",
  "contradiction_lens",
]

export function RunTriggerPanel({
  onTrigger,
  running,
  hasCandidates,
  className,
}: RunTriggerPanelProps) {
  const [docLabel, setDocLabel] = useState("AI tooling brief.pdf")
  const [hnQuery, setHnQuery] = useState("AI tooling")
  const [seedCount, setSeedCount] = useState(10)
  const [modeForKind, setModeForKind] = useState<Record<RunKind, RunMode>>({
    seed_ideas: "scripted",
    document_upload: "scripted",
    hn_search: "scripted",
    contradiction_lens: "scripted",
    cross_domain_lens: "scripted",
  })

  const setMode = (kind: RunKind, mode: RunMode) =>
    setModeForKind((prev) => ({ ...prev, [kind]: mode }))

  const trigger = async (kind: RunKind) => {
    const mode = modeForKind[kind]
    const input: Record<string, unknown> = {}
    if (kind === "seed_ideas") input.count = seedCount
    if (kind === "document_upload") input.document_label = docLabel
    if (kind === "hn_search") input.query = hnQuery
    await onTrigger(kind, { mode, input })
  }

  return (
    <div
      className={cn(
        "rounded-xl border bg-card/60 p-4 shadow-sm space-y-3",
        className,
      )}
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">Trigger a run</h2>
        <span className="text-[11px] text-muted-foreground">
          each run records its per-candidate diff
        </span>
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {KIND_ORDER.map((kind) => {
          const meta = RUN_KIND_META[kind]
          const isRunning = running === kind
          const disabled = running !== null
          const realAvailable = kind === "contradiction_lens"
          const seedRequired = kind !== "seed_ideas" && !hasCandidates
          return (
            <div
              key={kind}
              className={cn(
                "rounded-lg border bg-muted/30 p-3 space-y-2 transition-colors",
                isRunning && "border-amber-400/60 bg-amber-400/5",
                seedRequired && "opacity-60",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <span className="text-base leading-none">{meta.icon}</span>
                  <span className="text-sm font-medium">{meta.label}</span>
                </div>
                <ModeToggle
                  mode={modeForKind[kind]}
                  onChange={(m) => setMode(kind, m)}
                  realAvailable={realAvailable}
                />
              </div>
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                {meta.description}
                {seedRequired && (
                  <span className="ml-1 text-amber-400">
                    (seed first to enable)
                  </span>
                )}
              </p>
              {kind === "seed_ideas" && (
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={seedCount}
                  onChange={(e) => setSeedCount(Number(e.target.value))}
                  className="w-full rounded border bg-background px-2 py-1 text-xs"
                  placeholder="how many candidates"
                />
              )}
              {kind === "document_upload" && (
                <input
                  type="text"
                  value={docLabel}
                  onChange={(e) => setDocLabel(e.target.value)}
                  className="w-full rounded border bg-background px-2 py-1 text-xs"
                  placeholder="document label"
                />
              )}
              {kind === "hn_search" && (
                <input
                  type="text"
                  value={hnQuery}
                  onChange={(e) => setHnQuery(e.target.value)}
                  className="w-full rounded border bg-background px-2 py-1 text-xs"
                  placeholder="search query"
                />
              )}
              <Button
                size="sm"
                className="w-full h-7 gap-1.5"
                disabled={disabled || seedRequired}
                onClick={() => void trigger(kind)}
              >
                {isRunning ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin" />
                    Running…
                  </>
                ) : (
                  <>Run {meta.label}</>
                )}
              </Button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ModeToggle({
  mode,
  onChange,
  realAvailable,
}: {
  mode: RunMode
  onChange: (m: RunMode) => void
  realAvailable: boolean
}) {
  return (
    <div className="flex items-center gap-1 rounded border bg-background p-0.5 text-[10px]">
      <button
        type="button"
        onClick={() => onChange("scripted")}
        className={cn(
          "rounded px-1.5 py-0.5 transition-colors",
          mode === "scripted"
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        scripted
      </button>
      <button
        type="button"
        onClick={() => realAvailable && onChange("real")}
        disabled={!realAvailable}
        className={cn(
          "rounded px-1.5 py-0.5 transition-colors",
          mode === "real"
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground",
          !realAvailable && "cursor-not-allowed opacity-40",
        )}
        title={
          realAvailable
            ? "Use the real LLM-backed runner"
            : "Real path not yet wired for this kind"
        }
      >
        real
      </button>
    </div>
  )
}

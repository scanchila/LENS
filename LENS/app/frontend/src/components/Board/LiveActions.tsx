import { Brain, ScanSearch, Sparkles, Zap } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface LiveActionsProps {
  onRunLens: (lens: string) => Promise<number>
  onAuditAll: () => Promise<number>
  loading: boolean
  className?: string
}

export function LiveActions({
  onRunLens,
  onAuditAll,
  loading,
  className,
}: LiveActionsProps) {
  const [last, setLast] = useState<string | null>(null)

  const fire = async (label: string, fn: () => Promise<number>) => {
    const n = await fn()
    setLast(`${label}: ${n}`)
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-xl border bg-amber-500/5 p-3",
        className,
      )}
    >
      <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">
        <Brain className="mr-1 inline size-3.5" />
        Live LLM
      </span>
      <Button
        size="sm"
        variant="outline"
        disabled={loading}
        onClick={() =>
          fire("cross-domain", () => onRunLens("cross_domain_transfer"))
        }
        className="h-7 gap-1 border-amber-500/40 text-amber-200 hover:bg-amber-500/10"
      >
        <Sparkles className="size-3.5" />
        Run cross-domain (Codex)
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={loading}
        onClick={() =>
          fire("contradiction", () => onRunLens("contradiction_surfacing"))
        }
        className="h-7 gap-1 border-violet-500/40 text-violet-200 hover:bg-violet-500/10"
      >
        <Zap className="size-3.5" />
        Run contradiction (Codex)
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={loading}
        onClick={() => fire("audit", onAuditAll)}
        className="h-7 gap-1 border-emerald-500/40 text-emerald-200 hover:bg-emerald-500/10"
      >
        <ScanSearch className="size-3.5" />
        AGE provenance audit
      </Button>
      {loading && (
        <span className="ml-1 text-[11px] text-amber-200/80">
          working… (LLM calls take 10–30s)
        </span>
      )}
      {last && !loading && (
        <span className="ml-auto text-[11px] text-muted-foreground">{last}</span>
      )}
    </div>
  )
}

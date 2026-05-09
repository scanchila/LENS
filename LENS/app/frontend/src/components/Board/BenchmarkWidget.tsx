import { Eye, EyeOff, Trophy } from "lucide-react"
import { cn } from "@/lib/utils"

import { Button } from "@/components/ui/button"
import { getYcRfsItems } from "./demoScript"
import { Sparkline } from "./Sparkline"
import type { Candidate, YcScore } from "./types"

interface BenchmarkWidgetProps {
  candidates: Candidate[]
  ycScore: YcScore
  revealed: boolean
  onReveal: () => void
  className?: string
}

export function BenchmarkWidget({
  candidates,
  ycScore,
  revealed,
  onReveal,
  className,
}: BenchmarkWidgetProps) {
  const precisionHistory = ycScore.history.map((h) => h.precision)
  const recallHistory = ycScore.history.map((h) => h.recall)
  const live = candidates.filter(
    (c) => c.status !== "killed" && c.status !== "merged_into",
  )
  const top10 = [...live]
    .sort((a, b) => b.v_hat * b.c_hat - a.v_hat * a.c_hat)
    .slice(0, 10)

  return (
    <div
      className={cn(
        "rounded-xl border bg-card/60 p-4 shadow-sm",
        className,
      )}
    >
      <div className="mb-3 flex items-center gap-2">
        <Trophy className="size-4 text-rose-300" />
        <h3 className="text-sm font-semibold">YC Summer 2026 benchmark</h3>
        <span className="ml-auto text-[10px] text-muted-foreground">
          held out · published 2026-05-04
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Metric
          label="Precision @10"
          value={
            ycScore.revealed
              ? `${(ycScore.precision * 100).toFixed(0)}%`
              : "–"
          }
          history={precisionHistory}
          stroke="oklch(0.7 0.18 16)"
        />
        <Metric
          label="Recall @10"
          value={
            ycScore.revealed
              ? `${(ycScore.recall * 100).toFixed(0)}%`
              : "–"
          }
          history={recallHistory}
          stroke="oklch(0.65 0.16 165)"
        />
      </div>

      <div className="mt-3 flex items-center justify-between gap-2">
        <div className="text-[11px] text-muted-foreground">
          {ycScore.revealed
            ? `${ycScore.direct_matches} direct · ${ycScore.adjacent} adjacent · ${ycScore.excess} excess`
            : "Reveal to score against the held-out RFS list"}
        </div>
        <Button
          size="sm"
          variant={revealed ? "outline" : "default"}
          onClick={onReveal}
          className={cn(
            "h-7 gap-1.5",
            revealed
              ? ""
              : "bg-rose-500/90 text-white hover:bg-rose-500",
          )}
        >
          {revealed ? (
            <>
              <EyeOff className="size-3.5" />
              Hide reveal
            </>
          ) : (
            <>
              <Eye className="size-3.5" />
              Reveal RFS
            </>
          )}
        </Button>
      </div>

      {revealed && (
        <div className="mt-4 space-y-3 border-t pt-3">
          <div className="grid grid-cols-2 gap-2">
            <ColumnHeader>Top-10 predictions</ColumnHeader>
            <ColumnHeader>YC RFS Summer 2026</ColumnHeader>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              {top10.map((c, i) => {
                const m = ycScore.matches.find((x) => x.prediction_id === c.id)
                return (
                  <div
                    key={c.id}
                    className={cn(
                      "rounded-md border bg-card/60 px-2 py-1 text-[11px] leading-tight",
                      m?.match_kind === "direct" &&
                        "border-emerald-500/40 bg-emerald-500/5",
                      m?.match_kind === "adjacent" &&
                        "border-sky-500/40 bg-sky-500/5",
                      !m && c.ahead_of_yc && "border-rose-500/40 bg-rose-500/5",
                    )}
                  >
                    <span className="mr-1 font-mono text-muted-foreground">
                      #{i + 1}
                    </span>
                    {c.statement.slice(0, 88)}
                    {c.statement.length > 88 ? "…" : ""}
                  </div>
                )
              })}
            </div>
            <div className="space-y-1.5">
              {getYcRfsItems().map((item) => {
                const matched = ycScore.matches.some(
                  (m) =>
                    m.rfs_item_id === item.id && m.match_kind === "direct",
                )
                return (
                  <div
                    key={item.id}
                    className={cn(
                      "rounded-md border bg-card/60 px-2 py-1 text-[11px] leading-tight",
                      matched
                        ? "border-emerald-500/40 bg-emerald-500/5"
                        : "border-border/60 text-muted-foreground",
                    )}
                  >
                    <span className="mr-1 font-mono">{item.id.replace("rfs-", "")}</span>
                    {item.title}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Metric({
  label,
  value,
  history,
  stroke,
}: {
  label: string
  value: string
  history: number[]
  stroke: string
}) {
  return (
    <div className="rounded-lg border bg-muted/30 p-2">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] text-muted-foreground">{label}</span>
        <span className="font-mono text-base font-semibold tabular-nums">
          {value}
        </span>
      </div>
      <Sparkline
        values={history}
        width={120}
        height={20}
        stroke={stroke}
        className="mt-1"
      />
    </div>
  )
}

function ColumnHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
      {children}
    </div>
  )
}

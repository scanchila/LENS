import { ChevronLeft, ChevronRight, RotateCcw } from "lucide-react"
import { cn } from "@/lib/utils"

import { Button } from "@/components/ui/button"
import type { DemoStage } from "./demoScript"

interface DemoControllerProps {
  stages: DemoStage[]
  stageIndex: number
  currentStage: DemoStage | null
  onNext: () => void
  onPrev: () => void
  onReset: () => void
  onJumpTo: (index: number) => void
  className?: string
}

export function DemoController({
  stages,
  stageIndex,
  currentStage,
  onNext,
  onPrev,
  onReset,
  onJumpTo,
  className,
}: DemoControllerProps) {
  const total = stages.length
  const next = stageIndex < total ? stages[stageIndex] : null

  return (
    <div
      className={cn(
        "rounded-xl border bg-card/60 p-3 shadow-sm",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] text-muted-foreground">
          stage {stageIndex} / {total}
        </span>
        <span className="ml-1 truncate text-sm font-medium">
          {next ? next.label : currentStage ? "Demo complete" : "Ready"}
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <Button
            size="sm"
            variant="outline"
            onClick={onPrev}
            disabled={stageIndex === 0}
            className="h-7 gap-1"
          >
            <ChevronLeft className="size-3.5" />
            Prev
          </Button>
          <Button
            size="sm"
            onClick={onNext}
            disabled={stageIndex >= total}
            className="h-7 gap-1"
          >
            Next
            <ChevronRight className="size-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onReset}
            className="h-7 gap-1"
            title="Reset to cold start"
          >
            <RotateCcw className="size-3.5" />
            Reset
          </Button>
        </div>
      </div>

      {currentStage && (
        <p className="mt-2 text-[11px] text-muted-foreground">
          <span className="text-foreground">{currentStage.label.split(" ")[0]}</span>{" "}
          — {currentStage.narration}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-1">
        {stages.map((s, i) => {
          const done = i < stageIndex
          const active = i === stageIndex
          return (
            <button
              key={s.key}
              type="button"
              onClick={() => onJumpTo(i)}
              title={s.label}
              className={cn(
                "h-1.5 flex-1 min-w-[12px] rounded-full transition-colors",
                done && "bg-primary",
                active && "bg-amber-400",
                !done && !active && "bg-muted hover:bg-muted-foreground/40",
              )}
            />
          )
        })}
      </div>
    </div>
  )
}

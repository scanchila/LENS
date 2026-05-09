import { cn } from "@/lib/utils"

interface ConfidenceBarProps {
  label: string
  value: number
  tone?: "primary" | "warm"
  className?: string
}

export function ConfidenceBar({
  label,
  value,
  tone = "primary",
  className,
}: ConfidenceBarProps) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div className={cn("flex items-center gap-2 text-xs", className)}>
      <span className="w-6 font-mono text-muted-foreground">{label}</span>
      <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "absolute inset-y-0 left-0 rounded-full transition-[width] duration-500 ease-out",
            tone === "primary"
              ? "bg-gradient-to-r from-primary/70 to-primary"
              : "bg-gradient-to-r from-amber-500/70 to-amber-400",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-9 text-right font-mono tabular-nums text-muted-foreground">
        {value.toFixed(2)}
      </span>
    </div>
  )
}

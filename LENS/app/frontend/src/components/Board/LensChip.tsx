import { cn } from "@/lib/utils"
import { lensMeta } from "./lensMeta"
import type { LensName } from "./types"

interface LensChipProps {
  lens: LensName
  pulse?: boolean
  className?: string
}

export function LensChip({ lens, pulse = false, className }: LensChipProps) {
  const meta = lensMeta(lens)
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
        meta.chipClass,
        pulse && meta.pulseClass,
        className,
      )}
    >
      <span aria-hidden>{meta.icon}</span>
      <span>{meta.label}</span>
    </span>
  )
}

import type { LensName } from "./types"

export const LENS_META: Record<
  LensName,
  { icon: string; label: string; chipClass: string; pulseClass: string }
> = {
  cross_domain_transfer: {
    icon: "💡",
    label: "Cross-domain",
    chipClass:
      "bg-amber-500/15 text-amber-300 border-amber-500/40 ring-1 ring-amber-500/20",
    pulseClass: "animate-[lens-pulse_1.6s_ease-out]",
  },
  contradiction_surfacing: {
    icon: "⚡",
    label: "Contradiction",
    chipClass:
      "bg-violet-500/15 text-violet-300 border-violet-500/40 ring-1 ring-violet-500/20",
    pulseClass: "animate-[lens-pulse_1.6s_ease-out]",
  },
  distance_from_focus: {
    icon: "🧭",
    label: "Adjacent",
    chipClass:
      "bg-sky-500/15 text-sky-300 border-sky-500/40 ring-1 ring-sky-500/20",
    pulseClass: "animate-[lens-pulse_1.6s_ease-out]",
  },
}

export function lensMeta(lens: LensName) {
  return LENS_META[lens]
}

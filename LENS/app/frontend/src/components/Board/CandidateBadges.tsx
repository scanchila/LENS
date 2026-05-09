import { cn } from "@/lib/utils"
import type { Candidate } from "./types"

interface CandidateBadgesProps {
  candidate: Candidate
  className?: string
}

export function CandidateBadges({
  candidate,
  className,
}: CandidateBadgesProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {candidate.dossier_grounded && (
        <Badge tone="amber" title={`${candidate.source_count} sources in evidence dossier`}>
          📚 {candidate.source_count} sources
        </Badge>
      )}
      {candidate.challenger_verdict === "held" && (
        <Badge tone="emerald" title="Survived adversarial Challenger pass">
          ✓ challenged & held
        </Badge>
      )}
      {candidate.provenance_audited && (
        <Badge tone="sky" title="Every claim traces to a source via AGE">
          ✓ provenance audited
        </Badge>
      )}
      {candidate.reinforces && candidate.reinforces.length > 0 && (
        <Badge
          tone="violet"
          title={`Reinforced across lenses: ${candidate.reinforces.join(", ")}`}
        >
          🔁 reinforces ×{candidate.reinforces.length}
        </Badge>
      )}
      {candidate.merged_from && candidate.merged_from.length > 0 && (
        <Badge tone="sky" title="Merged from duplicate candidates by Synthesizer">
          ⤲ merged ×{candidate.merged_from.length}
        </Badge>
      )}
      {candidate.ahead_of_yc && (
        <Badge tone="rose" title="Defensible non-overlap with YC RFS — ahead of YC">
          🚀 ahead of YC
        </Badge>
      )}
      {candidate.challenger_verdict === "provenance_failed" && (
        <Badge tone="red" title="Challenger flagged unsourced claim">
          ⚠ provenance failed
        </Badge>
      )}
    </div>
  )
}

interface BadgeProps {
  tone: "amber" | "emerald" | "sky" | "violet" | "rose" | "red"
  title?: string
  children: React.ReactNode
}

function Badge({ tone, title, children }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-medium",
        toneClass(tone),
      )}
    >
      {children}
    </span>
  )
}

function toneClass(tone: BadgeProps["tone"]) {
  switch (tone) {
    case "amber":
      return "border-amber-500/40 bg-amber-500/10 text-amber-300"
    case "emerald":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
    case "sky":
      return "border-sky-500/40 bg-sky-500/10 text-sky-300"
    case "violet":
      return "border-violet-500/40 bg-violet-500/10 text-violet-300"
    case "rose":
      return "border-rose-500/40 bg-rose-500/10 text-rose-300"
    case "red":
      return "border-red-500/50 bg-red-500/10 text-red-300"
  }
}

import { Check, FlaskConical, Pause, X } from "lucide-react"
import { cn } from "@/lib/utils"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { CandidateBadges } from "./CandidateBadges"
import { LensChip } from "./LensChip"
import type { Candidate } from "./types"

interface OpportunityBriefDialogProps {
  candidate: Candidate | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onVerdict?: (verdict: "accept" | "reject" | "park" | "request_dossier") => void
}

export function OpportunityBriefDialog({
  candidate,
  open,
  onOpenChange,
  onVerdict,
}: OpportunityBriefDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl sm:max-w-2xl">
        {!candidate ? (
          <>
            <DialogHeader>
              <DialogTitle>No candidate selected</DialogTitle>
            </DialogHeader>
          </>
        ) : (
          <>
            <DialogHeader>
              <div className="flex items-center gap-2">
                <DialogTitle className="text-base">Opportunity brief</DialogTitle>
                <LensChip lens={candidate.lens} />
              </div>
              <DialogDescription>
                Evidence-backed hypothesis for partner review. Read the
                contradictions before the assumptions.
              </DialogDescription>
            </DialogHeader>

            <div className="max-h-[70vh] space-y-5 overflow-y-auto pr-2">
              <Section title="Problem">
                <p className="text-sm leading-relaxed">{candidate.statement}</p>
                <CandidateBadges candidate={candidate} className="mt-2" />
              </Section>

              {candidate.pain_owner && (
                <Section title="Who has the pain">
                  <p className="text-sm leading-relaxed">{candidate.pain_owner}</p>
                </Section>
              )}

              {candidate.evidence_sources && candidate.evidence_sources.length > 0 && (
                <Section title={`Evidence (${candidate.source_count} sources)`}>
                  <ul className="space-y-1.5">
                    {candidate.evidence_sources.map((s, i) => (
                      <li key={i} className="text-xs">
                        <span
                          className={cn(
                            "mr-2 inline-flex items-center rounded-md border px-1 py-0.5 text-[10px] uppercase tracking-wide",
                            kindClass(s.kind),
                          )}
                        >
                          {s.kind}
                        </span>
                        {s.url ? (
                          <a
                            href={s.url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-foreground hover:underline"
                          >
                            {s.title}
                          </a>
                        ) : (
                          <span className="text-foreground">{s.title}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              {candidate.contradictions && candidate.contradictions.length > 0 && (
                <Section title="Contradictions / risks" tone="warn">
                  <ul className="list-disc space-y-1 pl-4 text-sm">
                    {candidate.contradictions.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {candidate.why_now && (
                <Section title="Why now">
                  <p className="text-sm leading-relaxed">{candidate.why_now}</p>
                </Section>
              )}

              {candidate.open_assumptions && candidate.open_assumptions.length > 0 && (
                <Section title="Open assumptions">
                  <ul className="list-disc space-y-1 pl-4 text-sm">
                    {candidate.open_assumptions.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {candidate.validation_path && candidate.validation_path.length > 0 && (
                <Section title="Recommended validation path" tone="positive">
                  <ol className="list-decimal space-y-1 pl-4 text-sm">
                    {candidate.validation_path.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ol>
                </Section>
              )}
            </div>

            <DialogFooter className="border-t pt-3">
              <span className="mr-auto text-[11px] text-muted-foreground">
                Human verdict
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onVerdict?.("park")}
                className="gap-1.5"
              >
                <Pause className="size-3.5" />
                Park
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onVerdict?.("request_dossier")}
                className="gap-1.5"
              >
                <FlaskConical className="size-3.5" />
                Request dossier
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onVerdict?.("reject")}
                className="gap-1.5 text-destructive hover:text-destructive"
              >
                <X className="size-3.5" />
                Reject
              </Button>
              <Button
                size="sm"
                onClick={() => onVerdict?.("accept")}
                className="gap-1.5 bg-emerald-500 text-white hover:bg-emerald-500/90"
              >
                <Check className="size-3.5" />
                Accept
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

interface SectionProps {
  title: string
  tone?: "warn" | "positive"
  children: React.ReactNode
}

function Section({ title, tone, children }: SectionProps) {
  return (
    <div>
      <h4
        className={cn(
          "mb-1.5 text-[11px] font-semibold uppercase tracking-wider",
          tone === "warn" && "text-amber-300",
          tone === "positive" && "text-emerald-300",
          !tone && "text-muted-foreground",
        )}
      >
        {title}
      </h4>
      {children}
    </div>
  )
}

function kindClass(kind: "web" | "paper" | "forum" | "blog" | "doc") {
  switch (kind) {
    case "paper":
      return "border-violet-500/40 bg-violet-500/10 text-violet-300"
    case "blog":
      return "border-amber-500/40 bg-amber-500/10 text-amber-300"
    case "forum":
      return "border-sky-500/40 bg-sky-500/10 text-sky-300"
    case "doc":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
    default:
      return "border-border bg-muted/40 text-muted-foreground"
  }
}

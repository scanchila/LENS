import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRight, Eye, FlaskConical, Skull, Sparkles } from "lucide-react"

import { Button } from "@/components/ui/button"
import useAuth from "@/hooks/useAuth"

const DEMO_SESSION_ID = "00000000-0000-4000-8000-000000000001"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: "LENS · Dashboard",
      },
    ],
  }),
})

function Dashboard() {
  const { user: currentUser } = useAuth()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Hi, {currentUser?.full_name || currentUser?.email}
        </h1>
        <p className="text-muted-foreground">
          LENS turns messy public and private signals into evidence-backed
          opportunity briefs, then challenges them.
        </p>
      </div>

      <div className="rounded-xl border bg-card/60 p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <h2 className="text-lg font-semibold">Watch it get smarter</h2>
            <p className="text-sm text-muted-foreground max-w-2xl">
              The demo arc is staged: cold start, drop corpora, queue evidence
              dossiers, run adversarial review, reveal the YC benchmark, and
              open the opportunity brief. Press <span className="font-mono">Next</span>{" "}
              to advance one stage at a time.
            </p>
          </div>
          <Button asChild>
            <Link to="/board/$sessionId" params={{ sessionId: DEMO_SESSION_ID }} className="gap-1.5">
              Open prediction board
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        </div>

        <div className="mt-6 grid gap-3 md:grid-cols-4">
          <Tile
            icon={<Sparkles className="size-4 text-primary" />}
            title="Cross-domain candidates"
            body="Structurally analogous problems imported from the CS/AI catalog."
          />
          <Tile
            icon={<FlaskConical className="size-4 text-amber-300" />}
            title="Evidence dossiers"
            body="High-V̂ candidates trigger CAR + Hermes deep research."
          />
          <Tile
            icon={<Skull className="size-4 text-destructive" />}
            title="Adversarial review"
            body="Challenger kills weak claims; provenance audit catches unsourced reasoning."
          />
          <Tile
            icon={<Eye className="size-4 text-rose-300" />}
            title="YC benchmark"
            body="Held-out RFS Summer 2026 reveal with precision/recall."
          />
        </div>
      </div>
    </div>
  )
}

function Tile({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode
  title: string
  body: string
}) {
  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <div className="mb-1 flex items-center gap-1.5 text-sm font-medium">
        {icon}
        {title}
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">{body}</p>
    </div>
  )
}
